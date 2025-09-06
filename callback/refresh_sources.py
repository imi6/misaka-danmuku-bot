import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.api import call_danmaku_api
from utils.permission import check_user_permission

logger = logging.getLogger(__name__)

@check_user_permission
async def handle_refresh_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理刷新相关的回调查询"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("refresh_episodes_page_"):
        page = int(data.split("_")[-1])
        await handle_episode_page_callback(update, context, page)
    else:
        await query.edit_message_text("未知的刷新选项")

async def handle_episode_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    """处理分集列表分页回调"""
    query = update.callback_query
    
    # 获取保存的分集数据
    episodes = context.user_data.get('refresh_episodes')
    if not episodes:
        await query.edit_message_text("❌ 分集数据丢失，请重新开始")
        return
    
    # 显示指定页的分集列表
    from handlers.refresh_sources import show_episode_list
    await show_episode_list(update, context, episodes, page)