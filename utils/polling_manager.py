import asyncio
import logging
import time
from typing import Optional
from telegram.ext import Application
from config import POLLING_INTERVAL_ACTIVE, POLLING_INTERVAL_IDLE

# 初始化日志
logger = logging.getLogger(__name__)

class DynamicPollingManager:
    """动态轮询管理器，根据用户活动状态调整轮询间隔"""
    
    def __init__(self, application: Application, active_interval: int = None, idle_interval: int = None):
        self.application = application
        self.active_interval = active_interval or POLLING_INTERVAL_ACTIVE
        self.idle_interval = idle_interval or POLLING_INTERVAL_IDLE
        self.current_interval = self.idle_interval  # 默认使用空闲间隔
        self.is_polling = False
        self.polling_task: Optional[asyncio.Task] = None
        self.updater_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        # 用户活动跟踪
        self.last_activity_time = 0
        self.activity_timeout = 60  # 60秒无活动后切换到空闲模式
        
    async def start_dynamic_polling(self):
        """启动真正的动态轮询"""
        if self.is_polling:
            logger.warning("⚠️ 动态轮询已在运行中")
            return
            
        self.is_polling = True
        self._stop_event.clear()
        
        # 启动会话监控任务
        self.polling_task = asyncio.create_task(self._monitor_sessions())
        # 启动动态轮询任务
        self.updater_task = asyncio.create_task(self._dynamic_polling_loop())
        
        logger.info(f"🚀 动态轮询已启动，初始轮询间隔: {self.current_interval}秒")
        
    async def start_monitoring(self):
        """启动会话监控（保留兼容性）"""
        await self.start_dynamic_polling()
        
    async def start_polling(self):
        """启动动态轮询（保留兼容性）"""
        await self.start_dynamic_polling()
        
    async def stop_polling(self):
        """停止轮询"""
        if not self.is_polling:
            return
            
        logger.info("🛑 正在停止动态轮询...")
        self.is_polling = False
        self._stop_event.set()
        
        # 停止会话监控任务
        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()
            try:
                await asyncio.wait_for(self.polling_task, timeout=3.0)
            except asyncio.CancelledError:
                logger.debug("📡 会话监控任务已取消")
            except asyncio.TimeoutError:
                logger.warning("⚠️ 会话监控任务取消超时")
            except Exception as e:
                logger.error(f"❌ 停止会话监控任务时出错: {e}")
            finally:
                self.polling_task = None
            
        # 停止动态轮询任务
        if self.updater_task and not self.updater_task.done():
            self.updater_task.cancel()
            try:
                await asyncio.wait_for(self.updater_task, timeout=3.0)
            except asyncio.CancelledError:
                logger.debug("📡 动态轮询任务已取消")
            except asyncio.TimeoutError:
                logger.warning("⚠️ 动态轮询任务取消超时")
            except Exception as e:
                logger.error(f"❌ 停止动态轮询任务时出错: {e}")
            finally:
                self.updater_task = None
            
        logger.info("🛑 动态轮询已停止")
        
    def _calculate_polling_interval(self) -> int:
        """根据用户活动状态计算轮询间隔"""
        current_time = time.time()
        time_since_activity = current_time - self.last_activity_time
        
        if time_since_activity < self.activity_timeout:
            # 有近期活动时使用短间隔
            return self.active_interval
        else:
            # 无近期活动时使用长间隔
            return self.idle_interval
    
    def record_user_activity(self):
        """记录用户活动时间"""
        self.last_activity_time = time.time()
            
    async def _dynamic_polling_loop(self):
        """动态轮询循环，实现智能延迟处理"""
        try:
            while self.is_polling and not self._stop_event.is_set():
                # 等待5秒后检查是否需要调整处理策略，使用更短的超时以便快速响应取消
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), 
                        timeout=1.0  # 缩短超时时间，提高响应速度
                    )
                    break  # 如果 stop_event 被设置，退出循环
                except asyncio.TimeoutError:
                    # 超时是正常的，继续下一次循环
                    continue
                except asyncio.CancelledError:
                    # 任务被取消，立即退出
                    logger.debug("📡 动态轮询循环任务被取消")
                    raise
                    
        except asyncio.CancelledError:
            # 任务被取消，正常退出
            logger.debug("📡 动态轮询循环任务已取消")
            raise  # 重新抛出 CancelledError 以确保任务正确结束
        except Exception as e:
            logger.error(f"❌ 动态轮询循环异常: {e}", exc_info=True)
        finally:
            logger.debug("📡 动态轮询循环任务结束")
                
    async def _monitor_sessions(self):
        """监控用户活动状态并动态调整轮询间隔"""
        try:
            while self.is_polling and not self._stop_event.is_set():
                # 计算当前应该使用的轮询间隔
                new_interval = self._calculate_polling_interval()
                
                # 如果间隔发生变化，记录日志
                if new_interval != self.current_interval:
                    current_time = time.time()
                    time_since_activity = current_time - self.last_activity_time
                    status = "活跃" if time_since_activity < self.activity_timeout else "空闲"
                    logger.info(
                        f"🔄 轮询间隔调整: {self.current_interval}s -> {new_interval}s "
                        f"(状态: {status}, 距上次活动: {int(time_since_activity)}s)"
                    )
                    self.current_interval = new_interval
                    
                # 等待5秒后再次检查，使用更短的超时以便快速响应取消
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), 
                        timeout=5.0  # 每5秒检查一次状态变化
                    )
                    break  # 如果 stop_event 被设置，退出循环
                except asyncio.TimeoutError:
                    # 超时是正常的，继续下一次循环
                    continue
                except asyncio.CancelledError:
                    # 任务被取消，立即退出
                    logger.debug("📡 活动监控任务被取消")
                    raise
                    
        except asyncio.CancelledError:
            # 任务被取消，正常退出
            logger.debug("📡 活动监控任务已取消")
            raise  # 重新抛出 CancelledError 以确保任务正确结束
        except Exception as e:
            logger.error(f"❌ 活动监控异常: {e}", exc_info=True)
        finally:
            logger.debug("📡 活动监控任务结束")
            
    def get_status(self) -> dict:
        """获取轮询状态"""
        current_time = time.time()
        time_since_activity = current_time - self.last_activity_time
        is_active = time_since_activity < self.activity_timeout
        
        return {
            "is_polling": self.is_polling,
            "current_interval": self.current_interval,
            "is_active": is_active,
            "time_since_activity": int(time_since_activity),
            "polling_interval_active": POLLING_INTERVAL_ACTIVE,
            "polling_interval_idle": POLLING_INTERVAL_IDLE
        }
        
# 注意：这个类需要在应用程序初始化后创建实例
# polling_manager = DynamicPollingManager(application)