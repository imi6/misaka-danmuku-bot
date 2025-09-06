import re
from typing import Optional, Dict, Any

def parse_tmdb_url(url: str) -> Optional[Dict[str, Any]]:
    """解析 TMDB URL，提取媒体类型和 ID
    
    Args:
        url: TMDB URL，如 https://www.themoviedb.org/tv/292575-the-narcotic-operation
        
    Returns:
        Dict 包含 media_type 和 tmdb_id，如果解析失败返回 None
        
    Examples:
        parse_tmdb_url("https://www.themoviedb.org/tv/292575-the-narcotic-operation")
        # 返回: {"media_type": "tv_series", "tmdb_id": "292575"}
        
        parse_tmdb_url("https://www.themoviedb.org/movie/1109586")
        # 返回: {"media_type": "movie", "tmdb_id": "1109586"}
    """
    # TMDB URL 正则表达式
    tmdb_pattern = r'https?://(?:www\.)?themoviedb\.org/(tv|movie)/(\d+)(?:-[^/?]*)?(?:\?.*)?$'
    
    match = re.match(tmdb_pattern, url.strip())
    if not match:
        return None
    
    media_type_raw, tmdb_id = match.groups()
    
    # 转换媒体类型
    media_type = "tv_series" if media_type_raw == "tv" else "movie"
    
    return {
        "media_type": media_type,
        "tmdb_id": tmdb_id
    }

def is_tmdb_url(text: str) -> bool:
    """检查文本是否为 TMDB URL
    
    Args:
        text: 要检查的文本
        
    Returns:
        bool: 如果是 TMDB URL 返回 True，否则返回 False
    """
    return parse_tmdb_url(text) is not None

def parse_tvdb_url(url: str) -> Optional[Dict[str, Any]]:
    """解析 TVDB URL，提取媒体类型和 slug
    
    Args:
        url: TVDB URL，如 https://www.thetvdb.com/series/san-da-dui
        
    Returns:
        Dict 包含 media_type 和 slug，如果解析失败返回 None
        
    Examples:
        parse_tvdb_url("https://www.thetvdb.com/series/san-da-dui")
        # 返回: {"media_type": "tv_series", "slug": "san-da-dui"}
        
        parse_tvdb_url("https://www.thetvdb.com/movies/san-da-dui")
        # 返回: {"media_type": "movie", "slug": "san-da-dui"}
    """
    # TVDB URL 正则表达式
    tvdb_pattern = r'https?://(?:www\.)?thetvdb\.com/(series|movies)/([^/?]+)(?:\?.*)?$'
    
    match = re.match(tvdb_pattern, url.strip())
    if not match:
        return None
    
    media_type_raw, slug = match.groups()
    
    # 转换媒体类型
    media_type = "tv_series" if media_type_raw == "series" else "movie"
    
    return {
        "media_type": media_type,
        "slug": slug
    }

def is_tvdb_url(text: str) -> bool:
    """检查文本是否为 TVDB URL
    
    Args:
        text: 要检查的文本
        
    Returns:
        bool: 如果是 TVDB URL 返回 True，否则返回 False
    """
    return parse_tvdb_url(text) is not None

def is_tt_id(text: str) -> bool:
    """检查文本是否为 tt 开头的 ID 格式（如 tt525553）
    
    Args:
        text: 要检查的文本
        
    Returns:
        bool: 如果是 tt 开头的 ID 返回 True，否则返回 False
    """
    return bool(re.match(r'^tt\d+$', text.strip()))

def determine_input_type(text: str) -> Dict[str, Any]:
    """判断输入文本的类型并返回相应的处理信息
    
    Args:
        text: 用户输入的文本
        
    Returns:
        Dict 包含输入类型和相关信息
        
    Examples:
        determine_input_type("https://www.themoviedb.org/tv/292575")
        # 返回: {"type": "tmdb_url", "media_type": "tv_series", "tmdb_id": "292575"}
        
        determine_input_type("https://www.thetvdb.com/series/san-da-dui")
        # 返回: {"type": "tvdb_url", "media_type": "tv_series", "slug": "san-da-dui"}
        
        determine_input_type("tt525553")
        # 返回: {"type": "tt_id", "value": "tt525553"}
        
        determine_input_type("海贼王")
        # 返回: {"type": "keyword", "value": "海贼王"}
    """
    text = text.strip()
    
    # 检查是否为 TMDB URL
    tmdb_info = parse_tmdb_url(text)
    if tmdb_info:
        return {
            "type": "tmdb_url",
            "media_type": tmdb_info["media_type"],
            "tmdb_id": tmdb_info["tmdb_id"]
        }
    
    # 检查是否为 TVDB URL
    tvdb_info = parse_tvdb_url(text)
    if tvdb_info:
        return {
            "type": "tvdb_url",
            "media_type": tvdb_info["media_type"],
            "slug": tvdb_info["slug"]
        }
    
    # 检查是否为 tt 开头的 ID
    if is_tt_id(text):
        return {
            "type": "tt_id",
            "value": text
        }
    
    # 默认为关键词搜索
    return {
        "type": "keyword",
        "value": text
    }