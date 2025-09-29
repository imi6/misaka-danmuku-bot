import logging
import re
from typing import Optional, Dict, Any
from utils.api import call_danmaku_api

logger = logging.getLogger(__name__)

def get_webhook_filter_config() -> Dict[str, Any]:
    """
    通过API获取webhook过滤配置
    
    Returns:
        包含webhookFilterMode和webhookFilterRegex的配置字典
    """
    try:
        # 调用/config接口获取配置
        response = call_danmaku_api(
            method="GET",
            endpoint="/config"
        )
        
        if not response.get("success"):
            logger.error(f"❌ API调用失败: {response.get('error', '未知错误')}")
            return {"mode": "blacklist", "regex": ""}
            
        data = response.get("data", {})
        configs = data.get("configs", [])
        
        # 提取webhook过滤配置
        filter_mode = "blacklist"  # 默认值
        filter_regex = ""  # 默认值
        
        for config in configs:
            key = config.get("key")
            value = config.get("value", "")
            
            if key == "webhookFilterMode":
                filter_mode = value
            elif key == "webhookFilterRegex":
                filter_regex = value
        
        logger.debug(f"🔍 获取到webhook过滤配置: mode={filter_mode}, regex={filter_regex}")
        
        return {
            "mode": filter_mode,
            "regex": filter_regex
        }
        
    except Exception as e:
        logger.error(f"❌ 获取webhook过滤配置异常: {e}")
        return {"mode": "blacklist", "regex": ""}

def should_filter_webhook_title(title: str, series_name: Optional[str] = None) -> bool:
    """
    根据API配置判断是否应该过滤webhook标题
    
    Args:
        title: 媒体标题
        series_name: 系列名称（可选）
        
    Returns:
        True表示应该过滤（阻止处理），False表示允许处理
    """
    if not title and not series_name:
        return False
    
    # 获取过滤配置
    config = get_webhook_filter_config()
    filter_mode = config.get("mode", "blacklist")
    filter_regex = config.get("regex", "")
    
    # 如果是whitelist模式，忽略regex配置
    if filter_mode == "whitelist":
        logger.debug("🔍 Webhook过滤模式为whitelist，忽略regex配置，允许所有内容")
        return False
    
    # 如果没有配置正则表达式，不进行过滤
    if not filter_regex.strip():
        logger.debug("🔍 未配置webhook过滤正则表达式，允许所有内容")
        return False
    
    # blacklist模式：匹配正则表达式的内容将被过滤
    try:
        # 编译正则表达式
        pattern = re.compile(filter_regex, re.IGNORECASE)
        
        # 检查标题
        if title and pattern.search(title):
            logger.info(f"🚫 标题 '{title}' 匹配黑名单正则表达式，将被过滤")
            return True
            
        # 检查系列名称
        if series_name and pattern.search(series_name):
            logger.info(f"🚫 系列名称 '{series_name}' 匹配黑名单正则表达式，将被过滤")
            return True
            
        logger.debug(f"✅ 标题 '{title}' 和系列名称 '{series_name}' 未匹配黑名单正则表达式，允许处理")
        return False
        
    except re.error as e:
        logger.error(f"❌ 正则表达式编译失败: {filter_regex}, 错误: {e}")
        # 正则表达式错误时，不进行过滤
        return False