# -*- coding: UTF-8 -*-
import datetime
import json
import os
import platform
import time

import croniter
import httpx
import pyrogram
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from pyrogram import Client, filters
from pyrogram.types import BotCommand, Message

from api.alist_api import AListAPI
from config.config import (
    config,
    admin,
    alist_host,
    alist_token,
    backup_time,
    write_config,
    api_id,
    api_hash,
    bot_token,
    scheme,
    hostname,
    port,
    cloudflare_cfg, member,
)
from tool.scheduler_manager import aps
from tool.utils import is_admin, parse_cron

# 如果当前操作系统不是 Windows，则设置环境变量 TZ 为 'Asia/Shanghai'
if platform.system() != "Windows":
    os.environ["TZ"] = "Asia/Kuala_Lumpur"
    time.tzset()

logger.add("logs/bot.log", rotation="5 MB")

scheduler = AsyncIOScheduler()

proxy = {
    "scheme": scheme,  # 支持“socks4”、“socks5”和“http”
    "hostname": hostname,
    "port": port,
}

plugins = dict(root="module")
app = Client(
    "my_bot",
    proxy=proxy if all([scheme, hostname, port]) else None,
    bot_token=bot_token,
    api_id=api_id,
    api_hash=api_hash,
    plugins=plugins,
    lang_code="en",
)


# 开始
@app.on_message(filters.command("start"))
async def start(_, message: Message):
    if member and message.chat.id not in member:
        return
    await message.reply("Send `/s+filename` to search")


# 帮助
@app.on_message(filters.command("help") & filters.private & is_admin)
async def _help(_, message: Message):
    text = """
Send pictures to view picture bed function
"""
    await message.reply(text)


# setting menu
@app.on_message(filters.command("menu") & filters.private & is_admin)
async def menu(_, message: Message):
    # Admin private chat is visible
    a_bot_menu = [
        BotCommand(command="s", description="Search files"),
        BotCommand(command="roll", description="Random recommendation"),
        BotCommand(command="sl", description="Set the number of search results"),
        BotCommand(command="zl", description="Turn on/off direct link"),
        BotCommand(command="st", description="Storage management"),
        BotCommand(command="sf", description="Cloudflare node management"),
        BotCommand(command="vb", description="View download node information"),
        BotCommand(command="bc", description="Back up Alist configuration"),
        BotCommand(command="sbt", description="Set up scheduled backup"),
        BotCommand(command="sr", description="Random recommended settings"),
        BotCommand(command="help", description="View help"),
    ]

    # All visible
    b_bot_menu = [
        BotCommand(command="s", description="Search files"),
        BotCommand(command="roll", description="Random recommendation"),
        BotCommand(command="vb", description="View download node information"),
    ]

    await app.delete_bot_commands()
    await app.set_bot_commands(
        a_bot_menu, scope=pyrogram.types.BotCommandScopeChat(chat_id=admin)
    )
    await app.set_bot_commands(b_bot_menu)
    await message.reply("菜单设置成功，请退出聊天界面重新进入来刷新菜单")


# Back up alist configuration
def backup_config():
    bc_list = ["setting", "user", "storage", "meta"]
    bc_dic = {"settings": "", "users": "users", "storages": "", "metas": ""}
    for i in range(len(bc_list)):
        bc_url = f"{alist_host}/api/admin/{bc_list[i]}/list"
        bc_header = {"Authorization": alist_token, "accept": "application/json"}
        bc_post = httpx.get(bc_url, headers=bc_header)
        data = json.loads(bc_post.text)
        bc_dic[f"{bc_list[i]}s"] = data["data"] if i == 0 else data["data"]["content"]
    data = json.dumps(bc_dic, indent=4, ensure_ascii=False)  # 格式化json
    now = datetime.datetime.now()
    current_time = now.strftime("%Y_%m_%d_%H_%M_%S")  # 获取当前时间
    bc_file_name = f"alist_bot_backup_{current_time}.json"
    with open(bc_file_name, "w", encoding="utf-8") as b:
        b.write(data)
    return bc_file_name


# 监听回复消息的消息
@app.on_message(
    (filters.text & filters.reply & filters.private) & ~filters.regex("^/") & is_admin
)
async def echo_bot(_, message: Message):
    if message.reply_to_message.document:  # 判断回复的消息是否包含文件
        await message.delete()
        await app.edit_message_caption(
            chat_id=message.chat.id,
            message_id=message.reply_to_message_id,
            caption=f"#Alist配置备份\n{message.text}",
        )


