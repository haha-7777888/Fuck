
# Copyright (C) 2021-2022 by TheAloneteam@Github, < https://github.com/TheAloneTeam >.
#
# This file is part of < https://github.com/TheAloneTeam/AloneMusic > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/TheAloneTeam/AloneMusic/blob/master/LICENSE >
#
# All rights reserved.

import math
from typing import Union

from pyrogram.types import InlineKeyboardButton

from AloneMusic import app
from AloneMusic.utils.formatters import time_to_seconds


# --------------------------------------------------
# COLORED BUTTON HELPER
# --------------------------------------------------

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


# --------------------------------------------------
# TRACK SELECTION
# --------------------------------------------------

def track_markup(_, videoid, user_id, channel, fplay, thumb: Union[bool, str] = None):
    buttons = [
        [
            btn(
    " ",
    "success",
    5334665104677941170,
    callback_data=f"MusicStream {videoid}|{user_id}|a|{channel}|{fplay}",
),
            btn(
    " ",
    "primary",
    5258077307985207053,
    callback_data=f"MusicStream {videoid}|{user_id}|v|{channel}|{fplay}",
),
        ],
        [
            btn(
    " ",
    "primary",
    5323404142809467476,
    callback_data=f"MusicThumb {videoid}|{user_id}|{channel}|{fplay}",
),
            btn(
    " ",
    "danger",
    5260342697075416641,
    callback_data=f"forceclose {videoid}|{user_id}",
),
        ],
    ]
    return buttons


# --------------------------------------------------
# STREAM CONTROLS WITH TIMER
# --------------------------------------------------

def stream_markup_timer(
    _,
    chat_id,
    played,
    dur,
    autoplay: Union[bool, str] = None,
    thumb: Union[bool, str] = None,
    chat_filter: Union[bool, str] = None,
    more: bool = False,
):
    played_sec = time_to_seconds(played)
    duration_sec = time_to_seconds(dur)

    remaining_sec = max(0, duration_sec - played_sec)

    rem_min = remaining_sec // 60
    rem_sec = remaining_sec % 60
    remaining = f"{rem_min:02d}:{rem_sec:02d}"

    percentage = (played_sec / duration_sec) * 100 if duration_sec else 0
    umm = math.floor(percentage)

    if 0 < umm <= 10:
        bar = "|♬—————————|"
    elif 10 < umm < 20:
        bar = "|—♬————————|"
    elif 20 <= umm < 30:
        bar = "|——♬———————|"
    elif 30 <= umm < 40:
        bar = "|———♬——————|"
    elif 40 <= umm < 50:
        bar = "|————♬—————|"
    elif 50 <= umm < 60:
        bar = "|—————♬————|"
    elif 60 <= umm < 70:
        bar = "|——————♬———|"
    elif 70 <= umm < 80:
        bar = "|———————♬——|"
    elif 80 <= umm < 95:
        bar = "|————————♬—|"
    else:
        bar = "|—————————♬|"

    if not more:
        buttons = [
            [
                btn(
                    f"{played} {bar} {remaining}",
                    "primary",
                    url=f"https://t.me/{app.username}?startgroup=true",
                )
            ],
            [
                btn("▷", "success", callback_data=f"ADMIN Resume|{chat_id}"),
                btn("II", "primary", callback_data=f"ADMIN Pause|{chat_id}"),
                btn("‣‣I", "success", callback_data=f"ADMIN Skip|{chat_id}"),
                btn("↻ ", "primary", callback_data=f"ADMIN Replay|{chat_id}"),
                btn("▢", "danger", callback_data=f"ADMIN Stop|{chat_id}"),
            ],
            [
                btn("<-𝟤𝟢 s", "primary", callback_data="seek_backward_20"),
                btn("☰", "primary", callback_data=f"ADMIN More|{chat_id}"),
                btn("𝟤𝟢s+ >", "primary", callback_data="seek_forward_20"),
            ],
            [
                btn("ᴄʟᴏsᴇ", "danger",callback_data="close"),
            ],
        ]

    else:
        f_text = (
            chat_filter.replace("Normal", "🎶")
            .replace("Bass", "🔊")
            .replace("Echo", "🎧")
            .replace("Slowed", "🎬")
            .replace("Nightcore", "🌙")
            if chat_filter
            else "ɴᴏʀᴍᴀʟ"
        )

        buttons = [
            [
                btn(
                    f"{played} {bar} {remaining}",
                    "primary",
                    url=f"https://t.me/{app.username}?startgroup=true",
                )
            ],
            [
                btn("ᴀᴜᴛᴏᴘʟᴀʏ", "primary", callback_data=f"ADMIN Autoplay|{chat_id}"),
                btn(
                    "ᴏɴ" if autoplay else "ᴏғғ",
                    "success" if autoplay else "danger",
                    callback_data=f"ADMIN Autoplay|{chat_id}",
                ),
            ],
            [
                btn("ᴛʜᴜᴍʙɴᴀɪʟ", "primary", callback_data=f"ADMIN Thumb|{chat_id}"),
                btn(
                    "ᴏɴ" if thumb else "ᴏғғ",
                    "success" if thumb else "danger",
                    callback_data=f"ADMIN Thumb|{chat_id}",
                ),
            ],
            [
                btn("ᴠᴏɪᴄᴇ ᴄᴏɴᴛʀᴏʟ", "primary", callback_data=f"ADMIN Filter|{chat_id}"),
                btn(f_text, "success", callback_data=f"ADMIN Filter|{chat_id}"),
            ],
            [
                btn(" ʙᴀᴄᴋ", "primary", callback_data=f"ADMIN Back|{chat_id}"),
                btn(" ᴄʟᴏsᴇ", "danger", callback_data="close"),
            ],
        ]

    return buttons


