
from pyrogram.types import InlineKeyboardButton

import config
from AloneMusic import app


def btn(text, style=None, icon=None, **kw):
    try:
        from pyrogram.enums import ButtonStyle

        extra = {}

        if style:
            extra["style"] = getattr(ButtonStyle, style.upper())

        if icon:
            extra["icon_custom_emoji_id"] = str(icon)

        return InlineKeyboardButton(text=text, **kw, **extra)

    except (ImportError, TypeError, AttributeError):
        return InlineKeyboardButton(text=text, **kw)


def start_panel(_):
    """Buttons for group start: Add Me + Support in one row."""
    return [
        [
            btn(
                "𝐀ᴅᴅ 𝐌ᴇ",
                "success",
                5134476056241112076,
                url=f"https://t.me/{app.username}?startgroup=true",
            ),
            btn(
                "𝐒ᴜᴘᴘᴏʀᴛ",
                "success",
                5134202243486057363,
                url=config.SUPPORT_CHAT,
            ),
        ],
    ]


def private_panel(_):
    """Buttons for private/DM start."""
    return [
        [
            btn(
                " 𝐀ᴅᴅ 𝐌ᴇ",
                "success",
                5134476056241112076,
                url=f"https://t.me/{app.username}?startgroup=true",
            ),
        ],
        [
            btn(
                " 𝐒ᴜᴘᴘᴏʀᴛ",
                "success",
                5134202243486057363,
                url=config.SUPPORT_CHAT,
            ),
            btn(
                " 𝐂ᴏᴅᴇ 𝐂ʀᴇᴡ",
                "success",
                5085022089103016925,
                url=config.CODE_CREW_CHANNEL,
            ),
        ],
        [
            btn(
                "𝐂ᴏᴍᴍᴀɴᴅs",
                "success",
                5134202243486057363,
                callback_data="settings_back_helper",
            ),
        ],
    ]
