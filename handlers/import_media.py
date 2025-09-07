import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler
from utils.api import call_danmaku_api
from utils.permission import check_user_permission
from utils.url_parser import determine_input_type
from utils.tmdb_api import get_media_type_suggestion, format_tmdb_results_info, format_tmdb_media_info, get_tmdb_tv_seasons, get_tmdb_media_details
from utils.tvdb_api import search_tvdb_by_slug, get_tvdb_tv_seasons
from utils.imdb_scraper import get_imdb_info
from utils.bgm_scraper import get_bgm_info

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
IMPORT_AUTO_SEASON_SELECTION = 4  # 季度选择状态
# IMPORT_AUTO_SEASON_INPUT = 4  # 季度输入状态（已移除）
# IMPORT_AUTO_EPISODE_INPUT = 5  # 分集输入状态（已移除）
# IMPORT_AUTO_METHOD_SELECTION = 6  # 导入方式选择状态（已移除） 


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
    
    # 4. 保存搜索结果到上下文
    context.user_data["search_results"] = items
    
    # 5. 直接显示分页结果（每页5条）
    from callback.import_media import show_paged_results
    await show_paged_results(update, context, items, page=0, per_page=5)
    
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
        "🤖 **自动导入功能**\n\n"
        "请选择搜索方式：\n\n"
        "• 🔍 **关键词搜索**：输入影视名称，TMDB智能识别类型和季度\n"
        "• 🆔 **平台ID**：直接使用各平台的ID或链接，支持季度选择\n\n"
        "💡 **快速导入**：直接使用 `/auto 关键词` 或 `/auto 平台链接`",
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
        # TMDB URL：分步骤处理
        media_type = input_info["media_type"]
        tmdb_id = input_info["tmdb_id"]
        
        # 域名验证
        from utils.url_parser import is_tmdb_url
        if not is_tmdb_url(input_text):
            await update.message.reply_text(
                "❌ **域名验证失败**\n\n"
                "请确保输入的是有效的TMDB链接：\n"
                "• https://www.themoviedb.org/movie/xxx\n"
                "• https://www.themoviedb.org/tv/xxx",
                parse_mode="Markdown"
            )
            return ConversationHandler.END


