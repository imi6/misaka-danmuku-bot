import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes, ConversationHandler
from utils.api import call_danmaku_api
from utils.permission import check_user_permission

# 初始化日志
logger = logging.getLogger(__name__)
# 对话状态（仅保留搜索相关）
SEARCH_MEDIA = 0
EPISODES_PER_PAGE = 10  # 每页显示分集数量
INPUT_EPISODE_RANGE = 1  # 集数输入对话状态
CALLBACK_DATA_MAX_LEN = 60 


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
        logger.info(f"🔘 生成导入按钮回调数据：{callback_data_import}")
        
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
    