# --------------------------------------------------
# STREAM CONTROLS
# --------------------------------------------------

def stream_markup(
    _,
    chat_id,
    autoplay: Union[bool, str] = None,
    thumb: Union[bool, str] = None,
    chat_filter: Union[bool, str] = None,
    more: bool = False,
):
    if not more:
        buttons = [
            [
                btn("▷", "success", callback_data=f"ADMIN Resume|{chat_id}"),
                btn("II", "primary", callback_data=f"ADMIN Pause|{chat_id}"),
                btn("‣‣I", "success", callback_data=f"ADMIN Skip|{chat_id}"),
                btn("↻", "primary", callback_data=f"ADMIN Replay|{chat_id}"),
                btn("▢", "danger", callback_data=f"ADMIN Stop|{chat_id}"),
            ],
            [
                btn("☰", "primary", callback_data=f"ADMIN More|{chat_id}"),
                btn("ᴄʟᴏsᴇ", "danger", 5258130763148172425, callback_data="close"),
            ],
        ]

    else:
        f_text = (
            chat_filter.replace("Normal", "ɴᴏʀᴍᴀʟ")
            .replace("Bass", "ʙᴀss")
            .replace("Echo", "ᴇᴄʜᴏ")
            .replace("Slowed", "sʟᴏᴡᴇᴅ")
            .replace("Nightcore", "ɴɪɢʜᴛᴄᴏʀᴇ")
            if chat_filter
            else "ɴᴏʀᴍᴀʟ"
        )

        buttons = [
            [
                btn("ᴀᴜᴛᴏᴘʟᴀʏ", "primary", callback_data=f"ADMIN Autoplay|{chat_id}"),
                btn(
                    "ᴇɴᴀʙʟᴇᴅ" if autoplay else "ᴅɪsᴀʙʟᴇᴅ",
                    "success" if autoplay else "danger",
                    callback_data=f"ADMIN Autoplay|{chat_id}",
                ),
            ],
            [
                btn("ᴛʜᴜᴍʙɴᴀɪʟ", "primary", callback_data=f"ADMIN Thumb|{chat_id}"),
                btn(
                    "ᴇɴᴀʙʟᴇᴅ" if thumb else "ᴅɪsᴀʙʟᴇᴅ",
                    "success" if thumb else "danger",
                    callback_data=f"ADMIN Thumb|{chat_id}",
                ),
            ],
            [
                btn("ᴠᴏɪᴄᴇ ᴄᴏɴᴛʀᴏʟ", "primary", callback_data=f"ADMIN Filter|{chat_id}"),
                btn(f_text, "success", callback_data=f"ADMIN Filter|{chat_id}"),
            ],
            [
                btn("⟵ ʙᴀᴄᴋ", "primary", callback_data=f"ADMIN Back|{chat_id}"),
                btn("🗑 ᴄʟᴏsᴇ", "danger", callback_data="close"),
            ],
        ]

    return buttons


