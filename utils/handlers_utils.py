# -*- coding: utf-8 -*-
import logging
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

def wrap_with_session_management(handler_func):
    """包装处理器函数"""
    async def wrapper(update, context):
        return await handler_func(update, context)
    return wrapper


def wrap_conversation_entry_point(handler_func):
    """包装对话入口点处理器，确保在执行新流程前终止当前对话并清理用户数据"""
    async def wrapper(update, context):
        # 清理用户数据，确保没有残留的对话状态
        if context.user_data:
            context.user_data.clear()
        
        # 执行原始处理器函数
        return await handler_func(update, context)
    return wrapper