async def import_auto_season_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理季度选择"""
    query = update.callback_query
    logger.info(f"🎭 进入季度选择处理函数，回调数据: {query.data}")
    logger.info(f"🔍 用户数据上下文: {context.user_data}")
    
    try:
        await query.answer()
        logger.info(f"✅ 回调查询应答成功")
    except Exception as answer_error:
        logger.error(f"❌ 回调查询应答失败: {answer_error}")
    
    if query.data == "cancel":
        logger.info("❌ 用户取消导入操作")
        try:
            await query.edit_message_text("❌ 已取消导入操作")
            logger.info("✅ 取消消息发送成功")
        except Exception as cancel_error:
            logger.error(f"❌ 取消消息发送失败: {cancel_error}")
        return ConversationHandler.END
    
    if query.data.startswith("season_"):
        try:
            season_number = int(query.data.replace("season_", ""))
            logger.info(f"✅ 用户选择季度: {season_number}")
            context.user_data["selected_season"] = season_number
            
            try:
                await query.edit_message_text(
                    f"✅ **已选择第{season_number}季**\n\n"
                    f"🚀 开始导入选定季度的内容..."
                )
                logger.info(f"✅ 季度选择确认消息发送成功")
            except Exception as edit_error:
                logger.error(f"❌ 季度选择确认消息发送失败: {edit_error}")
            
            # 获取导入参数并添加季度信息
            import_params = context.user_data.get("import_auto_params", {})
            logger.info(f"📋 原始导入参数: {import_params}")
            import_params["season"] = season_number
            logger.info(f"📋 添加季度后的导入参数: {import_params}")
            
            # 调用导入API
            logger.info(f"🚀 准备调用导入API")
            await call_import_auto_api(update, context, import_params)
            logger.info(f"✅ 导入API调用完成")
            return ConversationHandler.END
            
        except ValueError as value_error:
            logger.error(f"❌ 季度数字解析失败: {value_error}")
            try:
                await query.edit_message_text("❌ 无效的季度选择")
            except Exception as error_msg_error:
                logger.error(f"❌ 错误消息发送失败: {error_msg_error}")
            return ConversationHandler.END
        except Exception as season_error:
            logger.error(f"❌ 季度选择处理异常: {season_error}")
            try:
                await query.edit_message_text(f"❌ 处理季度选择时出错: {str(season_error)}")
            except Exception as error_msg_error:
                logger.error(f"❌ 异常消息发送失败: {error_msg_error}")
            return ConversationHandler.END
    
    logger.warning(f"⚠️ 未识别的回调数据: {query.data}")
    try:
        await query.edit_message_text("❌ 无效的选择")
    except Exception as invalid_error:
        logger.error(f"❌ 无效选择消息发送失败: {invalid_error}")
    return ConversationHandler.END


async def call_import_auto_api_with_query(query, context: ContextTypes.DEFAULT_TYPE, import_params: dict):
    """使用callback query调用导入API"""
    logger.info(f"🔧 call_import_auto_api_with_query 开始执行，参数: {import_params}")
    
    try:
        # 构建API请求参数
        api_params = {
            "searchType": import_params.get("searchType", "tmdb"),
            "searchTerm": import_params.get("searchTerm", ""),
            "mediaType": import_params.get("mediaType", "tv_series"),
            "importMethod": import_params.get("importMethod", "auto")
        }
        
        # 如果有季度信息，添加到参数中
        if "season" in import_params:
            api_params["season"] = import_params["season"]
            logger.info(f"📺 添加季度参数: season={import_params['season']}")
        
        logger.info(f"🚀 开始调用导入API，完整参数: {api_params}")
        
        # 调用API
        response = call_danmaku_api(
            method="POST",
            endpoint="/import/auto",
            params=api_params
        )
        
        logger.info(f"📡 API响应: {response}")
        
        # 处理API响应
        if response and response.get("success"):
            message = f"✅ **导入成功!**\n\n{response.get('message', '导入完成')}"
            if "data" in response and response["data"]:
                data = response["data"]
                if "imported_count" in data:
                    message += f"\n📊 导入数量: {data['imported_count']}"
            logger.info(f"✅ 导入成功，消息: {message}")
        else:
            error_msg = response.get("message", "未知错误") if response else "API调用失败"
            message = f"❌ **导入失败**\n\n{error_msg}"
            logger.error(f"❌ 导入失败，错误: {error_msg}")
        
        # 发送结果消息
        try:
            await query.edit_message_text(message, parse_mode="Markdown")
            logger.info(f"📤 消息发送成功")
        except Exception as msg_error:
            logger.error(f"❌ 消息发送失败: {msg_error}")
            # 如果编辑消息失败，尝试发送新消息
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=message,
                    parse_mode="Markdown"
                )
                logger.info(f"📤 新消息发送成功")
            except Exception as new_msg_error:
                logger.error(f"❌ 新消息发送也失败: {new_msg_error}")
        
    except Exception as e:
        logger.error(f"❌ call_import_auto_api_with_query 执行异常: {e}")
        try:
            await query.edit_message_text(
                f"❌ **系统错误**\n\n{str(e)}",
                parse_mode="Markdown"
            )
        except Exception as error_msg_error:
            logger.error(f"❌ 错误消息发送失败: {error_msg_error}")
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"❌ **系统错误**\n\n{str(e)}",
                    parse_mode="Markdown"
                )
            except Exception as final_error:
                logger.error(f"❌ 最终错误消息发送失败: {final_error}")
    
    # 清理用户数据
    context.user_data.pop("import_auto_params", None)
    context.user_data.pop("selected_season", None)


async def process_auto_input(update: Update, context: ContextTypes.DEFAULT_TYPE, input_text: str):
    """处理自动导入输入"""
    # 验证域名
    input_info = determine_input_type(input_text)
    
    if input_info["type"] == "invalid_domain":
        await update.message.reply_text(
            "❌ **域名验证失败**\n\n"
            "请确保输入的链接来自支持的平台：\n"
            "• TMDB、TVDB、IMDB、豆瓣、BGM等",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    if input_info["type"] == "tmdb_url":
        # 处理TMDB链接
        tmdb_id = input_info["tmdb_id"]
        media_type = input_info["media_type"]
        
        # 第一步：立即显示检测结果
        type_icon = "📺" if media_type == 'tv_series' else "🎬"
        await update.message.reply_text(f"{type_icon} 检测到 TMDB {'电视剧' if media_type == 'tv_series' else '电影'}\n\n🆔 ID: {tmdb_id}")
        
        # 第二步：尝试获取并显示详细信息
        await update.message.reply_text("🔍 正在获取TMDB媒体信息...")
        
        try:
            detailed_info = format_tmdb_media_info(tmdb_id, media_type)
            await update.message.reply_text(detailed_info)
        except Exception as e:
            logger.warning(f"TMDB信息解析失败，直接使用ID导入: {e}")
            await update.message.reply_text(
                f"⚠️ **TMDB信息解析失败，将直接使用ID导入**\n\n"
                f"📋 TMDB ID: {tmdb_id}\n"
                f"🔄 跳过详细信息获取，直接进行导入..."
            )
        
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
            
            return await show_import_options(update, context, {
                "searchType": "tmdb",
                "searchTerm": tmdb_id,
                "mediaType": media_type
            })
    
    elif input_info["type"] == "tvdb_url":
        # TVDB URL：分步骤处理
        media_type = input_info["media_type"]
        slug = input_info["slug"]
        
        # 域名验证
        from utils.url_parser import is_tvdb_url
        if not is_tvdb_url(input_text):
            await update.message.reply_text(
                "❌ **域名验证失败**\n\n"
                "请确保输入的是有效的TVDB链接：\n"
                "• https://www.thetvdb.com/series/xxx\n"
                "• https://www.thetvdb.com/movies/xxx",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        # 第一步：立即显示检测结果
        type_icon = "📺" if media_type == 'tv_series' else "🎬"
        await update.message.reply_text(f"{type_icon} 检测到 TVDB {'电视剧' if media_type == 'tv_series' else '电影'}")
        
        # 第二步：显示正在查询的状态
        await update.message.reply_text("🔍 正在查询TVDB API获取数字ID...")
        
        # 通过API获取数字ID
        tvdb_result = await search_tvdb_by_slug(slug, media_type)
        
        # 如果指定类型查询失败，尝试查询另一种类型作为回退
        if not tvdb_result or "tvdb_id" not in tvdb_result:
            fallback_type = "tv_series" if media_type == "movie" else "movie"
            await update.message.reply_text(f"⚠️ 未找到对应的{'电影' if media_type == 'movie' else '电视剧'}，尝试查询{'电视剧' if fallback_type == 'tv_series' else '电影'}...")
            tvdb_result = await search_tvdb_by_slug(slug, fallback_type)
            if tvdb_result and "tvdb_id" in tvdb_result:
                media_type = fallback_type  # 更新为实际找到的类型
                await update.message.reply_text(f"✅ 找到了{'电视剧' if media_type == 'tv_series' else '电影'}版本，将使用此类型进行导入")
        
        if tvdb_result and "tvdb_id" in tvdb_result:
            # 提取数字ID部分（去掉series-前缀）
            raw_tvdb_id = tvdb_result["tvdb_id"]
            if raw_tvdb_id.startswith("series-"):
                tvdb_id = raw_tvdb_id.replace("series-", "")
            elif raw_tvdb_id.startswith("movie-"):
                tvdb_id = raw_tvdb_id.replace("movie-", "")
            else:
                tvdb_id = str(raw_tvdb_id)
            title = tvdb_result.get("name", "未知标题")
            
            type_icon = "📺" if media_type == 'tv_series' else "🎬"
            type_name = "电视剧" if media_type == 'tv_series' else "电影"
            
            # 根据媒体类型显示不同的提示信息
            if media_type == "movie":
                status_text = "🚀 开始自动导入..."
            else:
                status_text = "🔍 正在获取季度信息..."
            
            await update.message.reply_text(
                f"✅ **TVDB查询成功**\n\n"
                f"🎬 标题: {title}\n"
                f"🆔 ID: `{tvdb_id}`\n"
                f"{type_icon} 类型: {type_name}\n\n"
                f"{status_text}",
                parse_mode="Markdown"
            )
            
            # 根据媒体类型决定导入方式
            if media_type == "movie":
                # 电影类型：直接导入
                import_params = {
                    "searchType": "tvdb",
                    "searchTerm": tvdb_id,
                    "mediaType": media_type,
                    "importMethod": "auto"
                }
                await call_import_auto_api(update, context, import_params)
                return ConversationHandler.END
            else:
                # 电视剧类型：显示导入方式选择
                context.user_data["import_auto_search_type"] = "tvdb"
                context.user_data["import_auto_id"] = tvdb_id
                context.user_data["import_auto_media_type"] = media_type
                
                return await show_import_options(update, context, {
                    "searchType": "tvdb",
                    "searchTerm": tvdb_id,
                    "mediaType": media_type
                })
        else:
            await update.message.reply_text(f"❌ TVDB查询失败\n\n无法找到slug '{slug}' 对应的媒体信息，请检查链接是否正确。")
            return ConversationHandler.END
    
    elif input_info["type"] == "douban_url":
        # 豆瓣链接：分步骤处理
        douban_id = input_info["douban_id"]
        
        # 域名验证
        from utils.url_parser import is_douban_url
        if not is_douban_url(input_text):
            await update.message.reply_text(
                "❌ **域名验证失败**\n\n"
                "请确保输入的是有效的豆瓣链接：\n"
                "• https://movie.douban.com/subject/xxx/\n"
                "• https://m.douban.com/movie/subject/xxx/",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        # 第一步：立即显示检测结果
        await update.message.reply_text(f"🎭 检测到豆瓣链接\n\n🆔 ID: {douban_id}")
        
        # 第二步：显示正在获取信息的状态
        await update.message.reply_text("🔍 正在获取豆瓣媒体信息...")
        
        # 通过爬虫获取豆瓣媒体信息
        from utils.douban_scraper import get_douban_media_info
        
        try:
            douban_info = await get_douban_media_info(douban_id)
            
            if douban_info and douban_info.get('success'):
                media_title = douban_info.get('title', 'N/A')
                media_year = douban_info.get('year', 'N/A')
                genres = douban_info.get('genres', [])
                rating = douban_info.get('rating', 'N/A')
                
                # 使用豆瓣爬虫返回的媒体类型
                media_type = douban_info.get('media_type', 'movie')
                if media_type == 'tv_series':
                    type_name = '电视剧/动漫'
                else:
                    type_name = '电影'
                
                # 根据媒体类型显示对应图标
                if media_type == "movie":
                    type_icon = "🎬"
                    type_name = "电影"
                else:
                    type_icon = "📺"
                    type_name = "电视剧"
                
                await update.message.reply_text(
                    f"✅ **豆瓣信息获取成功**\n\n"
                    f"🎬 标题: {media_title}\n"
                    f"📅 年份: {media_year}\n"
                    f"{type_icon} 类型: {type_name}\n"
                    f"⭐ 评分: {rating}\n\n"
                    f"🚀 开始自动导入...",
                    parse_mode="Markdown"
                )
                
                # 根据媒体类型决定导入方式
                if media_type == "movie":
                    # 电影类型：直接导入
                    import_params = {
                        "searchType": "douban",
                        "searchTerm": douban_id,
                        "mediaType": media_type,
                        "importMethod": "auto"
                    }
                    await call_import_auto_api(update, context, import_params)
                    return ConversationHandler.END
                else:
                    # 电视剧类型：显示导入方式选择
                    context.user_data["import_auto_search_type"] = "douban"
                    context.user_data["import_auto_id"] = douban_id
                    context.user_data["import_auto_media_type"] = media_type
                    
                    return await show_import_options(update, context, {
                        "searchType": "douban",
                        "searchTerm": douban_id,
                        "mediaType": media_type
                    })
            else:
                # 豆瓣信息获取失败，跳过解析步骤，直接使用ID导入
                error_msg = douban_info.get('error', '未知错误') if douban_info else '网络请求失败'
                logger.warning(f"豆瓣信息解析失败，直接使用ID导入: {error_msg}")
                
                await update.message.reply_text(
                    f"⚠️ **豆瓣信息解析失败，将直接使用ID导入**\n\n"
                    f"📋 豆瓣ID: `{douban_id}`\n"
                    f"📺 默认按电视剧类型导入\n\n"
                    f"🔄 跳过详细信息获取，直接进行导入...",
                    parse_mode="Markdown"
                )
                
                # 默认按电视剧类型导入
                import_params = {
                    "searchType": "douban",
                    "searchTerm": douban_id,
                    "mediaType": "tv",
                    "importMethod": "auto"
                }
                await call_import_auto_api(update, context, import_params)
                return ConversationHandler.END
                
        except Exception as e:
            logger.error(f"豆瓣爬虫异常: douban_id='{douban_id}', error={str(e)}")
            
            await update.message.reply_text(
                f"❌ **豆瓣信息获取异常**\n\n"
                f"处理豆瓣ID '{douban_id}' 时发生错误。\n\n"
                f"💡 **可能的原因:**\n"
                f"• 豆瓣网站访问限制\n"
                f"• 网络连接问题\n"
                f"• 页面结构变化\n\n"
                f"🔄 **建议:**\n"
                f"• 稍后重试\n"
                f"• 使用其他搜索方式",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
    
    elif input_info["type"] == "imdb_url":
        # IMDB链接：分步骤处理
        imdb_id = input_info["imdb_id"]
        media_type = input_info.get("media_type")  # 从URL ref参数获取的类型
        
        # 域名验证
        from utils.url_parser import is_imdb_url
        if not is_imdb_url(input_text):
            await update.message.reply_text(
                "❌ **域名验证失败**\n\n"
                "请确保输入的是有效的IMDB链接：\n"
                "• https://www.imdb.com/title/ttxxxxxxx/\n"
                "• https://m.imdb.com/title/ttxxxxxxx/",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        # 第一步：立即显示检测结果
        await update.message.reply_text(f"🌟 检测到IMDB链接\n\n🆔 ID: {imdb_id}")
        
        if media_type:
            # 从链接参数识别到类型，跳过爬虫直接导入
            type_name = '电视剧/动漫' if media_type == 'tv' else '电影'
            await update.message.reply_text(f"🎭 类型: {type_name}")
            
            # 转换媒体类型格式
            if media_type == 'tv':
                media_type = 'tv_series'
        else:
            # 无法从链接识别类型，使用爬虫获取信息
            await update.message.reply_text("🔍 正在获取IMDB媒体信息...")
            
            try:
                imdb_info = get_imdb_info(imdb_id)
                
                if imdb_info and imdb_info.get('success'):
                    media_title = imdb_info.get('title', 'N/A')
                    media_year = imdb_info.get('year', 'N/A')
                    genres = imdb_info.get('genres', [])
                    rating = imdb_info.get('rating', 'N/A')
                    
                    # 使用IMDB爬虫返回的媒体类型
                    media_type = imdb_info.get('media_type', 'movie')
                    if media_type == 'tv_series':
                        type_name = '电视剧/动漫'
                    else:
                        type_name = '电影'
                    
                    await update.message.reply_text(
                        f"✅ **IMDB信息获取成功**\n\n"
                        f"🎬 标题: {media_title}\n"
                        f"📅 年份: {media_year}\n"
                        f"🎭 类型: {type_name}\n"
                        f"⭐ 评分: {rating}\n\n"
                        "",
                        parse_mode="Markdown"
                    )
                else:
                    # IMDB信息获取失败
                    error_msg = imdb_info.get('error', '未知错误') if imdb_info else '网络请求失败'
                    
                    await update.message.reply_text(
                        f"❌ **IMDB信息获取失败**\n\n"
                        f"无法获取IMDB ID '{imdb_id}' 的媒体信息。\n\n"
                        f"💡 **错误信息:** {error_msg}\n\n"
                        f"🔄 **建议:**\n"
                        f"• 检查IMDB链接是否正确\n"
                        f"• 稍后重试\n"
                        f"• 使用其他搜索方式",
                        parse_mode="Markdown"
                    )
                    return ConversationHandler.END
                    
            except Exception as e:
                logger.error(f"IMDB爬虫异常: imdb_id='{imdb_id}', error={str(e)}")
                
                await update.message.reply_text(
                    f"❌ **IMDB信息获取异常**\n\n"
                    f"处理IMDB ID '{imdb_id}' 时发生错误。\n\n"
                    f"💡 **可能的原因:**\n"
                    f"• IMDB网站访问限制\n"
                    f"• 网络连接问题\n"
                    f"• 页面结构变化\n\n"
                    f"🔄 **建议:**\n"
                    f"• 稍后重试\n"
                    f"• 使用其他搜索方式",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END
        
        # 处理导入逻辑
        if media_type == "movie":
            # 电影：直接导入
            import_params = {
                "searchType": "imdb",
                "searchTerm": imdb_id,
                "mediaType": media_type,
                "importMethod": "auto"
            }
            await call_import_auto_api(update, context, import_params)
            return ConversationHandler.END
        else:
            # 电视剧：显示导入方式选择
            context.user_data["import_auto_search_type"] = "imdb"
            context.user_data["import_auto_id"] = imdb_id
            context.user_data["import_auto_media_type"] = media_type
            
            return await show_import_options(update, context, {
                "searchType": "imdb",
                "searchTerm": imdb_id,
                "mediaType": media_type
            })
    
    elif input_info["type"] == "bgm_url":
        # BGM链接：分步骤处理
        bgm_url = input_text  # 使用原始输入文本作为URL
        bgm_id = input_info["bgm_id"]
        
        # 验证域名
        from utils.url_parser import is_bgm_url
        if not is_bgm_url(bgm_url):
            await update.message.reply_text(
                "❌ **无效的BGM链接**\n\n"
                "请确保输入的是有效的BGM链接。",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
        # 第一步：立即显示检测结果
        await update.message.reply_text(f"🎯 检测到BGM链接\n\n📋 BGM ID: `{bgm_id}`", parse_mode="Markdown")
        
        # 第二步：显示正在获取信息的状态
        await update.message.reply_text("🔍 正在获取BGM媒体信息...")
        
        try:
            bgm_info = get_bgm_info(bgm_id)
            
            if bgm_info and bgm_info.get('success'):
                media_title = bgm_info.get('title', 'N/A')
                media_year = bgm_info.get('year', 'N/A')
                genres = bgm_info.get('genres', [])
                rating = bgm_info.get('rating', 'N/A')
                
                # 使用BGM爬虫返回的媒体类型
                media_type = bgm_info.get('media_type', 'tv_series')
                if media_type == 'tv_series':
                    type_name = '电视剧/动漫'
                else:
                    type_name = '电影'
                
                # 根据媒体类型显示对应图标
                if media_type == "movie":
                    type_icon = "🎬"
                    type_name = "电影"
                else:
                    type_icon = "📺"
                    type_name = "电视剧/动漫"
                
                await update.message.reply_text(
                    f"✅ **BGM信息获取成功**\n\n"
                    f"🎬 标题: {media_title}\n"
                    f"📅 年份: {media_year}\n"
                    f"{type_icon} 类型: {type_name}\n"
                    f"⭐ 评分: {rating}\n\n"
                    f"🚀 开始自动导入...",
                    parse_mode="Markdown"
                )
                
                # 根据媒体类型决定导入方式
                if media_type == "movie":
                    # 电影类型：直接导入
                    import_params = {
                        "searchType": "bangumi",
                        "searchTerm": bgm_id,
                        "mediaType": media_type,
                        "importMethod": "auto"
                    }
                    await call_import_auto_api(update, context, import_params)
                    return ConversationHandler.END
                else:
                    # 电视剧类型：显示导入方式选择
                    context.user_data["import_auto_search_type"] = "bangumi"
                    context.user_data["import_auto_id"] = bgm_id
                    context.user_data["import_auto_media_type"] = media_type
                    
                    return await show_import_options(update, context, {
                        "searchType": "bangumi",
                        "searchTerm": bgm_id,
                        "mediaType": media_type
                    })
            else:
                # BGM信息获取失败，跳过解析步骤，直接使用ID导入
                error_msg = bgm_info.get('error', '未知错误') if bgm_info else '网络请求失败'
                logger.warning(f"BGM信息解析失败，直接使用ID导入: {error_msg}")
                
                await update.message.reply_text(
                    f"⚠️ **BGM信息解析失败，将直接使用ID导入**\n\n"
                    f"📋 BGM ID: `{bgm_id}`\n"
                    f"🔄 跳过详细信息获取，直接进行导入...",
                    parse_mode="Markdown"
                )
                
                # 默认按电视剧类型导入（BGM主要是动漫）
                import_params = {
                    "searchType": "bangumi",
                    "searchTerm": bgm_id,
                    "mediaType": "tv_series",
                    "importMethod": "auto"
                }
                await call_import_auto_api(update, context, import_params)
                return ConversationHandler.END
                
        except Exception as e:
            logger.error(f"BGM爬虫异常: bgm_id='{bgm_id}', error={str(e)}")
            logger.warning(f"BGM信息解析异常，直接使用ID导入: {str(e)}")
            
            await update.message.reply_text(
                f"⚠️ **BGM信息解析异常，将直接使用ID导入**\n\n"
                f"📋 BGM ID: `{bgm_id}`\n"
                f"🔄 跳过详细信息获取，直接进行导入...",
                parse_mode="Markdown"
            )
            
            # 默认按电视剧类型导入（BGM主要是动漫）
            import_params = {
                "searchType": "bangumi",
                "searchTerm": bgm_id,
                "mediaType": "tv_series",
                "importMethod": "auto"
            }
            await call_import_auto_api(update, context, import_params)
            return ConversationHandler.END
    
    elif input_info["type"] == "tt_id":
        # tt 开头的 ID：使用 IMDB 搜索
        tt_id = input_info["value"]
        
        await update.message.reply_text(f"🌟 检测到 IMDB ID: `{tt_id}`\n\n正在获取详细信息...", parse_mode="Markdown")
        
        try:
            # 尝试获取IMDB详细信息
            imdb_info = get_imdb_info(tt_id)
            
            if imdb_info and imdb_info.get('success'):
                # 获取成功，显示详细信息
                title = imdb_info.get('title', 'Unknown')
                year = imdb_info.get('year', 'Unknown')
                media_type = imdb_info.get('type', 'Unknown')
                
                # 根据检测到的类型自动导入
                detected_type = "movie" if media_type.lower() in ["movie", "电影"] else "tv_series"
                
                # 根据媒体类型显示对应图标
                if detected_type == "movie":
                    type_icon = "🎬"
                    type_name = "电影"
                else:
                    type_icon = "📺"
                    type_name = "电视剧"
                
                await update.message.reply_text(
                    f"✅ **IMDB信息获取成功**\n\n"
                    f"🎬 标题: {title}\n"
                    f"📅 年份: {year}\n"
                    f"{type_icon} 类型: {type_name}\n\n"
                    f"🚀 开始自动导入...",
                    parse_mode="Markdown"
                )
                import_params = {
                    "searchType": "imdb",
                    "searchTerm": tt_id,
                    "mediaType": detected_type,
                    "importMethod": "auto"
                }
                await call_import_auto_api(update, context, import_params)
                return ConversationHandler.END
            else:
                # IMDB信息获取失败，跳过解析步骤，直接使用ID导入
                error_msg = imdb_info.get('error', '未知错误') if imdb_info else '网络请求失败'
                logger.warning(f"IMDB信息解析失败，直接使用ID导入: {error_msg}")
                
                await update.message.reply_text(
                    f"⚠️ **IMDB信息解析失败，将直接使用ID导入**\n\n"
                    f"📋 IMDB ID: `{tt_id}`\n"
                    f"🔄 跳过详细信息获取，直接进行导入...",
                    parse_mode="Markdown"
                )
                
                # 默认按电视剧类型导入
                import_params = {
                    "searchType": "imdb",
                    "searchTerm": tt_id,
                    "mediaType": "tv_series",
                    "importMethod": "auto"
                }
                await call_import_auto_api(update, context, import_params)
                return ConversationHandler.END
                
        except Exception as e:
            logger.error(f"IMDB爬虫异常: tt_id='{tt_id}', error={str(e)}")
            logger.warning(f"IMDB信息解析异常，直接使用ID导入: {str(e)}")
            
            await update.message.reply_text(
                f"⚠️ **IMDB信息解析异常，将直接使用ID导入**\n\n"
                f"📋 IMDB ID: `{tt_id}`\n"
                f"🔄 跳过详细信息获取，直接进行导入...",
                parse_mode="Markdown"
            )
            
            # 默认按电视剧类型导入
            import_params = {
                "searchType": "imdb",
                "searchTerm": tt_id,
                "mediaType": "tv_series",
                "importMethod": "auto"
            }
            await call_import_auto_api(update, context, import_params)
            return ConversationHandler.END
    
    else:
        # 关键词搜索：检查是否启用TMDB辅助搜索
        keyword = input_info["value"]
        
        # 保存搜索类型和关键词
        context.user_data["import_auto_search_type"] = "keyword"
        context.user_data["import_auto_keyword"] = keyword
        
        # 检查TMDB是否启用
        from config import TMDB_ENABLED
        
        if TMDB_ENABLED:
            await update.message.reply_text(f"🔍 关键词搜索: {keyword}\n\n正在使用TMDB辅助搜索...")
            
            # 尝试TMDB辅助搜索
            suggested_type = get_media_type_suggestion(keyword)
            tmdb_info = format_tmdb_results_info(keyword)
        else:
            await update.message.reply_text(f"🔍 关键词搜索: {keyword}\n\nℹ️ 未配置TMDB API Key，将跳过TMDB辅助搜索")
            suggested_type = None
            tmdb_info = None
        
        if suggested_type:
            # TMDB建议了明确的类型
            type_name = "📺 电视剧/动漫" if suggested_type == "tv_series" else "🎬 电影"
            
            await update.message.reply_text(
                f"🎯 **TMDB智能识别**\n\n{tmdb_info}\n\n✅ 自动识别类型：{type_name}",
                parse_mode="Markdown"
            )
            
            # 获取最佳匹配的TMDB ID和详细信息
            from utils.tmdb_api import search_tmdb_multi, get_tmdb_media_details
            search_result = search_tmdb_multi(keyword)
            best_match = search_result.get_best_match() if search_result else None
            tmdb_id = str(best_match.get('id')) if best_match else None
            
            # 对于电视剧，预先获取详细信息（包含季度信息）以优化后续处理
            if tmdb_id and suggested_type == "tv_series":
                # 预先获取详细信息，这样后续的季度选择就不需要额外API调用
                media_details = get_tmdb_media_details(tmdb_id, "tv_series")
                if media_details and 'processed_seasons' in media_details:
                    logger.info(f"🎯 预先获取TMDB季度信息成功，共{len(media_details['processed_seasons'])}季")
            
            # 构建导入参数
            if tmdb_id and suggested_type == "tv_series":
                # 电视剧且有TMDB ID：使用TMDB搜索
                import_params = {
                    "searchType": "tmdb",
                    "searchTerm": tmdb_id,
                    "mediaType": suggested_type,
                    "importMethod": "auto"
                }
            else:
                # 电影或无TMDB ID：使用关键词搜索
                import_params = {
                    "searchType": "keyword",
                    "searchTerm": keyword,
                    "mediaType": suggested_type,
                    "importMethod": "auto"
                }
            
            # 根据类型决定处理方式
            if suggested_type == "movie":
                # 电影类型：直接导入
                await update.message.reply_text("🚀 开始自动导入...")
                await call_import_auto_api(update, context, import_params)
                return ConversationHandler.END
            else:
                # 电视剧类型：进入季度选择流程
                return await show_import_options(update, context, import_params)
        else:
            # TMDB无法确定类型或未启用，显示手动选择
            message_text = f"🔍 **关键词搜索: {keyword}**\n\n"
            
            if tmdb_info is None:
                # TMDB未启用
                message_text += "❓ 请手动选择媒体类型：\n\n"
            elif tmdb_info == "🔍 TMDB未找到相关结果":
                # TMDB启用但未找到结果
                message_text += f"{tmdb_info}\n\n❓ 未找到TMDB数据，请手动选择媒体类型：\n\n"
            else:
                # TMDB启用但无法确定单一类型（可能是类型混合或其他原因）
                # 直接进入搜索流程
                await update.message.reply_text(
                    f"{message_text}{tmdb_info}\n\n🔍 **检测到多种媒体类型，正在为您启动搜索流程以获得更精确的结果...**",
                    parse_mode="Markdown"
                )
                
                # 直接调用搜索功能
                await process_search_media(update, keyword, context)
                return ConversationHandler.END
            
            keyboard = [
                [InlineKeyboardButton("📺 电视剧/动漫", callback_data=json.dumps({"action": "import_auto_media_type", "type": "tv_series"}, ensure_ascii=False))],
                [InlineKeyboardButton("🎬 电影", callback_data=json.dumps({"action": "import_auto_media_type", "type": "movie"}, ensure_ascii=False))]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            return 2  # 等待媒体类型选择


async def import_auto_keyword_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收用户输入的关键词"""
    keyword = update.message.text.strip()
    if not keyword:
        await update.message.reply_text("❌ 关键词不能为空，请重新输入：")
        return IMPORT_AUTO_KEYWORD_INPUT
    
    # 保存关键词到上下文
    context.user_data["import_auto_keyword"] = keyword
    
    # 检查TMDB是否启用
    from config import TMDB_ENABLED
    
    if TMDB_ENABLED:
        await update.message.reply_text(f"🔍 关键词搜索: {keyword}\n\n正在使用TMDB辅助搜索...")
        
        # 尝试TMDB辅助搜索
        suggested_type = get_media_type_suggestion(keyword)
        tmdb_info = format_tmdb_results_info(keyword)
    else:
        await update.message.reply_text(f"🔍 关键词搜索: {keyword}\n\nℹ️ 未配置TMDB API Key，将跳过TMDB辅助搜索")
        suggested_type = None
        tmdb_info = None
    
    if suggested_type:
        # TMDB建议了明确的类型
        type_name = "📺 电视剧/动漫" if suggested_type == "tv_series" else "🎬 电影"
        
        # 根据类型显示对应图标
        if suggested_type == "movie":
            type_icon = "🎬"
        else:
            type_icon = "📺"
        
        await update.message.reply_text(
            f"🎯 **TMDB智能识别**\n\n{tmdb_info}\n\n✅ 自动识别类型：{type_icon} {type_name}",
            parse_mode="Markdown"
        )
        
        # 获取最佳匹配的TMDB ID和详细信息
        from utils.tmdb_api import search_tmdb_multi, get_tmdb_media_details
        search_result = search_tmdb_multi(keyword)
        best_match = search_result.get_best_match() if search_result else None
        tmdb_id = str(best_match.get('id')) if best_match else None
        
        # 对于电视剧，预先获取详细信息（包含季度信息）以优化后续处理
        if tmdb_id and suggested_type == "tv_series":
            # 预先获取详细信息，这样后续的季度选择就不需要额外API调用
            media_details = get_tmdb_media_details(tmdb_id, "tv_series")
            if media_details and 'processed_seasons' in media_details:
                logger.info(f"🎯 预先获取TMDB季度信息成功，共{len(media_details['processed_seasons'])}季")
        
        # 构建导入参数
        if tmdb_id and suggested_type == "tv_series":
            # 电视剧且有TMDB ID：使用TMDB搜索
            import_params = {
                "searchType": "tmdb",
                "searchTerm": tmdb_id,
                "mediaType": suggested_type,
                "importMethod": "auto"
            }
        else:
            # 电影或无TMDB ID：使用关键词搜索
            import_params = {
                "searchType": "keyword",
                "searchTerm": keyword,
                "mediaType": suggested_type,
                "importMethod": "auto"
            }
        
        # 根据类型决定处理方式
        if suggested_type == "movie":
            # 电影类型：直接导入
            await update.message.reply_text("🚀 开始自动导入...")
            await call_import_auto_api(update, context, import_params)
            return ConversationHandler.END
        else:
            # 电视剧类型：进入季度选择流程
            return await show_import_options(update, context, import_params)
    else:
        # TMDB无法确定类型或未启用，显示手动选择
        message_text = f"🔍 **关键词搜索: {keyword}**\n\n"
        
        if tmdb_info is None:
            # TMDB未启用
            message_text += "❓ 请手动选择媒体类型：\n\n"
        elif tmdb_info != "🔍 TMDB未找到相关结果":
            # TMDB启用但类型混合
            message_text += f"{tmdb_info}\n\n⚠️ 类型混合，请手动选择：\n\n"
        else:
            # TMDB启用但未找到结果
            message_text += f"{tmdb_info}\n\n❓ 未找到TMDB数据，请手动选择媒体类型：\n\n"
        
        keyboard = [
            [InlineKeyboardButton("📺 电视剧/动漫", callback_data=json.dumps({"action": "import_auto_media_type", "type": "tv_series"}, ensure_ascii=False))],
            [InlineKeyboardButton("🎬 电影", callback_data=json.dumps({"action": "import_auto_media_type", "type": "movie"}, ensure_ascii=False))]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return 2  # 等待媒体类型选择


def validate_platform_match(user_input: str, selected_platform: str) -> tuple[bool, str]:
    """验证用户输入的链接是否与选择的平台匹配
    
    Args:
        user_input: 用户输入的文本
        selected_platform: 用户选择的平台 (tmdb, tvdb, bangumi, douban, imdb)
        
    Returns:
        tuple: (是否匹配, 错误消息)
    """
    result = determine_input_type(user_input)
    input_type = result.get('type')
    
    # 如果输入的是纯ID或关键词，则不需要验证
    if input_type in ['keyword', 'tt_id'] or not input_type.endswith('_url'):
        return True, ""
    
    # 平台映射
    platform_mapping = {
        'tmdb': 'tmdb_url',
        'tvdb': 'tvdb_url', 
        'bangumi': 'bgm_url',
        'douban': 'douban_url',
        'imdb': 'imdb_url'
    }
    
    expected_type = platform_mapping.get(selected_platform)
    if not expected_type:
        return True, ""  # 未知平台，跳过验证
    
    if input_type != expected_type:
        # 构建错误消息
        platform_names = {
            'tmdb': 'TMDB',
            'tvdb': 'TVDB', 
            'bangumi': 'BGM/Bangumi',
            'douban': '豆瓣',
            'imdb': 'IMDB'
        }
        
        detected_platform = {
            'tmdb_url': 'TMDB',
            'tvdb_url': 'TVDB',
            'bgm_url': 'BGM/Bangumi', 
            'douban_url': '豆瓣',
            'imdb_url': 'IMDB'
        }.get(input_type, '未知')
        
        selected_name = platform_names.get(selected_platform, selected_platform)
        
        error_msg = (
            f"❌ **平台不匹配**\n\n"
            f"🎯 您选择的平台: **{selected_name}**\n"
            f"🔍 检测到的平台: **{detected_platform}**\n\n"
            f"💡 **解决方案:**\n"
            f"• 请输入正确的 {selected_name} 链接\n"
            f"• 或者输入纯 ID 进行搜索\n"
            f"• 或者重新选择正确的平台"
        )
        return False, error_msg
    
    return True, ""


async def show_season_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, seasons: list, media_info: dict):
    """显示季度选择界面
    
    Args:
        update: Telegram更新对象
        context: 上下文对象
        seasons: 季度信息列表
        media_info: 媒体基本信息
    """
    if not seasons or len(seasons) == 0:
        # 没有找到季度信息，使用默认导入（电视剧设置season=1）
        await update.message.reply_text(
            f"⚠️ **未找到季度信息**\n\n"
            f"🎬 标题: {media_info.get('title', 'N/A')}\n"
            f"📅 年份: {media_info.get('year', 'N/A')}\n\n"
            f"✅ 使用默认方式导入（第1季）..."
        )
        
        import_params = context.user_data.get("import_auto_params", {})
        import_params["season"] = 1  # 电视剧默认导入第1季
        await call_import_auto_api(update, context, import_params)
        return ConversationHandler.END
        
    elif len(seasons) == 1:
        # 只有一季，直接导入season=1
        season = seasons[0]
        await update.message.reply_text(
            f"📺 **检测到单季电视剧**\n\n"
            f"🎬 标题: {media_info.get('title', 'N/A')}\n"
            f"📅 年份: {media_info.get('year', 'N/A')}\n"
            f"🎭 季度: {season['name']}\n\n"
            f"✅ 自动导入单季内容..."
        )
        
        # 电视剧单季直接设置season=1
        context.user_data["selected_season"] = 1
        import_params = context.user_data.get("import_auto_params", {})
        import_params["season"] = 1
        
        await call_import_auto_api(update, context, import_params)
        return ConversationHandler.END
    
    elif len(seasons) > 1:
        # 多季，显示选择界面
        title = media_info.get('title', 'N/A')
        year = media_info.get('year', 'N/A')
        
        message_text = (
            f"🎭 共找到 {len(seasons)} 季\n\n"
            f"请选择要导入的季度:"
        )
        
        # 创建季度选择按钮
        keyboard = []
        for season in seasons:
            season_num = season['season_number']
            season_name = season['name']
            episode_info = f" ({season['episode_count']}集)" if season['episode_count'] > 0 else ""
            
            button_text = f"{season_name}{episode_info}"
            callback_data = f"season_{season_num}"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # 添加取消按钮
        keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="cancel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message_text, reply_markup=reply_markup)
        
        return IMPORT_AUTO_SEASON_SELECTION


