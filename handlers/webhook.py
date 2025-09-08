import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from telegram import Bot
from config import ConfigManager
from handlers.import_url import get_library_data, search_video_by_keyword
from utils.tmdb_api import get_tmdb_media_details, search_tv_series_by_name_year, validate_tv_series_match
from utils.api import call_danmaku_api

logger = logging.getLogger(__name__)

class WebhookHandler:
    """Webhook处理器，用于处理来自Emby等媒体服务器的通知"""
    
    def __init__(self, bot: Optional[Bot] = None):
        self.config = ConfigManager()
        self.bot = bot
        
    def validate_api_key(self, provided_key: str) -> bool:
        """验证API密钥"""
        if not self.config.webhook.enabled:
            logger.warning("🔒 Webhook功能未启用，拒绝请求")
            return False
            
        if not provided_key:
            logger.warning("🔒 缺少API密钥")
            return False
            
        if provided_key != self.config.webhook.api_key:
            logger.warning(f"🔒 API密钥验证失败: {provided_key[:8]}...")
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
            
            # 提取TMDB ID信息（Emby刮削后的元数据）
            provider_ids = item.get('ProviderIds', {})
            tmdb_id = provider_ids.get('Tmdb') or provider_ids.get('TheMovieDb')
            imdb_id = provider_ids.get('Imdb')
            tvdb_id = provider_ids.get('Tvdb') or provider_ids.get('TheTVDB')
            
            # 调试日志：显示提供商ID信息
            logger.debug(f"🔍 媒体提供商ID信息: {provider_ids}")
            logger.debug(f"🎯 提取的TMDB ID: {tmdb_id}, IMDB ID: {imdb_id}, TVDB ID: {tvdb_id}")
            
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
            tmdb_id = media_info.get('tmdb_id')
            media_type = media_info.get('type', '')
            title = media_info.get('title')
            
            # 详细检查缺失的信息
            missing_info = []
            if not tmdb_id:
                missing_info.append('TMDB ID')
            if not title:
                missing_info.append('标题')
            
            # 对于电视剧，如果缺少TMDB ID但有剧集名称，尝试通过名称搜索
            if not tmdb_id and media_type == 'Episode':
                series_name = media_info.get('series_name')
                year = media_info.get('year')
                if series_name:
                    logger.info(f"🔍 电视剧缺少TMDB ID，尝试通过剧集名称搜索: {series_name} ({year})")
                    # 这里可以调用TMDB搜索API来获取TMDB ID
                    # 暂时先记录日志，后续可以扩展搜索功能
                    logger.debug(f"📺 剧集信息: 名称='{series_name}', 年份='{year}', 季数='{media_info.get('season')}', 集数='{media_info.get('episode')}'")
            
            # 如果仍然缺少关键信息，跳过智能管理
            if not tmdb_id and not title:
                logger.info(f"ℹ️ 媒体缺少必要信息（{', '.join(missing_info)}），跳过智能管理")
                logger.debug(f"🔍 媒体信息详情: TMDB ID='{tmdb_id}', 标题='{title}', 类型='{media_type}'")
                return
            elif not tmdb_id:
                logger.info(f"⚠️ 媒体缺少TMDB ID但有标题信息，继续处理: {title}")
                logger.debug(f"🔍 媒体信息详情: TMDB ID='{tmdb_id}', 标题='{title}', 类型='{media_type}'")
            
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
            tmdb_id = media_info.get('tmdb_id')
            movie_title = media_info.get('original_title') or media_info.get('title')
            year = media_info.get('year', '')
            
            logger.info(f"🎬 开始电影智能管理: {movie_title} ({year}) (TMDB: {tmdb_id})")
            
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
                # 未找到精确匹配：使用TMDB ID自动导入电影
                logger.info(f"📥 未找到匹配的电影，开始自动导入: {movie_title} ({year})")
                await self._import_movie(tmdb_id)
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
            tmdb_id = media_info.get('tmdb_id')
            series_name = media_info.get('series_name') or media_info.get('title')
            season = media_info.get('season')
            episode = media_info.get('episode')
            year = media_info.get('year', '')
            
            if not series_name:
                logger.info("ℹ️ 电视剧缺少剧集名称，跳过智能管理")
                return
            
            # 确保season和episode是整数类型
            try:
                season_num = int(season) if season else 0
                episode_num = int(episode) if episode else 0
            except (ValueError, TypeError):
                logger.warning(f"⚠️ 无效的季集编号: season={season}, episode={episode}")
                season_num = 0
                episode_num = 0
            
            logger.info(f"🤖 开始电视剧智能管理: {series_name} S{season_num:02d}E{episode_num:02d} (TMDB: {tmdb_id})")
            
            # 1. 检查缓存库中的影视库，使用series_name和季度进行匹配
            library_data = await get_library_data()
            if not library_data:
                logger.warning("⚠️ 无法获取影视库数据")
                return
            
            matches = search_video_by_keyword(library_data, series_name, media_type='tv_series')
            
            # 优先匹配：名称 + 季度信息
            season_matches = []
            if season:
                for match in matches:
                    match_title = match.get('title', '').lower()
                    # 检查标题中是否包含季度信息
                    if (f"season {season}" in match_title or 
                        f"s{season}" in match_title or 
                        f"第{season}季" in match_title or
                        f"第{season}部" in match_title):
                        season_matches.append(match)
            
            # 如果通过季度匹配到多个结果，执行严格匹配策略
            if len(season_matches) > 1:
                exact_matches = [match for match in season_matches 
                               if match.get('title', '').lower() == series_name.lower()]
                final_matches = exact_matches if exact_matches else season_matches[:1]
            elif len(season_matches) == 1:
                final_matches = season_matches
            else:
                # 没有季度匹配，使用名称精确匹配
                exact_matches = [match for match in matches 
                               if match.get('title', '').lower() == series_name.lower()]
                final_matches = exact_matches
            
            if not final_matches:
                # 未找到匹配项：检查是否有TMDB ID进行自动导入
                if tmdb_id:
                    logger.info(f"📥 未找到匹配项，开始自动导入: {series_name} S{season_num} (TMDB: {tmdb_id})")
                    await self._import_episodes(tmdb_id, season_num, [episode_num, episode_num + 1])
                else:
                    # 尝试通过TMDB API搜索获取TMDB ID
                    logger.info(f"🔍 未找到匹配项且缺少TMDB ID，尝试通过TMDB搜索: {series_name} ({year})")
                    tmdb_search_result = search_tv_series_by_name_year(series_name, year)
                    
                    if tmdb_search_result:
                        # 验证搜索结果是否匹配
                        if validate_tv_series_match(tmdb_search_result, series_name, year, season_num, episode_num):
                            found_tmdb_id = tmdb_search_result.get('tmdb_id')
                            logger.info(f"✅ TMDB搜索成功，找到匹配的剧集: {tmdb_search_result.get('name')} (ID: {found_tmdb_id})")
                            logger.info(f"📥 开始自动导入: {series_name} S{season_num} (TMDB: {found_tmdb_id})")
                            await self._import_episodes(found_tmdb_id, season_num, [episode_num, episode_num + 1])
                        else:
                            logger.warning(f"⚠️ TMDB搜索结果验证失败，跳过自动导入: {series_name}")
                            logger.debug(f"💡 建议: 请在Emby中为该剧集添加TMDB刮削信息，或手动导入到弹幕库中")
                    else:
                        logger.info(f"ℹ️ TMDB搜索未找到匹配结果，无法自动导入: {series_name} S{season_num}")
                        logger.debug(f"💡 建议: 请在Emby中为该剧集添加TMDB刮削信息，或手动导入到弹幕库中")
            else:
                # 存在匹配项：使用refresh功能更新
                selected_match = final_matches[0]
                logger.info(f"🔄 找到匹配项，开始刷新: {selected_match.get('title', series_name)} S{season_num}")
                
                # 获取源列表进行刷新
                anime_id = selected_match.get('animeId')
                if anime_id:
                    sources_response = call_danmaku_api('GET', f'/library/anime/{anime_id}/sources')
                    if sources_response and sources_response.get('success'):
                        sources = sources_response.get('data', [])
                        if sources:
                            source_id = sources[0].get('sourceId')
                            if source_id:
                                # 只有在有TMDB ID时才传递，否则传递None跳过导入
                                await self._refresh_episodes(source_id, [episode_num, episode_num + 1], tmdb_id if tmdb_id else None, season_num)
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
    
    async def _import_movie(self, tmdb_id: str):
        """导入单个电影
        
        Args:
            tmdb_id: TMDB电影ID
        """
        try:
            logger.info(f"📥 开始导入电影 (TMDB: {tmdb_id})")
            
            # 调用导入API
            import_params = {
                "searchType": "tmdb",
                "searchTerm": tmdb_id
            }
            
            response = call_danmaku_api('POST', '/import/auto', params=import_params)
            
            if response and response.get('success'):
                logger.info(f"✅ 电影导入成功 (TMDB: {tmdb_id})")
            else:
                error_msg = response.get('message', '未知错误') if response else '请求失败'
                logger.error(f"❌ 电影导入失败 (TMDB: {tmdb_id}): {error_msg}")
                
        except Exception as e:
            logger.error(f"❌ 导入电影时发生错误 (TMDB: {tmdb_id}): {e}", exc_info=True)
    
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
            
            if not episode_id:
                logger.error(f"❌ 未找到电影的episodeId (源ID: {source_id})")
                return
            
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
    
    async def _import_episodes(self, tmdb_id: str, season: int, episodes: list):
        """导入指定集数
        
        Args:
            tmdb_id: TMDB ID
            season: 季度
            episodes: 集数列表
        """
        try:
            for episode in episodes:
                # 确保episode是整数类型
                episode_num = int(episode) if isinstance(episode, str) else episode
                
                # 构建导入参数
                import_params = {
                    "searchType": "tmdb",
                    "searchTerm": tmdb_id,
                    "mediaType": "tv_series",
                    "season": season,
                    "episode": episode_num
                }
                
                logger.info(f"🚀 开始导入: TMDB {tmdb_id} S{season:02d}E{episode_num:02d}")
                
                # 调用导入API
                response = call_danmaku_api(
                    method="POST",
                    endpoint="/import/auto",
                    params=import_params
                )
                
                if response and response.get("success"):
                    logger.info(f"✅ 导入成功: S{season:02d}E{episode_num:02d}")
                else:
                    logger.info(f"ℹ️ 集数可能不存在或已导入: S{season:02d}E{episode_num:02d}")
                    
        except Exception as e:
            logger.error(f"❌ 导入集数异常: {e}")
    

    

     
    async def _refresh_episodes(self, source_id: str, episodes: list, tmdb_id: Optional[str], season_num: int):
        """刷新指定集数
        
        Args:
            source_id: 源ID
            episodes: 集数列表
            tmdb_id: TMDB ID（可选，为None时跳过导入操作）
            season_num: 季度号
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
            
            # 创建集数索引到episodeId的映射
            episode_map = {ep.get('episodeIndex'): ep.get('episodeId') for ep in source_episodes if ep.get('episodeId')}
            
            for episode in episodes:
                episode_id = episode_map.get(episode)
                if not episode_id:
                    if tmdb_id:
                        logger.warning(f"⚠️ 未找到第{episode}集的episodeId，尝试导入")
                        # 当集数不存在且有TMDB ID时，尝试导入该集
                        await self._import_single_episode(tmdb_id, season_num, episode)
                    else:
                        logger.info(f"ℹ️ 未找到第{episode}集的episodeId且缺少TMDB ID，跳过导入")
                    continue
                
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