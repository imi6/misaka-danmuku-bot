from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.api import call_danmaku_api
import logging
from datetime import datetime
import json

# 初始化日志
logger = logging.getLogger(__name__)

# 状态映射字典
STATUS_MAPPING = {
    "in_progress": "进行中",
    "completed": "已完成",
}

def get_status_display(status: str) -> str:
    """获取状态的中文显示名称"""
    return STATUS_MAPPING.get(status, status)

def escape_markdown(text: str) -> str:
    """转义Markdown特殊字符"""
    if not text:
        return text
    # 转义Markdown特殊字符
    special_chars = ['*', '_', '`', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def handle_tasks_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    处理tasks相关的回调查询
    支持刷新任务列表和切换状态过滤
    """
    query = update.callback_query
    await query.answer()
    
    try:
        callback_data = query.data
        
        # 解析回调数据
        if callback_data.startswith("tasks_refresh_"):
            # 刷新指定状态的任务列表
            status = callback_data.replace("tasks_refresh_", "")
            await refresh_tasks_list(query, status)
            
        elif callback_data.startswith("tasks_status_"):
            # 切换任务状态过滤
            status = callback_data.replace("tasks_status_", "")
            if status == "all":
                await show_all_tasks(query)
            else:
                await refresh_tasks_list(query, status)
        
        logger.info(f"✅ 用户 {update.effective_user.id} 执行了tasks回调: {callback_data}")
        
    except Exception as e:
        logger.error(f"❌ 处理tasks回调时出错: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ 处理请求时出现错误，请稍后重试"
        )

async def refresh_tasks_list(query, status: str):
    """
    刷新指定状态的任务列表
    """
    try:
        # 调用API获取任务列表
        params = {"status": status}
        api_response = call_danmaku_api("GET", "/tasks", params=params)
        
        if not api_response["success"]:
            await query.edit_message_text(
                f"❌ 获取任务列表失败：{api_response.get('error', '未知错误')}"
            )
            return
        
        tasks_data = api_response["data"]
        
        # 添加刷新时间戳避免重复内容错误
        refresh_time = datetime.now().strftime("%H:%M:%S")
        
        if not tasks_data or len(tasks_data) == 0:
            status_display = get_status_display(status)
            message = f"📋 暂无 {status_display} 状态的任务\n\n🕐 刷新时间: {refresh_time}"
        else:
            # 格式化任务列表消息
            status_display = get_status_display(status)
            message = f"📋 **任务列表** (状态: {status_display})\n🕐 刷新时间: {refresh_time}\n\n"
            
            for i, task in enumerate(tasks_data, 1):
                # 必须显示的字段
                task_id = task.get("taskId", "未知")
                title = task.get("title", "未知任务")
                progress = task.get("progress", 0)
                
                # 可选显示的字段
                description = task.get("description", "")
                created_at = task.get("createdAt", "")
                task_status = task.get("status", "未知")
                
                # 格式化创建时间
                formatted_time = ""
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        formatted_time = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        formatted_time = created_at
                
                # 构建任务信息
                escaped_title = escape_markdown(title)
                task_info = f"{i}. **{escaped_title}**\n"
                task_info += f"   🆔 ID: `{task_id}`\n"
                task_info += f"   📊 进度: {progress}%\n"
                
                if task_status != status:  # 如果状态与过滤条件不同，显示实际状态
                    task_status_display = get_status_display(task_status)
                    task_info += f"   🏷️ 状态: {task_status_display}\n"
                
                if description:
                    # 限制描述长度，避免消息过长
                    desc_preview = description[:50] + "..." if len(description) > 50 else description
                    escaped_desc = escape_markdown(desc_preview)
                    task_info += f"   📝 描述: {escaped_desc}\n"
                
                if formatted_time:
                    task_info += f"   🕐 创建时间: {formatted_time}\n"
                
                message += task_info + "\n"
        
        # 添加操作按钮
        keyboard = [
            [
                InlineKeyboardButton("🔄 刷新", callback_data=f"tasks_refresh_{status}"),
            ],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"❌ 刷新任务列表时出错: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ 刷新任务列表时出现错误，请稍后重试"
        )

async def show_all_tasks(query):
    """
    显示所有状态的任务列表
    """
    try:
        # 调用API获取所有任务
        api_response = call_danmaku_api("GET", "/tasks")
        
        if not api_response["success"]:
            await query.edit_message_text(
                f"❌ 获取任务列表失败：{api_response.get('error', '未知错误')}"
            )
            return
        
        tasks_data = api_response["data"]
        
        # 添加刷新时间戳避免重复内容错误
        refresh_time = datetime.now().strftime("%H:%M:%S")
        
        if not tasks_data or len(tasks_data) == 0:
            message = f"📋 暂无任务\n\n🕐 刷新时间: {refresh_time}"
        else:
            # 按状态分组统计
            status_counts = {}
            for task in tasks_data:
                status = task.get("status", "未知")
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # 格式化消息
            message = f"📋 **任务概览** (全部状态)\n🕐 刷新时间: {refresh_time}\n\n"
            message += "📊 **状态统计:**\n"
            
            status_emojis = {
                "in_progress": "⏳",
                "completed": "✅",
                "paused": "⏸️",
                "failed": "❌",
                "pending": "⏰"
            }
            
            for status, count in status_counts.items():
                emoji = status_emojis.get(status, "📌")
                status_display = get_status_display(status)
                message += f"   {emoji} {status_display}: {count} 个\n"
            
            message += f"\n📈 **总计**: {len(tasks_data)} 个任务\n\n"
            
            # 显示最近的几个任务
            message += "🕐 **最近任务:**\n"
            recent_tasks = sorted(tasks_data, key=lambda x: x.get("createdAt", ""), reverse=True)[:5]
            
            for i, task in enumerate(recent_tasks, 1):
                title = task.get("title", "未知任务")
                status = task.get("status", "未知")
                progress = task.get("progress", 0)
                emoji = status_emojis.get(status, "📌")
                
                escaped_title = escape_markdown(title)
                message += f"{i}. {emoji} **{escaped_title}** ({progress}%)\n"
        
        # 添加操作按钮
        keyboard = [
            [
                InlineKeyboardButton("🔄 刷新", callback_data="tasks_status_all"),
                InlineKeyboardButton("⏳ 进行中", callback_data="tasks_status_in_progress")
            ],
            [
                InlineKeyboardButton("✅ 已完成", callback_data="tasks_status_completed"),
                InlineKeyboardButton("⏸️ 暂停", callback_data="tasks_status_paused")
            ],
            [
                InlineKeyboardButton("❌ 失败", callback_data="tasks_status_failed"),
                InlineKeyboardButton("⏰ 待处理", callback_data="tasks_status_pending")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"❌ 显示全部任务时出错: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ 显示任务概览时出现错误，请稍后重试"
        )