# -*- coding: utf-8 -*-
from utils.handlers_utils import wrap_conversation_entry_point, wrap_with_session_management, wrap_command_switcher
from telegram.ext import CommandHandler


def get_search_handler():
    """获取搜索媒体命令处理器"""
    # 懒导入以避免循环依赖
    from handlers.import_media import search_command
    # 在fallback中使用wrap_command_switcher以正确切换会话
    return CommandHandler("search", wrap_command_switcher(search_command))


def get_auto_handler():
    """获取自动导入命令处理器"""
    from handlers.import_media import auto_command
    return CommandHandler("auto", wrap_command_switcher(auto_command))


def get_url_handler():
    """获取URL导入命令处理器"""
    from handlers.import_url import url_command
    return CommandHandler("url", wrap_command_switcher(url_command))


def get_refresh_handler():
    """获取刷新数据源命令处理器"""
    from handlers.refresh_sources import refresh_command
    return CommandHandler("refresh", wrap_command_switcher(refresh_command))


def get_tokens_handler():
    """获取API令牌管理命令处理器"""
    from handlers.token_management import tokens_command
    return CommandHandler("tokens", wrap_command_switcher(tokens_command))


def get_tasks_handler():
    """获取任务列表命令处理器"""
    from handlers.tasks import tasks_command
    return CommandHandler("tasks", wrap_command_switcher(tasks_command))


def get_users_handler():
    """获取用户管理命令处理器"""
    from handlers.user_management import users_command
    return CommandHandler("users", wrap_command_switcher(users_command))



def get_start_handler():
    """获取start命令处理器"""
    from handlers.general import start_command
    # start/help/cancel 仍然使用入口包装器即可
    return CommandHandler("start", wrap_conversation_entry_point(start_command))


def get_help_handler():
    """获取help命令处理器"""
    from handlers.general import help_command
    return CommandHandler("help", wrap_conversation_entry_point(help_command))


def get_cancel_handler():
    """获取cancel命令处理器"""
    from handlers.general import cancel_command
    return CommandHandler("cancel", wrap_conversation_entry_point(cancel_command))


def get_global_fallbacks():
    """返回全局共享的fallbacks处理器组，确保命令切换时正确终止当前对话"""
    # 首先添加cancel处理器，确保它始终是第一个fallback
    fallbacks = [get_cancel_handler()]
    
    # 添加其他主要命令处理器作为fallbacks，确保用户在切换命令时能正确终止前一个会话
    # 特别注意：url_handler应该放在search_handler之前，这样URL链接输入会被正确路由到url处理逻辑
    fallbacks.extend([
        get_url_handler(),
        get_search_handler(),
        get_auto_handler(),
        get_refresh_handler(),
        get_tokens_handler(),
        get_tasks_handler(),
        get_users_handler(),
        get_start_handler(),
        get_help_handler()
    ])
    
    return fallbacks


def get_minimal_fallbacks():
    """返回最小化的fallbacks处理器组（只包含cancel命令）"""
    return [
        get_cancel_handler(),
    ]