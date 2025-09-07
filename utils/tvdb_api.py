import requests
import logging
import os
import urllib3
from typing import Optional, Dict, Any, List
from config import TVDB_API_KEY, TVDB_BASE_URL, TVDB_ENABLED

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

class TVDBAPIError(Exception):
    """TVDB API 错误"""
    pass

class TVDBAPI:
    """TVDB API 客户端"""
    
    def __init__(self):
        self.api_key = TVDB_API_KEY
        self.base_url = TVDB_BASE_URL
        self.token = None
        
    def _get_auth_token(self) -> str:
        """获取认证令牌"""
        if not self.api_key:
            raise TVDBAPIError("TVDB API密钥未配置")
            
        if self.token:
            return self.token
            
        try:
            url = f"{self.base_url}/login"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; MisakaBot/1.0)"
            }
            data = {
                "apikey": self.api_key
            }
            
            # 配置请求参数，处理SSL和代理问题
            request_kwargs = {
                'json': data,
                'headers': headers,
                'timeout': 30,
                'verify': False  # 禁用SSL验证以避免SSL错误
            }
            
            # 如果有代理配置，使用代理
            proxies = {}
            if os.getenv('HTTP_PROXY'):
                proxies['http'] = os.getenv('HTTP_PROXY')
            if os.getenv('HTTPS_PROXY'):
                proxies['https'] = os.getenv('HTTPS_PROXY')
            if proxies:
                request_kwargs['proxies'] = proxies
                
            response = requests.post(url, **request_kwargs)
            response.raise_for_status()
            
            result = response.json()
            if result.get("status") == "success":
                self.token = result["data"]["token"]
                return self.token
            else:
                raise TVDBAPIError(f"获取认证令牌失败: {result.get('message', '未知错误')}")
                
        except requests.RequestException as e:
            logger.error(f"TVDB API认证请求失败: {e}")
            raise TVDBAPIError(f"TVDB API认证请求失败: {e}")
        except Exception as e:
            logger.error(f"TVDB API认证时发生错误: {e}")
            raise TVDBAPIError(f"TVDB API认证时发生错误: {e}")
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """发起API请求"""
        token = self._get_auth_token()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; MisakaBot/1.0)"
        }
        
        try:
            # 配置请求参数，处理SSL和代理问题
            request_kwargs = {
                'headers': headers,
                'params': params,
                'timeout': 30,
                'verify': False  # 禁用SSL验证以避免SSL错误
            }
            
            # 如果有代理配置，使用代理
            proxies = {}
            if os.getenv('HTTP_PROXY'):
                proxies['http'] = os.getenv('HTTP_PROXY')
            if os.getenv('HTTPS_PROXY'):
                proxies['https'] = os.getenv('HTTPS_PROXY')
            if proxies:
                request_kwargs['proxies'] = proxies
                
            response = requests.get(url, **request_kwargs)
            response.raise_for_status()
            
            result = response.json()
            if result.get("status") == "success":
                return result["data"]
            else:
                raise TVDBAPIError(f"API请求失败: {result.get('message', '未知错误')}")
                
        except requests.RequestException as e:
            logger.error(f"TVDB API请求失败: {e}")
            raise TVDBAPIError(f"TVDB API请求失败: {e}")
        except Exception as e:
            logger.error(f"TVDB API请求时发生错误: {e}")
            raise TVDBAPIError(f"TVDB API请求时发生错误: {e}")
    
    def get_tv_seasons(self, tvdb_id: str) -> Optional[List[Dict[str, Any]]]:
        """获取TVDB电视剧的季度信息
        
        Args:
            tvdb_id: TVDB电视剧ID
            
        Returns:
            季度信息列表，每个季度包含season_number、name、episode_count等信息
            如果获取失败返回None
        """
        try:
            # 获取电视剧的基本信息，包含季度数据
            endpoint = f"series/{tvdb_id}/extended"
            data = self._make_request(endpoint)
            
            if not data:
                logger.info(f"未找到TVDB ID '{tvdb_id}' 对应的电视剧信息")
                return None
            
            seasons = data.get('seasons', [])
            
            # 过滤和格式化季度信息
            valid_seasons = []
            for season in seasons:
                season_number = season.get('number', 0)
                season_name = season.get('name', '').lower()
                
                # 过滤掉特殊季度：
                # 1. season_number <= 0 (通常Specials是0)
                # 2. name包含"special"、"specials"等关键词
                if (season_number > 0 and 
                    'special' not in season_name and 
                    'extras' not in season_name and
                    'bonus' not in season_name):
                    
                    valid_seasons.append({
                        'season_number': season_number,
                        'name': season.get('name', f'Season {season_number}'),
                        'episode_count': len(season.get('episodes', [])),
                        'air_date': season.get('year', ''),
                        'overview': season.get('overview', '')
                    })
            
            # 按季度号排序
            valid_seasons.sort(key=lambda x: x['season_number'])
            
            logger.info(f"✅ TVDB电视剧季度信息获取成功，共{len(valid_seasons)}季")
            return valid_seasons
            
        except TVDBAPIError:
            raise
        except Exception as e:
            logger.error(f"获取TVDB季度信息时发生错误: {e}")
            raise TVDBAPIError(f"获取TVDB季度信息时发生错误: {e}")
    
    def search_by_slug(self, slug: str, media_type: str) -> Optional[Dict[str, Any]]:
        """通过slug搜索获取TVDB ID
        
        Args:
            slug: URL中的slug部分，如 'san-da-dui'
            media_type: 媒体类型，'movie' 或 'tv_series'
            
        Returns:
            包含TVDB ID和相关信息的字典，如果未找到返回None
        """
        try:
            # 使用搜索API查找匹配的内容
            params = {
                "q": slug.replace("-", " "),  # 将连字符替换为空格进行搜索
                "type": "series" if media_type == "tv_series" else "movie"
            }
            
            results = self._make_request("search", params)
            
            if not results:
                logger.info(f"未找到slug '{slug}' 对应的{media_type}")
                return None
            
            # 查找最匹配的结果
            for item in results:
                # 检查slug是否匹配
                item_slug = item.get("slug", "")
                if item_slug == slug:
                    return {
                        "tvdb_id": str(item.get("id", "")),
                        "name": item.get("name", ""),
                        "slug": item_slug,
                        "media_type": media_type,
                        "year": item.get("year", ""),
                        "overview": item.get("overview", "")
                    }
            
            # 如果没有完全匹配的slug，返回第一个结果
            first_result = results[0]
            logger.info(f"未找到完全匹配的slug，返回最相似的结果: {first_result.get('name')}")
            
            return {
                "tvdb_id": str(first_result.get("id", "")),
                "name": first_result.get("name", ""),
                "slug": first_result.get("slug", ""),
                "media_type": media_type,
                "year": first_result.get("year", ""),
                "overview": first_result.get("overview", "")
            }
            
        except TVDBAPIError:
            raise
        except Exception as e:
            logger.error(f"搜索TVDB内容时发生错误: {e}")
            raise TVDBAPIError(f"搜索TVDB内容时发生错误: {e}")

