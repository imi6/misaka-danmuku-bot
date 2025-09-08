import re
from typing import Any, Dict, Optional


def mask_sensitive_data(value: Any, sensitive_keys: Optional[list] = None) -> str:
    """
    对敏感数据进行脱敏处理，保留首尾各4位，中间用*代替
    
    Args:
        value: 需要脱敏的值
        sensitive_keys: 敏感字段列表，如果为None则使用默认列表
    
    Returns:
        脱敏后的字符串
    """
    if sensitive_keys is None:
        sensitive_keys = [
            'WEBHOOK_API_KEY',
            'TMDB_PROXY_URL', 
            'TMDB_API_KEY',
            'DANMAKU_API_KEY',
            'DANMAKU_API_BASE_URL',
            'TELEGRAM_BOT_TOKEN',
            'BGM_ACCESS_TOKEN',
            'TVDB_API_KEY'
        ]
    
    # 转换为字符串
    str_value = str(value)
    
    # 如果字符串长度小于等于8位，则全部用*代替（保护短密钥）
    if len(str_value) <= 8:
        return '*' * len(str_value)
    
    # 保留首尾各4位，中间用*代替
    return str_value[:4] + '*' * (len(str_value) - 8) + str_value[-4:]


def mask_sensitive_in_text(text: str, sensitive_keys: Optional[list] = None) -> str:
    """
    在文本中查找并脱敏敏感信息
    
    Args:
        text: 需要处理的文本
        sensitive_keys: 敏感字段列表，如果为None则使用默认列表
    
    Returns:
        脱敏后的文本
    """
    if sensitive_keys is None:
        sensitive_keys = [
            'WEBHOOK_API_KEY',
            'TMDB_PROXY_URL', 
            'TMDB_API_KEY',
            'DANMAKU_API_KEY',
            'DANMAKU_API_BASE_URL',
            'TELEGRAM_BOT_TOKEN',
            'BGM_ACCESS_TOKEN',
            'TVDB_API_KEY'
        ]
    
    # 匹配可能的敏感信息模式
    patterns = [
        # API密钥模式 (字母数字组合，长度8-64)
        r'\b[A-Za-z0-9]{8,64}\b',
        # URL模式
        r'https?://[^\s]+',
        # Token模式 (包含冒号的)
        r'\b\d+:[A-Za-z0-9_-]{35,}\b'
    ]
    
    result_text = text
    
    for pattern in patterns:
        matches = re.finditer(pattern, result_text)
        for match in reversed(list(matches)):  # 从后往前替换，避免位置偏移
            matched_text = match.group()
            # 只对长度大于8的匹配项进行脱敏
            if len(matched_text) > 8:
                masked_value = mask_sensitive_data(matched_text)
                result_text = result_text[:match.start()] + masked_value + result_text[match.end():]
    
    return result_text


def mask_dict_values(data: Dict[str, Any], sensitive_keys: Optional[list] = None) -> Dict[str, Any]:
    """
    对字典中的敏感字段值进行脱敏
    
    Args:
        data: 需要脱敏的字典
        sensitive_keys: 敏感字段列表，如果为None则使用默认列表
    
    Returns:
        脱敏后的字典副本
    """
    if sensitive_keys is None:
        sensitive_keys = [
            'WEBHOOK_API_KEY',
            'TMDB_PROXY_URL', 
            'TMDB_API_KEY',
            'DANMAKU_API_KEY',
            'DANMAKU_API_BASE_URL',
            'TELEGRAM_BOT_TOKEN',
            'BGM_ACCESS_TOKEN',
            'TVDB_API_KEY',
            'api_key',
            'token',
            'password',
            'secret'
        ]
    
    result = {}
    
    for key, value in data.items():
        # 检查键名是否包含敏感字段
        is_sensitive = any(sensitive_key.lower() in key.lower() for sensitive_key in sensitive_keys)
        
        if is_sensitive and isinstance(value, (str, int, float)):
            result[key] = mask_sensitive_data(value)
        elif isinstance(value, dict):
            result[key] = mask_dict_values(value, sensitive_keys)
        elif isinstance(value, list):
            result[key] = [mask_dict_values(item, sensitive_keys) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value
    
    return result