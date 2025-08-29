import logging
import requests
from functools import wraps
from typing import Dict, Optional, Any
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from config import (
    TELEGRAM_BOT_TOKEN,
    ALLOWED_USER_IDS,
    DANMAKU_API_BASE_URL,
    DANMAKU_API_KEY,
    API_TIMEOUT,
    DANMAKU_API_HEADERS,
    LOG_LEVEL,
)
import json
# ------------------------------
# 日志配置（支持Docker日志查看）
# ------------------------------
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# ------------------------------
# 对话状态（多步指令使用）
# ------------------------------
SEARCH_MEDIA, INPUT_IMPORT_URL, CONFIRM_DELETE_ANIME, CONFIRM_DELETE_EPISODE = range(4)

# ------------------------------
# 1. 权限验证装饰器（核心安全逻辑）
# ------------------------------
def check_user_permission(func):
    """装饰器：验证用户是否在白名单中，未授权则拒绝执行"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # 获取当前用户信息
        user = update.effective_user
        if not user:
            logger.warning("❌ 无法获取用户信息，拒绝请求")
            await update.message.reply_text("❌ 无法验证身份，请稍后重试")
            return

        user_id = user.id
        username = user.username or "未知用户名"

        # 验证白名单
        if user_id not in ALLOWED_USER_IDS:
            logger.warning(f"⚠️ 未授权访问：用户ID={user_id}，用户名={username}")
            await update.message.reply_text("❌ 你没有使用该机器人的权限，请联系管理员")
            return

        # 有权限：记录日志并执行原指令
        logger.info(f"✅ 授权访问：用户ID={user_id}，用户名={username}，指令={func.__name__}")
        return await func(update, context, *args, **kwargs)
    return wrapper

# ------------------------------
# 2. API调用工具函数（通用请求逻辑）
# ------------------------------
# ------------------------------
# 2. API调用工具函数（核心修改：移除api_key参数）
# ------------------------------
# ------------------------------
# 2. API调用工具函数（仅修改URL拼接部分，其他逻辑不变）
# ------------------------------
def call_danmaku_api(
    method: str,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    调用Misaka Danmaku API的通用函数（仅修复URL拼接错误）
    """
    
    # 1. 先拼“基础地址 + 端点”（如：https://xxx/api/control + /search → https://xxx/api/control/search）
    base_url_with_endpoint = f"{DANMAKU_API_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    
    # 2. 手动添加apikey参数（用?或&连接，避免与其他参数冲突）
    if "?" in base_url_with_endpoint:
        # 若端点后已有其他参数（如?xxx=yyy），用&拼接apikey
        full_url = f"{base_url_with_endpoint}&api_key={DANMAKU_API_KEY}"
    else:
        # 若端点后无参数，用?拼接apikey
        full_url = f"{base_url_with_endpoint}?api_key={DANMAKU_API_KEY}"
    # ------------------------------
    # 以下代码完全不变（保留原逻辑）
    # ------------------------------
    params = params or {}

    try:
        response = requests.request(
            method=method.upper(),
            url=full_url,  # 使用修复后的full_url
            params=params,
            json=json_data,
            headers=DANMAKU_API_HEADERS,
            timeout=API_TIMEOUT,
            verify=True
        )

        print(format_request_as_curl(response))

        response.raise_for_status()
        return {
            "success": True,
            "data": response.json()
        }

    except requests.exceptions.Timeout:
        logger.error(f"⏱️ API请求超时：{full_url}")
        return {"success": False, "error": "请求超时，请稍后重试"}
    except requests.exceptions.ConnectionError:
        logger.error(f"🔌 API连接失败：{full_url}")
        return {"success": False, "error": "API连接失败，请检查地址是否正确"}
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP错误 {e.response.status_code}：{e.response.text[:100]}"
        logger.error(f"❌ API请求错误：{full_url}，{error_msg}")
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"未知错误：{str(e)[:50]}"
        logger.error(f"❌ API请求异常：{full_url}，{error_msg}")
        return {"success": False, "error": error_msg}

