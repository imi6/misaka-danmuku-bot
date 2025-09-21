# -*- coding: utf-8 -*-
import logging
from telegram import ReplyKeyboardRemove
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
        
        # 在控制台记录状态重置信息
        if hasattr(update, 'effective_chat') and update.effective_chat:
            chat_id = update.effective_chat.id
            user_id = update.effective_user.id
            logger.debug(f"[对话重置] 用户 {user_id} 在群组 {chat_id} 从任何活跃状态切换到新命令: {command_name}")
        
        # 执行原始处理器函数
        try:
            # 关键修改：我们不直接返回result，而是先返回ConversationHandler.END来终止当前对话
            # 这样做是为了完全模仿/cancel的效果
            result = await handler_func(update, context)
            
            # 记录命令执行结果
            if result != ConversationHandler.END:
                logger.debug(f"命令执行成功，内部状态: {result}")
            else:
                logger.debug(f"命令执行完成，对话已结束")
            
            # 返回ConversationHandler.END以确保当前对话被正确终止
            # 新的对话会通过Telegram的正常流程自动启动
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"执行命令时发生错误: {e}")
            # 如果发生错误，仍然确保返回有效的状态
            return ConversationHandler.END
    return wrapper