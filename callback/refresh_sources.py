import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.api import call_danmaku_api
from utils.permission import check_user_permission

logger = logging.getLogger(__name__)

@check_user_permission
async def handle_refresh_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理刷新相关的回调查询"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("refresh_episodes_page_"):
        page = int(data.split("_")[-1])
        return await handle_episode_page_callback(update, context, page)
    elif data.startswith("refresh_select_anime_"):
        anime_index = int(data.split("_")[-1])
        return await handle_anime_selection_callback(update, context, anime_index)
    elif data.startswith("refresh_library_page_"):
        page = int(data.split("_")[-1])
        return await handle_library_page_callback(update, context, page)
    elif data == "refresh_cancel":
        return await handle_cancel_callback(update, context)
    else:
        await query.edit_message_text("未知的刷新选项")
        from telegram.ext import ConversationHandler
        return ConversationHandler.END

async def handle_episode_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    """处理分集列表分页回调"""
    query = update.callback_query
    
    # 获取保存的分集数据
    episodes = context.user_data.get('refresh_episodes')
    if not episodes:
        await query.edit_message_text("❌ 分集数据丢失，请重新开始")
        from telegram.ext import ConversationHandler
        return ConversationHandler.END
    
    # 显示指定页的分集列表
    from handlers.refresh_sources import show_episode_list
    return await show_episode_list(update, context, episodes, page)

async def handle_anime_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, anime_index: int):
    """处理从弹幕库选择动漫的回调"""
    query = update.callback_query
    
    # 显示加载状态
    await query.edit_message_text("🔄 正在获取最新数据...")
    
    try:
        # 重新调用/library接口获取最新库数据
        response = call_danmaku_api('GET', '/library')
        if not response or 'data' not in response:
            await query.edit_message_text("❌ 获取弹幕库数据失败，请稍后重试")
            from telegram.ext import ConversationHandler
            return ConversationHandler.END
        
        library_data = response['data']
        if not library_data or anime_index >= len(library_data):
            await query.edit_message_text("❌ 数据索引无效或库为空，请重新开始")
            from telegram.ext import ConversationHandler
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"获取库数据失败: {e}")
        await query.edit_message_text("❌ 获取弹幕库数据失败，请稍后重试")
        from telegram.ext import ConversationHandler
        return ConversationHandler.END
    
    # 获取选中的动漫
    selected_anime = library_data[anime_index]
    context.user_data['refresh_selected_anime'] = selected_anime
    
    # 进入源选择流程
    from handlers.refresh_sources import show_refresh_sources
    return await show_refresh_sources(update, context, selected_anime)

async def handle_library_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int):
    """处理弹幕库列表分页回调"""
    # 直接显示指定页，无需重新加载数据
    from handlers.refresh_sources import show_library_selection
    return await show_library_selection(update, context, page)

async def handle_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """处理取消操作的回调"""
    query = update.callback_query
    
    # 清理用户数据
    keys_to_remove = [
        'refresh_keyword', 'refresh_anime_matches', 'refresh_selected_anime',
        'refresh_selected_source', 'refresh_episodes', 'refresh_episode_ids'
    ]
    for key in keys_to_remove:
        context.user_data.pop(key, None)
    
    await query.edit_message_text("❌ 刷新操作已取消")
    from telegram.ext import ConversationHandler
    return ConversationHandler.END