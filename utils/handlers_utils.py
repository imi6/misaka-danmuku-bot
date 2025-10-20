# -*- coding: utf-8 -*-
import logging
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)


def wrap_with_session_management(handler_func):
    """包装处理器函数"""
    async def wrapper(update, context):
        return await handler_func(update, context)
    return wrapper


def wrap_conversation_entry_point(handler_func):
    """包装对话入口点处理器，确保在执行新流程前终止当前对话并清理用户数据"""
    async def wrapper(update, context):
        # 记录新命令的开始
        command_name = getattr(handler_func, '__name__', str(handler_func))
        logger.info(f"用户启动新命令: {command_name}")
        
        # 完全清理用户数据，完全模拟cancel的行为
        context.user_data.clear()
        
        # 执行原始处理器函数
        try:
            # 执行原始处理器函数并返回其结果
            # 这确保了新对话能够正确启动并管理状态
            result = await handler_func(update, context)
            return result
        except Exception as e:
            logger.error(f"执行命令时发生错误: {e}")
            # 如果发生错误，仍然确保返回有效的状态
            return ConversationHandler.END
            
    return wrapper


def wrap_command_switcher(handler_func):
    """用于fallback场景的命令切换包装器：结束当前对话并重新分派该更新。
    目的：在其他会话的fallback中接收到主命令（如 /url、/search 等）时，
    结束当前会话并让全局分发器重新把同一更新交给对应会话的entry_points处理，
    从而正确启动新的ConversationHandler。
    """
    async def wrapper(update: ContextTypes.DEFAULT_TYPE, context: ContextTypes.DEFAULT_TYPE):
        command_name = getattr(handler_func, '__name__', str(handler_func))
        logger.info(f"🔁 会话切换：{command_name} — 结束当前对话并重新分派更新")
        
        # 清理当前会话的用户数据
        try:
            context.user_data.clear()
        except Exception as e:
            logger.warning(f"清理用户数据失败: {e}")
        
        # 尝试重新分派当前更新，让对应命令的ConversationHandler接管
        try:
            # 注意：重新分派需要在当前处理返回后才能真正接管，因此使用异步任务调度
            # 目标：让 /url 等命令由其所在的 ConversationHandler 的 entry_points 处理
            context.application.create_task(context.application.process_update(update))
        except Exception as re_dispatch_error:
            logger.error(f"重新分派更新失败：{re_dispatch_error}，尝试直接调用命令函数作为降级")
            try:
                await handler_func(update, context)
            except Exception as direct_call_error:
                logger.error(f"直接调用命令函数失败：{direct_call_error}")
        
        # 返回END以结束当前会话
        return ConversationHandler.END
    
    return wrapper