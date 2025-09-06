import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler
from utils.api import call_danmaku_api
from utils.permission import check_user_permission
from utils.url_parser import determine_input_type

# 初始化日志
logger = logging.getLogger(__name__)
# 对话状态（仅保留搜索相关）
SEARCH_MEDIA = 0
SEARCH_RESULTS = 1  # 搜索结果展示状态，等待用户点击按钮
EPISODES_PER_PAGE = 10  # 每页显示分集数量
INPUT_EPISODE_RANGE = 2  # 集数输入对话状态
CALLBACK_DATA_MAX_LEN = 60

# import_auto 对话状态
IMPORT_AUTO_KEYWORD_INPUT = 2  # 关键词输入状态
IMPORT_AUTO_ID_INPUT = 3  # ID输入状态
IMPORT_AUTO_SEASON_INPUT = 4  # 季度输入状态
IMPORT_AUTO_EPISODE_INPUT = 5  # 分集输入状态
IMPORT_AUTO_METHOD_SELECTION = 6  # 导入方式选择状态 


@check_user_permission
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """搜索媒体：支持直接带关键词或后续输入"""
    # 1. 直接带参数（如：/search 海贼王）
    if context.args:
        keyword = " ".join(context.args)
        return await process_search_media(update, keyword, context)

    # 2. 无参数：引导用户输入关键词
    await update.message.reply_text("请输入要搜索的媒体关键词（如：海贼王、进击的巨人）：")
    return SEARCH_MEDIA


async def search_media_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收用户输入的搜索关键词"""
    keyword = update.message.text.strip()
    if not keyword:
        await update.message.reply_text("❌ 关键词不能为空，请重新输入：")
        return SEARCH_MEDIA

    return await process_search_media(update, keyword, context)


async def process_search_media(update: Update, keyword: str, context: ContextTypes.DEFAULT_TYPE):
    """处理搜索逻辑：生成带「导入按钮」的结果列表"""
    await update.message.reply_text(f"🔍 正在搜索关键词「{keyword}」...")
    
    # 1. 调用API搜索
    api_result = call_danmaku_api(
        method="GET",
        endpoint="/search",
        params={"keyword": keyword}
    )

    # 2. 处理API响应
    if not api_result["success"]:
        await update.message.reply_text(f"❌ 搜索失败：{api_result['error']}")
        return
    search_data = api_result["data"]
    search_id = search_data.get("searchId", "")
    items = search_data.get("results", [])
    
    if not search_id:
        await update.message.reply_text("❌ 搜索结果缺少searchId，无法后续导入")
        return
    if not items:
        await update.message.reply_text(f"❌ 未找到关键词「{keyword}」的媒体")
        return

    # 3. 保存searchId到上下文（供后续导入使用）
    context.user_data["search_id"] = search_id
    await update.message.reply_text(f"✅ 找到 {len(items)} 个结果，点击「导入」按钮直接添加：")
    
    # 4. 生成带「导入按钮」的结果消息
    for idx, item in enumerate(items, 1):
        result_text = f"""
