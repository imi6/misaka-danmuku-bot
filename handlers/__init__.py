# 导入所有处理器模块
from .general import start_command, help_command, cancel_command
from .import_media import (
    create_search_handler,
    create_import_auto_handler,
    create_episode_input_handler
)

# 导入用户管理处理器
from .user_management import create_user_management_handler

# 导入任务管理处理器
from .tasks import create_tasks_handler

# 导入webhook处理器
from .webhook import WebhookHandler

def get_user_handler():
    """获取用户管理处理器"""
    return create_user_management_handler()

# blacklist handler removed

def get_task_handler():
    """获取任务管理处理器"""
    return create_tasks_handler()

# 导出所有处理器创建函数
__all__ = [
    # 基础命令
    'start_command',
    'help_command', 
    'cancel_command',
    
    # 导入媒体处理器
    'create_search_handler',
    'create_import_auto_handler',
    'create_episode_input_handler',
    
    # 管理功能处理器
    'create_user_management_handler',
    'create_tasks_handler',
    
    # Webhook处理器
    'WebhookHandler',
    
    # 便捷获取函数
    'get_user_handler',
    'get_task_handler',
]