# 发送备份文件
@app.on_message(filters.command("bc") & filters.private & is_admin)
async def send_backup_file(_, message: Message):
    bc_file_name = backup_config()
    await message.reply_document(document=bc_file_name, caption="#Alist配置备份")
    os.remove(bc_file_name)


# 定时任务——发送备份文件
async def recovery_send_backup_file():
    bc_file_name = backup_config()
    await app.send_document(
        chat_id=admin, document=bc_file_name, caption="#Alist配置定时备份"
    )
    os.remove(bc_file_name)
    logger.info("定时备份成功")


# 设置备份时间&开启定时备份
@app.on_message(filters.command("sbt") & filters.private & is_admin)
async def set_backup_time(_, message: Message):
    mtime = " ".join(message.command[1:])
    if len(mtime.split()) == 5:
        config["bot"]["backup_time"] = mtime
        write_config("config/config.yaml", config)

        cron = croniter.croniter(backup_time(), datetime.datetime.now())
        next_run_time = cron.get_next(datetime.datetime)  # 下一次备份时间
        if aps.job_exists("send_backup_messages_regularly_id"):
            aps.modify_job(
                job_id="send_backup_messages_regularly_id",
                trigger=CronTrigger.from_crontab(backup_time()),
            )
            text = f"修改成功！\n下一次备份时间：{next_run_time}"
        else:
            aps.add_job(
                func=recovery_send_backup_file,
                trigger=CronTrigger.from_crontab(backup_time()),
                job_id="send_backup_messages_regularly_id",
            )
            text = f"已开启定时备份！\n下一次备份时间：{next_run_time}"
        await message.reply(text)
    elif mtime == "0":
        config["bot"]["backup_time"] = mtime
        write_config("config/config.yaml", config)
        aps.pause_job("send_backup_messages_regularly_id")
        await message.reply("已关闭定时备份")
    elif not mtime:
        text = f"""
格式：/sbt + 5位cron表达式，0为关闭
下一次备份时间：`{parse_cron(backup_time()) if backup_time() != '0' else '已关闭'}`

例：
<code>/sbt 0</code> 关闭定时备份
<code>/sbt 0 8 * * *</code> 每天上午8点运行
<code>/sbt 30 20 */3 * *</code> 每3天晚上8点30运行

 5位cron表达式格式说明
  ——分钟（0 - 59）
 |  ——小时（0 - 23）
 | |  ——日（1 - 31）
 | | |  ——月（1 - 12）
 | | | |  ——星期（0 - 6，0是星期一）
 | | | | |
 * * * * *

"""
        await message.reply(text)
    else:
        await message.reply("格式错误")


#####################################################################################
#####################################################################################


# bot重启后要恢复的任务
def recovery_task():
    from module.cloudflare.storage_mgmt import (
        send_cronjob_bandwidth_push,
        send_cronjob_status_push,
    )

    # Alist配置定时备份
    if backup_time() != "0":
        aps.add_job(
            func=recovery_send_backup_file,
            trigger=CronTrigger.from_crontab(backup_time()),
            job_id="send_backup_messages_regularly_id",
        )
        logger.info("定时备份已启动")

    if cloudflare_cfg["cronjob"]["bandwidth_push"]:
        aps.add_job(
            func=send_cronjob_bandwidth_push,
            args=[app],
            trigger=CronTrigger.from_crontab(cloudflare_cfg["cronjob"]["time"]),
            job_id="cronjob_bandwidth_push",
        )
        logger.info("带宽通知已启动")

    cronjob = cloudflare_cfg["cronjob"]
    if any(
        cronjob[key] for key in ["status_push", "storage_mgmt", "auto_switch_nodes"]
    ):
        aps.add_job(
            func=send_cronjob_status_push,
            args=[app],
            trigger="interval",
            job_id="cronjob_status_push",
            seconds=10,
        )
        logger.info("节点监控已启动")


# bot启动时验证
def examine():
    try:
        code = AListAPI.storage_list_()
    except json.decoder.JSONDecodeError:
        logger.error("连接Alist失败，请检查配置alist_host是否填写正确")
        exit()
    except httpx.ReadTimeout:
        logger.error("连接Alist超时，请检查网站状态")
        exit()
    else:
        if code["code"] == 401 and code["message"] == "that's not even a token":
            logger.error("Alist token错误")
            exit()
    return


if __name__ == "__main__":
    logger.info("Bot开始运行...")
    examine()
    recovery_task()
    app.run()
