#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BGM (Bangumi) 数据获取模块
支持API和网页爬虫两种方式获取动漫、电影和电视剧信息
"""

import requests
from bs4 import BeautifulSoup
import re
import asyncio
import concurrent.futures
from typing import Dict, Any, Optional
import logging
from utils.security import mask_sensitive_in_text

# 导入配置
try:
    from config import BGM_ACCESS_TOKEN, BGM_BASE_URL, BGM_ENABLED
except ImportError:
    # 如果无法导入配置，使用默认值
    BGM_ACCESS_TOKEN = None
    BGM_BASE_URL = "https://api.bgm.tv"
    BGM_ENABLED = False

logger = logging.getLogger(__name__)


class BGMAPI:
    """BGM API 客户端类"""
    
    def __init__(self):
        self.access_token = BGM_ACCESS_TOKEN
        self.base_url = BGM_BASE_URL
        self.session = requests.Session()
        
        if self.access_token:
            self.session.headers.update({
                'Authorization': f'Bearer {self.access_token}',
                'User-Agent': 'MisakaBot/1.0 (https://github.com/your-repo)',
                'Accept': 'application/json',
            })
    
    def get_subject_info(self, subject_id: str) -> Dict[str, Any]:
        """通过API获取条目信息
        
        Args:
            subject_id: BGM条目ID
            
        Returns:
            Dict: 包含媒体信息的字典
        """
        if not self.access_token:
            raise ValueError("BGM Access Token未配置")
            
        try:
            # 获取基本信息
            url = f"{self.base_url}/v0/subjects/{subject_id}"
            logger.info(f"正在调用 BGM API: {mask_sensitive_in_text(url)}")
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # 转换为统一格式
            return self._convert_api_data(data, subject_id)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"BGM API请求失败: {e}")
            return {
                'success': False,
                'error': f'API请求失败: {str(e)}'
            }
        except Exception as e:
            logger.error(f"BGM API处理异常: {e}")
            return {
                'success': False,
                'error': f'API处理异常: {str(e)}'
            }
    
    def _convert_api_data(self, data: Dict[str, Any], subject_id: str) -> Dict[str, Any]:
        """将API数据转换为统一格式
        
        Args:
            data: API返回的原始数据
            subject_id: 条目ID
            
        Returns:
            Dict: 转换后的媒体信息
        """
        try:
            # 提取基本信息
            title = data.get('name', 'N/A')
            title_cn = data.get('name_cn', '')
            if title_cn:
                title = title_cn  # 优先使用中文标题
            
            # 提取年份
            year = 'N/A'
            date = data.get('date')
            if date:
                year = date.split('-')[0] if '-' in date else date
            
            # 提取评分
            rating = 'N/A'
            rating_info = data.get('rating')
            if rating_info and rating_info.get('score'):
                rating = str(rating_info['score'])
            
            # 提取类型信息
            media_type = self._determine_media_type_from_api(data)
            
            # 提取标签/类型
            genres = []
            tags = data.get('tags', [])
            for tag in tags[:5]:  # 取前5个标签
                if isinstance(tag, dict) and tag.get('name'):
                    genres.append(tag['name'])
            
            # 提取简介
            summary = data.get('summary', 'N/A')
            if len(summary) > 200:
                summary = summary[:200] + '...'
            
            return {
                'success': True,
                'title': title,
                'year': year,
                'rating': rating,
                'media_type': media_type,
                'genres': genres,
                'summary': summary,
                'bgm_id': subject_id,
                'source': 'api'
            }
            
        except Exception as e:
            logger.error(f"API数据转换失败: {e}")
            return {
                'success': False,
                'error': f'数据转换失败: {str(e)}'
            }
    
    def _determine_media_type_from_api(self, data: Dict[str, Any]) -> str:
        """根据API数据判断媒体类型
        
        Args:
            data: API返回的数据
            
        Returns:
            str: 媒体类型 ('movie' 或 'tv_series')
        """
        try:
            # 检查type字段
            subject_type = data.get('type')
            if subject_type == 3:  # 动画
                # 进一步判断是电影还是电视剧
                eps = data.get('eps', 0)
                if eps == 1:
                    return "movie"
                else:
                    return "tv_series"
            elif subject_type == 2:  # 动画电影
                return "movie"
            
            # 检查平台信息
            platform = data.get('platform', '')
            if '剧场版' in platform or '电影' in platform:
                return "movie"
            
            # 检查话数
            eps = data.get('eps', 0)
            if eps == 1:
                return "movie"
            elif eps > 1:
                return "tv_series"
            
            # 默认返回电视剧
            return "tv_series"
            
        except Exception as e:
            logger.error(f"API媒体类型判断失败: {e}")
            return "tv_series"


class BGMScraper:
    """BGM 网页爬虫类"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Charset': 'utf-8',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
        })
    
    def get_media_info(self, bgm_id: str) -> Dict[str, Any]:
        """获取媒体信息
        
        Args:
            bgm_id: BGM subject ID，如 '453888'
            
        Returns:
            Dict: 包含媒体信息的字典
        """
        try:
            url = f"https://bgm.tv/subject/{bgm_id}"
            logger.info(f"正在爬取 BGM 页面: {url}")
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            # 确保正确的编码
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                return self._extract_media_info(response.text, bgm_id)
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"请求 BGM 页面失败: {e}")
            return {
                "success": False,
                "error": f"网络请求失败: {str(e)}"
            }
        except Exception as e:
            logger.error(f"解析 BGM 页面异常: {e}")
            return {
                "success": False,
                "error": f"解析异常: {str(e)}"
            }
    
    def _extract_media_info(self, html_content: str, bgm_id: str) -> Dict[str, Any]:
        """从 HTML 内容中提取媒体信息
        
        Args:
            html_content: HTML 页面内容
            bgm_id: BGM subject ID
            
        Returns:
            Dict: 提取的媒体信息
        """
        soup = BeautifulSoup(html_content, 'html.parser', from_encoding='utf-8')
        
        info = {
            "success": True,
            "bgm_id": bgm_id,
            "title": "",
            "year": "",
            "media_type": "tv_series",  # 默认为电视剧
            "rating": "",
            "genres": [],
            "plot": "",
            "episodes": ""
        }
        
        try:
            # 提取标题
            title_selectors = [
                'h1.nameSingle a',
                'h1.nameSingle',
                '.infobox .title',
                'h1'
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title_text = title_elem.get_text().strip()
                    info["title"] = title_text
                    
                    # 从标题中解析季度信息
                    season_number = self._extract_season_from_title(title_text)
                    if season_number:
                        info["season"] = season_number
                    break
            
            # 提取年份
            infobox = soup.select_one('.infobox')
            if infobox:
                # 查找放送开始或上映年份
                year_patterns = [
                    r'放送开始[：:]\s*(\d{4})',
                    r'上映年度[：:]\s*(\d{4})',
                    r'发售日期[：:]\s*(\d{4})',
                    r'(\d{4})年\d+月\d+日',
                    r'(\d{4})-\d+-\d+'
                ]
                
                infobox_text = infobox.get_text()
                for pattern in year_patterns:
                    year_match = re.search(pattern, infobox_text)
                    if year_match:
                        info["year"] = year_match.group(1)
                        break
            
            # 判断媒体类型
            media_type = self._determine_media_type(soup)
            info["media_type"] = media_type
            
            # 提取评分
            rating_elem = soup.select_one('.global_score .number')
            if rating_elem:
                info["rating"] = rating_elem.get_text().strip()
            
            # 提取类型/标签
            genre_elems = soup.select('.subject_tag_section .inner a')
            if genre_elems:
                info["genres"] = [elem.get_text().strip() for elem in genre_elems[:5]]  # 取前5个标签
            
            # 提取简介
            plot_elem = soup.select_one('#subject_summary')
            if plot_elem:
                info["plot"] = plot_elem.get_text().strip()
            
            # 提取集数（如果是电视剧）
            if infobox and media_type == "tv_series":
                episodes_match = re.search(r'话数[：:]\s*(\d+)', infobox.get_text())
                if episodes_match:
                    info["episodes"] = episodes_match.group(1)
            
            logger.info(f"BGM 爬虫成功提取信息: 标题={info['title']}, 年份={info['year']}, 类型={info['media_type']}")
            
        except Exception as e:
            logger.error(f"提取 BGM 信息时出错: {e}")
            info["success"] = False
            info["error"] = f"信息提取失败: {str(e)}"
        
        return info
    
    def _determine_media_type(self, soup: BeautifulSoup) -> str:
        """判断媒体类型
        
        Args:
            soup: BeautifulSoup 对象
            
        Returns:
            str: 媒体类型 ('movie' 或 'tv_series')
        """
        try:
            # 获取页面文本内容
            page_text = soup.get_text()
            
            # 电影特征关键词
            movie_indicators = [
                '电影', '剧场版', '剧场', '上映年度', '上映日期',
                '时长', '分钟', 'min', '片长', '电影版'
            ]
            
            # 电视剧/动漫特征关键词
            tv_indicators = [
                '电视', 'TV', '放送开始', '放送', '话数', '集数',
                '每话长度', '动画', '番剧', '连载', '季度'
            ]
            
            # 计算特征权重
            movie_score = 0
            tv_score = 0
            
            for indicator in movie_indicators:
                if indicator in page_text:
                    movie_score += 1
            
            for indicator in tv_indicators:
                if indicator in page_text:
                    tv_score += 1
            
            # 检查infobox中的具体信息
            infobox = soup.select_one('.infobox')
            if infobox:
                infobox_text = infobox.get_text()
                
                # 如果有话数信息，很可能是电视剧/动漫
                if re.search(r'话数[：:]\s*\d+', infobox_text):
                    tv_score += 3
                
                # 如果有时长但没有话数，可能是电影
                if re.search(r'时长[：:]', infobox_text) and not re.search(r'话数[：:]', infobox_text):
                    movie_score += 2
                
                # 检查类型字段
                if '电影' in infobox_text or '剧场版' in infobox_text:
                    movie_score += 3
                elif 'TV' in infobox_text or '电视' in infobox_text:
                    tv_score += 3
            
            # 根据权重判断
            if movie_score > tv_score:
                return "movie"
            else:
                return "tv_series"
                
        except Exception as e:
            logger.error(f"判断媒体类型时出错: {e}")
            return "tv_series"  # 默认返回电视剧
    
    def _extract_season_from_title(self, title: str) -> Optional[int]:
        """从标题中提取季度信息
        
        Args:
            title: 标题文本
            
        Returns:
            Optional[int]: 季度数字，如果没有找到则返回None
        """
        if not title:
            return None
            
        try:
            # 季度匹配模式
            season_patterns = [
                r'第([一二三四五六七八九十\d]+)季',  # 第X季
                r'Season\s*(\d+)',  # Season X
                r'S(\d+)',  # SX
                r'第([一二三四五六七八九十\d]+)部',  # 第X部
                r'([一二三四五六七八九十\d]+)期',  # X期
            ]
            
            for pattern in season_patterns:
                match = re.search(pattern, title, re.IGNORECASE)
                if match:
                    season_str = match.group(1)
                    
                    # 处理中文数字
                    chinese_numbers = {
                        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
                    }
                    
                    if season_str in chinese_numbers:
                        return chinese_numbers[season_str]
                    elif season_str.isdigit():
                        return int(season_str)
            
            return None
            
        except Exception as e:
            logger.error(f"解析季度信息时出错: {e}")
            return None

# 创建全局实例
bgm_api = BGMAPI()
bgm_scraper = BGMScraper()

def get_bgm_info(bgm_id: str) -> Dict[str, Any]:
    """获取 BGM 媒体信息的便捷函数
    
    优先使用 API 方式获取数据，如果 API 不可用则回退到网页爬虫方式。
    
    Args:
        bgm_id: BGM subject ID
        
    Returns:
        Dict: 媒体信息字典
    """
    # 优先尝试使用 API
    if BGM_ENABLED and BGM_ACCESS_TOKEN:
        try:
            logger.info(f"尝试使用 BGM API 获取条目 {bgm_id} 的信息")
            result = bgm_api.get_subject_info(bgm_id)
            
            if result.get('success'):
                logger.info(f"BGM API 获取成功: {result.get('title', 'N/A')}")
                return result
            else:
                logger.warning(f"BGM API 获取失败: {result.get('error', 'Unknown error')}")
        except Exception as e:
            logger.error(f"BGM API 调用异常: {e}")
    
    # API 不可用或失败时，回退到网页爬虫
    logger.info(f"回退到网页爬虫方式获取条目 {bgm_id} 的信息")
    result = bgm_scraper.get_media_info(bgm_id)
    
    # 为爬虫结果添加source标识
    if isinstance(result, dict) and result.get('success'):
        result['source'] = 'scraper'
    
    return result

if __name__ == "__main__":
    # 测试代码
    test_ids = ["453888", "38124"]  # 电视剧和电影示例
    
    for bgm_id in test_ids:
        print(f"\n测试 BGM ID: {bgm_id}")
        result = get_bgm_info(bgm_id)
        print(f"结果: {result}")