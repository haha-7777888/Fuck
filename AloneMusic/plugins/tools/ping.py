#
# Copyright (C) 2021-2022 by TheAloneteam@Github, < https://github.com/TheAloneTeam >.
#
# This file is part of < https://github.com/TheAloneTeam/AloneMusic > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/TheAloneTeam/AloneMusic/blob/master/LICENSE >
#
# All rights reserved.

from datetime import datetime

from pyrogram import filters
from pyrogram.types import Message

from AloneMusic import app
from AloneMusic.core.call import Alone
from AloneMusic.utils import bot_sys_stats
from AloneMusic.utils.decorators.language import language
from AloneMusic.utils.inline import supp_markup
from config import BANNED_USERS, PING_IMG_URL


@app.on_message(filters.command(["ping", "alive"]) & ~BANNED_USERS)
@language
async def ping_com(client, message: Message, _):
    start = datetime.now()
    
    # Try sending photo; fallback to text if photo URL fails
    try:
        response = await message.reply_photo(
            photo=PING_IMG_URL,
            caption=_["ping_1"].format(app.mention),
        )
        has_photo = True
    except Exception:
        response = await message.reply_text(
            text=_["ping_1"].format(app.mention),
        )
        has_photo = False

    pytgping = await Alone.ping()
    UP, CPU, RAM, DISK = await bot_sys_stats()
    resp = (datetime.now() - start).microseconds / 1000

    text_to_send = _["ping_2"].format(resp, app.mention, UP, RAM, CPU, DISK, pytgping)

    if has_photo:
        await response.edit_caption(
            caption=text_to_send,
            reply_markup=supp_markup(_),
        )
    else:
        await response.edit_text(
            text=text_to_send,
            reply_markup=supp_markup(_),
        )