# 构建curl命令
def format_request_as_curl(response):
    request = response.request
    
    # 基础命令
    curl_cmd = f"curl '{request.url}' \\\n"
    
    # 添加请求方法（如果不是GET）
    if request.method != "GET":
        curl_cmd += f"  -X {request.method} \\\n"
    
    # 添加headers
    for key, value in request.headers.items():
        # 跳过一些自动生成的headers，避免重复
        if key.lower() not in ['content-length', 'accept-encoding']:
            curl_cmd += f"  -H '{key}: {value}' \\\n"
    
    # 添加cookies
    if request._cookies:
        for cookie in request._cookies:
            curl_cmd += f"  -b '{cookie.name}={cookie.value}' \\\n"
    
    # 添加请求体（如果有）
    if request.body:
        body = request.body.decode('utf-8') if isinstance(request.body, bytes) else str(request.body)
        curl_cmd += f"  -d '{body}' \\\n"
    
    # 去除最后一个换行和反斜杠
    if curl_cmd.endswith("\\\n"):
        curl_cmd = curl_cmd[:-2]
    
    return curl_cmd

# ------------------------------
# 3. 基础指令（无风险，支持所有人查看）
# ------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """发送欢迎消息和指令列表"""
    welcome_msg = """
👋 欢迎使用 Misaka 弹幕系统机器人！
仅授权用户可使用以下指令，直接发送指令即可操作：

【📥 媒体导入】
/auto_import [关键词]   - 全自动搜索并导入（如：/auto_import 海贼王）
/url_import [URL]      - 从作品URL导入（如：/url_import 视频地址）
/direct_import [ID]    - 从搜索结果ID导入（需先/search_media）

【📚 媒体库管理】
/search_media [关键词] - 搜索媒体（如：/search_media 火影忍者）
/list_library          - 查看媒体库所有作品
/get_anime [ID]        - 获取单个作品详情（如：/get_anime 456）
/get_sources [ID]      - 获取作品数据源（如：/get_sources 456）

【💬 弹幕操作】
/get_danmaku [集ID]    - 获取某分集弹幕（如：/get_danmaku 789）
/refresh_danmaku [集ID]- 刷新某分集弹幕（如：/refresh_danmaku 789）

【🗑️ 高危操作（需二次确认）】
/delete_anime [ID]     - 删除整个作品（如：/delete_anime 456）
/delete_episode [集ID] - 删除单个分集（如：/delete_episode 789）

【其他】
/help  - 查看帮助信息
/cancel - 取消当前操作
    """
    await update.message.reply_text(welcome_msg, reply_markup=ReplyKeyboardRemove())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """重复发送帮助信息"""
    await start(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消当前对话流程"""
    # 清除上下文缓存
    context.user_data.clear()
    await update.message.reply_text("✅ 已取消当前操作", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ------------------------------
# 4. 媒体搜索与导入指令（需授权）
# ------------------------------
@check_user_permission
async def search_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """搜索媒体：支持直接带关键词或后续输入"""
    # 1. 直接带参数（如：/search_media 海贼王）
    if context.args:
        keyword = " ".join(context.args)
        await process_search_media(update, keyword, context)
        return

    # 2. 无参数：引导用户输入关键词
    await update.message.reply_text("请输入要搜索的媒体关键词（如：海贼王、进击的巨人）：")
    return SEARCH_MEDIA

async def search_media_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收用户输入的搜索关键词"""
    keyword = update.message.text.strip()
    if not keyword:
        await update.message.reply_text("❌ 关键词不能为空，请重新输入：")
        return SEARCH_MEDIA

    await process_search_media(update, keyword, context)
    return ConversationHandler.END

async def process_search_media(update: Update, keyword: str, context: ContextTypes.DEFAULT_TYPE):
    """处理搜索逻辑：生成带「导入按钮」的结果列表"""
    await update.message.reply_text(f"🔍 正在搜索关键词「{keyword}」...")
    
    # 1. 调用API搜索（原逻辑不变）
    api_result = call_danmaku_api(
        method="GET",
        endpoint="/search",
        params={"keyword": keyword}
    )

    # 2. 处理API响应（原逻辑不变，确保searchId有效）
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

    # 3. 保存searchId到上下文（供回调导入使用）
    context.user_data["search_id"] = search_id
    # 额外保存结果总数（可选：用于按钮提示）
    context.user_data["search_result_count"] = len(items)

    # 4. 生成带「导入按钮」的结果消息（每条结果独立一行+按钮）
    await update.message.reply_text(f"✅ 找到 {len(items)} 个结果，点击「导入」按钮直接添加：")
    
    # 遍历每个结果，生成独立消息+内联按钮
    for idx, item in enumerate(items, 1):
        # 格式化单条结果文本（简洁展示关键信息）
        result_text = f"""
【{idx}/{len(items)}】{item.get('title', '未知名称')}
• 类型：{item.get('type', '未知类型')} | 来源：{item.get('provider', '未知来源')}
• 年份：{item.get('year', '未知年份')} | 季度：{item.get('season', '未知季度')}
• 总集数：{item.get('episodeCount', '0')}集
        """
        
        callback_data = json.dumps({
            "action": "import_media",  # 必须与业务回调的 pattern 一致
            "result_index": idx - 1    # 0开始的索引
        }, ensure_ascii=False)
        print(f"🔘 生成按钮的 callback_data：{callback_data}")  # 新增：打印生成的data
        
        # 生成「导入按钮」：callback_data 携带 result_index（注意：idx-1 适配API的0开始索引）
        keyboard = [
            [InlineKeyboardButton(
                text="🔗 立即导入",
                callback_data=json.dumps({
                    "action": "import_media",  # 标识操作类型（便于后续扩展）
                    "result_index": idx - 1    # 传递API要求的result_index（0开始）
                }, ensure_ascii=False)
            )]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 发送单条结果+按钮（每条结果独立成消息，避免混乱）
        await update.message.reply_text(
            text=result_text.strip(),  # 去除多余空行
            reply_markup=reply_markup,
            parse_mode=None  # 若文本含特殊符号（如[ ]），禁用解析模式避免格式错误
        )

@check_user_permission
async def handle_import_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理「导入按钮」的回调事件：执行导入逻辑"""
    # 1. 获取回调数据（解析按钮传递的result_index）
    query = update.callback_query
    print(f"📥 收到回调数据：query.data = {query.data}")  # 打印关键的 callback_data
    try:
        # 解析callback_data中的JSON数据（避免参数传递错误）
        callback_data = json.loads(query.data)
        action = callback_data.get("action")
        result_index = callback_data.get("result_index")
        
        # 验证回调数据合法性
        if action != "import_media" or result_index is None:
            await query.answer("❌ 无效的操作请求", show_alert=True)
            return
    except json.JSONDecodeError:
        await query.answer("❌ 数据解析失败，请重试", show_alert=True)
        return

    # 2. 读取上下文保存的searchId（与搜索结果关联）
    search_id = context.user_data.get("search_id", "")
    if not search_id:
        await query.answer("❌ 未找到历史搜索记录，请重新搜索", show_alert=True)
        return

    # 3. 按钮加载状态提示（避免用户重复点击）
    await query.answer("🔄 正在发起导入请求...", show_alert=False)  # 底部短暂提示
    # 编辑按钮为「加载中」状态（优化用户体验）
    try:
        loading_keyboard = [
            [InlineKeyboardButton(text="⏳ 导入中...", callback_data="empty")]  # empty避免重复触发
        ]
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(loading_keyboard)
        )
    except BadRequest:
        # 若消息已被编辑过，忽略异常（不影响核心逻辑）
        pass

    # 4. 执行导入逻辑（复用原direct_import的API调用代码）
    api_result = call_danmaku_api(
        method="POST",
        endpoint="/import/direct",
        json_data={
            "searchId": search_id,
            "result_index": result_index,
            "tmdbId": "",
            "tvdbId": "",
            "bangumiId": "",
            "imdbId": "",
            "doubanId": ""
        }
    )

    # 5. 处理导入结果（编辑按钮状态+发送结果通知）
    if api_result["success"]:
        data = api_result["data"]
        # 编辑按钮为「导入成功」（绿色提示）
        success_keyboard = [
            [InlineKeyboardButton(text="✅ 导入成功", callback_data="empty")]
        ]
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(success_keyboard)
        )
        # 发送详细结果通知（含任务ID）
        await query.message.reply_text(f"""
🎉 导入请求已提交成功！
• 任务ID：{data.get('taskId', '无')}
• 提示：可稍后用 /get_anime [作品ID] 查看详情
        """)
    else:
        # 编辑按钮为「导入失败」（红色提示）
        fail_keyboard = [
            [InlineKeyboardButton(text="❌ 导入失败", callback_data="empty")]
        ]
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(fail_keyboard)
        )
        # 发送失败原因（含错误信息）
        await query.message.reply_text(f"""
❌ 导入失败：{api_result['error']}
• 建议：若多次失败，可尝试重新搜索后导入
        """)


@check_user_permission
async def url_import(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """从URL导入媒体：支持直接带URL或后续输入"""
    if context.args:
        import_url = " ".join(context.args)
        await process_url_import(update, import_url)
        return

    # 无参数：引导输入URL
    await update.message.reply_text("请输入要导入的作品URL（如：https://example.com/anime/123）：")
    return INPUT_IMPORT_URL

async def input_import_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """接收用户输入的导入URL"""
    import_url = update.message.text.strip()
    if not import_url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ 无效的URL，请输入以http://或https://开头的链接：")
        return INPUT_IMPORT_URL

    await process_url_import(update, import_url)
    return ConversationHandler.END

async def process_url_import(update: Update, import_url: str):
    """处理URL导入的核心逻辑"""
    # 隐藏长URL的中间部分，避免消息过长
    display_url = import_url if len(import_url) <= 50 else f"{import_url[:30]}...{import_url[-20:]}"
    await update.message.reply_text(f"🔄 正在从URL导入：{display_url}...")

    # 调用API导入
    api_result = call_danmaku_api(
        method="POST",
        endpoint="/import/url",
        json_data={"url": import_url}
    )

    if api_result["success"]:
        data = api_result["data"]
        await update.message.reply_text(f"""
✅ URL导入请求已提交！
作品ID：{data.get('animeId', '无')}
任务ID：{data.get('taskId', '无')}
状态：{data.get('status', '处理中')}
        """)
    else:
        await update.message.reply_text(f"❌ URL导入失败：{api_result['error']}")

# ------------------------------
# 5. 媒体库管理指令（需授权）
# ------------------------------
@check_user_permission
async def list_library(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看媒体库所有作品"""
    await update.message.reply_text("📚 正在获取媒体库列表...")

    # 调用API获取列表
    api_result = call_danmaku_api(
        method="GET",
        endpoint="/library"
    )

    if not api_result["success"]:
        await update.message.reply_text(f"❌ 获取失败：{api_result['error']}")
        return

    library_data = api_result["data"]
    animes = library_data.get("animes", [])
    if not animes:
        await update.message.reply_text("📭 媒体库为空，可先使用导入指令添加作品")
        return

    # 格式化列表（最多显示10个，避免消息过长）
    result_msg = f"✅ 媒体库共 {len(animes)} 个作品（使用 /get_anime [ID] 查看详情）：\n"
    display_count = min(10, len(animes))
    
    for idx, anime in enumerate(animes[:display_count], 1):
        result_msg += f"""
{idx}. 名称：{anime.get('name', '未知名称')}
   ID：{anime.get('id', '无ID')}
   分集数：{len(anime.get('episodes', []))}
   更新时间：{anime.get('updatedAt', '未知')[:10]}
        """

    if len(animes) > 10:
        result_msg += f"\n... 还有 {len(animes)-10} 个作品未显示"
    
    await update.message.reply_text(result_msg)

@check_user_permission
async def get_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """获取单个作品详情"""
    if not context.args:
        await update.message.reply_text("❌ 请指定作品ID，格式：/get_anime [作品ID]（从/list_library获取）")
        return

    anime_id = context.args[0]
    await update.message.reply_text(f"🔍 正在获取作品ID「{anime_id}」的详情...")

    # 调用API获取详情
    api_result = call_danmaku_api(
        method="GET",
        endpoint=f"/library/anime/{anime_id}"
    )

    if not api_result["success"]:
        await update.message.reply_text(f"❌ 获取失败：{api_result['error']}")
        return

    anime_data = api_result["data"]
    # 格式化详情
    result_msg = f"""
✅ 作品详情：
名称：{anime_data.get('name', '未知名称')}
ID：{anime_data.get('id', '无ID')}
类型：{anime_data.get('type', '未知类型')}
状态：{anime_data.get('status', '未知状态')}
描述：{anime_data.get('description', '无描述')[:100]}...
更新时间：{anime_data.get('updatedAt', '未知')}

📺 分集列表（前5个）：
    """
    episodes = anime_data.get('episodes', [])
    for ep in episodes[:5]:
        result_msg += f"""
- 标题：{ep.get('title', '未知标题')}
  分集ID：{ep.get('id', '无ID')}
  时长：{ep.get('duration', '未知')}
  弹幕数：{ep.get('danmakuCount', 0)}
        """
    
    if len(episodes) > 5:
        result_msg += f"\n... 还有 {len(episodes)-5} 个分集未显示"
    
    await update.message.reply_text(result_msg)

@check_user_permission
async def get_sources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """获取作品的数据源"""
    if not context.args:
        await update.message.reply_text("❌ 请指定作品ID，格式：/get_sources [作品ID]")
        return

    anime_id = context.args[0]
    await update.message.reply_text(f"🔍 正在获取作品ID「{anime_id}」的数据源...")

    # 调用API获取数据源
    api_result = call_danmaku_api(
        method="GET",
        endpoint=f"/library/anime/{anime_id}/sources"
    )

    if not api_result["success"]:
        await update.message.reply_text(f"❌ 获取失败：{api_result['error']}")
        return

    sources_data = api_result["data"]
    sources = sources_data.get("sources", [])
    if not sources:
        await update.message.reply_text(f"❌ 作品ID「{anime_id}」没有数据源")
        return

    # 格式化数据源列表
    result_msg = f"✅ 作品ID「{anime_id}」的数据源（共{len(sources)}个）：\n"
    for idx, source in enumerate(sources, 1):
        result_msg += f"""
{idx}. 名称：{source.get('name', '未知名称')}
   类型：{source.get('type', '未知类型')}
   状态：{source.get('status', '未知状态')}
   URL：{source.get('url', '无URL')[:50]}...
        """
    
    await update.message.reply_text(result_msg)

# ------------------------------
# 6. 弹幕操作指令（需授权）
# ------------------------------
@check_user_permission
async def get_danmaku(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """获取某分集的弹幕"""
    if not context.args:
        await update.message.reply_text("❌ 请指定分集ID，格式：/get_danmaku [分集ID]（从/get_anime获取）")
        return

    episode_id = context.args[0]
    await update.message.reply_text(f"💬 正在获取分集ID「{episode_id}」的弹幕...")

    # 调用API获取弹幕
    api_result = call_danmaku_api(
        method="GET",
        endpoint=f"/danmaku/episode/{episode_id}"
    )

    if not api_result["success"]:
        await update.message.reply_text(f"❌ 获取失败：{api_result['error']}")
        return

    danmaku_data = api_result["data"]
    danmakus = danmaku_data.get("danmakus", [])
    if not danmakus:
        await update.message.reply_text(f"❌ 分集ID「{episode_id}」没有弹幕")
        return

    # 格式化弹幕（最多显示5条，避免消息过长）
    result_msg = f"✅ 分集ID「{episode_id}」的弹幕（共{len(danmakus)}条，前5条）：\n"
    for idx, dm in enumerate(danmakus[:5], 1):
        result_msg += f"""
{idx}. [时间：{dm.get('time', '00:00')}] {dm.get('text', '无内容')}
        """
    
    if len(danmakus) > 5:
        result_msg += f"\n... 还有 {len(danmakus)-5} 条弹幕未显示"
    
    await update.message.reply_text(result_msg)

@check_user_permission
async def refresh_danmaku(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """刷新某分集的弹幕"""
    if not context.args:
        await update.message.reply_text("❌ 请指定分集ID，格式：/refresh_danmaku [分集ID]")
        return

    episode_id = context.args[0]
    await update.message.reply_text(f"🔄 正在刷新分集ID「{episode_id}」的弹幕...")

    # 调用API刷新弹幕
    api_result = call_danmaku_api(
        method="POST",
        endpoint=f"/danmaku/episode/{episode_id}/refresh"
    )

    if api_result["success"]:
        data = api_result["data"]
        await update.message.reply_text(f"""
✅ 弹幕刷新请求已提交！
任务ID：{data.get('taskId', '无')}
状态：{data.get('status', '处理中')}
提示：稍后可用 /get_danmaku {episode_id} 查看更新后结果
        """)
    else:
        await update.message.reply_text(f"❌ 刷新失败：{api_result['error']}")

# ------------------------------
# 7. 高危操作指令（需授权+二次确认）
# ------------------------------
@check_user_permission
async def delete_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """删除整个作品（需二次确认）"""
    if not context.args:
        await update.message.reply_text("❌ 请指定作品ID，格式：/delete_anime [作品ID]（谨慎操作！）")
        return

    anime_id = context.args[0]
    # 存储ID到上下文，等待确认
    context.user_data["delete_anime_id"] = anime_id
    await update.message.reply_text(
        f"⚠️ 确认删除作品ID「{anime_id}」？此操作不可恢复！\n"
        f"请发送「确认删除{anime_id}」完成操作，其他消息将取消"
    )
    return CONFIRM_DELETE_ANIME

async def confirm_delete_anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理作品删除的二次确认"""
    anime_id = context.user_data.get("delete_anime_id")
    if not anime_id:
        await update.message.reply_text("❌ 未找到待删除的作品ID，请重新发起删除指令")
        return ConversationHandler.END

    # 验证确认消息
    user_input = update.message.text.strip()
    if user_input != f"确认删除{anime_id}":
        await update.message.reply_text("❌ 已取消删除操作")
        context.user_data.clear()
        return ConversationHandler.END

    # 执行删除
    await update.message.reply_text(f"🗑️ 正在删除作品ID「{anime_id}」...")
    api_result = call_danmaku_api(
        method="DELETE",
        endpoint=f"/library/anime/{anime_id}"
    )

    if api_result["success"]:
        await update.message.reply_text(f"✅ 作品ID「{anime_id}」已成功删除")
    else:
        await update.message.reply_text(f"❌ 删除失败：{api_result['error']}")

    context.user_data.clear()
    return ConversationHandler.END

@check_user_permission
async def delete_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """删除单个分集（需二次确认）"""
    if not context.args:
        await update.message.reply_text("❌ 请指定分集ID，格式：/delete_episode [分集ID]（谨慎操作！）")
        return

    episode_id = context.args[0]
    # 存储ID到上下文，等待确认
    context.user_data["delete_episode_id"] = episode_id
    await update.message.reply_text(
        f"⚠️ 确认删除分集ID「{episode_id}」？此操作不可恢复！\n"
        f"请发送「确认删除{episode_id}」完成操作，其他消息将取消"
    )
    return CONFIRM_DELETE_EPISODE

async def confirm_delete_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理分集删除的二次确认"""
    episode_id = context.user_data.get("delete_episode_id")
    if not episode_id:
        await update.message.reply_text("❌ 未找到待删除的分集ID，请重新发起删除指令")
        return ConversationHandler.END

    # 验证确认消息
    user_input = update.message.text.strip()
    if user_input != f"确认删除{episode_id}":
        await update.message.reply_text("❌ 已取消删除操作")
        context.user_data.clear()
        return ConversationHandler.END

    # 执行删除
    await update.message.reply_text(f"🗑️ 正在删除分集ID「{episode_id}」...")
    api_result = call_danmaku_api(
        method="DELETE",
        endpoint=f"/library/episode/{episode_id}"
    )

    if api_result["success"]:
        await update.message.reply_text(f"✅ 分集ID「{episode_id}」已成功删除")
    else:
        await update.message.reply_text(f"❌ 删除失败：{api_result['error']}")

    context.user_data.clear()
    return ConversationHandler.END

async def test_empty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """测试回调监听是否生效"""
    query = update.callback_query
    # 无论点击什么按钮，都返回提示（证明能收到事件）
    await query.answer("✅ 回调监听已生效！", show_alert=True)  # show_alert=True会弹出弹窗


# ------------------------------
# 8. 机器人启动入口
# ------------------------------
async def main():
    """创建机器人应用实例（不直接启动，返回实例供后续启动）"""
    # 确保导入 filters（对话处理器中的 MessageHandler 需要）
    from telegram.ext import filters
    # 创建应用实例
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # ------------------------------
    # 1. 第一步：先注册所有 ConversationHandler（对话处理器）
    # 原因：对话处理器仅处理「对话状态内的文本消息」，先注册避免拦截后续回调
    # ------------------------------
    # 搜索媒体对话
    search_handler = ConversationHandler(
        entry_points=[CommandHandler("search_media", search_media)],
        states={
            SEARCH_MEDIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_media_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(search_handler)

    # URL导入对话
    url_import_handler = ConversationHandler(
        entry_points=[CommandHandler("url_import", url_import)],
        states={
            INPUT_IMPORT_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_import_url)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(url_import_handler)

    # 删除动漫对话
    delete_anime_handler = ConversationHandler(
        entry_points=[CommandHandler("delete_anime", delete_anime)],
        states={
            CONFIRM_DELETE_ANIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete_anime)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(delete_anime_handler)

    # 删除剧集对话
    delete_episode_handler = ConversationHandler(
        entry_points=[CommandHandler("delete_episode", delete_episode)],
        states={
            CONFIRM_DELETE_EPISODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete_episode)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(delete_episode_handler)

    # ------------------------------
    # 2. 第二步：注册普通指令处理器
    # 原因：处理无状态指令（/start、/help 等），不影响回调
    # ------------------------------
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("list_library", list_library))
    application.add_handler(CommandHandler("get_anime", get_anime))
    application.add_handler(CommandHandler("get_sources", get_sources))
    application.add_handler(CommandHandler("get_danmaku", get_danmaku))
    application.add_handler(CommandHandler("refresh_danmaku", refresh_danmaku))

    # ------------------------------
    # 3. 第三步：最后注册 CallbackQueryHandler（导入回调）
    # 原因：确保回调事件不被前序的 ConversationHandler 或指令处理器拦截
    # ------------------------------
    application.add_handler(CallbackQueryHandler(
        handle_import_callback,
        pattern=r'{"action": "import_media".*}'  # 精准匹配导入按钮的回调
    ))

    # （可选：测试回调，若需要保留，也注册在最后）
    # application.add_handler(CallbackQueryHandler(
    #     callback=test_empty_callback,
    #     pattern=r'.*'
    # ))

    return application

# ------------------------------
# 新：显式管理事件循环，启动机器人（替代原 asyncio.run(main())）
# ------------------------------
if __name__ == "__main__":
    import asyncio
    from telegram.ext._application import Application  # 确保导入Application

    try:
        # 1. 获取当前事件循环（若不存在则创建）
        loop = asyncio.get_event_loop()
        # 2. 运行main()获取应用实例（同步等待异步函数结果）
        application: Application = loop.run_until_complete(main())
        logger.info("🚀 机器人应用初始化完成，开始监听指令...")
        
        # 3. 显式初始化应用（避免初始化时循环冲突）
        loop.run_until_complete(application.initialize())
        # 4. 启动轮询（指定allowed_updates，且不阻塞后续逻辑）
        loop.create_task(application.run_polling(allowed_updates=Update.ALL_TYPES))
        
        # 5. 保持循环运行（直到手动终止）
        loop.run_forever()

    except KeyboardInterrupt:
        # 捕获Ctrl+C，优雅关闭应用
        logger.info("\n🛑 收到终止信号，正在关闭机器人...")
        if 'application' in locals():
            loop.run_until_complete(application.shutdown())
        loop.close()
        logger.info("✅ 机器人已正常关闭")

    except Exception as e:
        # 捕获其他异常
        logger.error(f"❌ 机器人启动失败：{str(e)}", exc_info=True)
        if 'loop' in locals() and loop.is_running():
            loop.close()