【{idx}/{len(items)}】{item.get('title', '未知名称')}
• 类型：{item.get('type', '未知类型')} | 来源：{item.get('provider', '未知来源')}
• 年份：{item.get('year', '未知年份')} | 季度：{item.get('season', '未知季度')}
• 总集数：{item.get('episodeCount', '0')}集
        """.strip()
        
        # 构造回调数据（含result_index，0开始）
        callback_data_import = json.dumps({
            "action": "import_media",
            "result_index": idx - 1
        }, ensure_ascii=False)

        callback_data_episode = json.dumps({
            "action": "get_media_episode",
            "data_id": str(idx - 1)  # 使用data_id统一参数名
        }, ensure_ascii=False)
        
        # 生成内联键盘
        keyboard = [
            [InlineKeyboardButton(
                text="🔗 立即导入",
                callback_data=callback_data_import
            ),
            InlineKeyboardButton(
                text="🔗 分集导入",
                callback_data=callback_data_episode
            )]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 发送单条结果+按钮
        await update.message.reply_text(
            text=result_text,
            reply_markup=reply_markup,
            parse_mode=None  # 避免特殊符号解析错误
        )
    
    # 返回搜索结果状态，保持对话继续
    return SEARCH_RESULTS


@check_user_permission
async def import_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """自动导入命令：支持直接带参数或显示选择界面"""
    # 检查是否有参数
    if context.args:
        # 有参数：直接处理输入
        input_text = " ".join(context.args)
        return await process_auto_input(update, context, input_text)
    
    # 无参数：显示searchType选择界面
    keyboard = [
        [InlineKeyboardButton("🔍 关键词搜索", callback_data=json.dumps({"action": "import_auto_search_type", "type": "keyword"}, ensure_ascii=False))],
        [InlineKeyboardButton("🎬 TMDB ID", callback_data=json.dumps({"action": "import_auto_search_type", "type": "tmdb"}, ensure_ascii=False))],
        [InlineKeyboardButton("📺 TVDB ID", callback_data=json.dumps({"action": "import_auto_search_type", "type": "tvdb"}, ensure_ascii=False))],
        [InlineKeyboardButton("🎭 豆瓣 ID", callback_data=json.dumps({"action": "import_auto_search_type", "type": "douban"}, ensure_ascii=False))],
        [InlineKeyboardButton("🌟 IMDB ID", callback_data=json.dumps({"action": "import_auto_search_type", "type": "imdb"}, ensure_ascii=False))],
        [InlineKeyboardButton("🎯 Bangumi ID", callback_data=json.dumps({"action": "import_auto_search_type", "type": "bangumi"}, ensure_ascii=False))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🚀 **自动导入媒体**\n\n请选择搜索类型：\n\n💡 **提示**：你也可以直接使用 `/auto 关键词` 或 `/auto TMDB链接` 进行快速导入",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    # 返回状态1，等待搜索类型选择
    return 1


async def process_auto_input(update: Update, context: ContextTypes.DEFAULT_TYPE, input_text: str):
    """处理自动输入的文字或链接"""
    # 判断输入类型
    input_info = determine_input_type(input_text)
    
    if input_info["type"] == "tmdb_url":
        # TMDB URL：直接解析并导入
        media_type = input_info["media_type"]
        tmdb_id = input_info["tmdb_id"]
        
        await update.message.reply_text(f"🎬 检测到 TMDB {'电视剧' if media_type == 'tv_series' else '电影'}\n\n正在导入...")
        
        if media_type == "movie":
            # 电影：直接导入
            import_params = {
                "searchType": "tmdb",
                "searchTerm": tmdb_id,
                "mediaType": media_type,
                "importMethod": "auto"
            }
            await call_import_auto_api(update, context, import_params)
            return ConversationHandler.END
        else:
            # 电视剧：显示导入方式选择
            context.user_data["import_auto_search_type"] = "tmdb"
            context.user_data["import_auto_id"] = tmdb_id
            context.user_data["import_auto_media_type"] = media_type
            
            await show_import_options(update, context, {
                "searchType": "tmdb",
                "searchTerm": tmdb_id,
                "mediaType": media_type
            })
            return IMPORT_AUTO_METHOD_SELECTION
    
    elif input_info["type"] == "tt_id":
        # tt 开头的 ID：使用 IMDB 搜索
        tt_id = input_info["value"]
        
        await update.message.reply_text(f"🌟 检测到 IMDB ID: {tt_id}\n\n请选择媒体类型：")
        
        # 显示媒体类型选择
        context.user_data["import_auto_search_type"] = "imdb"
        context.user_data["import_auto_id"] = tt_id
        
        keyboard = [
            [InlineKeyboardButton("📺 电视剧", callback_data=json.dumps({"action": "import_auto_media_type", "type": "tv_series"}, ensure_ascii=False))],
            [InlineKeyboardButton("🎬 电影", callback_data=json.dumps({"action": "import_auto_media_type", "type": "movie"}, ensure_ascii=False))]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "请选择媒体类型：",
            reply_markup=reply_markup
        )
        return 2  # 等待媒体类型选择
    
    else:
        # 关键词搜索：默认为电视剧
        keyword = input_info["value"]
        
        await update.message.reply_text(f"🔍 关键词搜索: {keyword}\n\n请选择媒体类型：")
        
        # 显示媒体类型选择
        context.user_data["import_auto_search_type"] = "keyword"
        context.user_data["import_auto_keyword"] = keyword
        
        keyboard = [
            [InlineKeyboardButton("📺 电视剧", callback_data=json.dumps({"action": "import_auto_media_type", "type": "tv_series"}, ensure_ascii=False))],
            [InlineKeyboardButton("🎬 电影", callback_data=json.dumps({"action": "import_auto_media_type", "type": "movie"}, ensure_ascii=False))]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "请选择媒体类型：",
            reply_markup=reply_markup
        )
        return 2  # 等待媒体类型选择


async def import_auto_keyword_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收用户输入的关键词"""
    keyword = update.message.text.strip()
    if not keyword:
        await update.message.reply_text("❌ 关键词不能为空，请重新输入：")
        return IMPORT_AUTO_KEYWORD_INPUT
    
    # 保存关键词和媒体类型到上下文
    context.user_data["import_auto_keyword"] = keyword
    media_type = context.user_data.get("import_auto_media_type", "tv")
    
    # 根据媒体类型决定流程
    if media_type == "movie":
        # 电影类型：直接导入
        await update.message.reply_text("🎬 电影导入\n\n正在导入电影...")
        import_params = {
            "searchType": "keyword",
            "searchTerm": keyword,
            "mediaType": media_type,
            "importMethod": "auto"
        }
        await call_import_auto_api(update, context, import_params)
        return ConversationHandler.END
    else:
        # 电视剧类型：显示导入方式选择
        await show_import_options(update, context, {
            "searchType": "keyword",
            "searchTerm": keyword,
            "mediaType": media_type
        })
        return IMPORT_AUTO_METHOD_SELECTION


