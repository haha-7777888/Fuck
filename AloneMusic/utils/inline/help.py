
#
# Copyright (C) 2021-2022 by TheAloneteam@Github, < https://github.com/TheAloneTeam >.
#
# This file is part of < https://github.com/TheAloneTeam/ZeroTwo > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/TheAloneTeam/ZeroTwo/blob/master/LICENSE >
#
# All rights reserved.

from typing import Union

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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


def help_pannel(_, START: Union[bool, int] = None):
    first = [
        btn(
            text=_["CLOSE_BUTTON"],
            callback_data="close",
        )
    ]

    second = [
        btn(
            text=_["BACK_BUTTON"],
            callback_data="settingsback_helper",
        ),
    ]

    mark = second if START else first

    upl = InlineKeyboardMarkup(
        [
            [
                btn(
                    text=_["H_B_1"],
                   # style="success",
                    callback_data="help_callback hb1",
                ),
                btn(
                    text=_["H_B_2"],
                   # style="success",
                    callback_data="help_callback hb2",
                ),
                btn(
                    text=_["H_B_3"],
                  #  style="success",
                    callback_data="help_callback hb3",
                ),
            ],
            [
                btn(
                    text=_["H_B_4"],
                   # style="success",
                    callback_data="help_callback hb4",
                ),
                btn(
                    text=_["H_B_5"],
                   # style="success",
                    callback_data="help_callback hb5",
                ),
                btn(
                    text=_["H_B_6"],
                   # style="success",
                    callback_data="help_callback hb6",
                ),
            ],
            [
                btn(
                    text=_["H_B_7"],
                    #style="success",
                    callback_data="help_callback hb7",
                ),
                btn(
                    text=_["H_B_8"],
                   # style="success",
                    callback_data="help_callback hb8",
                ),
                btn(
                    text=_["H_B_9"],
                   # style="success",
                    callback_data="help_callback hb9",
                ),
            ],
            [
                btn(
                    text=_["H_B_10"],
                   # style="success",
                    callback_data="help_callback hb10",
                ),
                btn(
                    text=_["H_B_11"],
                   # style="success",
                    callback_data="help_callback hb11",
                ),
            ],
          #  [
              #  btn(
                #    text=_["H_B_12"],
                 #   style="success",
                #    callback_data="help_callback hb12",
               # ),
              #  btn(
                 #   text=_["H_B_13"],
                 #   style="success",
                 #   callback_data="help_callback hb13",
              #  ),
            #],
            mark,
        ]
    )

    return upl


def help_back_markup(_):
    upl = InlineKeyboardMarkup(
        [
            [
                btn(
                    text=_["BACK_BUTTON"],
                    callback_data="settings_back_helper",
                ),
            ]
        ]
    )

    return upl


def private_help_panel(_):
    buttons = [
        [
            btn(
                text=_["S_B_4"],
                url=f"https://t.me/{app.username}?start=help",
            ),
        ],
    ]

    return buttons
