import logging
from functools import wraps
from typing import Callable, Any
from telegram import Update
from telegram.ext import ContextTypes
from config import ConfigManager

# 初始化日志
logger = logging.getLogger(__name__)

def check_user_permission(func: Callable) -> Callable:
    """装饰器：验证用户是否在白名单中，未授权则拒绝执行"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs) -> Any:
        # 获取配置管理器实例
        config_manager = ConfigManager()
        
        # 获取当前用户信息
        user = update.effective_user
        if not user:
            logger.warning("❌ 无法获取用户信息，拒绝请求")
            await update.message.reply_text("❌ 无法验证身份，请稍后重试")
            return

        user_id = user.id
        username = user.username or "未知用户名"

        # 验证白名单
        if user_id not in config_manager.telegram.allowed_user_ids:
            logger.warning(f"⚠️ 未授权访问：用户ID={user_id}，用户名={username}")
            await update.message.reply_text("❌ 你没有使用该机器人的权限，请联系管理员")
            return

        # 有权限：记录日志并执行原指令
        logger.info(f"✅ 授权访问：用户ID={user_id}，用户名={username}，指令={func.__name__}")
        return await func(update, context, *args, **kwargs)
    return wrapper