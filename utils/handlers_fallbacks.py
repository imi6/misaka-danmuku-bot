# -*- coding: utf-8 -*-
from utils.handlers_utils import wrap_conversation_entry_point, wrap_with_session_management
from telegram.ext import CommandHandler


def get_search_handler():
    """获取搜索媒体命令处理器"""
    # 懒导入以避免循环依赖
    from handlers.import_media import search_media
    return CommandHandler("search", wrap_conversation_entry_point(search_media))


def get_auto_handler():
    """获取自动导入命令处理器"""
    from handlers.import_media import import_auto
    return CommandHandler("auto", wrap_conversation_entry_point(import_auto))


def get_url_handler():
    """获取URL导入命令处理器"""
    from handlers.import_url import import_url_start
    return CommandHandler("url", wrap_conversation_entry_point(import_url_start))


def get_refresh_handler():
    """获取刷新数据源命令处理器"""
    from handlers.refresh_sources import refresh_command
    return CommandHandler("refresh", wrap_with_session_management(refresh_command))


def get_tokens_handler():
    """获取API令牌管理命令处理器"""
    from handlers.token_management import show_tokens_list
    return CommandHandler("tokens", wrap_conversation_entry_point(show_tokens_list))


def get_tasks_handler():
    """获取任务列表命令处理器"""
    from handlers.tasks import tasks_command
    return CommandHandler("tasks", wrap_with_session_management(tasks_command))


def get_users_handler():
    """获取用户管理处理器
    
    Returns:
        ConversationHandler: 用户管理对话处理器
    """
    from handlers.user_management import create_user_management_handler
    return create_user_management_handler()


def get_identify_handler():
    """获取识别词映射管理命令处理器"""
    from handlers.identify_management import identify_command
    return CommandHandler("identify", wrap_conversation_entry_point(identify_command))


def get_blacklist_handler():
    """获取黑名单管理命令处理器"""
    from handlers.blacklist_management import blacklist_command
    return CommandHandler("blacklist", wrap_conversation_entry_point(blacklist_command))


def get_start_handler():
    """获取start命令处理器"""
    from handlers.general import start
    return CommandHandler("start", wrap_with_session_management(start))


def get_help_handler():
    """获取help命令处理器"""
    from handlers.general import help_command
    return CommandHandler("help", wrap_with_session_management(help_command))


def get_cancel_handler():
    """获取cancel命令处理器"""
    from handlers.general import cancel
    return CommandHandler("cancel", wrap_with_session_management(cancel))


def get_global_fallbacks():
    """返回全局共享的fallbacks处理器组"""
    return [
        get_cancel_handler(),
        get_search_handler(),
        get_auto_handler(),
        # get_url_handler(),
        # get_refresh_handler(),
        # get_tokens_handler(),
        # get_tasks_handler(),
        # get_users_handler(),
        # get_identify_handler(),
        # get_blacklist_handler(),
        get_start_handler(),
        get_help_handler(),
    ]


def get_minimal_fallbacks():
    """返回最小化的fallbacks处理器组（只包含cancel命令）"""
    return [
        get_cancel_handler(),
    ]