# --------------------------------------------------
# PLAYLIST TRACK SELECTION
# --------------------------------------------------

def playlist_markup(
    _, videoid, user_id, ptype, channel, fplay,
    thumb: Union[bool, str] = None
):
    buttons = [
        [
            btn(
                "🎵",
                "success",
                callback_data=f"AlonePlaylists {videoid}|{user_id}|{ptype}|a|{channel}|{fplay}",
            ),
            btn(
                "🎥",
                "primary",
                callback_data=f"AlonePlaylists {videoid}|{user_id}|{ptype}|v|{channel}|{fplay}",
            ),
        ],
        [
            btn(
                "⎘",
                "primary",
                callback_data=f"PlaylistThumb {videoid}|{user_id}|{ptype}|{channel}|{fplay}",
            ),
            btn(
                "✖",
                "danger",
                callback_data=f"forceclose {videoid}|{user_id}",
            ),
        ],
    ]
    return buttons


# --------------------------------------------------
# LIVESTREAM TRACK SELECTION
# --------------------------------------------------

def livestream_markup(
    _, videoid, user_id, mode, channel, fplay,
    thumb: Union[bool, str] = None
):
    buttons = [
        [
            btn(
                "🎬",
                "success",
                callback_data=f"LiveStream {videoid}|{user_id}|{mode}|{channel}|{fplay}",
            ),
        ],
        [
            btn(
                "⎘",
                "primary",
                callback_data=f"LiveThumb {videoid}|{user_id}|{mode}|{channel}|{fplay}",
            ),
            btn(
                "✖",
                "danger",
                callback_data=f"forceclose {videoid}|{user_id}",
            ),
        ],
    ]
    return buttons


# --------------------------------------------------
# SEARCH SLIDER
# --------------------------------------------------

def slider_markup(
    _, videoid, user_id, query, query_type, channel, fplay,
    thumb: Union[bool, str] = None
):
    query = f"{query[:20]}"

    buttons = [
        [
            btn(
                "🎵",
                "success",
                callback_data=f"MusicStream {videoid}|{user_id}|a|{channel}|{fplay}",
            ),
            btn(
                "🎥",
                "primary",
                callback_data=f"MusicStream {videoid}|{user_id}|v|{channel}|{fplay}",
            ),
        ],
        [
            btn(
                "◁",
                "primary",
                callback_data=f"slider B|{query_type}|{query}|{user_id}|{channel}|{fplay}",
            ),
            btn(
                "⎘",
                "primary",
                callback_data=f"SliderThumb {videoid}|{user_id}|{query}|{query_type}|{channel}|{fplay}",
            ),
            btn(
                "▷",
                "primary",
                callback_data=f"slider F|{query_type}|{query}|{user_id}|{channel}|{fplay}",
            ),
        ],
        [
            btn(
                "✖",
                "danger",
                callback_data=f"forceclose {query}|{user_id}",
            ),
        ],
    ]

    return buttons