async def import_auto_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收用户输入的平台ID"""
    platform_id = update.message.text.strip()
    if not platform_id:
        await update.message.reply_text("❌ ID不能为空，请重新输入：")
        return IMPORT_AUTO_ID_INPUT
    
    # 保存ID和搜索类型到上下文
    context.user_data["import_auto_id"] = platform_id
    search_type = context.user_data.get("import_auto_search_type", "tmdb")
    media_type = context.user_data.get("import_auto_media_type", "tv_series")
    
    # 根据媒体类型决定流程
    if media_type == "movie":
        # 电影类型：直接导入
        await update.message.reply_text("🎬 电影导入\n\n正在导入电影...")
        import_params = {
            "searchType": search_type,
            "searchTerm": platform_id,
            "mediaType": media_type,
            "importMethod": "auto"
        }
        await call_import_auto_api(update, context, import_params)
        return ConversationHandler.END
    else:
        # 电视剧类型：显示导入方式选择
        await show_import_options(update, context, {
            "searchType": search_type,
            "searchTerm": platform_id,
            "mediaType": media_type
        })
        return IMPORT_AUTO_METHOD_SELECTION


async def import_auto_season_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收用户输入的季度"""
    try:
        season = int(update.message.text.strip())
        if season < 0:
            raise ValueError("季度不能为负数")
    except ValueError:
        await update.message.reply_text("❌ 请输入有效的季度数字（如：1, 2, 3...）：")
        return IMPORT_AUTO_SEASON_INPUT
    
    # 保存季度到上下文
    context.user_data["import_auto_season"] = season
    
    # 检查是否为分集导入模式
    episode_mode = context.user_data.get("import_auto_episode_mode")
    
    if episode_mode:
        # 分集导入模式：继续输入集数
        await update.message.reply_text(f"✅ 已选择第 {season} 季\n\n请输入要导入的集数（如：1, 2, 3...）：")
        return IMPORT_AUTO_EPISODE_INPUT
    else:
        # 分季导入模式：直接调用API
        import_params = context.user_data.get("import_auto_params", {})
        import_params["season"] = season
        import_params["importMethod"] = "season"  # 添加导入方式标识
        
        await call_import_auto_api_with_continue(update, context, import_params)
        # 不结束对话，等待用户选择继续导入或完成
        return IMPORT_AUTO_SEASON_INPUT


