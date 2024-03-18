# -*- coding: UTF-8 -*-
import asyncio
import urllib.parse

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)

from api.alist_api import AListAPI
from config.config import config, per_page, z_url, alist_web, write_config, member
from tool.utils import is_admin
from tool.utils import pybyte


@Client.on_message(filters.command("sl") & is_admin)
async def sl(_, message: Message):
    sl_str = " ".join(message.command[1:])
    if sl_str.isdigit():
        config["bot"]["search"]["per_page"] = int(sl_str)
        write_config("config/config.yaml", config)
        await message.reply(f"The number of modified search results is：{sl_str}")
    else:
        await message.reply("Please enter a positive integer")


# 设置直链
@Client.on_message(filters.command("zl") & is_admin)
async def zl(_, message: Message):
    zl_str = " ".join(message.command[1:])
    if zl_str == "1":
        config["bot"]["search"]["z_url"] = True
        await message.reply("Direct link enabled")
    elif zl_str == "0":
        config["bot"]["search"]["z_url"] = False
        await message.reply("Direct link closed")
    else:
        await message.reply("Please add 1 or 0 after the command (1=on, 0=off)")
    write_config("config/config.yaml", config)


chat_id_message = {}

page_button = [
    InlineKeyboardButton("⬆️Previous page", callback_data="search_previous_page"),
    InlineKeyboardButton("⬇️Next page", callback_data="search_next_page"),
]


# 搜索
@Client.on_message(filters.command("s"))
async def s(_, message: Message):
    if member and message.chat.id not in member:
        return
    s_str = " ".join(message.command[1:])
    if not s_str or "_bot" in s_str:
        return await message.reply("Please add the file name, for example: /s chocolate")
    # 搜索文件
    alist_post_json = await AListAPI.search(s_str)

    if not alist_post_json["data"]["content"]:
        return await message.reply("No file found, try changing the keywords.")
    result_deduplication = [
        dict(t) for t in {tuple(d.items()) for d in alist_post_json["data"]["content"]}
    ]
    msg = await message.reply("searching...")

    task = [get_(count, item) for count, item in enumerate(result_deduplication)]
    textx = await asyncio.gather(*task)

    chat_id = message.chat.id
    chat_message = f"{chat_id}|{message.id + 1}"
    chat_id_message[chat_message] = {
        "page": 1,
        "pointer": 0,
        "text": textx,
    }
    page_count = (
        len(chat_id_message[chat_message]["text"]) + per_page() - 1
    ) // per_page()
    search_button = [
        [InlineKeyboardButton(f"1/{page_count}", callback_data="search_pages")],
        page_button,
    ]
    await msg.edit(
        text="".join(chat_id_message[chat_message]["text"][: per_page()]),
        reply_markup=InlineKeyboardMarkup(search_button),
        disable_web_page_preview=True,
    )


async def get_(count, item):
    file_name, path, file_size, folder = (
        item["name"],
        item["parent"],
        item["size"],
        item["is_dir"],
    )

    # 获取文件直链
    if folder:
        folder_tg_text = "📁folder："
        z_folder_f = ""
        z_url_link = ""
    elif z_url():
        folder_tg_text = "📄document："
        z_folder = "Download"
        z_folder_f = "|"
        r = await AListAPI.fs_get(f"{path}/{file_name}")
        z_url_link = f'<a href="{r["data"]["raw_url"]}">{z_folder}</a>'
    else:
        folder_tg_text = "📄document："
        z_folder_f = ""
        z_url_link = ""

    file_url = urllib.parse.quote(f"{alist_web}{path}/{file_name}", safe=":/")
    return f"""{count + 1}.{folder_tg_text}<code>{file_name}</code>
<a href="{file_url}">🌐Open website</a>|{z_url_link}{z_folder_f}大小: {pybyte(file_size)}

"""


# Turn page
@Client.on_callback_query(filters.regex(r"^search"))
async def search_button_callback(_, query: CallbackQuery):
    data = query.data
    chat_message_id = f"{query.message.chat.id}|{query.message.id}"

    async def turn():
        pointer = chat_id_message[chat_message_id]["pointer"]
        text = chat_id_message[chat_message_id]["text"][pointer : pointer + per_page()]

        search_button = [
            [
                InlineKeyboardButton(
                    f"{chat_id_message[chat_message_id]['page']}/{page_count}",
                    callback_data="search_pages",
                )
            ],
            page_button,
        ]
        await query.message.edit(
            text="".join(text),
            reply_markup=InlineKeyboardMarkup(search_button),
            disable_web_page_preview=True,
        )

    page = chat_id_message[chat_message_id]["page"]
    page_count = (
        len(chat_id_message[chat_message_id]["text"]) + per_page() - 1
    ) // per_page()
    if data == "search_next_page":
        if page < page_count:
            chat_id_message[chat_message_id]["pointer"] += per_page()  # 指针每次加5，表示下一页
            chat_id_message[chat_message_id]["page"] += 1
            await turn()
    elif data == "search_previous_page":
        if page > 1:
            chat_id_message[chat_message_id]["page"] -= 1
            chat_id_message[chat_message_id]["pointer"] -= per_page()  # 指针每次减5，表示上一页
            await turn()
