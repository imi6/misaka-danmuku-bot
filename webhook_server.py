import asyncio
import logging
from aiohttp import web, ClientSession
from typing import Optional
from handlers.webhook import webhook_handler
from config import config
from utils.security import mask_sensitive_data

logger = logging.getLogger(__name__)

class WebhookServer:
    """Webhook HTTP服务器"""
    
    def __init__(self):
        self.app: Optional[web.Application] = None
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        
    async def create_app(self) -> web.Application:
        """创建aiohttp应用"""
        app = web.Application()
        
        # 添加路由
        app.router.add_post('/api/webhook/emby', self.handle_emby_webhook)
        
        # 添加健康检查端点
        app.router.add_get('/health', self.health_check)
        
        return app
    
    async def handle_emby_webhook(self, request: web.Request) -> web.Response:
        """处理Emby webhook请求"""
        try:
            # 验证API密钥
            api_key = request.query.get('api_key')
            if not api_key or api_key != config.webhook.api_key:
                logger.warning(f"Invalid API key in webhook request: {mask_sensitive_data(api_key) if api_key else 'None'}")
                return web.Response(status=401, text="Unauthorized")
            
            # 获取请求体
            try:
                data = await request.json()
            except Exception as e:
                logger.error(f"Failed to parse webhook JSON: {e}")
                return web.Response(status=400, text="Invalid JSON")
            
            # 处理webhook数据
            await webhook_handler.handle_emby_webhook(data, api_key)
            
            return web.Response(status=200, text="OK")
            
        except Exception as e:
            logger.error(f"Error handling Emby webhook: {e}", exc_info=True)
            return web.Response(status=500, text="Internal Server Error")
    
    async def health_check(self, request: web.Request) -> web.Response:
        """健康检查端点"""
        return web.Response(status=200, text="Webhook server is running")
    
    async def start(self) -> None:
        """启动HTTP服务器"""
        if not config.webhook.enabled:
            logger.info("🔌 Webhook server is disabled")
            return
            
        try:
            self.app = await self.create_app()
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(
                self.runner, 
                '0.0.0.0', 
                config.webhook.port
            )
            await self.site.start()
            
            logger.info(f"🔌 Webhook server started on http://0.0.0.0:{config.webhook.port}")
            logger.info(f"🔗 Local webhook URL: http://127.0.0.1:{config.webhook.port}/api/webhook/emby?api_key={mask_sensitive_data(config.webhook.api_key)}")
            
        except Exception as e:
            logger.error(f"❌ Failed to start webhook server: {e}", exc_info=True)
            raise
    
    async def stop(self) -> None:
        """停止HTTP服务器"""
        try:
            if self.site:
                await self.site.stop()
                logger.info("🔌 Webhook server site stopped")
            
            if self.runner:
                await self.runner.cleanup()
                logger.info("🔌 Webhook server runner cleaned up")
                
        except Exception as e:
            logger.error(f"❌ Error stopping webhook server: {e}", exc_info=True)

# 全局服务器实例
webhook_server = WebhookServer()