async def import_auto_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收用户输入的平台ID或链接"""
    user_input = update.message.text.strip()
    if not user_input:
        await update.message.reply_text("❌ 输入不能为空，请重新输入：")
        return IMPORT_AUTO_ID_INPUT
    
    search_type = context.user_data.get("import_auto_search_type", "tmdb")
    
    # 验证平台匹配
    is_valid, error_msg = validate_platform_match(user_input, search_type)
    if not is_valid:
        await update.message.reply_text(error_msg)
        return IMPORT_AUTO_ID_INPUT  # 继续等待正确的输入
    
    # 解析输入类型
    result = determine_input_type(user_input)
    input_type = result.get('type')
    
    # 根据输入类型处理
    if input_type == "tmdb_url" and search_type == "tmdb":
        # TMDB链接：使用解析出的ID和媒体类型
        platform_id = result['tmdb_id']
        auto_detected_type = result['media_type']
        type_name = '电影' if auto_detected_type == 'movie' else '电视剧/动漫'
        
        await update.message.reply_text(
            f"🔗 **TMDB链接解析成功**\n\n"
            f"📋 ID: {platform_id}\n"
            f"🎭 检测到类型: {type_name}\n\n"
            f"✅ 自动使用检测到的类型进行导入..."
        )
        
        # 保存解析结果
        context.user_data["import_auto_id"] = platform_id
        context.user_data["import_auto_media_type"] = auto_detected_type
        
        if auto_detected_type == "movie":
            # 电影类型：直接导入
            import_params = {
                "searchType": search_type,
                "searchTerm": platform_id,
                "mediaType": auto_detected_type,
                "importMethod": "auto"
            }
            await call_import_auto_api(update, context, import_params)
            return ConversationHandler.END
        else:
            # 电视剧类型：显示导入方式选择
            context.user_data["import_auto_params"] = {
                "searchType": search_type,
                "searchTerm": platform_id,
                "mediaType": auto_detected_type
            }
            
            await show_import_options(update, context, context.user_data["import_auto_params"])
            return ConversationHandler.END
        
    elif input_type == "imdb_url" and search_type == "imdb":
        # IMDB链接：使用解析出的ID并通过爬虫获取媒体类型
        imdb_id = result['imdb_id']
        
        await update.message.reply_text(
            f"🔗 **IMDB链接解析成功**\n\n"
            f"📋 ID: {imdb_id}\n\n"
            f"🔍 正在获取IMDB媒体信息..."
        )
        
        # 通过爬虫获取IMDB媒体信息
        try:
            imdb_info = get_imdb_info(imdb_id)
            
            if imdb_info and imdb_info.get('success'):
                media_title = imdb_info.get('title', 'N/A')
                media_year = imdb_info.get('year', 'N/A')
                media_type = imdb_info.get('media_type', 'movie')
                rating = imdb_info.get('rating', 'N/A')
                
                type_name = '电影' if media_type == 'movie' else '电视剧/动漫'
                
                await update.message.reply_text(
                    f"✅ **IMDB信息获取成功**\n\n"
                    f"🎬 名称: {media_title}\n"
                    f"📅 年份: {media_year}\n"
                    f"⭐ 评分: {rating}\n"
                    f"🎭 类型: {type_name}\n\n"
                    f"✅ 自动使用检测到的类型进行导入..."
                )
                
                # 保存解析结果
                context.user_data["import_auto_id"] = imdb_id
                context.user_data["import_auto_media_type"] = media_type
                
                if media_type == "movie":
                    # 电影类型：直接导入
                    import_params = {
                        "searchType": search_type,
                        "searchTerm": imdb_id,
                        "mediaType": media_type,
                        "importMethod": "auto"
                    }
                    await call_import_auto_api(update, context, import_params)
                    return ConversationHandler.END
                else:
                    # 电视剧类型：显示导入方式选择
                    context.user_data["import_auto_params"] = {
                        "searchType": search_type,
                        "searchTerm": imdb_id,
                        "mediaType": media_type
                    }
                    
                    await show_import_options(update, context, context.user_data["import_auto_params"])
                    return ConversationHandler.END
            else:
                # IMDB信息获取失败
                error_msg = imdb_info.get('error', '未知错误') if imdb_info else '网络请求失败'
                await update.message.reply_text(
                    f"❌ **IMDB信息获取失败**\n\n"
                    f"🔍 ID: {imdb_id}\n"
                    f"❗ 错误: {error_msg}\n\n"
                    f"💡 **可能的原因:**\n"
                    f"• IMDB网站访问限制\n"
                    f"• 网络连接问题\n"
                    f"• 页面结构变化\n\n"
                    f"🔄 **建议:**\n"
                    f"• 稍后重试\n"
                    f"• 使用其他搜索方式",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END
        except Exception as e:
            logger.error(f"IMDB爬虫异常: {e}")
            await update.message.reply_text(
                f"❌ **IMDB信息获取异常**\n\n"
                f"🔍 ID: {imdb_id}\n"
                f"❗ 异常: {str(e)}\n\n"
                f"🔄 请稍后重试或使用其他搜索方式",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
    elif input_type == "bgm_url" and search_type == "bangumi":
        # BGM链接：使用解析出的ID并通过爬虫获取媒体类型
        bgm_id = result['bgm_id']
        
        await update.message.reply_text(
            f"🔗 **BGM链接解析成功**\n\n"
            f"📋 ID: {bgm_id}\n\n"
            f"🔍 正在获取BGM媒体信息..."
        )
        
        # 通过爬虫获取BGM媒体信息
        try:
            bgm_info = get_bgm_info(bgm_id)
            
            if bgm_info and bgm_info.get('success'):
                media_title = bgm_info.get('title', 'N/A')
                media_year = bgm_info.get('year', 'N/A')
                media_type = bgm_info.get('media_type', 'tv_series')
                rating = bgm_info.get('rating', 'N/A')
                
                type_name = '电影' if media_type == 'movie' else '电视剧/动漫'
                
                await update.message.reply_text(
                    f"✅ **BGM信息获取成功**\n\n"
                    f"🎬 名称: {media_title}\n"
                    f"📅 年份: {media_year}\n"
                    f"⭐ 评分: {rating}\n"
                    f"🎭 类型: {type_name}\n\n"
                    f"✅ 自动使用检测到的类型进行导入..."
                )
                
                # 保存解析结果
                context.user_data["import_auto_id"] = bgm_id
                context.user_data["import_auto_media_type"] = media_type
                
                if media_type == "movie":
                    # 电影类型：直接导入
                    import_params = {
                        "searchType": search_type,
                        "searchTerm": bgm_id,
                        "mediaType": media_type,
                        "importMethod": "auto"
                    }
                    await call_import_auto_api(update, context, import_params)
                    return ConversationHandler.END
                else:
                    # 电视剧类型：显示导入方式选择
                    context.user_data["import_auto_params"] = {
                        "searchType": search_type,
                        "searchTerm": bgm_id,
                        "mediaType": media_type
                    }
                    
                    await show_import_options(update, context, context.user_data["import_auto_params"])
                    return ConversationHandler.END
            else:
                # BGM信息获取失败
                error_msg = bgm_info.get('error', '未知错误') if bgm_info else '网络请求失败'
                await update.message.reply_text(
                    f"❌ **BGM信息获取失败**\n\n"
                    f"🔍 ID: {bgm_id}\n"
                    f"❗ 错误: {error_msg}\n\n"
                    f"💡 **可能的原因:**\n"
                    f"• BGM网站访问限制\n"
                    f"• 网络连接问题\n"
                    f"• 页面结构变化\n\n"
                    f"🔄 **建议:**\n"
                    f"• 稍后重试\n"
                    f"• 使用其他搜索方式",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END
        except Exception as e:
            logger.error(f"BGM爬虫异常: {e}")
            await update.message.reply_text(
                f"❌ **BGM信息获取异常**\n\n"
                f"🔍 ID: {bgm_id}\n"
                f"❗ 异常: {str(e)}\n\n"
                f"🔄 请稍后重试或使用其他搜索方式",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        
    elif input_type == "tvdb_url" and search_type == "tvdb":
        # TVDB链接：通过API查询获取数字ID
        slug = result['slug']
        auto_detected_type = result['media_type']
        type_name = '电影' if auto_detected_type == 'movie' else '电视剧/动漫'
        
        await update.message.reply_text(
            f"🔗 **TVDB链接解析成功**\n\n"
            f"📋 Slug: {slug}\n"
            f"🎭 检测到类型: {type_name}\n\n"
            f"🔍 正在查询TVDB数字ID..."
        )
        
    elif input_type == "douban_url" and search_type == "douban":
        # 豆瓣链接：通过爬虫获取媒体信息
        douban_id = result['douban_id']
        
        await update.message.reply_text(
            f"🔗 **豆瓣链接解析成功**\n\n"
            f"📋 ID: {douban_id}\n\n"
            f"🔍 正在获取豆瓣媒体信息..."
        )
        
        # 通过爬虫获取豆瓣媒体信息
        from utils.douban_scraper import get_douban_media_info
        
        try:
            douban_info = await get_douban_media_info(douban_id)
            
            if douban_info and douban_info.get('success'):
                media_title = douban_info.get('title', 'N/A')
                media_year = douban_info.get('year', 'N/A')
                genres = douban_info.get('genres', [])
                rating = douban_info.get('rating', 'N/A')
                
                # 使用豆瓣爬虫返回的媒体类型（与process_auto_input保持一致）
                auto_detected_type = douban_info.get('media_type', 'movie')
                if auto_detected_type == 'tv_series':
                    type_name = '电视剧/动漫'
                else:
                    type_name = '电影'
                
                await update.message.reply_text(
                    f"✅ **豆瓣信息获取成功**\n\n"
                    f"🎬 标题: {media_title}\n"
                    f"📅 年份: {media_year}\n"
                    f"🎭 类型: {type_name}\n"
                    f"⭐ 评分: {rating}\n\n"
                    f"✅ 自动使用检测到的类型进行导入..."
                )
                
                # 保存解析结果
                context.user_data["import_auto_id"] = douban_id
                context.user_data["import_auto_media_type"] = auto_detected_type
                
                if auto_detected_type == "movie":
                    # 电影类型：直接导入
                    import_params = {
                        "searchType": search_type,
                        "searchTerm": douban_id,
                        "mediaType": auto_detected_type,
                        "importMethod": "auto"
                    }
                    await call_import_auto_api(update, context, import_params)
                    return ConversationHandler.END
                else:
                    # 电视剧类型：显示导入方式选择
                    context.user_data["import_auto_params"] = {
                        "searchType": search_type,
                        "searchTerm": douban_id,
                        "mediaType": auto_detected_type
                    }
                    
                    await show_import_options(update, context, context.user_data["import_auto_params"])
                    return ConversationHandler.END
            else:
                # 豆瓣信息获取失败
                error_msg = douban_info.get('error', '未知错误') if douban_info else '网络请求失败'
                
                await update.message.reply_text(
                    f"❌ **豆瓣信息获取失败**\n\n"
                    f"无法获取豆瓣ID '{douban_id}' 的媒体信息。\n\n"
                    f"💡 **错误信息:** {error_msg}\n\n"
                    f"🔄 **建议:**\n"
                    f"• 检查豆瓣链接是否正确\n"
                    f"• 稍后重试\n"
                    f"• 使用关键词搜索"
                )
                return ConversationHandler.END
                
        except Exception as e:
            logger.error(f"豆瓣爬虫异常: douban_id='{douban_id}', error={str(e)}")
            
            await update.message.reply_text(
                f"❌ **豆瓣信息获取异常**\n\n"
                f"处理豆瓣ID '{douban_id}' 时发生错误。\n\n"
                f"💡 **可能的原因:**\n"
                f"• 豆瓣网站访问限制\n"
                f"• 网络连接问题\n"
                f"• 页面结构变化\n\n"
                f"🔄 **建议:**\n"
                f"• 稍后重试\n"
                f"• 使用其他搜索方式"
            )
            return ConversationHandler.END
    
    elif input_type == "bgm_url" and search_type == "bgm":
        # BGM链接：通过爬虫获取媒体信息
        bgm_id = result['bgm_id']
        
        await update.message.reply_text(
            f"🔗 **BGM链接解析成功**\n\n"
            f"📋 ID: {bgm_id}\n\n"
            f"🔍 正在获取BGM媒体信息..."
        )
        
        # 通过爬虫获取BGM媒体信息
        try:
            bgm_info = await get_bgm_info(bgm_id)
            
            if bgm_info and bgm_info.get('success'):
                media_title = bgm_info.get('title', 'N/A')
                media_year = bgm_info.get('year', 'N/A')
                media_type = bgm_info.get('media_type', 'tv_series')
                rating = bgm_info.get('rating', 'N/A')
                
                type_name = '电影' if media_type == 'movie' else '电视剧/动漫'
                
                await update.message.reply_text(
                    f"✅ **BGM信息获取成功**\n\n"
                    f"🎬 标题: {media_title}\n"
                    f"📅 年份: {media_year}\n"
                    f"🎭 类型: {type_name}\n"
                    f"⭐ 评分: {rating}\n\n"
                    f"✅ 自动使用检测到的类型进行导入..."
                )
                
                # 保存解析结果
                context.user_data["import_auto_id"] = bgm_id
                context.user_data["import_auto_media_type"] = media_type
                
                if media_type == "movie":
                    # 电影类型：直接导入
                    import_params = {
                        "searchType": search_type,
                        "searchTerm": bgm_id,
                        "mediaType": media_type,
                        "importMethod": "auto"
                    }
                    await call_import_auto_api(update, context, import_params)
                    return ConversationHandler.END
                else:
                    # 电视剧类型：显示导入方式选择
                    context.user_data["import_auto_params"] = {
                        "searchType": search_type,
                        "searchTerm": bgm_id,
                        "mediaType": media_type
                    }
                    
                    await show_import_options(update, context, context.user_data["import_auto_params"])
                    return ConversationHandler.END
            else:
                # BGM信息获取失败
                error_msg = bgm_info.get('error', '未知错误') if bgm_info else '网络请求失败'
                await update.message.reply_text(
                    f"❌ **BGM信息获取失败**\n\n"
                    f"🔍 ID: {bgm_id}\n"
                    f"❗ 错误: {error_msg}\n\n"
                    f"💡 **可能的原因:**\n"
                    f"• BGM网站访问限制\n"
                    f"• 网络连接问题\n"
                    f"• 页面结构变化\n\n"
                    f"🔄 **建议:**\n"
                    f"• 稍后重试\n"
                    f"• 使用其他搜索方式",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END
        except Exception as e:
            logger.error(f"BGM爬虫异常: {e}")
            await update.message.reply_text(
                f"❌ **BGM信息获取异常**\n\n"
                f"🔍 ID: {bgm_id}\n"
                f"❗ 异常: {str(e)}\n\n"
                f"🔄 请稍后重试或使用其他搜索方式",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
    
    elif input_type == "tvdb_url" and search_type == "tvdb":
        # TVDB链接：通过API查询获取数字ID
        slug = result['slug']
        auto_detected_type = result['media_type']
        type_name = '电影' if auto_detected_type == 'movie' else '电视剧/动漫'
        
        await update.message.reply_text(
            f"🔗 **TVDB链接解析成功**\n\n"
            f"📋 Slug: {slug}\n"
            f"🎭 检测到类型: {type_name}\n\n"
            f"🔍 正在查询TVDB数字ID..."
        )
        
        # 通过API查询获取数字ID
        logger.info(f"开始TVDB查询: slug='{slug}', media_type='{auto_detected_type}'")
        tvdb_info = await search_tvdb_by_slug(slug, auto_detected_type)
        logger.info(f"TVDB查询结果: {tvdb_info}")
        
        # 如果指定类型查询失败，尝试查询另一种类型作为回退
        if not tvdb_info or not tvdb_info.get('tvdb_id'):
            fallback_type = "tv_series" if auto_detected_type == "movie" else "movie"
            fallback_type_name = '电视剧/动漫' if fallback_type == 'tv_series' else '电影'
            
            await update.message.reply_text(
                f"⚠️ **未找到对应的{type_name}**\n\n"
                f"🔄 尝试查询{fallback_type_name}..."
            )
            
            logger.info(f"回退查询: slug='{slug}', media_type='{fallback_type}'")
            tvdb_info = await search_tvdb_by_slug(slug, fallback_type)
            logger.info(f"回退查询结果: {tvdb_info}")
            
            if tvdb_info and tvdb_info.get('tvdb_id'):
                auto_detected_type = fallback_type  # 更新为实际找到的类型
                type_name = fallback_type_name
                await update.message.reply_text(
                    f"✅ **找到了{type_name}版本**\n\n"
                    f"将使用此类型进行导入"
                )
        
        if tvdb_info and tvdb_info.get('tvdb_id'):
            # 提取ID中的数字部分（如果格式为 'series-443536'，只保留 '443536'）
            raw_id = tvdb_info['tvdb_id']
            if '-' in raw_id:
                platform_id = raw_id.split('-')[-1]  # 取最后一个'-'后面的部分
            else:
                platform_id = raw_id
            
            await update.message.reply_text(
                f"✅ **TVDB查询成功**\n\n"
                f"📋 ID: {platform_id}\n"
                f"🎬 名称: {tvdb_info.get('name', 'N/A')}\n"
                f"🎭 类型: {type_name}\n\n"
                f"✅ 自动使用检测到的类型进行导入..."
            )
            
            # 保存解析结果
            context.user_data["import_auto_id"] = platform_id
            context.user_data["import_auto_media_type"] = auto_detected_type
            
            if auto_detected_type == "movie":
                # 电影类型：直接导入
                import_params = {
                    "searchType": search_type,
                    "searchTerm": platform_id,
                    "mediaType": auto_detected_type,
                    "importMethod": "auto"
                }
                await call_import_auto_api(update, context, import_params)
                return ConversationHandler.END
            else:
                # 电视剧类型：显示导入方式选择
                context.user_data["import_auto_params"] = {
                    "searchType": search_type,
                    "searchTerm": platform_id,
                    "mediaType": auto_detected_type
                }
                
                await show_import_options(update, context, context.user_data["import_auto_params"])
                return ConversationHandler.END
        else:
            # 记录详细的错误信息用于调试
            logger.error(f"TVDB查询失败: slug='{slug}', media_type='{auto_detected_type}', tvdb_info={tvdb_info}")
            
            await update.message.reply_text(
                f"❌ **TVDB查询失败**\n\n"
                f"无法找到slug '{slug}' 对应的媒体信息，请检查链接是否正确。\n\n"
                f"💡 **可能的原因:**\n"
                f"• TVDB API暂时不可用\n"
                f"• 网络连接问题\n"
                f"• 该内容在TVDB中不存在\n\n"
                f"🔄 **建议:**\n"
                f"• 稍后重试\n"
                f"• 使用TMDB链接或关键词搜索"
            )
            return ConversationHandler.END
        
    elif input_type in ["tt_id", "keyword"] or search_type != "tmdb":
        # 纯ID、关键词或非TMDB搜索：直接使用
        platform_id = result.get('value', user_input)
        context.user_data["import_auto_id"] = platform_id
        
        # 特殊处理：如果是BGM平台且输入的是纯数字ID，尝试通过爬虫获取媒体信息
        if search_type == "bangumi" and platform_id.isdigit():
            await update.message.reply_text(
                f"🆔 **BGM ID: {platform_id}**\n\n🔍 正在获取BGM媒体信息..."
            )
            
            try:
                bgm_info = get_bgm_info(platform_id)
                
                if bgm_info and bgm_info.get('success'):
                    media_title = bgm_info.get('title', 'N/A')
                    media_year = bgm_info.get('year', 'N/A')
                    media_type = bgm_info.get('media_type', 'tv_series')
                    rating = bgm_info.get('rating', 'N/A')
                    
                    type_name = '电影' if media_type == 'movie' else '电视剧/动漫'
                    
                    await update.message.reply_text(
                        f"✅ **BGM信息获取成功**\n\n"
                        f"🎬 名称: {media_title}\n"
                        f"📅 年份: {media_year}\n"
                        f"⭐ 评分: {rating}\n"
                        f"🎭 类型: {type_name}\n\n"
                        f"✅ 自动使用检测到的类型进行导入..."
                    )
                    
                    # 保存解析结果
                    context.user_data["import_auto_media_type"] = media_type
                    
                    if media_type == "movie":
                        # 电影类型：直接导入
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
                        context.user_data["import_auto_params"] = {
                            "searchType": search_type,
                            "searchTerm": platform_id,
                            "mediaType": media_type
                        }
                        
                        await show_import_options(update, context, context.user_data["import_auto_params"])
                        return ConversationHandler.END
                else:
                    # BGM信息获取失败，回退到手动选择类型
                    error_msg = bgm_info.get('error', '未知错误') if bgm_info else '网络请求失败'
                    await update.message.reply_text(
                        f"⚠️ **BGM信息获取失败**\n\n"
                        f"🔍 ID: {platform_id}\n"
                        f"❗ 错误: {error_msg}\n\n"
                        f"🔄 将回退到手动选择媒体类型模式\n\n"
                        f"请选择媒体类型："
                    )
            except Exception as e:
                logger.error(f"BGM爬虫异常: {e}")
                await update.message.reply_text(
                    f"⚠️ **BGM信息获取异常**\n\n"
                    f"🔍 ID: {platform_id}\n"
                    f"❗ 异常: {str(e)}\n\n"
                    f"🔄 将回退到手动选择媒体类型模式\n\n"
                    f"请选择媒体类型："
                )
        else:
            await update.message.reply_text(
                f"🆔 **平台ID: {platform_id}**\n\n请选择媒体类型："
            )
        
    else:
        # 其他情况：直接使用输入
        platform_id = user_input
        context.user_data["import_auto_id"] = platform_id
        
        await update.message.reply_text(
            f"🆔 **平台ID: {platform_id}**\n\n请选择媒体类型："
        )
    
    # 显示媒体类型选择按钮
    keyboard = [
        [InlineKeyboardButton("📺 电视剧/动漫", callback_data=json.dumps({"action": "import_auto_media_type", "type": "tv_series"}, ensure_ascii=False))],
        [InlineKeyboardButton("🎬 电影", callback_data=json.dumps({"action": "import_auto_media_type", "type": "movie"}, ensure_ascii=False))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "请选择媒体类型：",
        reply_markup=reply_markup
    )
    
    return IMPORT_AUTO_ID_INPUT  # 等待媒体类型选择


# 已移除import_auto_season_input和import_auto_episode_input函数，因为不再需要分季导入和分集导入功能


async def show_import_options(update: Update, context: ContextTypes.DEFAULT_TYPE, params: dict):
    """显示导入选项，对于电视剧检查季度信息"""
    # 保存参数到上下文
    context.user_data["import_auto_params"] = params
    
    # 检查是否为电视剧类型
    if params.get("mediaType") == "tv_series":
        # 电视剧类型：检查季度信息
        search_type = params.get("searchType")
        search_term = params.get("searchTerm")
        
        await update.message.reply_text("🔍 正在获取季度信息...")
        
        # 根据平台获取季度信息
        seasons = None
        media_info = {}
        
        try:
            if search_type == "tmdb":
                # 优化：直接从get_tmdb_media_details获取详情和季度信息
                from utils.tmdb_api import get_tmdb_media_details
                media_details = get_tmdb_media_details(search_term, "tv_series")
                
                if media_details:
                    # 获取季度信息（优先使用已处理的季度信息）
                    if 'processed_seasons' in media_details:
                        seasons = media_details['processed_seasons']
                    else:
                        # 如果没有预处理，调用get_tmdb_tv_seasons
                        seasons = get_tmdb_tv_seasons(search_term)
                    
                    # 提取媒体基本信息
                    title = media_details.get('title') or media_details.get('name', f'TMDB ID: {search_term}')
                    first_air_date = media_details.get('first_air_date', '')
                    year = first_air_date[:4] if first_air_date else 'N/A'
                    media_info = {'title': title, 'year': year}
                else:
                    # 如果获取详情失败，回退到原来的方式
                    seasons = get_tmdb_tv_seasons(search_term)
                    media_info = {'title': f'TMDB ID: {search_term}', 'year': 'N/A'}
                    
            elif search_type == "tvdb":
                seasons = get_tvdb_tv_seasons(search_term)
                media_info = {'title': f'TVDB ID: {search_term}', 'year': 'N/A'}
                
            elif search_type == "imdb":
                # 从IMDB爬虫获取信息（包含季度信息）
                imdb_info = get_imdb_info(search_term)
                if imdb_info and imdb_info.get('success'):
                    seasons = imdb_info.get('seasons', [])
                    media_info = {
                        'title': imdb_info.get('title', f'IMDB ID: {search_term}'),
                        'year': imdb_info.get('year', 'N/A')
                    }
                else:
                    media_info = {'title': f'IMDB ID: {search_term}', 'year': 'N/A'}
                    
            elif search_type == "douban":
                # 从豆瓣爬虫获取信息（包含从标题解析的季度信息）
                from utils.douban_scraper import get_douban_info
                douban_info = get_douban_info(search_term)
                if douban_info:
                    # 如果豆瓣爬虫解析出了季度信息，直接使用
                    season_number = douban_info.get('season')
                    if season_number:
                        # 直接导入指定季度
                        params["season"] = season_number
                        params["importMethod"] = "auto"
                        
                        await update.message.reply_text(
                            f"✅ **从标题解析出季度信息**\n\n"
                            f"🎬 标题: {douban_info.get('title', 'N/A')}\n"
                            f"📅 年份: {douban_info.get('year', 'N/A')}\n"
                            f"🎭 季度: 第{season_number}季\n\n"
                            f"🚀 开始导入第{season_number}季内容..."
                        )
                        
                        await call_import_auto_api(update, context, params)
                        return ConversationHandler.END
                    else:
                        # 没有解析出季度信息，默认设置为第1季
                        params["season"] = 1
                        await update.message.reply_text(
                            f"✅ **未从标题解析出季度信息，默认导入第1季**\n\n"
                            f"🎬 标题: {douban_info.get('title', 'N/A')}\n"
                            f"📅 年份: {douban_info.get('year', 'N/A')}\n"
                            f"🎭 季度: 第1季（默认）\n\n"
                            f"🚀 开始导入第1季内容..."
                        )
                        
                        await call_import_auto_api(update, context, params)
                        return ConversationHandler.END
                else:
                    seasons = None
                    media_info = {'title': f'豆瓣ID: {search_term}', 'year': 'N/A'}
                    
            elif search_type == "bangumi":
                # 从BGM爬虫获取信息（包含从标题解析的季度信息）
                bgm_info = get_bgm_info(search_term)
                if bgm_info and bgm_info.get('success'):
                    # 如果BGM爬虫解析出了季度信息，直接使用
                    season_number = bgm_info.get('season')
                    if season_number:
                        # 直接导入指定季度
                        params["season"] = season_number
                        params["importMethod"] = "auto"
                        
                        await update.message.reply_text(
                            f"✅ **从标题解析出季度信息**\n\n"
                            f"🎬 标题: {bgm_info.get('title', 'N/A')}\n"
                            f"📅 年份: {bgm_info.get('year', 'N/A')}\n"
                            f"🎭 季度: 第{season_number}季\n\n"
                            f"🚀 开始导入第{season_number}季内容..."
                        )
                        
                        await call_import_auto_api(update, context, params)
                        return ConversationHandler.END
                    else:
                        # 没有解析出季度信息，默认设置为第1季
                        params["season"] = 1
                        await update.message.reply_text(
                            f"✅ **未从标题解析出季度信息，默认导入第1季**\n\n"
                            f"🎬 标题: {bgm_info.get('title', 'N/A')}\n"
                            f"📅 年份: {bgm_info.get('year', 'N/A')}\n"
                            f"🎭 季度: 第1季（默认）\n\n"
                            f"🚀 开始导入第1季内容..."
                        )
                        
                        await call_import_auto_api(update, context, params)
                        return ConversationHandler.END
                else:
                    seasons = None
                    media_info = {'title': f'BGM ID: {search_term}', 'year': 'N/A'}
                    
        except Exception as e:
            logger.warning(f"获取季度信息失败: {e}")
            seasons = None
            
        # 调用季度选择函数
        return await show_season_selection(update, context, seasons, media_info)
    else:
        # 电影类型：直接执行自动导入，不需要season参数
        params["importMethod"] = "auto"
        # 确保电影类型不包含season参数
        if "season" in params:
            del params["season"]
        await call_import_auto_api(update, context, params)
        return ConversationHandler.END


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
    
    # 移除中间状态提示，直接调用API
    
    # 调用API
    api_result = call_danmaku_api(
        method="POST",
        endpoint="/import/auto",
        params=params
    )
    
    # 处理API响应
    if api_result["success"]:
        success_message = f"✅ 导入成功！"
        
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


# 已移除call_import_auto_api_with_continue函数，因为不再需要分季导入和分集导入功能
    