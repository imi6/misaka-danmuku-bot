#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IMDB 网页爬虫模块
用于从 IMDB 网站获取电影和电视剧信息
"""

import requests
from bs4 import BeautifulSoup
import re
import asyncio
import concurrent.futures
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

class IMDBScraper:
    """IMDB 网页爬虫类"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
        })
    
    def get_media_info(self, imdb_id: str) -> Dict[str, Any]:
        """获取媒体信息
        
        Args:
            imdb_id: IMDB ID，如 'tt1234567'
            
        Returns:
            Dict: 包含媒体信息的字典
        """
        try:
            url = f"https://www.imdb.com/title/{imdb_id}/"
            logger.info(f"正在爬取 IMDB 页面: {url}")
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            if response.status_code == 200:
                return self._extract_media_info(response.text, imdb_id)
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"请求 IMDB 页面失败: {e}")
            return {
                "success": False,
                "error": f"网络请求失败: {str(e)}"
            }
        except Exception as e:
            logger.error(f"解析 IMDB 页面异常: {e}")
            return {
                "success": False,
                "error": f"解析异常: {str(e)}"
            }
    
    def _clean_html_content(self, html_content: str) -> str:
        """清理HTML内容中可能导致解析错误的字符
        
        Args:
            html_content: 原始HTML内容
            
        Returns:
            str: 清理后的HTML内容
        """
        try:
            # 移除或替换可能导致XML解析错误的字符
            # 替换常见的问题实体
            html_content = html_content.replace('&nbsp;', ' ')
            html_content = html_content.replace('&amp;', '&')
            html_content = html_content.replace('&lt;', '<')
            html_content = html_content.replace('&gt;', '>')
            html_content = html_content.replace('&quot;', '"')
            html_content = html_content.replace('&apos;', "'")
            
            # 移除无效的XML实体引用
            html_content = re.sub(r'&[^;\s]{1,10};?', '', html_content)
            
            # 移除控制字符（除了换行、回车、制表符）
            html_content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', html_content)
            
            return html_content
        except Exception as e:
            logger.error(f"清理HTML内容时出错: {e}")
            return html_content
    

        except Exception as e:
            logger.warning(f"HTML清理失败，返回原内容: {e}")
            return html_content
    
    def _extract_media_info(self, html_content: str, imdb_id: str) -> Dict[str, Any]:
        """从 HTML 内容中提取媒体信息
        
        Args:
            html_content: HTML 页面内容
            imdb_id: IMDB ID
            
        Returns:
            Dict: 提取的媒体信息
        """
        try:
            # 预处理HTML内容，清理可能导致解析错误的字符
            cleaned_html = self._clean_html_content(html_content)
            
            # 使用lxml解析器，更好地处理格式错误的HTML
            soup = BeautifulSoup(cleaned_html, 'lxml', from_encoding='utf-8')
        except Exception as e:
            logger.warning(f"lxml解析失败，回退到html.parser: {e}")
            try:
                # 回退到html.parser
                cleaned_html = self._clean_html_content(html_content)
                soup = BeautifulSoup(cleaned_html, 'html.parser')
            except Exception as e2:
                logger.error(f"HTML解析完全失败: {e2}")
                return {
                    "success": False,
                    "error": f"HTML解析失败: {str(e2)}"
                }
        
        info = {
            "success": True,
            "imdb_id": imdb_id,
            "title": "",
            "year": "",
            "media_type": "movie",  # 默认为电影
            "rating": "",
            "genres": [],
            "plot": "",
            "runtime": ""
        }
        
        try:
            # 提取标题
            title_selectors = [
                'h1[data-testid="hero__pageTitle"] span',
                'h1.titleHeader__title',
                'h1 .itemprop',
                'h1'
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    info["title"] = title_elem.get_text().strip()
                    break
            
            # 提取年份
            year_selectors = [
                'ul[data-testid="hero__pageTitle"] li a',
                '.titleBar .nobr a',
                '.title_wrapper .subtext a[title]'
            ]
            
            for selector in year_selectors:
                year_elem = soup.select_one(selector)
                if year_elem:
                    year_text = year_elem.get_text().strip()
                    year_match = re.search(r'(\d{4})', year_text)
                    if year_match:
                        info["year"] = year_match.group(1)
                        break
            
            # 如果年份选择器没找到，尝试从页面文本中提取
            if not info["year"]:
                page_text = soup.get_text()
                year_match = re.search(r'\b(19|20)\d{2}\b', page_text)
                if year_match:
                    info["year"] = year_match.group(0)
            
            # 判断媒体类型（通过页面结构和内容判断）
            page_text = soup.get_text()
            
            # 电视剧特征关键词
            tv_indicators = [
                'TV Series', 'TV Mini Series', 'TV Movie', 'Episodes',
                'Season', 'seasons', 'episode', 'episodes',
                'TV-', 'Series', 'Mini-Series'
            ]
            
            # 电影特征关键词
            movie_indicators = [
                'Runtime:', 'runtime', 'minutes', 'min',
                'Release Date', 'Box Office', 'Budget'
            ]
            
            # 计算特征权重
            tv_score = 0
            movie_score = 0
            
            for indicator in tv_indicators:
                if indicator in page_text:
                    tv_score += 1
            
            for indicator in movie_indicators:
                if indicator in page_text:
                    movie_score += 1
            
            # 检查页面标题和元数据
            title_text = soup.find('title')
            if title_text:
                title_content = title_text.get_text()
                if 'TV Series' in title_content or 'TV Mini Series' in title_content:
                    tv_score += 3
                elif 'TV Movie' in title_content:
                    tv_score += 2
            
            # 检查结构化数据
            json_ld = soup.find('script', {'type': 'application/ld+json'})
            if json_ld:
                try:
                    import json
                    data = json.loads(json_ld.string)
                    if isinstance(data, dict) and '@type' in data:
                        if data['@type'] == 'TVSeries':
                            tv_score += 5
                        elif data['@type'] == 'Movie':
                            movie_score += 5
                except:
                    pass
            
            # 根据权重判断类型
            if tv_score > movie_score:
                info["media_type"] = "tv_series"
                # IMDB没有可靠的API，季度信息使用默认逻辑
                info["seasons"] = []
            else:
                info["media_type"] = "movie"
            
            # 提取评分
            rating_selectors = [
                'span[class*="rating"]',
                '.ratingValue strong span',
                '.imdbRating .ratingValue',
                '[data-testid="hero-rating-bar__aggregate-rating__score"] span'
            ]
            
            for selector in rating_selectors:
                rating_elem = soup.select_one(selector)
                if rating_elem:
                    rating_text = rating_elem.get_text().strip()
                    rating_match = re.search(r'(\d+\.\d+)', rating_text)
                    if rating_match:
                        info["rating"] = rating_match.group(1)
                        break
            
            # 提取类型标签
            genre_selectors = [
                '[data-testid="genres"] .chip__label',
                '.see-more.inline.canwrap a',
                '.subtext a[href*="genres"]'
            ]
            
            for selector in genre_selectors:
                genre_elems = soup.select(selector)
                if genre_elems:
                    info["genres"] = [elem.get_text().strip() for elem in genre_elems]
                    break
            
            # 提取剧情简介
            plot_selectors = [
                '[data-testid="plot"] .plot-xl',
                '.plot_summary .summary_text',
                '.storyline .inline.canwrap p'
            ]
            
            for selector in plot_selectors:
                plot_elem = soup.select_one(selector)
                if plot_elem:
                    info["plot"] = plot_elem.get_text().strip()
                    break
            
            # 提取时长
            runtime_selectors = [
                '[data-testid="title-techspecs_section"] li:contains("Runtime")',
                '.subtext time',
                '.txt-block time'
            ]
            
            for selector in runtime_selectors:
                runtime_elem = soup.select_one(selector)
                if runtime_elem:
                    runtime_text = runtime_elem.get_text().strip()
                    runtime_match = re.search(r'(\d+)\s*min', runtime_text)
                    if runtime_match:
                        info["runtime"] = f"{runtime_match.group(1)} min"
                        break
            
        except Exception as e:
            logger.error(f"提取 IMDB 信息时出错: {e}")
            info["error"] = f"信息提取失败: {str(e)}"
        
        return info

# 全局爬虫实例
_imdb_scraper = None

def get_imdb_scraper() -> IMDBScraper:
    """获取 IMDB 爬虫实例（单例模式）"""
    global _imdb_scraper
    if _imdb_scraper is None:
        _imdb_scraper = IMDBScraper()
    return _imdb_scraper

def get_imdb_info(imdb_id: str) -> Dict[str, Any]:
    """获取 IMDB 信息（同步版本）
    
    Args:
        imdb_id: IMDB ID
        
    Returns:
        Dict: 媒体信息
    """
    scraper = get_imdb_scraper()
    return scraper.get_media_info(imdb_id)

async def get_imdb_media_info(imdb_id: str) -> Dict[str, Any]:
    """获取 IMDB 媒体信息（异步版本）
    
    Args:
        imdb_id: IMDB ID，如 'tt1234567'
        
    Returns:
        Dict: 包含以下字段的字典:
            - success: bool, 是否成功
            - imdb_id: str, IMDB ID
            - title: str, 标题
            - year: str, 年份
            - media_type: str, 媒体类型 ('movie' 或 'tv_series')
            - rating: str, 评分
            - genres: List[str], 类型标签
            - plot: str, 剧情简介
            - runtime: str, 时长
            - error: str, 错误信息（如果失败）
    """
    loop = asyncio.get_event_loop()
    
    # 在线程池中运行同步函数
    with concurrent.futures.ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, get_imdb_info, imdb_id)
    
    return result