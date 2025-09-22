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

def parse_douban_url(url: str) -> Optional[Dict[str, Any]]:
    """解析豆瓣 URL，提取 ID
    
    Args:
        url: 豆瓣 URL，如 https://movie.douban.com/subject/1234567/
        
    Returns:
        Dict 包含 douban_id，如果解析失败返回 None
        
    Examples:
        parse_douban_url("https://movie.douban.com/subject/1234567/")
        # 返回: {"douban_id": "1234567"}
        
        parse_douban_url("https://m.douban.com/movie/subject/1234567/")
        # 返回: {"douban_id": "1234567"}
    """
    # 豆瓣 URL 正则表达式，支持桌面版和移动版
    douban_pattern = r'https?://(?:(?:movie|m)\.)?douban\.com/(?:movie/)?subject/(\d+)/?(?:\?.*)?$'
    
    match = re.match(douban_pattern, url.strip())
    if not match:
        return None
    
    douban_id = match.group(1)
    
    return {
        "douban_id": douban_id
    }

def is_douban_url(text: str) -> bool:
    """检查文本是否为豆瓣 URL
    
    Args:
        text: 要检查的文本
        
    Returns:
        bool: 如果是豆瓣 URL 返回 True，否则返回 False
    """
    return parse_douban_url(text) is not None

def parse_imdb_url(url: str) -> Optional[Dict[str, Any]]:
    """解析 IMDB URL 并提取 IMDB ID 和媒体类型
    
    Args:
        url: IMDB URL 字符串
        
    Returns:
        dict: 包含 imdb_id 和可能的 media_type 的字典，如果解析失败返回 None
        
    Examples:
        parse_imdb_url("https://www.imdb.com/title/tt1234567/")
        # 返回: {"imdb_id": "tt1234567"}
        
        parse_imdb_url("https://m.imdb.com/title/tt1234567/?ref_=fn_all_ttl_1")
        # 返回: {"imdb_id": "tt1234567", "media_type": "movie"}
        
        parse_imdb_url("https://www.imdb.com/title/tt1234567/?ref_=fn_all_tv_1")
        # 返回: {"imdb_id": "tt1234567", "media_type": "tv"}
    """
    # IMDB URL 正则表达式，支持桌面版和移动版，捕获查询参数
    imdb_pattern = r'https?://(?:(?:www|m)\.)?imdb\.com/title/(tt\d+)/?(?:\?(.*))?$'
    
    match = re.match(imdb_pattern, url.strip())
    if not match:
        return None
    
    imdb_id = match.group(1)
    query_params = match.group(2) if match.group(2) else ""
    
    result = {"imdb_id": imdb_id, "original_url": url.strip()}
    
    # 从ref参数推断媒体类型
    # 严格规则：只有fn_all_ttl_1=电视剧，fn_all_ttl_2=电影，其他任何ref都走爬虫
    if "ref_=" in query_params:
        if "fn_all_ttl_1" in query_params:  # 电视剧
            result["media_type"] = "tv"
        elif "fn_all_ttl_2" in query_params:  # 电影
            result["media_type"] = "movie"
        # 其他任何ref参数都不设置media_type，让系统走爬虫流程
    
    return result

def is_imdb_url(text: str) -> bool:
    """检查文本是否为 IMDB URL
    
    Args:
        text: 要检查的文本
        
    Returns:
        bool: 如果是 IMDB URL 返回 True，否则返回 False
    """
    return parse_imdb_url(text) is not None

def parse_bgm_url(url: str) -> Optional[Dict[str, Any]]:
    """解析 BGM (Bangumi) URL，提取 subject ID
    
    Args:
        url: BGM URL，如 https://bgm.tv/subject/453888
        
    Returns:
        Dict 包含 bgm_id，如果解析失败返回 None
        
    Examples:
        parse_bgm_url("https://bgm.tv/subject/453888")
        # 返回: {"bgm_id": "453888"}
        
        parse_bgm_url("https://bangumi.tv/subject/38124")
        # 返回: {"bgm_id": "38124"}
    """
    # BGM URL 正则表达式，支持 bgm.tv 和 bangumi.tv 域名
    bgm_pattern = r'https?://(?:(?:www\.)?(?:bgm|bangumi)\.tv)/subject/(\d+)/?(?:\?.*)?$'
    
    match = re.match(bgm_pattern, url.strip())
    if not match:
        return None
    
    bgm_id = match.group(1)
    
    return {
        "bgm_id": bgm_id
    }

def is_bgm_url(text: str) -> bool:
    """检查文本是否为 BGM URL
    
    Args:
        text: 要检查的文本
        
    Returns:
        bool: 如果是 BGM URL 返回 True，否则返回 False
    """
    return parse_bgm_url(text) is not None

def is_tt_id(text: str) -> bool:
    """检查文本是否为 IMDB ID 格式（tt开头或纯数字）
    
    Args:
        text: 要检查的文本
        
    Returns:
        bool: 如果是 IMDB ID 格式返回 True，否则返回 False
        
    Examples:
        is_tt_id("tt1234567")  # True - tt开头格式
        is_tt_id("1234567")    # True - 纯数字格式
        is_tt_id("abc123")     # False - 无效格式
    """
    text = text.strip()
    # 检查tt开头的格式
    if re.match(r'^tt\d+$', text):
        return True

    return False

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
        
        determine_input_type("https://movie.douban.com/subject/1234567/")
        # 返回: {"type": "douban_url", "douban_id": "1234567"}
        
        determine_input_type("https://www.imdb.com/title/tt1234567/")
        # 返回: {"type": "imdb_url", "imdb_id": "tt1234567"}
        
        determine_input_type("https://bgm.tv/subject/453888")
        # 返回: {"type": "bgm_url", "bgm_id": "453888"}
        
        determine_input_type("tt525553")
        # 返回: {"type": "tt_id", "value": "tt525553"}
        
        determine_input_type("海贼王")
        # 返回: {"type": "keyword", "value": "海贼王"}
    """
    text = text.strip()
    
    # 去除可能的反引号包围（Telegram消息中的代码格式）
    if text.startswith('`') and text.endswith('`'):
        text = text[1:-1].strip()
    
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
    
    # 检查是否为豆瓣 URL
    douban_info = parse_douban_url(text)
    if douban_info:
        return {
            "type": "douban_url",
            "douban_id": douban_info["douban_id"]
        }
    
    # 检查是否为 IMDB URL
    imdb_info = parse_imdb_url(text)
    if imdb_info:
        result = {
            "type": "imdb_url",
            "imdb_id": imdb_info["imdb_id"]
        }
        # 如果解析出了媒体类型，也包含进去
        if "media_type" in imdb_info:
            result["media_type"] = imdb_info["media_type"]
        # 如果有原始URL，也包含进去
        if "original_url" in imdb_info:
            result["original_url"] = imdb_info["original_url"]
        return result
    
    # 检查是否为 BGM URL
    bgm_info = parse_bgm_url(text)
    if bgm_info:
        return {
            "type": "bgm_url",
            "bgm_id": bgm_info["bgm_id"]
        }
    
    # 检查是否为 IMDB ID（tt开头或纯数字）
    if is_tt_id(text):
        # 如果是纯数字，转换为tt格式
        if text.isdigit():
            imdb_id = f"tt{text}"
        else:
            imdb_id = text
        return {
            "type": "imdb_url",
            "imdb_id": imdb_id
        }
    
    # 默认为关键词搜索
    return {
        "type": "keyword",
        "value": text
    }