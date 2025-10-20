import logging
import asyncio
import uuid
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from telegram import Bot
from config import ConfigManager
from utils.api import call_danmaku_api

logger = logging.getLogger(__name__)

class TaskInfo:
    """任务数据结构"""
    def __init__(self, task_id: str, operation_type: str, media_info: Dict[str, Any], 
                 message_id: int, chat_id: str):
        self.task_id = task_id
        self.operation_type = operation_type  # 'import' or 'refresh'
        self.media_info = media_info
        self.message_id = message_id  # Telegram消息ID
        self.chat_id = chat_id  # Telegram聊天ID
        self.task_ids: List[str] = []  # API返回的taskId列表
        self.task_statuses: Dict[str, str] = {}  # {taskId: task_status}
        self.created_at = datetime.now()
        self.completed = False

class TaskPollingManager:
    """任务轮询管理器，用于处理taskId轮询和状态更新"""
    
    def __init__(self):
        self.config = ConfigManager()
        # 从环境变量读取时区配置，默认为Asia/Shanghai
        self.timezone = ZoneInfo(os.getenv('TZ', 'Asia/Shanghai'))
        
        # Bot实例，用于发送消息
        self.bot = None
        
        # taskId轮询相关数据结构
        self._tasks = {}  # 任务记录: {task_id: TaskInfo}
        self._import_tasks = {}  # 入库任务记录: {import_task_id: task_id}
        self._polling_active = False  # 轮询状态标志
        self._polling_task = None  # 轮询任务引用
        
    async def start_polling_if_needed(self, callback_bot=None):
        """启动轮询任务（如果尚未启动）
        
        Args:
            callback_bot: 已初始化的Bot实例（可选）
        """
        # 保存Bot实例以供轮询使用
        if callback_bot:
            self.bot = callback_bot
            
        if not self._polling_active and (self._tasks or self._import_tasks):
            self._polling_active = True
            self._polling_task = asyncio.create_task(self._polling_loop(callback_bot))
            logger.info(f"🔄 启动taskId轮询任务，当前有 {len(self._tasks)} 个任务，{len(self._import_tasks)} 个入库任务")
    
    async def _polling_loop(self, callback_bot=None):
        """轮询循环，每5秒检查一次taskId状态"""
        try:
            while self._polling_active and (self._tasks or self._import_tasks):
                # logger.info(f"🔄 开始轮询检查，当前有 {len(self._tasks)} 个任务，{len(self._import_tasks)} 个入库任务")
                
                # 首先处理入库任务，获取真实的taskId
                completed_import_tasks = []
                timeout_import_tasks = []
                current_time = datetime.now(self.timezone)
                
                for import_task_id, import_task_info in list(self._import_tasks.items()):
                    original_task = import_task_info['task']
                    start_time = import_task_info['start_time']
                    timeout_minutes = import_task_info.get('timeout_minutes', 60)
                    all_task_ids = import_task_info.get('all_task_ids', [import_task_id])
                    
                    # 检查是否超时（默认1小时）
                    elapsed_time = current_time - start_time
                    if elapsed_time > timedelta(minutes=timeout_minutes):
                        logger.warning(f"⏰ 入库任务 {import_task_id} 轮询超时（{elapsed_time}），自动取消")
                        timeout_import_tasks.append((import_task_id, original_task))
                        continue
                    
                    all_real_task_ids = []
                    all_tasks_completed = True
                    # 轮询所有入库任务的execution接口
                    for task_id in all_task_ids:
                        # logger.info(f"🔍 轮询入库任务execution: {task_id} (已运行 {elapsed_time})")
                        real_task_ids = await self._poll_import_task_execution(task_id)
                        if real_task_ids:
                            all_real_task_ids.extend(real_task_ids)
                            # logger.info(f"✅ 入库任务 {task_id} 获取到executionTaskIds: {real_task_ids}")
                        else:
                            # logger.info(f"⏳ 入库任务 {task_id} 仍在处理中，继续等待")
                            all_tasks_completed = False
                            
                    # 只有当所有入库任务的execution接口都执行完毕并获取到真实的taskId后，才创建新的任务
                    if all_tasks_completed and all_real_task_ids:
                        # 获取到所有executionTaskId，创建新的任务
                        new_task_id = str(uuid.uuid4())
                        new_task = TaskInfo(
                            task_id=new_task_id,
                            operation_type=original_task.operation_type,
                            media_info=original_task.media_info.copy(),
                            message_id=original_task.message_id,
                            chat_id=original_task.chat_id
                        )
                        new_task.task_ids.extend(all_real_task_ids)
                        
                        # 将新任务添加到任务队列
                        self._tasks[new_task_id] = new_task
                        logger.info(f"✅ 入库任务 {import_task_id} 解析完成，所有execution接口已执行完毕，创建新任务 {new_task_id}，executionTaskIds: {all_real_task_ids}")
                        completed_import_tasks.append(import_task_id)
                    elif all_tasks_completed:
                        # 所有任务都已完成但没有获取到任何taskId
                        logger.warning(f"⚠️ 入库任务 {import_task_id} 所有execution接口已执行完毕，但未获取到任何taskId")
                        completed_import_tasks.append(import_task_id)
                        timeout_import_tasks.append((import_task_id, original_task))
                        continue
                    
                    all_real_task_ids = []
                    all_tasks_completed = True
                    # 轮询所有入库任务的execution接口
                    for task_id in all_task_ids:
                        # logger.info(f"🔍 轮询入库任务execution: {task_id} (已运行 {elapsed_time})")
                        real_task_ids = await self._poll_import_task_execution(task_id)
                        if real_task_ids:
                            all_real_task_ids.extend(real_task_ids)
                            # logger.info(f"✅ 入库任务 {task_id} 获取到executionTaskIds: {real_task_ids}")
                        else:
                            # logger.info(f"⏳ 入库任务 {task_id} 仍在处理中，继续等待")
                            all_tasks_completed = False
                            
                    # 只有当所有入库任务的execution接口都执行完毕并获取到真实的taskId后，才创建新的任务
                    if all_tasks_completed and all_real_task_ids:
                        # 获取到所有executionTaskId，创建新的任务
                        new_task_id = str(uuid.uuid4())
                        new_task = TaskInfo(
                            task_id=new_task_id,
                            operation_type=original_task.operation_type,
                            media_info=original_task.media_info.copy(),
                            message_id=original_task.message_id,
                            chat_id=original_task.chat_id
                        )
                        new_task.task_ids.extend(all_real_task_ids)
                        
                        # 将新任务添加到任务队列
                        self._tasks[new_task_id] = new_task
                        # logger.info(f"✅ 入库任务 {import_task_id} 解析完成，所有execution接口已执行完毕，创建新任务 {new_task_id}，executionTaskIds: {all_real_task_ids}")
                        completed_import_tasks.append(import_task_id)
                    elif all_tasks_completed:
                        # 所有任务都已完成但没有获取到任何taskId
                        # logger.warning(f"⚠️ 入库任务 {import_task_id} 所有execution接口已执行完毕，但未获取到任何taskId")
                        completed_import_tasks.append(import_task_id)
                    # else:
                        # logger.info(f"⏳ 入库任务 {import_task_id} 仍有任务在处理中，继续等待")
                 
                # 处理超时任务
                for timeout_task_id, timeout_task in timeout_import_tasks:
                    try:
                        if callback_bot:
                            # 构建超时失败消息
                            media_info = timeout_task.media_info
                            media_name = self._get_clean_media_name(media_info)
                            media_type = "电影" if media_info.get('Type', '').lower() == 'movie' else "剧集"
                            timestamp = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S")
                            
                            # 构建通知消息
                            message_lines = [
                                f"🎬 **任务导入通知**",
                                f"",
                                f"📺 **媒体信息**",
                                f"• 名称: {media_name}",
                                f"• 类型: {media_type}",
                                f"• 操作: 导入",
                                f"• 状态: 🔄 入库中 → ❌ 失败",
                                f"• 时间: {timestamp}"
                            ]
                            
                            # 添加超时信息
                            message_lines.append(f"• 原因: 导入任务执行失败")
                            
                            message = "\n".join(message_lines)
                            
                            # 更新消息
                            await callback_bot.edit_message_text(
                                chat_id=timeout_task.chat_id,
                                message_id=timeout_task.message_id,
                                text=message,
                                parse_mode='Markdown'
                            )
                            
                            logger.info(f"📤 已发送超时失败通知: {timeout_task_id}")
                        else:
                            logger.warning(f"🤖 Bot实例未提供，无法发送超时失败通知: {timeout_task_id}")
                    except Exception as e:
                        logger.error(f"❌ 发送超时失败通知失败: {e}")
                    
                    completed_import_tasks.append(timeout_task_id)
                
                # 清理已完成和超时的入库任务
                for import_task_id in completed_import_tasks:
                    if import_task_id in self._import_tasks:
                        del self._import_tasks[import_task_id]
                        logger.info(f"🗑️ 清理入库任务: {import_task_id}")
                    else:
                        logger.warning(f"⚠️ 尝试清理不存在的入库任务: {import_task_id}")
                
                # 检查所有任务
                completed_tasks = []
                
                for task_id, task in list(self._tasks.items()):
                    if task.completed:
                        continue
                    
                    # 检查该任务的所有taskId
                    for tid in task.task_ids:
                        if tid not in task.task_statuses:
                            logger.info(f"🔍 轮询taskId: {tid}")
                            # 轮询该taskId的状态
                            task_data = await self._poll_task_status(tid)
                            if task_data:
                                task.task_statuses[tid] = task_data
                                task_status = task_data.get('status', 'unknown')
                                # logger.info(f"✅ taskId {tid} 状态更新: {task_status}")
                        
                    # 如果所有taskId都有了最终状态，标记为完成
                    if len(task.task_statuses) == len(task.task_ids):
                        task.completed = True
                        completed_tasks.append(task_id)
                        logger.info(f"🎉 任务 {task_id} 所有taskId已完成轮询")
                        
                        # 更新通知消息
                        await self._update_notification_message(task)
                
                # 清理已完成的任务
                for task_id in completed_tasks:
                    if task_id in self._tasks:
                        del self._tasks[task_id]
                        logger.info(f"🗑️ 清理已完成的任务: {task_id}")
                    else:
                        logger.warning(f"⚠️ 尝试清理不存在的任务: {task_id}")
                
                # 如果没有待处理的任务，停止轮询
                if not self._tasks and not self._import_tasks:
                    self._polling_active = False
                    logger.info("⏹️ 所有任务已完成，停止轮询")
                    break
                
                # 等待5秒后继续下一轮轮询
                await asyncio.sleep(5)
                
        except Exception as e:
            logger.error(f"❌ 轮询任务异常: {e}")
            logger.error(f"📊 异常时状态 - 普通任务: {len(self._tasks)}, 入库任务: {len(self._import_tasks)}")
            # 记录当前任务详情以便调试
            for task_id, task in self._tasks.items():
                logger.error(f"🔍 普通任务 {task_id}: task_ids={task.task_ids}, completed={task.completed}")
            for import_id, import_info in self._import_tasks.items():
                logger.error(f"🔍 入库任务 {import_id}: all_task_ids={import_info.get('all_task_ids', [])}")
            
            # 异常情况下清理所有任务状态，避免资源泄漏
            try:
                logger.warning("🧹 异常情况下清理任务状态")
                self._tasks.clear()
                self._import_tasks.clear()
                logger.info("✅ 任务状态清理完成")
            except Exception as cleanup_error:
                logger.error(f"❌ 清理任务状态失败: {cleanup_error}")
            finally:
                self._polling_active = False
    
    async def _poll_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """轮询单个taskId的状态
        
        Args:
            task_id: 要轮询的taskId
            
        Returns:
            task data dict if completed, None if still running
        """
        try:
            logger.debug(f"🔍 开始轮询taskId: {task_id}")
            # 在线程池中运行同步API调用，避免阻塞事件循环
            response = await asyncio.to_thread(
                call_danmaku_api,
                method="GET",
                endpoint=f"/tasks/{task_id}"
            )
            
            logger.debug(f"📡 API响应: {response}")
            
            if response and response.get("success"):
                # 新的返回结构: { "data": { "taskId": "string", "title": "string", "status": "string", "progress": 0, "description": "string", "createdAt": "2025-09-19T15:33:29.845Z" } }
                data = response.get('data', {})
                task_status = data.get('status')
                task_progress = data.get('progress', 0)
                task_title = data.get('title', '')
                
                logger.info(f"📊 任务状态: {task_status}, 进度: {task_progress}%, 标题: {task_title}")
                logger.debug(f"📋 完整data字段: {data}")
                
                # 检查任务是否完成（根据实际API返回的状态值调整）
                if task_status in ['completed', 'finished', 'success', '已完成', '完成', '成功', '已成功']:
                    logger.info(f"✅ taskId {task_id} 已完成")
                    return data  # 返回完整的任务数据
                elif task_status in ['failed', 'error', '失败', '已失败']:
                    logger.warning(f"❌ taskId {task_id} 执行失败")
                    return data  # 返回完整的任务数据
                else:
                    logger.debug(f"⏳ taskId {task_id} 仍在执行中，状态: {task_status}")
                    return None
            elif response and response.get("status_code") == 404:
                # 任务还未准备好，继续等待
                logger.debug(f"⏳ taskId {task_id} 返回404，任务尚未准备好")
                return None
            else:
                logger.warning(f"⚠️ 轮询taskId {task_id} 失败: {response}")
                        
        except Exception as e:
            logger.error(f"❌ 轮询taskId {task_id} 失败: {e}")
        
        return None
    
    async def _poll_import_task_execution(self, import_task_id: str) -> Optional[List[str]]:
        """轮询入库任务的execution接口获取真实的taskId列表
        
        Args:
            import_task_id: 入库操作返回的taskId
            
        Returns:
            List of real taskIds if available, None if still processing
        """
        try:
            # logger.debug(f"🔍 开始轮询入库任务execution: {import_task_id}")
            # 调用/tasks/{taskId}/execution接口
            response = await asyncio.to_thread(
                call_danmaku_api,
                method="GET",
                endpoint=f"/tasks/{import_task_id}/execution"
            )
            
            # logger.debug(f"📡 入库任务execution API响应: {response}")
            
            if response and response.get("success"):
                data = response.get('data', {})
                task_ids = []
                
                if isinstance(data, dict):
                    # 检查是否有多任务ID字段
                    if 'executionTaskIds' in data and isinstance(data['executionTaskIds'], list):
                        # 如果有多个executionTaskId
                        task_ids.extend(data['executionTaskIds'])
                    elif 'tasks' in data and isinstance(data['tasks'], list):
                        # 检查是否有tasks列表
                        for task in data['tasks']:
                            if isinstance(task, dict):
                                task_id = task.get('taskId', task.get('id'))
                                if task_id:
                                    task_ids.append(task_id)
                    else:
                        # 检查单个taskId字段
                        execution_task_id = data.get('executionTaskId')
                        if not execution_task_id:
                            execution_task_id = data.get('taskId')
                            if not execution_task_id:
                                execution_task_id = data.get('id')
                        if execution_task_id:
                            task_ids.append(execution_task_id)
                elif isinstance(data, str):
                    # 如果data直接是taskId字符串
                    task_ids.append(data)
                elif isinstance(data, list):
                    # 如果data直接是taskIds列表
                    task_ids.extend(data)
                
                if task_ids:
                    # logger.info(f"✅ 入库任务 {import_task_id} 获取到taskIds: {task_ids}")
                    # 确保所有taskId都是字符串
                    return [str(task_id) for task_id in task_ids]
                else:
                    # logger.debug(f"⏳ 入库任务 {import_task_id} 尚未生成executionTaskId")
                    return None
            elif response and response.get("status_code") == 404:
                # 任务还未准备好，继续等待
                # logger.debug(f"⏳ 入库任务 {import_task_id} 返回404，任务尚未准备好")
                return None
                        
        except Exception as e:
            logger.error(f"❌ 轮询入库任务execution {import_task_id} 失败: {e}")
        
        return None
    
    def _get_clean_media_name(self, media_info: Dict[str, Any]) -> str:
        """获取清理后的媒体名称
        
        Args:
            media_info: 媒体信息字典
            
        Returns:
            str: 清理后的媒体名称
        """
        # 优先使用TMDB或library匹配的名称
        name = (
            media_info.get('LibraryTitle') or 
            media_info.get('TMDBTitle') or 
            media_info.get('SeriesName') or 
            media_info.get('Title') or 
            media_info.get('Name') or 
            '未知媒体'
        )
        
        # 清理名称中的特殊字符和多余空格
        import re
        name = re.sub(r'[^\w\s\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\-\(\)\[\]\.]+', '', name)
        return name.strip()
    
    async def _update_notification_message(self, task: TaskInfo):
        """更新通知消息，添加状态信息
        
        Args:
            task: 任务信息
        """
        try:
            # 使用现有的TELEGRAM_BOT_TOKEN创建Bot实例
            callback_bot = Bot(token=self.config.telegram.bot_token)
            
            # 构建更新后的消息
            timestamp = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S")
            
            # 获取媒体基本信息
            media_info = task.media_info
            media_name = self._get_clean_media_name(media_info)
            media_type = "电影" if media_info.get('Type', '').lower() == 'movie' else "剧集"
            
            # 构建操作类型描述
            base_operation_text = "导入" if task.operation_type == "import" else "刷新"
            
            # 为剧集构建包含季集信息的操作描述
            operation_text = base_operation_text
            if media_info.get('Type', '').lower() in {'series', 'tv_series'}:
                season = media_info.get('Season')
                episodes = media_info.get('Episodes', [])
                
                if season and episodes:
                    # 构建季集信息字符串
                    episode_list = []
                    for ep in episodes:
                        episode_list.append(f"S{season}E{ep:02d}")
                    
                    if episode_list:
                        operation_text = f"{base_operation_text}{','.join(episode_list)}"
            
            # 构建通知消息
            message_lines = [
                f"🎬 **任务{base_operation_text}通知**",
                f"",
                f"📺 **媒体信息**",
                f"• 名称: {media_name}",
                f"• 类型: {media_type}",
                f"• 操作: {operation_text}",
                f"• 状态: 🔄 刷新中 → ✅ 处理完成" if task.operation_type == "refresh" else (f"• 状态: 🔄 入库中 → ✅ 处理完成" if task.operation_type == "import" else f"• 状态: ✅ 成功 → ✅ 处理完成"),
                f"• 时间: {timestamp}"
            ]
            
            # 添加剧集特有信息
            if media_info.get('Type', '').lower() in {'series', 'tv_series'}:
                if media_info.get('Season'):
                    message_lines.insert(-1, f"• 季度: S{media_info.get('Season')}")
                
                # 添加统计信息
                success_count = media_info.get('SuccessCount', 0)
                failed_count = media_info.get('FailedCount', 0)
                total_count = media_info.get('TotalCount', 0)
                skipped_count = media_info.get('SkippedCount', 0)
                
                if total_count > 0:
                    stats_parts = []
                    if success_count > 0:
                        stats_parts.append(f"成功{success_count}集")
                    if failed_count > 0:
                        stats_parts.append(f"失败{failed_count}集")
                    if skipped_count > 0:
                        stats_parts.append(f"跳过{skipped_count}集")
                    
                    if stats_parts:
                        message_lines.insert(-1, f"• 统计: {' / '.join(stats_parts)} (共{total_count}集)")
            
            # 添加Provider信息
            if media_info.get('ProviderType') and media_info.get('ProviderId'):
                message_lines.insert(-1, f"• Provider: {media_info.get('ProviderType').upper()} {media_info.get('ProviderId')}")
            elif media_info.get('SourceId'):
                message_lines.insert(-1, f"• 源ID: {media_info.get('SourceId')}")
            
            # 添加任务执行信息
            message_lines.extend([
                f"",
                f"⚙️ **任务执行信息**"
            ])
            
            # 检查是否有失败的任务
            has_failed_tasks = any(
                isinstance(task_data, dict) and task_data.get('status') in ['failed', 'error', '失败', '已失败']
                or isinstance(task_data, str) and task_data in ['failed', 'error', '失败', '已失败']
                for task_data in task.task_statuses.values()
            )
            
            # 显示所有任务的详细信息
            for task_id, task_data in task.task_statuses.items():
                if isinstance(task_data, dict):
                    status = task_data.get('status', 'unknown')
                    description = task_data.get('description', '')
                    progress = task_data.get('progress', 0)
                    
                    # 为不同状态添加视觉指示
                    status_icon = "✅" if status in ['completed', 'finished', 'success', '已完成', '完成', '成功', '已成功'] else "❌" if status in ['failed', 'error', '失败', '已失败'] else "🔄"
                    status_text = f"{status_icon} {status}"
                    
                    # 显示任务ID
                    message_lines.append(f"• TaskID: `{task_id}`")
                    # 显示状态和进度
                    message_lines.append(f"  └─ 状态: {status_text} ({progress}%)" if progress > 0 else f"  └─ 状态: {status_text}")
                    
                    # 显示描述信息（如错误详情）
                    if description:
                        # 处理多行描述
                        description_lines = description.split('\n')
                        for line in description_lines:
                            if line.strip():
                                message_lines.append(f"  └─ 📋 {line.strip()}")
                else:
                    # 兼容旧格式（字符串状态）
                    status = str(task_data)
                    status_icon = "✅" if status in ['completed', 'finished', 'success', '已完成', '完成', '成功', '已成功'] else "❌" if status in ['failed', 'error', '失败', '已失败'] else "🔄"
                    status_text = f"{status_icon} {status}"
                    
                    message_lines.append(f"• TaskID: `{task_id}`")
                    message_lines.append(f"  └─ 状态: {status_text}")
            
            if media_info.get('Overview'):
                overview = media_info.get('Overview', '')[:100]
                if len(media_info.get('Overview', '')) > 100:
                    overview += "..."
                message_lines.extend([
                    f"",
                    f"📝 **简介**",
                    f"{overview}"
                ])
            
            message = "\n".join(message_lines)
            
            # 更新消息
            await callback_bot.edit_message_text(
                chat_id=task.chat_id,
                message_id=task.message_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"📝 更新通知消息成功: {operation_text} {media_name}")
            
        except Exception as e:
            logger.error(f"❌ 更新通知消息失败: {e}")
    
    async def send_callback_notification(self, operation_type: str, media_info: Dict[str, Any], result: str = "success", error_msg: str = None, task_ids: List[str] = None, user_id: str = None, import_method: str = None):
        """发送回调通知
        
        Args:
            operation_type: 操作类型 (import/refresh)
            media_info: 媒体信息
            result: 操作结果 (success/failed)
            error_msg: 错误信息（可选）
            task_ids: 任务ID列表（可选，用于轮询状态）
            user_id: 用户ID（可选，用于bot系统发送给特定用户）
            import_method: 导入方式（可选，auto需要查询execution，direct可直接轮询）
        """
        try:
            # 判断当前实例类型并设置目标聊天ID
            if self is webhook_task_polling_manager:
                # Webhook系统：保持原有逻辑不变
                # 检查回调通知是否启用
                if not self.config.webhook.callback_enabled:
                    return
                
                # 检查配置是否有效
                if not self.config.webhook.callback_chat_id:
                    logger.warning("⚠️ 回调通知聊天ID未配置，跳过发送")
                    return
                
                target_chat_id = self.config.webhook.callback_chat_id
            elif self is bot_task_polling_manager:
                # Bot系统：发送给指定用户ID
                if not user_id:
                    logger.warning("⚠️ Bot系统回调通知需要指定用户ID，跳过发送")
                    return
                
                target_chat_id = user_id
            else:
                # 其他实例：使用原有逻辑作为后备
                if not self.config.webhook.callback_enabled:
                    return
                
                if not self.config.webhook.callback_chat_id:
                    logger.warning("⚠️ 回调通知聊天ID未配置，跳过发送")
                    return
                
                target_chat_id = self.config.webhook.callback_chat_id
            
            # 使用现有的TELEGRAM_BOT_TOKEN创建Bot实例
            callback_bot = Bot(token=self.config.telegram.bot_token)
            
            # 构建通知消息
            timestamp = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S")
            
            # 获取媒体基本信息
            # 优先使用TMDB或library匹配的名称
            media_name = self._get_clean_media_name(media_info)
            media_type = "电影" if media_info.get('Type', '').lower() == 'movie' else "剧集"
            
            # 构建状态图标和描述
            if result == "success":
                if operation_type == "refresh":
                    status_icon = "🔄"
                    status_text = "刷新中"
                elif operation_type == "import":
                    status_icon = "🔄"
                    status_text = "入库中"
                else:
                    status_icon = "✅"
                    status_text = "成功"
            else:
                status_icon = "❌"
                status_text = "失败"
            
            # 构建操作类型描述
            base_operation_text = "导入" if operation_type == "import" else "刷新"
            
            # 为剧集构建包含季集信息的操作描述
            operation_text = base_operation_text
            if media_info.get('Type', '').lower() in {'series', 'tv_series'}:
                season = media_info.get('Season')
                episodes = media_info.get('Episodes', [])
                
                if season and episodes:
                    # 构建季集信息字符串
                    episode_list = []
                    for ep in episodes:
                        episode_list.append(f"S{season}E{ep:02d}")
                    
                    if episode_list:
                        operation_text = f"{base_operation_text}{','.join(episode_list)}"
            
            # 构建通知消息
            message_lines = [
                f"🎬 **任务{base_operation_text}通知**",
                f"",
                f"📺 **媒体信息**",
                f"• 名称: {media_name}",
                f"• 类型: {media_type}",
                f"• 操作: {operation_text}",
                f"• 状态: {status_icon} {status_text}",
                f"• 时间: {timestamp}"
            ]
            
            # 添加剧集特有信息
            if media_info.get('Type', '').lower() in {'series', 'tv_series'}:
                if media_info.get('Season'):
                    message_lines.insert(-1, f"• 季度: S{media_info.get('Season')}")
                
                # 添加统计信息
                success_count = media_info.get('SuccessCount', 0)
                failed_count = media_info.get('FailedCount', 0)
                total_count = media_info.get('TotalCount', 0)
                skipped_count = media_info.get('SkippedCount', 0)
                
                if total_count > 0:
                    stats_parts = []
                    if success_count > 0:
                        stats_parts.append(f"成功{success_count}集")
                    if failed_count > 0:
                        stats_parts.append(f"失败{failed_count}集")
                    if skipped_count > 0:
                        stats_parts.append(f"跳过{skipped_count}集")
                    
                    if stats_parts:
                        message_lines.insert(-1, f"• 统计: {' / '.join(stats_parts)} (共{total_count}集)")
            
            # 添加Provider信息
            if media_info.get('ProviderType') and media_info.get('ProviderId'):
                message_lines.insert(-1, f"• Provider: {media_info.get('ProviderType').upper()} {media_info.get('ProviderId')}")
            elif media_info.get('SourceId'):
                message_lines.insert(-1, f"• 源ID: {media_info.get('SourceId')}")
            
            # 如果有错误信息，添加到消息中
            if error_msg:
                message_lines.extend([
                    f"",
                    f"❌ **错误信息**",
                    f"```",
                    f"{error_msg}",
                    f"```"
                ])
            
            if media_info.get('Overview'):
                overview = media_info.get('Overview', '')[:100]
                if len(media_info.get('Overview', '')) > 100:
                    overview += "..."
                message_lines.extend([
                    f"",
                    f"📝 **简介**",
                    f"{overview}"
                ])
            
            message = "\n".join(message_lines)
            
            # 发送通知
            sent_message = await callback_bot.send_message(
                chat_id=target_chat_id,
                text=message,
                parse_mode='Markdown'
            )
            
            # 如果有taskIds，记录任务用于后续轮询
            if task_ids and sent_message:
                task_id = str(uuid.uuid4())
                task = TaskInfo(
                    task_id=task_id,
                    operation_type=operation_type,
                    media_info=media_info.copy(),
                    message_id=sent_message.message_id,
                    chat_id=target_chat_id  # 使用动态确定的目标聊天ID
                )
                
                if operation_type == "import":
                    # 入库操作：根据import_method决定处理方式
                    if task_ids:
                        # 使用第一个task_id作为键
                        main_task_id = task_ids[0]
                        
                        # 如果是direct导入（搜索后导入），可以直接轮询，跳过execution查询
                        if import_method == "direct":
                            task.task_ids.extend(task_ids)
                            logger.info(f"📝 记录直接导入任务: {task_id}, taskIds: {task_ids} (跳过execution查询)")
                            self._tasks[task_id] = task
                        else:
                            # auto导入（webhook或/auto命令）需要查询execution
                            self._import_tasks[main_task_id] = {
                                'task': task,
                                'start_time': datetime.now(self.timezone),
                                'timeout_minutes': 30,
                                'all_task_ids': task_ids  # 保存所有task_ids
                            }
                            logger.info(f"📝 记录入库任务: {task_id}, 待解析taskIds: {task_ids}")
                    # 入库任务不立即添加到_tasks，等获取executionTaskId后再创建新任务
                else:
                    # 刷新操作：taskIds可以直接轮询
                    task.task_ids.extend(task_ids)
                    logger.info(f"📝 记录刷新任务: {task_id}, taskIds: {task_ids}")
                    self._tasks[task_id] = task
                
                # 启动轮询任务（如果尚未启动），并传递已创建的callback_bot实例
                await self.start_polling_if_needed(callback_bot)
            
            logger.info(f"📤 回调通知发送成功: {operation_text} {media_name}")
            
        except Exception as e:
            logger.error(f"❌ 发送回调通知失败: {e}")


# Webhook系统专用的任务轮询管理器实例
webhook_task_polling_manager = TaskPollingManager()

# Bot系统专用的任务轮询管理器实例  
bot_task_polling_manager = TaskPollingManager()