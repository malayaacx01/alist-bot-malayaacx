from pyrogram import filters, Client
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    Message,
)

from api.cloudflare_api import list_zones, list_filters
from config.config import nodee, cloudflare_cfg, chat_data, write_config
from tool.utils import is_admin


# cf账号管理按钮回调
@Client.on_callback_query(filters.regex("^account_add$"))
async def account_add_callback(_, query: CallbackQuery):
    await account_add(query)
    chat_data["ad_message"] = query


# 添加/删除账号
async def account_add(query: CallbackQuery):
    text = []
    chat_data["account_add_return_button"] = [
        InlineKeyboardButton("↩️返回账号", callback_data="account_return"),
        InlineKeyboardButton("❌关闭菜单", callback_data="cf_close"),
    ]
    if nodee():
        for index, value in enumerate(nodee()):
            text_t = f"{index + 1} | <code>{value['email']}</code> | <code>{value['global_api_key']}</code>\n"
            text.append(text_t)
        t = "\n".join(text)
    else:
        t = "暂无账号"
    tt = """
——————————————
<b>添加：</b>
一次只能添加一个账号
第一行cf邮箱，第二行global_api_key，例：
<code>abc123@qq.com
285812f3012365412d33398713c156e2db314
</code>
<b>删除：</b>
*+序号，例：<code>*2</code>
"""
    await query.message.edit(
        text=t + tt,
        reply_markup=InlineKeyboardMarkup([chat_data["account_add_return_button"]]),
    )
    chat_data["account_add"] = True


def _account_add_filter(_, __, ___):
    return bool("account_add" in chat_data and chat_data["account_add"])


account_add_filter = filters.create(_account_add_filter)


# 开始处理
@Client.on_message(filters.text & account_add_filter & filters.private & is_admin)
async def account_edit(_, message: Message):
    mt = message.text
    await message.delete()
    if mt[0] != "*":
        try:
            i = mt.split("\n")

            lz = await list_zones(i[0], i[1])  # 获取区域id
            lz = lz.json()
            account_id = lz["result"][0]["account"]["id"]
            zone_id = lz["result"][0]["id"]
            lf = await list_filters(i[0], i[1], zone_id)  # 获取url
            lf = lf.json()
        except Exception as e:
            await chat_data["ad_message"].answer(text=f"错误：{str(e)}")
        else:
            if lf["result"]:
                url = lf["result"][0]["pattern"].rstrip("/*")
                d = {
                    "url": url,
                    "email": i[0],
                    "global_api_key": i[1],
                    "account_id": account_id,
                    "zone_id": zone_id,
                }
                if cloudflare_cfg["node"]:
                    cloudflare_cfg["node"].append(d)
                else:
                    cloudflare_cfg["node"] = [d]
                write_config("config/cloudflare_cfg.yaml", cloudflare_cfg)
                await account_add(chat_data["ad_message"])
            else:
                text = f"""
<b>添加失败: </b>

<code>{mt}</code>

该域名（<code>{lz['result'][0]['name']}</code>）未添加Workers路由
请检查后重新发送账号

<b>注：</b>默认使用第一个域名的第一个Workers路由
"""
                await chat_data["ad_message"].message.edit(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(
                        [chat_data["account_add_return_button"]]
                    ),
                )

    else:
        i = int(mt.split("*")[1])
        del cloudflare_cfg["node"][i - 1]
        write_config("config/cloudflare_cfg.yaml", cloudflare_cfg)
        await account_add(chat_data["ad_message"])
