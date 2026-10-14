import re

from pyrogram import filters
from pyrogram.handlers import MessageHandler

from AloneMusic import app


async def delete_commands(_, message):
    try:
        await message.delete()
    except Exception:
        pass


app.add_handler(
    MessageHandler(
        delete_commands,
        filters.group
        & filters.text
        & filters.regex(
            r"^/(play|vplay|cplay|stream|pause|resume|skip|end|stop)",
            re.IGNORECASE,
        ),
    ),
    group=9999,
)
