import requests
import re
import time
import random
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

class DoubanScraper:
    """豆瓣网页爬虫类
    
    由于豆瓣没有公开API，需要通过网页爬取获取数据
    """
    
    def __init__(self):
        self.session = requests.Session()
        # 设置User-Agent模拟浏览器访问
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
        })
        
    def _make_request(self, url: str, max_retries: int = 3) -> Optional[requests.Response]:
        """发送HTTP请求，包含重试机制和反爬虫处理
        
        Args:
            url: 请求URL
            max_retries: 最大重试次数
            
        Returns:
            requests.Response对象，失败返回None
        """
        for attempt in range(max_retries):
            try:
                # 随机延迟，避免被识别为爬虫
                if attempt > 0:
                    delay = random.uniform(1, 3)
                    time.sleep(delay)
                    
                response = self.session.get(url, timeout=10)
                
                # 检查是否被反爬虫拦截
                if response.status_code == 403:
                    logger.warning(f"豆瓣访问被拒绝 (403)，尝试 {attempt + 1}/{max_retries}")
                    continue
                    
                if response.status_code == 418:
                    logger.warning(f"豆瓣检测到爬虫行为 (418)，尝试 {attempt + 1}/{max_retries}")
                    # 增加更长的延迟
                    time.sleep(random.uniform(5, 10))
                    continue
                    
                response.raise_for_status()
                return response
                
            except requests.exceptions.RequestException as e:
                logger.error(f"请求豆瓣失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    return None
                    
        return None
    
    def get_media_info(self, douban_id: str) -> Optional[Dict[str, Any]]:
        """根据豆瓣ID获取媒体信息
        
        Args:
            douban_id: 豆瓣条目ID
            
        Returns:
            包含媒体信息的字典，失败返回None
            
        Returns格式:
            {
                "title": "标题",
                "original_title": "原标题",
                "year": "年份",
                "media_type": "movie" 或 "tv_series",
                "genres": ["类型1", "类型2"],
                "rating": "评分",
                "rating_count": "评分人数",
                "directors": ["导演1", "导演2"],
                "actors": ["演员1", "演员2"],
                "summary": "简介",
                "douban_id": "豆瓣ID"
            }
        """
        url = f"https://movie.douban.com/subject/{douban_id}/"
        
        response = self._make_request(url)
        if not response:
            logger.error(f"无法获取豆瓣页面: {url}")
            return None
            
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 检查页面是否存在
            if "页面不存在" in response.text or "条目不存在" in response.text:
                logger.error(f"豆瓣条目不存在: {douban_id}")
                return None
                
            return self._extract_media_info(soup, douban_id)
            
        except Exception as e:
            logger.error(f"解析豆瓣页面失败: {e}")
            return None
    
    def _extract_media_info(self, soup: BeautifulSoup, douban_id: str) -> Dict[str, Any]:
        """从BeautifulSoup对象中提取媒体信息
        
        Args:
            soup: BeautifulSoup解析的页面对象
            douban_id: 豆瓣ID
            
        Returns:
            包含媒体信息的字典
        """
        info = {"douban_id": douban_id}
        
        try:
            # 提取标题 - 尝试多种选择器
            title_element = soup.find('span', property='v:itemreviewed')
            if not title_element:
                title_element = soup.find('h1')
            if not title_element:
                title_element = soup.find('title')
            
            if title_element:
                title_text = title_element.get_text().strip()
                # 清理标题文本
                if '(豆瓣)' in title_text:
                    title_text = title_text.replace('(豆瓣)', '').strip()
                info["title"] = title_text
                
                # 从标题中解析季度信息
                season_number = self._extract_season_from_title(title_text)
                if season_number:
                    info["season"] = season_number
            
            # 提取年份 - 尝试多种方式
            year_element = soup.find('span', class_='year')
            if not year_element:
                # 尝试从页面文本中提取年份
                page_text = soup.get_text()
                year_match = re.search(r'(\d{4})', page_text)
                if year_match:
                    info["year"] = year_match.group(1)
            else:
                year_text = year_element.get_text().strip()
                year_match = re.search(r'(\d{4})', year_text)
                if year_match:
                    info["year"] = year_match.group(1)
            
            # 判断媒体类型（通过页面结构判断）
            page_text = soup.get_text()
            
            # 电视剧特征关键词
            tv_indicators = [
                '电视剧', '集数:', '集数：', '首播:', '首播：', 
                'episodes', '单集片长', '季数',
                '网络剧', '迷你剧', '限定剧'
            ]
            
            # 电影特征关键词
            movie_indicators = [
                '片长:', '片长：', '上映日期', '制片国家', '影片'
            ]
            
            # 计算特征权重
            tv_score = 0
            movie_score = 0
            
            for indicator in tv_indicators:
                if indicator in page_text:
                    # 排除导航栏中的"剧集"误判
                    if indicator == '剧集' and '选剧集' in page_text:
                        continue
                    tv_score += 1
            
            for indicator in movie_indicators:
                if indicator in page_text:
                    movie_score += 1
            
            # 根据权重判断类型
            if tv_score > movie_score:
                info["media_type"] = "tv_series"
            else:
                info["media_type"] = "movie"
            
            # 提取评分 - 尝试多种选择器
            rating_element = soup.find('strong', class_='rating_num')
            if not rating_element:
                rating_element = soup.find('span', class_='rating_num')
            if rating_element:
                info["rating"] = rating_element.get_text().strip()
            
            # 提取评分人数
            rating_count_element = soup.find('span', property='v:votes')
            if rating_count_element:
                info["rating_count"] = rating_count_element.get_text().strip()
            
            # 提取类型
            genres = []
            genre_elements = soup.find_all('span', property='v:genre')
            for genre_element in genre_elements:
                genres.append(genre_element.get_text().strip())
            info["genres"] = genres
            
            # 提取导演
            directors = []
            director_elements = soup.find_all('a', rel='v:directedBy')
            for director_element in director_elements:
                directors.append(director_element.get_text().strip())
            info["directors"] = directors
            
            # 提取主演
            actors = []
            actor_elements = soup.find_all('a', rel='v:starring')
            for actor_element in actor_elements:
                actors.append(actor_element.get_text().strip())
            info["actors"] = actors
            
            # 提取原标题（如果有）
            info_section = soup.find('div', id='info')
            if info_section:
                original_title_match = re.search(r'又名:</span>\s*([^<\n]+)', str(info_section))
                if original_title_match:
                    info["original_title"] = original_title_match.group(1).strip()
            
            # 提取简介
            summary_element = soup.find('span', property='v:summary')
            if summary_element:
                info["summary"] = summary_element.get_text().strip()
            
            logger.info(f"成功提取豆瓣信息: {info.get('title', '未知')} ({douban_id})")
            return info
            
        except Exception as e:
            logger.error(f"提取豆瓣信息失败: {e}")
            return info
    
    def _extract_season_from_title(self, title: str) -> Optional[int]:
        """从标题中提取季度信息
        
        Args:
            title: 媒体标题
            
        Returns:
            季度数字，如果未找到返回None
        """
        if not title:
            return None
            
        # 常见的季度表示模式
        season_patterns = [
            r'第([一二三四五六七八九十\d]+)季',  # 第X季
            r'Season\s*(\d+)',  # Season X
            r'S(\d+)',  # SX
            r'第([一二三四五六七八九十\d]+)部',  # 第X部
            r'([一二三四五六七八九十\d]+)季',  # X季
        ]
        
        # 中文数字到阿拉伯数字的映射
        chinese_to_arabic = {
            '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
        }
        
        for pattern in season_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                season_str = match.group(1)
                
                # 尝试直接转换为数字
                if season_str.isdigit():
                    return int(season_str)
                
                # 尝试中文数字转换
                if season_str in chinese_to_arabic:
                    return chinese_to_arabic[season_str]
                
                # 处理复合中文数字（如十一、十二等）
                if season_str.startswith('十') and len(season_str) > 1:
                    if season_str[1] in chinese_to_arabic:
                        return 10 + chinese_to_arabic[season_str[1]]
                elif season_str == '十':
                    return 10
        
        return None

# 全局实例
_douban_scraper = None

def get_douban_scraper() -> DoubanScraper:
    """获取豆瓣爬虫实例（单例模式）"""
    global _douban_scraper
    if _douban_scraper is None:
        _douban_scraper = DoubanScraper()
    return _douban_scraper

def get_douban_info(douban_id: str) -> Optional[Dict[str, Any]]:
    """根据豆瓣ID获取媒体信息的便捷函数
    
    Args:
        douban_id: 豆瓣条目ID
        
    Returns:
        包含媒体信息的字典，失败返回None
    """
    scraper = get_douban_scraper()
    return scraper.get_media_info(douban_id)

async def get_douban_media_info(douban_id: str) -> Optional[Dict[str, Any]]:
    """异步版本的豆瓣媒体信息获取函数
    
    Args:
        douban_id: 豆瓣条目ID
        
    Returns:
        包含媒体信息和成功标志的字典，失败返回None或包含错误信息的字典
        
    Returns格式:
        成功时: {
            "success": True,
            "title": "标题",
            "year": "年份",
            "type": "类型",
            "rating": "评分",
            "media_type": "movie" 或 "tv_series",
            ...
        }
        失败时: {
            "success": False,
            "error": "错误信息"
        }
    """
    import asyncio
    
    try:
        # 在线程池中运行同步函数
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, get_douban_info, douban_id)
        
        if result:
            # 添加成功标志
            result["success"] = True
            return result
        else:
            return {
                "success": False,
                "error": "无法获取豆瓣信息"
            }
            
    except Exception as e:
        logger.error(f"异步获取豆瓣信息失败: {e}")
        return {
            "success": False,
            "error": str(e)
        }