# 全局API实例
_tvdb_api = None

def get_tvdb_api() -> TVDBAPI:
    """获取TVDB API实例"""
    global _tvdb_api
    if _tvdb_api is None:
        _tvdb_api = TVDBAPI()
    return _tvdb_api

async def search_tvdb_by_slug(slug: str, media_type: str) -> Optional[Dict[str, Any]]:
    """通过slug搜索TVDB内容
    
    Args:
        slug: URL中的slug部分
        media_type: 媒体类型，'movie' 或 'tv_series'
        
    Returns:
        包含TVDB信息的字典，如果未找到或API未启用返回None
    """
    if not TVDB_ENABLED:
        logger.info("TVDB API未启用，跳过搜索")
        return None
        
    try:
        api = get_tvdb_api()
        return api.search_by_slug(slug, media_type)
    except TVDBAPIError as e:
        logger.error(f"TVDB搜索失败: {e}")
        return None
    except Exception as e:
        logger.error(f"TVDB搜索时发生未知错误: {e}")
        return None

def get_tvdb_tv_seasons(tvdb_id: str) -> Optional[List[Dict[str, Any]]]:
    """获取TVDB电视剧的季度信息
    
    Args:
        tvdb_id: TVDB电视剧ID
        
    Returns:
        季度信息列表，如果未找到或API未启用返回None
    """
    if not TVDB_ENABLED:
        logger.info("TVDB API未启用，跳过获取季度信息")
        return None
        
    try:
        api = get_tvdb_api()
        return api.get_tv_seasons(tvdb_id)
    except TVDBAPIError as e:
        logger.error(f"TVDB季度信息获取失败: {e}")
        return None
    except Exception as e:
        logger.error(f"TVDB季度信息获取时发生未知错误: {e}")
        return None

def validate_tvdb_api_key(api_key: str) -> bool:
    """验证TVDB API密钥是否有效
    
    Args:
        api_key: 要验证的API密钥
        
    Returns:
        bool: 如果API密钥有效返回True，否则返回False
    """
    try:
        # 临时创建API实例进行验证
        temp_api = TVDBAPI()
        temp_api.api_key = api_key
        temp_api._get_auth_token()
        return True
    except Exception as e:
        logger.error(f"TVDB API密钥验证失败: {e}")
        return False