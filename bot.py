
import os
import asyncio
import aiohttp
import logging
import tempfile
from functools import wraps
import socket
import psutil
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from dotenv import load_dotenv
from typing import List, Tuple

load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SERVER_PORT = os.getenv("SERVER_PORT", "26657")
BOT_TOKEN = os.getenv("BOT_TOKEN")
STORY_SERVICE = os.getenv("STORY_SERVICE")
STORY_GETH_SERVICE = os.getenv("STORY_GETH_SERVICE")
MONITORING_INTERVAL = int(os.getenv("MONITORING_INTERVAL", 300)) 
SERVER_PORT = os.getenv("SERVER_PORT", "26657")
RPC_ENDPOINT_1 = os.getenv("RPC_ENDPOINT_1")
RPC_ENDPOINT_2 = os.getenv("RPC_ENDPOINT_2")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

def safe_get(data, *keys, default="Not available"):
    for key in keys:
        try:
            data = data[key]
        except (KeyError, TypeError):
            return default
    return data


def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            if update.callback_query:
                await update.callback_query.answer("Sorry, you are not authorized to use this bot.", show_alert=True)
            else:
                await update.message.reply_text("Sorry, you are not authorized to use this bot.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped


async def fetch_latest_block(rpc_endpoint: str) -> int:
    async with aiohttp.ClientSession() as session:
        async with session.get(rpc_endpoint) as response:
            if response.status == 200:
                data = await response.json()
                latest_block = int(data['result']['sync_info']['latest_block_height'])
                return latest_block
            else:
                raise Exception(f"Failed to fetch data from {rpc_endpoint}, Status Code: {response.status}")
@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_main_menu(update, context)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("📊 Status", callback_data="status")],
        [InlineKeyboardButton("📜 Logs", callback_data="logs"),
         InlineKeyboardButton("🔄 Restart Services", callback_data="restart")],
        [InlineKeyboardButton("💻 System Info", callback_data="system_info"),
         InlineKeyboardButton("🔍 Monitor", callback_data="monitor")],
        [InlineKeyboardButton("📈 Performance", callback_data="performance"),
         InlineKeyboardButton("🌐 Network", callback_data="network")],
        [InlineKeyboardButton("✅ Validator", callback_data="validator"),
         InlineKeyboardButton("❓ Help", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text("🤖 Welcome to your Node Management Bot! Choose an option:", reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text("🤖 Main Menu:", reply_markup=reply_markup)

@admin_only
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.callback_query.answer("Sorry, you are not authorized to use this bot.", show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    handlers = {
        "status": check_status,
        "logs": show_log_options,
        "restart": show_restart_options,
        "system_info": system_info,
        "monitor": show_monitor_menu,
        "performance": performance_metrics,
        "network": network_stats,
        "validator": validator_info,
        "help": help_command
    }

    if query.data in handlers:
        await handlers[query.data](update, context)
    elif query.data.startswith("logs_"):
        service = query.data.split("_")[1]
        await view_logs(update, context, service)
    elif query.data.startswith("restart_"):
        service = query.data.split("_")[1]
        await restart_service(update, context, service)
    elif query.data.startswith("monitor_"):
        action = query.data.split("_")[1]
        if action == "activate":
            await activate_monitoring(update, context)
        elif action == "deactivate":
            await deactivate_monitoring(update, context)
        elif action == "status":
            await view_monitoring_status(update, context)
    elif query.data == "start":
        await show_main_menu(update, context)

async def show_log_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("story Logs", callback_data="logs_story"),
         InlineKeyboardButton("story-geth Logs", callback_data="logs_story-geth")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Choose which logs to view:", reply_markup=reply_markup)

async def show_monitor_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("✅ Activate Monitoring", callback_data="monitor_activate")],
        [InlineKeyboardButton("❌ Deactivate Monitoring", callback_data="monitor_deactivate")],
        [InlineKeyboardButton("📋 View Monitoring Status", callback_data="monitor_status")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("🔍 Monitor Options:", reply_markup=reply_markup)

async def activate_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if context.chat_data.get('monitoring', False):
        message = "🔍 Monitoring is already active."
    else:
        context.chat_data['monitoring'] = True
        context.job_queue.run_repeating(send_monitoring_update, interval=MONITORING_INTERVAL, first=10, chat_id=chat_id, name=f"monitor_{chat_id}")
        message = f"✅ Monitoring activated. You'll receive updates every {MONITORING_INTERVAL // 60} minutes."
    
    await update.callback_query.answer()
    await show_monitor_menu_with_message(update, context, message)

async def deactivate_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not context.chat_data.get('monitoring', False):
        message = "🔍 Monitoring is already inactive."
    else:
        context.chat_data['monitoring'] = False
        current_jobs = context.job_queue.get_jobs_by_name(f"monitor_{chat_id}")
        for job in current_jobs:
            job.schedule_removal()
        message = "❌ Monitoring deactivated."
    
    await update.callback_query.answer()
    await show_monitor_menu_with_message(update, context, message)

async def show_monitor_menu_with_message(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str) -> None:
    keyboard = [
        [InlineKeyboardButton("✅ Activate Monitoring", callback_data="monitor_activate")],
        [InlineKeyboardButton("❌ Deactivate Monitoring", callback_data="monitor_deactivate")],
        [InlineKeyboardButton("📋 View Monitoring Status", callback_data="monitor_status")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(f"{message}\n\n🔍 Monitor Options:", reply_markup=reply_markup)

async def view_monitoring_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    monitoring = context.chat_data.get('monitoring', False)
    status_message = "🔍 **Monitoring Status:**\n\n"
    status_message += f"• **Active**: {'✅ Yes' if monitoring else '❌ No'}\n"
    status_message += f"• **Monitoring Interval**: {MONITORING_INTERVAL // 60} minutes\n"
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Back to Monitor Menu", callback_data="monitor")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(status_message, reply_markup=reply_markup, parse_mode='Markdown')
       
async def show_restart_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Restart story", callback_data="restart_story"),
         InlineKeyboardButton("Restart story-geth", callback_data="restart_story-geth")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Choose which service to restart:", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = """
📚 Available commands:
• /start - Start the bot and show main menu

🔘 Menu options:
• 📊 Status - Check node status
• 📜 Logs - View recent logs
• 🔄 Restart Services - Restart story or story-geth service
• 💻 System Info - Show system information
• 🔍 Monitor - Toggle continuous monitoring
• 📈 Performance - View node performance metrics
• 🌐 Network - Show network statistics
• ✅ Validator - Show validator information
• ❓ Help - Display this help message

🔗 Additional Information:
• This bot is based on the GitHub project:
  https://github.com/0xlimon/story-wave2-task4-Useful-utility-for-validators

💡 Feedback and Suggestions:
We appreciate your feedback! If you have any suggestions, feature requests, or issues, please feel free to:
1. Open an issue on our GitHub repository
2. Submit a pull request with your improvements
3. Contact the developer directly

👤 Developer Contact:
For direct communication or urgent matters, you can reach out to the developer:
• Telegram: https://t.me/zxLimon

Thank you for using our Story Node Management Bot!
"""
    keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data="start")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(help_text, reply_markup=reply_markup, disable_web_page_preview=True)


async def fetch_and_save_logs(service: str, lines: int = 100) -> str:
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.log') as temp_file:
        process = await asyncio.create_subprocess_shell(
            f"journalctl -u {service} -n {lines} --no-pager",
            stdout=temp_file,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        return temp_file.name    


def split_message(message: str, max_length: int = 4000) -> list:
    parts = []
    while len(message) > max_length:
        split_index = message.rfind('\n', 0, max_length)
        if split_index == -1:
            split_index = max_length
        parts.append(message[:split_index])
        message = message[split_index:]
    parts.append(message)
    return parts


async def show_log_filter_options(update: Update, context: ContextTypes.DEFAULT_TYPE, service: str):
    keyboard = [
        [InlineKeyboardButton("All Levels", callback_data=f"log_filter_{service}_all")],
        [InlineKeyboardButton("ERROR", callback_data=f"log_filter_{service}_ERROR")],
        [InlineKeyboardButton("WARNING", callback_data=f"log_filter_{service}_WARNING")],
        [InlineKeyboardButton("INFO", callback_data=f"log_filter_{service}_INFO")],
        [InlineKeyboardButton("Back to Logs Menu", callback_data="logs")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text("Select log level to filter:", reply_markup=reply_markup)

async def handle_log_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, service, level = query.data.split('_')[2:]

    if level == 'all':
        level = None
    
    await view_logs(update, context, service, level)

async def view_logs(update: Update, context: ContextTypes.DEFAULT_TYPE, service: str, level: str = None):
    try:
        temp_file_path = await fetch_and_save_logs(service)
        
        with open(temp_file_path, 'rb') as log_file:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=log_file,
                filename=f"{service}_logs.txt",
                caption=f"Recent logs for {service}"
            )
        
        os.unlink(temp_file_path)  

        keyboard = [
            [InlineKeyboardButton("Back to Logs Menu", callback_data="logs")],
            [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.message.reply_text(
            f"Logs for {service} have been sent as a file. Use the buttons below for more options:",
            reply_markup=reply_markup
        )

        await update.callback_query.answer()
    except Exception as e:
        await update.callback_query.message.reply_text(f"❌ Error fetching logs for {service}: {str(e)}")
        await update.callback_query.answer()


async def restart_service(update: Update, context: ContextTypes.DEFAULT_TYPE, service_name: str) -> None:
    try:
        subprocess.run(["sudo", "systemctl", "restart", service_name], check=True)
        message = f"✅ {service_name} service restarted successfully."
    except subprocess.CalledProcessError as e:
        message = f"❌ Error restarting {service_name} service: {str(e)}"
    
    keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data="start")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(message, reply_markup=reply_markup)

async def fetch_node_status() -> dict:
    node_rpc_url = f"http://localhost:{SERVER_PORT}/status"
    async with aiohttp.ClientSession() as session:
        async with session.get(node_rpc_url) as response:
            if response.status == 200:
                return await response.json()
            else:
                raise Exception(f"Failed to fetch node status, Status Code: {response.status}")
async def compare_block_heights() -> Tuple[str, bool]:
    try:

        try:
            latest_block_rpc1 = await fetch_latest_block(RPC_ENDPOINT_1)
            logger.info(f"Latest block from RPC_ENDPOINT_1: {latest_block_rpc1}")
        except Exception as e:
            logger.error(f"Error fetching from RPC_ENDPOINT_1: {e}")

            latest_block_rpc1 = await fetch_latest_block(RPC_ENDPOINT_2)
            logger.info(f"Latest block from RPC_ENDPOINT_2: {latest_block_rpc1}")


        node_status = await fetch_node_status()
        node_block_height = int(node_status['result']['sync_info']['latest_block_height'])
        logger.info(f"Node's current block height: {node_block_height}")


        if node_block_height < latest_block_rpc1:
            difference = latest_block_rpc1 - node_block_height
            message = (
                f"🚨 **Block Synchronization Alert:**\n\n"
                f"Your node is behind by {difference} blocks.\n"
                f"Node Block Height: {node_block_height}\n"
                f"Network Latest Block: {latest_block_rpc1}\n\n"
                f"🔍 Please check your node to ensure it's operating correctly."
            )
            return message, False
        else:
            message = (
                f"✅ **Block Synchronization Status:**\n\n"
                f"Your node is fully synchronized.\n"
                f"Node Block Height: {node_block_height}\n"
                f"Network Latest Block: {latest_block_rpc1}"
            )
            return message, True

    except Exception as e:
        logger.error(f"Error in compare_block_heights: {e}")
        return f"❌ **Block Synchronization Error:** {e}", False

async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:

        story_status = subprocess.check_output(["systemctl", "is-active", STORY_SERVICE]).decode().strip()
        story_geth_status = subprocess.check_output(["systemctl", "is-active", STORY_GETH_SERVICE]).decode().strip()


        async with aiohttp.ClientSession() as session:
            async with session.get(f'http://localhost:{SERVER_PORT}/status') as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to fetch Node status: HTTP {resp.status}")
                status_data = await resp.json()


        node_info = status_data.get('result', {}).get('node_info', {})
        sync_info = status_data.get('result', {}).get('sync_info', {})
        validator_info = status_data.get('result', {}).get('validator_info', {})


        block_message, is_synced = await compare_block_heights()


        message = "📊 **Node Status:**\n\n"
        message += f"**System Services:**\n"
        message += f"• `{STORY_SERVICE}`: `{story_status}`\n"
        message += f"• `{STORY_GETH_SERVICE}`: `{story_geth_status}`\n\n"

        message += "**Node Status:**\n"
        message += f"• Node ID: `{node_info.get('id', 'N/A')}`\n"
        message += f"• Listen Address: `{node_info.get('listen_addr', 'N/A')}`\n"
        message += f"• Network: `{node_info.get('network', 'N/A')}`\n"
        message += f"• Version: `{node_info.get('version', 'N/A')}`\n\n"

        message += "**Synchronization Info:**\n"
        message += f"• Latest Block Height: `{sync_info.get('latest_block_height', 'N/A')}`\n"
        message += f"• Latest Block Time: `{sync_info.get('latest_block_time', 'N/A')}`\n"
        message += f"• Catching Up: `{sync_info.get('catching_up', False)}`\n\n"

        message += "**Validator Info:**\n"
        message += f"• Address: `{validator_info.get('address', 'N/A')}`\n"
        message += f"• Voting Power: `{validator_info.get('voting_power', 'N/A')}`\n"
        message += f"• Proposer Priority: `{validator_info.get('proposer_priority', 'N/A')}`\n\n"


        message += block_message

        keyboard = [
            [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)


        if len(message) <= 4096:
            await update.callback_query.edit_message_text(
                message, reply_markup=reply_markup, parse_mode='Markdown'
            )
        else:
            messages = split_message(message)
            for idx, msg in enumerate(messages):
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=msg,
                    reply_markup=reply_markup if idx == 0 else None,
                    parse_mode='Markdown'
                )

        await update.callback_query.answer()
    except Exception as e:
        await update.callback_query.message.reply_text(f"❌ Error fetching status: {str(e)}")
        await update.callback_query.answer()

async def system_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
    
        message = "💻 System Information:\n\n"



        message += f"CPU Usage: {cpu_percent}%\n"
        message += f"Memory Usage: {memory.percent}%\n"
        message += f"Disk Usage: {disk.percent}%\n"
    
        keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    except Exception as e:
        await update.callback_query.edit_message_text(f"❌ Error fetching system information: {str(e)}")

async def toggle_monitoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if 'monitoring' not in context.chat_data:
        context.chat_data['monitoring'] = False

    context.chat_data['monitoring'] = not context.chat_data['monitoring']
    
    if context.chat_data['monitoring']:
        message = f"🔍 Continuous monitoring enabled. You'll receive updates every {MONITORING_INTERVAL // 60} minutes."
        context.job_queue.run_repeating(send_monitoring_update, interval=MONITORING_INTERVAL, first=5, chat_id=chat_id, name=f"monitor_{chat_id}")
    else:
        message = "🔍 Continuous monitoring disabled."
        current_jobs = context.job_queue.get_jobs_by_name(f"monitor_{chat_id}")
        for job in current_jobs:
            job.schedule_removal()

    keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data="start")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(message, reply_markup=reply_markup)


async def send_monitoring_update(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.chat_id
    if not context.chat_data.get('monitoring', False):
        return  

    try:

        story_status = subprocess.check_output(["systemctl", "is-active", STORY_SERVICE]).decode().strip()
        story_geth_status = subprocess.check_output(["systemctl", "is-active", STORY_GETH_SERVICE]).decode().strip()


        disk = psutil.disk_usage('/')
        message = "🔍 **Disk Monitoring:**\n\n"
        message += f"• **Total:** {disk.total / (1024 ** 3):.2f} GB\n"
        message += f"• **Used:** {disk.used / (1024 ** 3):.2f} GB ({disk.percent}%)\n"
        message += f"• **Free:** {disk.free / (1024 ** 3):.2f} GB\n\n"


        block_message, is_synced = await compare_block_heights()
        message += block_message


        keyboard = [
            [InlineKeyboardButton("Back to Main Menu", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)


        if len(message) <= 4096:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            messages = split_message(message)
            for idx, msg in enumerate(messages):
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=msg,
                    reply_markup=reply_markup if idx == 0 else None,
                    parse_mode='Markdown'
                )

    except Exception as e:
        error_message = f"Error in monitoring update: {str(e)}"
        logger.error(error_message)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ {error_message}")


async def performance_metrics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        cpu_times = psutil.cpu_times_percent()
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk_io = psutil.disk_io_counters()
        disk_usage = psutil.disk_usage('/')
        
        cpu_freq = psutil.cpu_freq()
        load_avg = psutil.getloadavg()

        message = "📈 Detailed Performance Metrics:\n\n"
        message += f"CPU Usage:\n"
        message += f"  User: {cpu_times.user}%\n"
        message += f"  System: {cpu_times.system}%\n"
        message += f"  Idle: {cpu_times.idle}%\n"
        message += f"  Current Frequency: {cpu_freq.current:.2f} MHz\n"
        message += f"  Load Average: {load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}\n\n"
        
        message += f"Memory Usage:\n"
        message += f"  Total: {memory.total / (1024 ** 3):.2f} GB\n"
        message += f"  Available: {memory.available / (1024 ** 3):.2f} GB\n"
        message += f"  Used: {memory.used / (1024 ** 3):.2f} GB ({memory.percent}%)\n"
        message += f"  Buffers: {memory.buffers / (1024 ** 3):.2f} GB\n"
        message += f"  Cached: {memory.cached / (1024 ** 3):.2f} GB\n\n"
        
        message += f"Swap Usage:\n"
        message += f"  Total: {swap.total / (1024 ** 3):.2f} GB\n"
        message += f"  Used: {swap.used / (1024 ** 3):.2f} GB ({swap.percent}%)\n"
        message += f"  Free: {swap.free / (1024 ** 3):.2f} GB\n\n"
        
        message += f"Disk Usage:\n"
        message += f"  Total: {disk_usage.total / (1024 ** 3):.2f} GB\n"
        message += f"  Used: {disk_usage.used / (1024 ** 3):.2f} GB ({disk_usage.percent}%)\n"
        message += f"  Free: {disk_usage.free / (1024 ** 3):.2f} GB\n\n"
        
        message += f"Disk I/O (since boot):\n"
        message += f"  Read: {disk_io.read_bytes / (1024 ** 3):.2f} GB\n"
        message += f"  Write: {disk_io.write_bytes / (1024 ** 3):.2f} GB\n"
        message += f"  Read Count: {disk_io.read_count}\n"
        message += f"  Write Count: {disk_io.write_count}\n"

        keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    except Exception as e:
        await update.callback_query.edit_message_text(f"❌ Error fetching performance metrics: {str(e)}")

async def network_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        net_io = psutil.net_io_counters()
        net_connections = psutil.net_connections()
        net_if_addrs = psutil.net_if_addrs()

        message = "🌐 Detailed Network Statistics:\n\n"
        message += f"Network I/O (since boot):\n"
        message += f"  Bytes Sent: {net_io.bytes_sent / (1024 ** 3):.2f} GB\n"
        message += f"  Bytes Received: {net_io.bytes_recv / (1024 ** 3):.2f} GB\n"
        message += f"  Packets Sent: {net_io.packets_sent}\n"
        message += f"  Packets Received: {net_io.packets_recv}\n"
        message += f"  Errors In: {net_io.errin}\n"
        message += f"  Errors Out: {net_io.errout}\n"
        message += f"  Drop In: {net_io.dropin}\n"
        message += f"  Drop Out: {net_io.dropout}\n\n"
        
        message += f"Active Connections: {len(net_connections)}\n\n"
        
        message += "Network Interfaces:\n"
        for interface, addrs in net_if_addrs.items():
            message += f"  {interface}:\n"
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    message += f"    IPv4 Address: {addr.address}\n"
                elif addr.family == socket.AF_INET6:
                    message += f"    IPv6 Address: {addr.address}\n"
        
        keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    except Exception as e:
        await update.callback_query.edit_message_text(f"❌ Error fetching network statistics: {str(e)}")

async def validator_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:

        async with aiohttp.ClientSession() as session:
            async with session.get(f'http://localhost:{SERVER_PORT}/status') as resp:
                status = await resp.json()
            
            async with session.get(f'http://localhost:{SERVER_PORT}/validators') as resp:
                validators = await resp.json()


        try:
            story_version_output = subprocess.check_output(["story", "version"], stderr=subprocess.STDOUT).decode().strip()
            
            story_version = {}
            for line in story_version_output.split('\n'):
                if "Version" in line:
                    story_version['version'] = line.split()[1].strip()
                elif "Git Commit" in line:
                    story_version['git_commit'] = line.split()[2].strip()
                elif "Git Timestamp" in line:
                    story_version['timestamp'] = ' '.join(line.split()[2:]).strip()
                    
        except Exception as e:
            logger.error(f"Error getting story version: {e}")
            story_version = {
                'version': 'Not available',
                'git_commit': 'Not available',
                'timestamp': 'Not available'
            }


        try:
            geth_version_output = subprocess.check_output(["story-geth", "version"], stderr=subprocess.STDOUT).decode().strip()
            
            geth_version = {}
            for line in geth_version_output.split('\n'):
                if line.startswith("Version:"):
                    geth_version['version'] = line.split(': ')[1].strip()
                elif line.startswith("Git Commit:"):
                    geth_version['git_commit'] = line.split(': ')[1].strip()
                elif line.startswith("Git Commit Date:"):
                    geth_version['git_date'] = line.split(': ')[1].strip()
                elif line.startswith("Go Version:"):
                    geth_version['go_version'] = line.split(': ')[1].strip()
                elif line.startswith("Operating System:"):
                    geth_version['os'] = line.split(': ')[1].strip()
                    
        except Exception as e:
            logger.error(f"Error getting story-geth version: {e}")
            geth_version = {
                'version': 'Not available',
                'git_commit': 'Not available',
                'git_date': 'Not available',
                'go_version': 'Not available',
                'os': 'Not available'
            }

        node_info = status['result']['node_info']
        sync_info = status['result']['sync_info']
        validator_info = status['result']['validator_info']

        message = "✅ Detailed Validator Information:\n\n"
        message += f"Story Node Version:\n"
        message += f"  Version: {story_version.get('version', 'Not available')}\n"
        message += f"  Git Commit: {story_version.get('git_commit', 'Not available')}\n"
        message += f"  Timestamp: {story_version.get('timestamp', 'Not available')}\n\n"
        
        message += f"Story-Geth Version:\n"
        message += f"  Version: {geth_version.get('version', 'Not available')}\n"
        message += f"  Git Commit: {geth_version.get('git_commit', 'Not available')}\n"
        message += f"  Git Date: {geth_version.get('git_date', 'Not available')}\n"
        message += f"  Go Version: {geth_version.get('go_version', 'Not available')}\n\n"
        
        message += f"Network Info:\n"
        message += f"  Network: {node_info['network']}\n"
        message += f"  Moniker: {node_info['moniker']}\n\n"
        
        message += f"Sync Status:\n"
        message += f"  Catching Up: {'Yes' if sync_info['catching_up'] else 'No'}\n"
        message += f"  Latest Block Height: {sync_info['latest_block_height']}\n"
        message += f"  Latest Block Time: {sync_info['latest_block_time']}\n\n"
        
        message += f"Validator Info:\n"
        message += f"  Address: {validator_info.get('address', 'Not available')}\n"
        message += f"  Voting Power: {validator_info.get('voting_power', 'Not available')}\n"
        message += f"  Proposer Priority: {validator_info.get('proposer_priority', 'Not available')}\n\n"

        keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in validator_info: {e}")
        await update.callback_query.edit_message_text(f"❌ Error fetching validator information: {str(e)}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Error occurred: {context.error}")
    try:
        if update.effective_message:
            await update.effective_message.reply_text("An error occurred. Please try again later.")
    except Exception as e:
        logger.error(f"Error in error handler: {e}")


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))

    application.add_error_handler(error_handler)
    

    application.add_handler(CallbackQueryHandler(button_handler))

    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