async def import_auto_episode_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收用户输入的集数"""
    try:
        episode = int(update.message.text.strip())
        if episode < 1:
            raise ValueError("集数必须大于0")
    except ValueError:
        await update.message.reply_text("❌ 请输入有效的集数数字（如：1, 2, 3...）：")
        return IMPORT_AUTO_EPISODE_INPUT
    
    # 保存集数到上下文
    context.user_data["import_auto_episode"] = episode
    
    # 调用导入API
    import_params = context.user_data.get("import_auto_params", {})
    season = context.user_data.get("import_auto_season")
    import_params["season"] = season
    import_params["episode"] = episode
    import_params["importMethod"] = "episode"  # 添加导入方式标识
    
    await call_import_auto_api_with_continue(update, context, import_params)
    # 不结束对话，等待用户选择继续导入或完成
    return IMPORT_AUTO_EPISODE_INPUT


async def show_import_options(update: Update, context: ContextTypes.DEFAULT_TYPE, params: dict):
    """显示导入方式选择界面"""
    # 保存参数到上下文
    context.user_data["import_auto_params"] = params
    
    # 构建导入方式选择按钮
    keyboard = [
        [InlineKeyboardButton("🚀 自动导入", callback_data=json.dumps({"action": "import_auto_method", "method": "auto"}, ensure_ascii=False))],
        [InlineKeyboardButton("📺 分季导入", callback_data=json.dumps({"action": "import_auto_method", "method": "season"}, ensure_ascii=False))],
        [InlineKeyboardButton("🎬 分集导入", callback_data=json.dumps({"action": "import_auto_method", "method": "episode"}, ensure_ascii=False))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # 判断是消息还是回调查询
    if update.callback_query:
        # 回调查询：发送新消息
        await update.callback_query.message.reply_text(
            "请选择导入方式：",
            reply_markup=reply_markup
        )
    else:
        # 普通消息：直接回复
        await update.message.reply_text(
            "请选择导入方式：",
            reply_markup=reply_markup
        )


async def call_import_auto_api(update: Update, context: ContextTypes.DEFAULT_TYPE, params: dict):
    """调用/import/auto API"""
    # 判断是消息还是回调查询
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        send_message = lambda text: context.bot.send_message(chat_id=chat_id, text=text)
        send_message_with_markup = lambda text, markup: context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    else:
        send_message = update.message.reply_text
        send_message_with_markup = lambda text, markup: update.message.reply_text(text, reply_markup=markup)
    
    await send_message("🔄 正在导入媒体...")
    
    # 调用API
    api_result = call_danmaku_api(
        method="POST",
        endpoint="/import/auto",
        params=params
    )
    
    # 处理API响应
    if api_result["success"]:
        success_message = f"✅ 导入成功！\n\n{api_result.get('message', '媒体已成功导入到库中')}"
        
        # 根据导入方式提供继续导入的按钮
        import_method = params.get("importMethod")
        if import_method in ["season", "episode"]:
            keyboard = []
            
            if import_method == "season":
                # 分季导入：提供导入其他季度的选项
                keyboard.append([
                    InlineKeyboardButton(
                        "📺 导入其他季度",
                        callback_data=json.dumps({
                            "action": "continue_season_import"
                        }, ensure_ascii=False)
                    )
                ])
            elif import_method == "episode":
                # 分集导入：提供导入同季其他集数或其他季度的选项
                keyboard.extend([
                    [InlineKeyboardButton(
                        "🎬 导入同季其他集数",
                        callback_data=json.dumps({
                            "action": "continue_episode_import",
                            "same_season": True
                        }, ensure_ascii=False)
                    )],
                    [InlineKeyboardButton(
                        "📺 导入其他季度",
                        callback_data=json.dumps({
                            "action": "continue_episode_import",
                            "same_season": False
                        }, ensure_ascii=False)
                    )]
                ])
            
            # 添加结束按钮
            keyboard.append([
                InlineKeyboardButton(
                    "✅ 完成导入",
                    callback_data=json.dumps({
                        "action": "finish_import"
                    }, ensure_ascii=False)
                )
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_message_with_markup(success_message, reply_markup)
        else:
            # 自动导入：直接显示成功消息
            await send_message(success_message)
    else:
        await send_message(f"❌ 导入失败：{api_result['error']}")


async def call_import_auto_api_with_continue(update: Update, context: ContextTypes.DEFAULT_TYPE, params: dict):
    """调用/import/auto API（用于继续导入流程，不结束对话）"""
    send_message = update.message.reply_text
    send_message_with_markup = lambda text, markup: update.message.reply_text(text, reply_markup=markup)
    
    await send_message("🔄 正在导入媒体...")
    
    # 调用API
    api_result = call_danmaku_api(
        method="POST",
        endpoint="/import/auto",
        params=params
    )
    
    # 处理API响应
    if api_result["success"]:
        success_message = f"✅ 导入成功！\n\n{api_result.get('message', '媒体已成功导入到库中')}"
        
        # 根据导入方式提供继续导入的按钮
        import_method = params.get("importMethod")
        if import_method in ["season", "episode"]:
            keyboard = []
            
            if import_method == "season":
                # 分季导入：提供导入其他季度的选项
                keyboard.append([
                    InlineKeyboardButton(
                        "📺 导入其他季度",
                        callback_data=json.dumps({
                            "action": "continue_season_import"
                        }, ensure_ascii=False)
                    )
                ])
            elif import_method == "episode":
                # 分集导入：提供导入同季其他集数或其他季度的选项
                keyboard.extend([
                    [InlineKeyboardButton(
                        "🎬 导入同季其他集数",
                        callback_data=json.dumps({
                            "action": "continue_episode_import",
                            "same_season": True
                        }, ensure_ascii=False)
                    )],
                    [InlineKeyboardButton(
                        "📺 导入其他季度",
                        callback_data=json.dumps({
                            "action": "continue_episode_import",
                            "same_season": False
                        }, ensure_ascii=False)
                    )]
                ])
            
            # 添加结束按钮
            keyboard.append([
                InlineKeyboardButton(
                    "✅ 完成导入",
                    callback_data=json.dumps({
                        "action": "finish_import"
                    }, ensure_ascii=False)
                )
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_message_with_markup(success_message, reply_markup)
        else:
            # 自动导入：直接显示成功消息
            await send_message(success_message)
    else:
        await send_message(f"❌ 导入失败：{api_result['error']}")
    