import logging
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Bot
from config import ConfigManager
from handlers.import_url import get_library_data, search_video_by_keyword
from utils.tmdb_api import get_tmdb_media_details, search_tv_series_by_name_year, validate_tv_series_match
from utils.api import call_danmaku_api
from utils.security import mask_sensitive_data

logger = logging.getLogger(__name__)

class WebhookHandler:
    """Webhook处理器，用于处理来自Emby等媒体服务器的通知"""
    
    def __init__(self, bot: Optional[Bot] = None):
        self.config = ConfigManager()
        self.bot = bot
        # 从环境变量读取时区配置，默认为Asia/Shanghai
        self.timezone = ZoneInfo(os.getenv('TZ', 'Asia/Shanghai'))
        self._tmdb_cache = {}  # TMDB搜索结果缓存
        
    def validate_api_key(self, provided_key: str) -> bool:
        """验证API密钥"""
        if not self.config.webhook.enabled:
            logger.warning("🔒 Webhook功能未启用，拒绝请求")
            return False
            
        if not provided_key:
            logger.warning("🔒 缺少API密钥")
            return False
            
        if provided_key != self.config.webhook.api_key:
            logger.warning(f"🔒 API密钥验证失败: {mask_sensitive_data(provided_key)}")
            return False
            
        return True
    
    async def handle_emby_webhook(self, data: Dict[str, Any], api_key: str) -> Dict[str, Any]:
        """处理Emby webhook通知
        
        Args:
            data: Emby发送的webhook数据
            api_key: 请求中的API密钥
            
        Returns:
            Dict[str, Any]: 响应数据
        """
        try:
            # 验证API密钥
            if not self.validate_api_key(api_key):
                return {
                    "success": False,
                    "error": "API密钥验证失败",
                    "code": 401
                }
            
            # 解析Emby通知数据
            event_type = data.get('Event', '')
            logger.info(f"📡 收到Emby通知，事件类型: {event_type}")
            
            # 记录完整的Emby消息体到日志（DEBUG级别）
            logger.debug(f"📋 完整Emby消息体:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
            
            # 记录关键信息到INFO级别日志
            item_info = data.get('Item', {})
            session_info = data.get('Session', {})
            user_info = data.get('User', {})
            logger.info(f"📺 媒体信息: {item_info.get('Name', '未知')} (类型: {item_info.get('Type', '未知')})")
            logger.info(f"👤 用户信息: {user_info.get('Name', '未知')} | 设备: {session_info.get('DeviceName', '未知')} ({session_info.get('Client', '未知')})")
            logger.info(f"🔗 提供商ID: {item_info.get('ProviderIds', {})}")
            
            # 只处理播放开始事件
            if event_type != 'playback.start':
                logger.info(f"ℹ️ 忽略非播放开始事件: {event_type}")
                return {
                    "success": True,
                    "message": f"事件 {event_type} 已忽略",
                    "processed": False
                }
            
            # 提取媒体信息
            media_info = self._extract_media_info(data)
            if not media_info:
                logger.warning("⚠️ 无法提取媒体信息")
                return {
                    "success": False,
                    "error": "无法提取媒体信息",
                    "code": 400
                }
            
            # 记录播放事件
            tmdb_info = f" [TMDB: {media_info['tmdb_id']}]" if media_info.get('tmdb_id') else ""
            logger.info(
                f"🎬 Emby播放开始: {media_info['title']} "
                f"(用户: {media_info.get('user', '未知')}){tmdb_info}"
            )
            
            # 执行智能影视库管理流程
            await self._process_smart_library_management(media_info)
            
            # 如果配置了Telegram机器人，可以发送通知给管理员
            if self.bot and self.config.telegram.admin_user_ids:
                await self._send_play_notification(media_info)
            
            return {
                "success": True,
                "message": "播放开始事件已处理",
                "processed": True,
                "media_info": media_info
            }
            
        except Exception as e:
            logger.error(f"❌ 处理Emby webhook时发生错误: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"处理webhook时发生错误: {str(e)}",
                "code": 500
            }
    
    def _extract_media_info(self, data: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """从Emby webhook数据中提取媒体信息
        
        Args:
            data: Emby webhook数据
            
        Returns:
            Optional[Dict[str, str]]: 提取的媒体信息，如果提取失败则返回None
        """
        try:
            item = data.get('Item', {})
            session = data.get('Session', {})
            user = data.get('User', {})
            
            # 提取基本信息
            title = item.get('Name', '未知标题')
            media_type = item.get('Type', '未知类型')
            year = item.get('ProductionYear', '')
            
            # 对于剧集，提取季和集信息
            season_number = item.get('ParentIndexNumber')
            episode_number = item.get('IndexNumber')
            series_name = item.get('SeriesName')
            
            # 优化年份提取：优先使用PremiereDate
            if not year and 'PremiereDate' in item and item['PremiereDate']:
                try:
                    premiere_date = datetime.fromisoformat(item['PremiereDate'].replace('Z', '+00:00'))
                    year = premiere_date.year
                    logger.debug(f"📅 从PremiereDate提取年份: {year}")
                except Exception as e:
                    logger.debug(f"解析PremiereDate失败: {e}")
            
            # 优化剧集名称提取：从路径中补充信息
            if not series_name and 'Path' in data:
                path = data['Path']
                import os
                import re
                
                path_parts = [p for p in path.split('/') if p.strip()]
                if len(path_parts) >= 3:
                    # 通常剧集名在倒数第三个或第四个位置
                    for i in range(-4, -1):
                        if abs(i) <= len(path_parts):
                            potential_name = path_parts[i]
                            # 跳过明显的季度文件夹
                            if not re.match(r'^Season\s+\d+$', potential_name, re.IGNORECASE):
                                series_name = potential_name
                                logger.debug(f"📺 从路径提取剧集名: {series_name}")
                                break
                
                # 从文件名中提取季集信息（如果Item中没有）
                if (not season_number or not episode_number) and path:
                    filename = os.path.basename(path)
                    patterns = [
                        r'S(\d+)E(\d+)',  # S01E01
                        r'Season\s*(\d+).*Episode\s*(\d+)',  # Season 1 Episode 1
                        r'第(\d+)季.*第(\d+)集',  # 第1季第1集
                        r'(\d+)x(\d+)',  # 1x01
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, filename, re.IGNORECASE)
                        if match:
                            if not season_number:
                                season_number = int(match.group(1))
                                logger.debug(f"📊 从文件名提取季度: S{season_number}")
                            if not episode_number:
                                episode_number = int(match.group(2))
                                logger.debug(f"📊 从文件名提取集数: E{episode_number}")
                            break
                
                # 从路径中提取年份（如果Item中没有）
                if not year:
                    year_match = re.search(r'\b(19|20)\d{2}\b', path)
                    if year_match:
                        year = int(year_match.group())
                        logger.debug(f"📅 从路径提取年份: {year}")
            
            # 清理剧集名称
            if series_name:
                import re
                series_name = series_name.strip()
                # 移除常见的无用后缀
                series_name = re.sub(r'\s*\(\d{4}\)\s*$', '', series_name)  # 移除年份括号
                series_name = re.sub(r'\s*-\s*Season\s+\d+\s*$', '', series_name, flags=re.IGNORECASE)  # 移除季度后缀
            
            # 提取TMDB ID信息（Emby刮削后的元数据）
            provider_ids = item.get('ProviderIds', {})
            tmdb_id = provider_ids.get('Tmdb') or provider_ids.get('TheMovieDb')
            imdb_id = provider_ids.get('Imdb')
            tvdb_id = provider_ids.get('Tvdb') or provider_ids.get('TheTVDB')
            
            # 调试日志：显示提供商ID信息
            logger.debug(f"🔍 媒体提供商ID信息: {provider_ids}")
            logger.debug(f"🎯 提取的TMDB ID: {tmdb_id}, IMDB ID: {imdb_id}, TVDB ID: {tvdb_id}")
            logger.debug(f"🎯 最终提取信息: 剧集='{series_name}', 季度={season_number}, 集数={episode_number}, 年份={year}, TMDB_ID={tmdb_id}")
            
            # 构建完整标题
            if media_type == 'Episode' and series_name:
                if season_number and episode_number:
                    full_title = f"{series_name} S{season_number:02d}E{episode_number:02d} - {title}"
                else:
                    full_title = f"{series_name} - {title}"
            else:
                full_title = f"{title} ({year})" if year else title
            
            return {
                "title": full_title,
                "original_title": title,
                "type": media_type,
                "year": str(year) if year else '',
                "series_name": series_name or '',
                "season": str(season_number) if season_number else '',
                "episode": str(episode_number) if episode_number else '',
                "tmdb_id": tmdb_id or '',
                "imdb_id": imdb_id or '',
                "tvdb_id": tvdb_id or '',
                "user": user.get('Name', '未知用户'),
                "client": session.get('Client', '未知客户端'),
                "device": session.get('DeviceName', '未知设备'),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ 提取媒体信息时发生错误: {e}")
            return None
    
    async def _send_play_notification(self, media_info: Dict[str, str]):
        """向管理员发送播放通知
        
        Args:
            media_info: 媒体信息
        """
        try:
            if not self.bot:
                return
                
            message = (
                f"🎬 **Emby播放通知**\n\n"
                f"📺 **媒体**: {media_info['title']}\n"
                f"👤 **用户**: {media_info['user']}\n"
                f"📱 **设备**: {media_info['device']} ({media_info['client']})\n"
                f"⏰ **时间**: {media_info['timestamp']}"
            )
            
            # 发送给所有管理员
            for admin_id in self.config.telegram.admin_user_ids:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=message,
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"❌ 向管理员 {admin_id} 发送通知失败: {e}")
                    
        except Exception as e:
            logger.error(f"❌ 发送播放通知时发生错误: {e}")
    
    async def _process_smart_library_management(self, media_info: Dict[str, str]):
        """执行智能影视库管理流程
        
        Args:
            media_info: 媒体信息
        """
        try:
            media_type = media_info.get('type', '')
            title = media_info.get('title')
            
            # 获取优先级Provider信息
            provider_type, provider_id, search_type = self._get_priority_provider_info(media_info)
            
            # 详细检查缺失的信息
            missing_info = []
            if not provider_id:
                missing_info.append('Provider ID')
            if not title:
                missing_info.append('标题')
            
            # 对于电视剧，如果缺少Provider ID但有剧集名称，尝试通过名称搜索TMDB ID
            if not provider_id and media_type == 'Episode':
                series_name = media_info.get('series_name')
                year = media_info.get('year')
                if series_name:
                    logger.info(f"🔍 电视剧缺少Provider ID，尝试通过剧集名称搜索TMDB ID: {series_name} ({year})")
                    # 这里可以调用TMDB搜索API来获取TMDB ID
                    # 暂时先记录日志，后续可以扩展搜索功能
                    logger.debug(f"📺 剧集信息: 名称='{series_name}', 年份='{year}', 季数='{media_info.get('season')}', 集数='{media_info.get('episode')}'")
            
            # 如果仍然缺少关键信息，跳过智能管理
            if not provider_id and not title:
                logger.info(f"ℹ️ 媒体缺少必要信息（{', '.join(missing_info)}），跳过智能管理")
                logger.debug(f"🔍 媒体信息详情: Provider='{provider_type}:{provider_id}', 标题='{title}', 类型='{media_type}'")
                return
            elif not provider_id:
                logger.info(f"⚠️ 媒体缺少Provider ID但有标题信息，继续处理: {title}")
                logger.debug(f"🔍 媒体信息详情: Provider='{provider_type}:{provider_id}', 标题='{title}', 类型='{media_type}'")
            else:
                logger.info(f"✅ 使用优先级Provider: {provider_type.upper()} ID={provider_id}")
            
            # 更新media_info中的Provider信息
            media_info['selected_provider_type'] = provider_type
            media_info['selected_provider_id'] = provider_id
            media_info['selected_search_type'] = search_type
            
            # 根据媒体类型选择处理方式
            if media_type == 'Movie':
                await self._process_movie_management(media_info)
            elif media_type == 'Episode':
                await self._process_tv_management(media_info)
            else:
                logger.info(f"ℹ️ 不支持的媒体类型: {media_type}，跳过智能管理")
                
        except Exception as e:
            logger.error(f"❌ 智能影视库管理处理失败: {e}", exc_info=True)
    
    async def _process_movie_management(self, media_info: Dict[str, str]):
        """处理电影智能管理流程
        
        Args:
            media_info: 电影媒体信息
        """
        try:
            # 获取优先级 provider 信息
            provider_id = media_info.get('selected_provider_id')
            provider_type = media_info.get('selected_provider_type', 'tmdb')
            
            movie_title = media_info.get('original_title') or media_info.get('title')
            year = media_info.get('year', '')
            
            logger.info(f"🎬 开始电影智能管理: {movie_title} ({year}) ({provider_type.upper()}: {provider_id})")
            
            # 1. 检查缓存库中的电影，使用电影名称进行匹配
            library_data = await get_library_data()
            if not library_data:
                logger.warning("⚠️ 无法获取影视库数据")
                return
            
            matches = search_video_by_keyword(library_data, movie_title, media_type='movie')
            
            # 电影严格匹配策略：优先完全匹配的标题
            exact_matches = [match for match in matches 
                           if match.get('title', '').lower() == movie_title.lower()]
            
            if not exact_matches:
                # 未找到精确匹配：使用优先级 provider ID 自动导入电影
                if provider_id:
                    logger.info(f"📥 未找到匹配的电影，开始自动导入: {movie_title} ({year}) 使用 {provider_type.upper()} ID")
                    await self._import_movie_by_provider(provider_id, provider_type)
                else:
                    logger.warning(f"⚠️ 无法导入电影，缺少有效的 provider ID: {movie_title}")
            else:
                # 存在匹配项：使用refresh功能更新电影数据
                selected_match = exact_matches[0]
                logger.info(f"🔄 找到匹配的电影，开始刷新: {selected_match.get('title', movie_title)}")
                
                # 获取源列表进行刷新
                anime_id = selected_match.get('animeId')
                if anime_id:
                    sources_response = call_danmaku_api('GET', f'/library/anime/{anime_id}/sources')
                    if sources_response and sources_response.get('success'):
                        sources = sources_response.get('data', [])
                        if sources:
                            source_id = sources[0].get('sourceId')
                            if source_id:
                                await self._refresh_movie(source_id)
                            else:
                                logger.error(f"❌ 无法获取源ID: {selected_match.get('title')}")
                        else:
                            logger.warning(f"⚠️ 未找到可用源: {selected_match.get('title')}")
                    else:
                        logger.error(f"❌ 获取源列表失败: {selected_match.get('title')}")
                else:
                    logger.error(f"❌ 无法获取动漫ID: {selected_match.get('title')}")
                    
        except Exception as e:
            logger.error(f"❌ 电影智能管理处理失败: {e}", exc_info=True)
    
    async def _process_tv_management(self, media_info: Dict[str, str]):
        """处理电视剧智能管理流程
        
        Args:
            media_info: 电视剧媒体信息
        """
        try:
            # 获取优先级 provider 信息
            provider_id = media_info.get('selected_provider_id')
            provider_type = media_info.get('selected_provider_type', 'tmdb')
            
            series_name = media_info.get('series_name') or media_info.get('title')
            season = media_info.get('season')
            episode = media_info.get('episode')
            year = media_info.get('year', '')
            
            if not series_name:
                logger.info("ℹ️ 电视剧缺少剧集名称，跳过智能管理")
                return
            
            # 确保season和episode是整数类型
            try:
                season = int(season) if season else 0
                episode = int(episode) if episode else 0
            except (ValueError, TypeError):
                logger.warning(f"⚠️ 无效的季集编号: season={season}, episode={episode}")
                season = 0
                episode = 0
            
            logger.info(f"🤖 开始电视剧智能管理: {series_name} {'S' + str(season).zfill(2) if season else ''}{('E' + str(episode).zfill(2)) if episode else ''} ({provider_type.upper()}: {provider_id})")
            
            # 1. 检查缓存库中的影视库，使用series_name和季度进行匹配
            library_data = await get_library_data()
            if not library_data:
                logger.warning("⚠️ 无法获取影视库数据")
                return

            # 使用剧名搜索电视剧类型的内容
            matches = search_video_by_keyword(library_data, series_name, 'tv_series')
            logger.info(f"📊 剧名搜索结果: {len(matches)} 个")
            
            # 计算匹配分数并筛选，重点关注season字段匹配
            season_matches = []
            for match in matches:
                match_title = match.get('title', '').lower()
                match_season = match.get('season', '')
                series_name_lower = series_name.lower()
                score = 0
                
                # 名称匹配评分
                if series_name_lower == match_title:
                    score += 100  # 完全匹配
                elif series_name_lower in match_title:
                    score += 70   # 包含匹配
                elif match_title in series_name_lower:
                    score += 50   # 被包含匹配
                    
                # 季度字段匹配评分（使用专门的season字段）
                if season and match_season:
                    try:
                        match_season_num = int(match_season)
                        if match_season_num == season:
                            score += 100  # 季度完全匹配
                            logger.debug(f"✅ 季度完全匹配: {match_title} S{season}")
                        elif abs(match_season_num - season) <= 1:
                            score += 50   # 季度相近匹配
                            logger.debug(f"⚠️ 季度相近匹配: {match_title} S{match_season_num} vs S{season}")
                    except (ValueError, TypeError):
                        # 如果season字段不是数字，尝试字符串匹配
                        if str(season) in str(match_season):
                            score += 80
                            logger.debug(f"📝 季度字符串匹配: {match_title} season={match_season}")
                elif not season and not match_season:
                    # 都没有季度信息，给予基础分数
                    score += 20
                        
                # 年份匹配评分
                if year:
                    match_year = match.get('year', '')
                    if match_year and str(year) == str(match_year):
                        score += 30
                    
                if score > 60:  # 只添加高匹配度的结果
                    season_matches.append({'match': match, 'score': score})
                    logger.debug(f"📊 匹配项: {match_title} (season={match_season}) 分数={score}")
                    
            # 按匹配分数排序
            season_matches.sort(key=lambda x: x['score'], reverse=True)
            season_matches = [item['match'] for item in season_matches]
            
            logger.info(f"📊 Library匹配结果: 找到 {len(season_matches)} 个匹配项（基于season字段匹配）")
            if season_matches:
                for i, match in enumerate(season_matches[:3]):  # 只显示前3个
                    logger.info(f"  {i+1}. {match.get('title')} (season={match.get('season')}, ID: {match.get('animeId')})")
                        
            # 检查是否有完全匹配的季度
            exact_season_match = False
            if season_matches and season:
                for match in season_matches:
                    match_season = match.get('season', '')
                    try:
                        if int(match_season) == season:
                            exact_season_match = True
                            break
                    except (ValueError, TypeError):
                        if str(season) in str(match_season):
                            exact_season_match = True
                            break
            
            # 如果没有找到季度匹配、没有完全匹配的季度或未匹配到具体集数，尝试通过TMDB API搜索
            should_search_tmdb = (
                not season_matches or 
                (season and not exact_season_match) or 
                not episode
            ) and not provider_id
            
            if should_search_tmdb:
                logger.info(f"🔍 触发TMDB搜索原因: 无匹配项={not season_matches}, 季度不匹配={season and not exact_season_match}, 无集数={not episode}")
                
                # 先检查缓存
                cached_result = self._get_cached_tmdb_result(series_name)
                tmdb_search_result = None
                
                if cached_result:
                    logger.info(f"💾 使用缓存的TMDB结果: {series_name}")
                    tmdb_search_result = cached_result
                else:
                    logger.info(f"🔍 开始TMDB搜索: {series_name} ({year if year else '年份未知'})")
                    tmdb_search_result = search_tv_series_by_name_year(series_name, year)
                    
                    if tmdb_search_result:
                        # 缓存搜索结果
                        self._cache_tmdb_result(series_name, tmdb_search_result)
                
                if tmdb_search_result:
                    # 增强的匹配验证
                    match_score = self._calculate_match_score(tmdb_search_result, series_name, year, season)
                    logger.info(f"📊 TMDB匹配评分: {tmdb_search_result.get('name')} ({tmdb_search_result.get('year', 'N/A')}) - {match_score}分")
                    
                    if match_score >= 70:  # 设置合理的匹配阈值
                        found_tmdb_id = tmdb_search_result.get('tmdb_id')
                        logger.info(f"✅ TMDB搜索匹配成功: {tmdb_search_result.get('name')} - 匹配分数: {match_score}")
                        logger.info(f"📥 开始自动导入: {series_name} S{season} (TMDB: {found_tmdb_id})")
                        await self._import_episodes_by_provider(found_tmdb_id, 'tmdb', season, [episode, episode + 1] if episode else None)
                        return True
                    else:
                        logger.info(f"❌ TMDB搜索结果匹配度不足: {tmdb_search_result.get('name')} - 匹配分数: {match_score}")
                else:
                    logger.info(f"❌ TMDB搜索未找到结果: {series_name}")
            
            # 如果通过季度匹配到多个结果，执行严格匹配策略
            final_matches = []
            if season_matches:
                # 严格匹配：完全匹配剧集名称
                for match in season_matches:
                    match_title = match.get('title', '').lower()
                    # 移除季度信息后进行比较
                    clean_match_title = match_title.replace(f'season {season}', '').replace(f's{season}', '')\
                                      .replace(f'第{season}季', '').replace(f'第{season}部', '').strip()
                    clean_series_name = series_name.lower().strip()
                    
                    if clean_match_title == clean_series_name:
                        final_matches.append(match)
                        break  # 找到完全匹配就停止
                
                # 如果没有完全匹配，使用第一个季度匹配结果
                if not final_matches:
                    final_matches = [season_matches[0]]
            else:
                # 如果没有季度匹配，尝试完全匹配
                for match in matches:
                    match_title = match.get('title', '').lower().strip()
                    if match_title == series_name.lower().strip():
                        final_matches.append(match)
                        break
            
            if not final_matches:
                # 未找到匹配项：检查是否有 provider ID 进行自动导入
                if provider_id:
                    logger.info(f"📥 未找到匹配项，开始自动导入: {series_name} S{season} ({provider_type.upper()}: {provider_id})")
                    await self._import_episodes_by_provider(provider_id, provider_type, season, [episode, episode + 1] if episode else None)
                else:
                    # 尝试通过TMDB API搜索获取TMDB ID
                    logger.info(f"🔍 未找到匹配项且缺少 provider ID，尝试通过TMDB搜索: {series_name} ({year})")
                    tmdb_search_result = search_tv_series_by_name_year(series_name, year)
                    
                    if tmdb_search_result:
                        # 验证搜索结果是否匹配
                        if validate_tv_series_match(tmdb_search_result, series_name, year, season, episode):
                            found_tmdb_id = tmdb_search_result.get('tmdb_id')
                            logger.info(f"✅ TMDB搜索成功，找到匹配的剧集: {tmdb_search_result.get('name')} (ID: {found_tmdb_id})")
                            logger.info(f"📥 开始自动导入: {series_name} S{season} (TMDB: {found_tmdb_id})")
                            await self._import_episodes_by_provider(found_tmdb_id, 'tmdb', season, [episode, episode + 1] if episode else None)
                        else:
                            logger.warning(f"⚠️ TMDB搜索结果验证失败: {series_name}")
                            logger.debug(f"💡 建议: 请检查剧集名称和年份是否正确，或在Emby中添加正确的TMDB刮削信息")
                    else:
                        logger.info(f"ℹ️ TMDB搜索未找到匹配结果: {series_name} ({year})")
                        logger.debug(f"💡 建议: 请检查剧集名称和年份是否正确，或在Emby中添加TMDB刮削信息")
            else:
                # 存在匹配项：使用refresh功能更新
                selected_match = final_matches[0]
                logger.info(f"🔄 找到匹配项，开始刷新: {selected_match.get('title', series_name)} S{season}")
                
                # 获取源列表进行刷新
                anime_id = selected_match.get('animeId')
                if anime_id:
                    sources_response = call_danmaku_api('GET', f'/library/anime/{anime_id}/sources')
                    if sources_response and sources_response.get('success'):
                        sources = sources_response.get('data', [])
                        if sources:
                            source_id = sources[0].get('sourceId')
                            if source_id:
                                # 传递剧集名称和年份，用于TMDB搜索
                                await self._refresh_episodes(source_id, [episode, episode + 1], tmdb_id, season, series_name, year)
                            else:
                                logger.error(f"❌ 无法获取源ID: {selected_match.get('title')}")
                        else:
                            logger.warning(f"⚠️ 未找到可用源: {selected_match.get('title')}")
                    else:
                        logger.error(f"❌ 获取源列表失败: {selected_match.get('title')}")
                else:
                    logger.error(f"❌ 无法获取动漫ID: {selected_match.get('title')}")
                    
        except Exception as e:
            logger.error(f"❌ 电视剧智能管理处理失败: {e}", exc_info=True)
    
    def _calculate_match_score(self, tmdb_result: dict, series_name: str, year: Optional[str], season: Optional[int]) -> int:
        """计算TMDB搜索结果的匹配分数
        
        Args:
            tmdb_result: TMDB搜索结果
            series_name: 剧集名称
            year: 年份
            season: 季度
            
        Returns:
            匹配分数 (0-200)
        """
        import time
        
        score = 0
        tmdb_name = tmdb_result.get('name', '').lower()
        tmdb_original_name = tmdb_result.get('original_name', '').lower()
        series_name_lower = series_name.lower()
        
        # 名称匹配评分 (最高100分)
        if series_name_lower == tmdb_name or series_name_lower == tmdb_original_name:
            score += 100  # 完全匹配
        elif series_name_lower in tmdb_name or series_name_lower in tmdb_original_name:
            score += 70   # 包含匹配
        elif tmdb_name in series_name_lower or tmdb_original_name in series_name_lower:
            score += 50   # 被包含匹配
        
        # 年份匹配评分 (最高30分)
        if year and tmdb_result.get('year'):
            tmdb_year = int(tmdb_result.get('year'))
            input_year = int(year)
            if tmdb_year == input_year:
                score += 30  # 年份完全匹配
            elif abs(tmdb_year - input_year) <= 1:
                score += 15  # 年份相差1年
        
        # 季度验证评分 (最高20分)
        if season and tmdb_result.get('number_of_seasons'):
            number_of_seasons = tmdb_result.get('number_of_seasons', 0)
            if number_of_seasons >= season:
                score += 20  # 季度数量合理
        
        return score
    
    def _cache_tmdb_result(self, series_name: str, tmdb_result: dict) -> None:
        """缓存TMDB搜索结果
        
        Args:
            series_name: 剧集名称
            tmdb_result: TMDB搜索结果
        """
        import time
        
        cache_key = series_name.lower().strip()
        self._tmdb_cache[cache_key] = {
            'result': tmdb_result,
            'timestamp': time.time()
        }
        logger.debug(f"💾 缓存TMDB搜索结果: {series_name} -> {tmdb_result.get('name')}")
    
    def _get_cached_tmdb_result(self, series_name: str) -> Optional[dict]:
        """获取缓存的TMDB搜索结果
        
        Args:
            series_name: 剧集名称
            
        Returns:
            缓存的TMDB结果，如果不存在或过期则返回None
        """
        import time
        
        cache_key = series_name.lower().strip()
        cached = self._tmdb_cache.get(cache_key)
        
        if cached:
            # 检查缓存是否过期 (24小时)
            if time.time() - cached['timestamp'] < 86400:
                logger.debug(f"💾 使用缓存的TMDB结果: {series_name}")
                return cached['result']
            else:
                # 清理过期缓存
                del self._tmdb_cache[cache_key]
                logger.debug(f"🗑️ 清理过期TMDB缓存: {series_name}")
        
        return None
    
    async def _import_movie_by_provider(self, provider_id: str, provider_type: str = 'tmdb'):
        """使用优先级 provider 导入单个电影
        
        Args:
            provider_id: Provider ID (tmdb_id, tvdb_id, 或 imdb_id)
            provider_type: Provider 类型 ('tmdb', 'tvdb', 'imdb')
        """
        try:
            logger.info(f"📥 开始导入电影 ({provider_type.upper()}: {provider_id})")
            
            # 调用导入API
            import_params = {
                "searchType": provider_type,
                "searchTerm": provider_id
            }
            
            response = call_danmaku_api('POST', '/import/auto', params=import_params)
            
            if response and response.get('success'):
                logger.info(f"✅ 电影导入成功 ({provider_type.upper()}: {provider_id})")
            else:
                error_msg = response.get('message', '未知错误') if response else '请求失败'
                logger.error(f"❌ 电影导入失败 ({provider_type.upper()}: {provider_id}): {error_msg}")
                
        except Exception as e:
            logger.error(f"❌ 导入电影时发生错误 ({provider_type.upper()}: {provider_id}): {e}", exc_info=True)
    
    async def _import_movie(self, tmdb_id: str):
        """导入单个电影 (兼容性方法)
        
        Args:
            tmdb_id: TMDB电影ID
        """
        await self._import_movie_by_provider(tmdb_id, 'tmdb')
    
    async def _refresh_movie(self, source_id: str):
        """刷新电影数据
        
        Args:
            source_id: 源ID
        """
        try:
            logger.info(f"🔄 开始刷新电影 (源ID: {source_id})")
            
            # 先获取源的分集列表来获取episodeId
            episodes_response = call_danmaku_api('GET', f'/library/source/{source_id}/episodes')
            if not episodes_response or not episodes_response.get('success'):
                logger.error(f"❌ 获取电影分集列表失败 (源ID: {source_id})")
                return
            
            source_episodes = episodes_response.get('data', [])
            if not source_episodes:
                logger.warning(f"⚠️ 电影源暂无分集信息 (源ID: {source_id})")
                return
            
            # 电影默认只取第一个分集的ID去刷新
            first_episode = source_episodes[0]
            episode_id = first_episode.get('episodeId')
            fetched_at = first_episode.get('fetchedAt')
            
            if not episode_id:
                logger.error(f"❌ 未找到电影的episodeId (源ID: {source_id})")
                return
            
            # 检查时间段判断机制：入库时间是否早于24小时
            if fetched_at:
                try:
                    # 解析fetchedAt时间（ISO 8601格式）并转换为配置的时区
                    fetched_time = datetime.fromisoformat(fetched_at.replace('Z', '+00:00'))
                    fetched_time_local = fetched_time.astimezone(self.timezone)
                    current_time_local = datetime.now(self.timezone)
                    time_diff = current_time_local - fetched_time_local
                    
                    if time_diff < timedelta(hours=24):
                        logger.info(f"⏰ 电影入库时间在24小时内 ({time_diff}），跳过刷新 (源ID: {source_id}) [时区: {self.timezone}]")
                        return
                    else:
                        logger.info(f"⏰ 电影入库时间超过24小时 ({time_diff}），执行刷新 (源ID: {source_id}) [时区: {self.timezone}]")
                except Exception as e:
                    logger.warning(f"⚠️ 解析入库时间失败，继续执行刷新: {e}")
            else:
                logger.info(f"ℹ️ 未找到入库时间信息，继续执行刷新 (源ID: {source_id})")
            
            logger.info(f"🔄 刷新电影分集 (episodeId: {episode_id})")
            
            # 使用episodeId刷新电影
            response = call_danmaku_api(
                method="POST",
                endpoint=f"/library/episode/{episode_id}/refresh"
            )
            
            if response and response.get('success'):
                logger.info(f"✅ 电影刷新成功 (源ID: {source_id})")
            else:
                error_msg = response.get('message', '未知错误') if response else '请求失败'
                logger.error(f"❌ 电影刷新失败 (源ID: {source_id}): {error_msg}")
                
        except Exception as e:
            logger.error(f"❌ 刷新电影时发生错误 (源ID: {source_id}): {e}", exc_info=True)
    
    async def _import_episodes_by_provider(self, provider_id: str, provider_type: str, season: int, episodes: list):
        """根据provider类型导入指定集数
        
        Args:
            provider_id: Provider ID (TMDB/TVDB/IMDB)
            provider_type: Provider类型 ('tmdb', 'tvdb', 'imdb')
            season: 季度
            episodes: 集数列表
        """
        if not episodes:
            logger.warning(f"⚠️ 集数列表为空，跳过导入: {provider_type.upper()} {provider_id} S{season}")
            return
        
        # 根据provider类型设置搜索参数
        search_type_map = {
            'tmdb': 'tmdb',
            'tvdb': 'tvdb', 
            'imdb': 'imdb'
        }
        
        search_type = search_type_map.get(provider_type.lower(), 'tmdb')
        
        # 获取详细信息进行验证（仅TMDB支持）
        max_episodes = 0
        try:
            if provider_type.lower() == 'tmdb':
                tmdb_info = get_tmdb_media_details(provider_id, 'tv_series')
                if tmdb_info:
                    logger.info(f"📺 准备导入剧集: {tmdb_info.get('name', 'Unknown')} ({tmdb_info.get('year', 'N/A')})")
                    
                    # 验证季度有效性
                    seasons = tmdb_info.get('seasons', [])
                    valid_season = None
                    for s in seasons:
                        if s.get('season_number') == season:
                            valid_season = s
                            break
                    
                    if not valid_season:
                        logger.error(f"❌ 无效的季度: S{season}，可用季度: {[s.get('season_number') for s in seasons]}")
                        return
                    
                    max_episodes = valid_season.get('episode_count', 0)
                    logger.info(f"📊 季度信息: S{season} 共{max_episodes}集")
                else:
                    logger.warning(f"⚠️ 无法获取TMDB详细信息: {provider_id}，继续尝试导入")
            else:
                logger.info(f"📺 准备导入剧集: {provider_type.upper()} {provider_id} S{season}")
        except Exception as e:
            logger.warning(f"⚠️ 验证{provider_type.upper()}信息时出错: {e}，继续尝试导入")
        
        success_count = 0
        failed_count = 0
        
        try:
            for episode in episodes:
                if episode is None:
                    continue
                    
                # 确保episode是整数类型
                try:
                    episode_num = int(episode) if isinstance(episode, str) else episode
                    if episode_num <= 0:
                        logger.warning(f"⚠️ 跳过无效集数: {episode_num}")
                        continue
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ 跳过无效集数格式: {episode}")
                    continue
                
                # 验证集数是否超出范围（仅TMDB支持）
                if provider_type.lower() == 'tmdb' and max_episodes > 0 and episode_num > max_episodes:
                    logger.warning(f"⚠️ 集数超出范围: S{season}E{episode_num} > {max_episodes}集，跳过")
                    continue
                
                # 构建导入参数
                import_params = {
                    "searchType": search_type,
                    "searchTerm": provider_id,
                    "mediaType": "tv_series",
                    "season": season,
                    "episode": episode_num
                }
                
                logger.info(f"🚀 开始导入: {provider_type.upper()} {provider_id} S{season:02d}E{episode_num:02d}")
                
                # 调用导入API
                try:
                    response = call_danmaku_api(
                        method="POST",
                        endpoint="/import/auto",
                        params=import_params
                    )
                    
                    if response and response.get("success"):
                        success_count += 1
                        logger.info(f"✅ 导入成功: S{season:02d}E{episode_num:02d}")
                    else:
                        failed_count += 1
                        error_msg = response.get('message', '未知错误') if response else '请求失败'
                        logger.warning(f"⚠️ 导入失败: S{season:02d}E{episode_num:02d} - {error_msg}")
                        
                except Exception as api_error:
                    failed_count += 1
                    logger.error(f"❌ 导入API调用异常: S{season:02d}E{episode_num:02d} - {api_error}")
            
            # 输出导入统计
            total_episodes = success_count + failed_count
            if total_episodes > 0:
                logger.info(f"📊 导入完成: 成功 {success_count}/{total_episodes} 集")
                if failed_count > 0:
                    logger.warning(f"⚠️ {failed_count} 集导入失败，请检查日志")
                    
        except Exception as e:
            logger.error(f"❌ 导入集数异常: {e}", exc_info=True)
    
    async def _import_episodes(self, tmdb_id: str, season: int, episodes: list):
        """导入指定集数（兼容性方法）
        
        Args:
            tmdb_id: TMDB ID
            season: 季度
            episodes: 集数列表
        """
        await self._import_episodes_by_provider(tmdb_id, 'tmdb', season, episodes)
    

    

     
    def _get_priority_provider_info(self, media_info: Dict[str, Any]) -> tuple:
        """
        获取优先级Provider信息 (tmdb > tvdb > imdb)
        
        Args:
            media_info: 已提取的媒体信息（包含provider ID）
            
        Returns:
            tuple: (provider_type, provider_id, search_type)
        """
        # 按优先级检查：tmdb > tvdb > imdb
        tmdb_id = media_info.get('tmdb_id')
        if tmdb_id:
            return 'tmdb', tmdb_id, 'tmdb'
            
        tvdb_id = media_info.get('tvdb_id')
        if tvdb_id:
            return 'tvdb', tvdb_id, 'tvdb'
            
        imdb_id = media_info.get('imdb_id')
        if imdb_id:
            return 'imdb', imdb_id, 'imdb'
            
        return None, None, None
    
    async def _refresh_episodes(self, source_id: str, episodes: list, tmdb_id: Optional[str], season_num: int, series_name: Optional[str] = None, year: Optional[str] = None):
        """刷新指定集数
        
        Args:
            source_id: 源ID
            episodes: 集数列表
            tmdb_id: TMDB ID（可选，为None时尝试通过TMDB搜索获取）
            season_num: 季度号
            series_name: 剧集名称（用于TMDB搜索）
            year: 年份（用于TMDB搜索）
        """
        try:
            # 先获取源的分集列表来获取episodeId
            episodes_response = call_danmaku_api('GET', f'/library/source/{source_id}/episodes')
            if not episodes_response or not episodes_response.get('success'):
                logger.error(f"❌ 获取分集列表失败: source_id={source_id}")
                return
            
            source_episodes = episodes_response.get('data', [])
            if not source_episodes:
                logger.warning(f"⚠️ 源暂无分集信息: source_id={source_id}")
                return
            
            # 创建集数索引到集信息的映射（包含episodeId和fetchedAt）
            episode_map = {}
            for ep in source_episodes:
                if ep.get('episodeId'):
                    episode_map[ep.get('episodeIndex')] = {
                        'episodeId': ep.get('episodeId'),
                        'fetchedAt': ep.get('fetchedAt')
                    }
            
            for episode in episodes:
                episode_info = episode_map.get(episode)
                if not episode_info:
                    # 当集数不存在时，尝试导入该集
                    current_tmdb_id = tmdb_id
                    
                    # 如果没有TMDB ID，尝试通过剧集名称搜索获取
                    if not current_tmdb_id and series_name:
                        logger.info(f"🔍 未找到第{episode}集且缺少TMDB ID，尝试通过TMDB搜索: {series_name} ({year})")
                        tmdb_search_result = search_tv_series_by_name_year(series_name, year)
                        
                        if tmdb_search_result:
                            # 验证搜索结果是否匹配
                            if validate_tv_series_match(tmdb_search_result, series_name, year, season_num, episode):
                                current_tmdb_id = tmdb_search_result.get('tmdb_id')
                                logger.info(f"✅ TMDB搜索成功，找到匹配的剧集: {tmdb_search_result.get('name')} (ID: {current_tmdb_id})")
                            else:
                                logger.warning(f"⚠️ TMDB搜索结果验证失败: {series_name}")
                        else:
                            logger.info(f"ℹ️ TMDB搜索未找到匹配结果: {series_name} ({year})")
                    
                    if current_tmdb_id:
                        logger.warning(f"⚠️ 未找到第{episode}集的episodeId，尝试导入")
                        # 当集数不存在且有TMDB ID时，尝试导入该集
                        await self._import_single_episode(current_tmdb_id, season_num, episode)
                    else:
                        logger.info(f"ℹ️ 未找到第{episode}集的episodeId且无法获取TMDB ID，跳过导入")
                    continue
                
                episode_id = episode_info['episodeId']
                fetched_at = episode_info['fetchedAt']
                
                # 检查时间段判断机制：入库时间是否早于24小时
                if fetched_at:
                    try:
                        # 解析fetchedAt时间（ISO 8601格式）并转换为配置的时区
                        fetched_time = datetime.fromisoformat(fetched_at.replace('Z', '+00:00'))
                        fetched_time_local = fetched_time.astimezone(self.timezone)
                        current_time_local = datetime.now(self.timezone)
                        time_diff = current_time_local - fetched_time_local
                        
                        if time_diff < timedelta(hours=24):
                            logger.info(f"⏰ 第{episode}集入库时间在24小时内 ({time_diff}），跳过刷新 [时区: {self.timezone}]")
                            continue
                        else:
                            logger.info(f"⏰ 第{episode}集入库时间超过24小时 ({time_diff}），执行刷新 [时区: {self.timezone}]")
                    except Exception as e:
                        logger.warning(f"⚠️ 解析第{episode}集入库时间失败，继续执行刷新: {e}")
                else:
                    logger.info(f"ℹ️ 第{episode}集未找到入库时间信息，继续执行刷新")
                
                logger.info(f"🔄 刷新集数: E{episode:02d} (episodeId: {episode_id})")
                
                # 使用新的API端点刷新指定集数
                response = call_danmaku_api(
                    method="POST",
                    endpoint=f"/library/episode/{episode_id}/refresh"
                )
                
                if response and response.get("success"):
                    logger.info(f"✅ 集数刷新成功: E{episode:02d}")
                else:
                    logger.warning(f"⚠️ 集数刷新失败: E{episode:02d}")
                    
        except Exception as e:
            logger.error(f"❌ 刷新集数异常: {e}")
    
    async def _import_single_episode(self, tmdb_id: str, season_num: int, episode: int):
        """导入单个集数
        
        Args:
            tmdb_id: TMDB ID
            season_num: 季度号
            episode: 集数
        """
        try:
            # 构建导入参数
            import_params = {
                "searchType": "tmdb",
                "searchTerm": str(tmdb_id),
                "mediaType": "tv_series",
                "importMethod": "auto",
                "season": season_num,
                "episode": episode
            }
            
            logger.info(f"🚀 开始导入单集: TMDB {tmdb_id} S{season_num:02d}E{episode:02d}")
            
            # 调用导入API
            response = call_danmaku_api(
                method="POST",
                endpoint="/import/auto",
                params=import_params
            )
            
            if response and response.get("success"):
                logger.info(f"✅ 单集导入成功: S{season_num:02d}E{episode:02d}")
            else:
                logger.info(f"ℹ️ 单集可能不存在或已导入: S{season_num:02d}E{episode:02d}")
                
        except Exception as e:
            logger.error(f"❌ 导入单集异常: {e}")


# 全局webhook处理器实例
webhook_handler = WebhookHandler()


def set_bot_instance(bot: Bot):
    """设置Bot实例
    
    Args:
        bot: Telegram Bot实例
    """
    global webhook_handler
    webhook_handler.bot = bot
    logger.info("🔌 Webhook handler bot instance set")