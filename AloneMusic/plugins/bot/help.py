
#
# Copyright (C) 2021-2022 by TheAloneteam@Github,
# < https://github.com/TheAloneTeam >.
#
# This file is part of
# < https://github.com/TheAloneTeam/ZeroTwo > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see
# < https://github.com/TheAloneTeam/ZeroTwo/blob/master/LICENSE >
#
# All rights reserved.

from typing import Union

from pyrogram import filters, types
from pyrogram.types import InlineKeyboardMarkup, Message

from ZeroTwo import app
from ZeroTwo.misc import SUDOERS
from ZeroTwo.utils import help_pannel
from ZeroTwo.utils.database import get_lang
from ZeroTwo.utils.decorators.language import LanguageStart
from ZeroTwo.utils.inline.help import help_back_markup

from config import BANNED_USERS, START_IMG_URL, SUPPORT_CHAT
from strings import get_string


def get_english_strings():
    """Load English strings from strings/langs/en.yml."""
    return get_string("en")


@app.on_message(filters.command(["help"]) & filters.private & ~BANNED_USERS)
@app.on_callback_query(
    filters.regex("^settings_back_helper$") & ~BANNED_USERS
)
async def helper_private(
    client: app,
    update: Union[types.Message, types.CallbackQuery],
):
    _ = get_english_strings()

    if isinstance(update, types.CallbackQuery):
        try:
            await update.answer()
        except Exception:
            pass

        if not update.message:
            return

        keyboard = help_pannel(_, True)

        await update.edit_message_text(
            _["help_1"].format(SUPPORT_CHAT),
            reply_markup=keyboard,
        )

    else:
        try:
            await update.delete()
        except Exception:
            pass

        keyboard = help_pannel(_)

        await update.reply_photo(
            photo=START_IMG_URL,
            has_spoiler=False,
            caption=_["help_1"].format(SUPPORT_CHAT),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


@app.on_message(filters.command(["help"]) & filters.group & ~BANNED_USERS)
async def help_com_group(client, message: Message):
    """Display the help menu in groups using English YAML strings."""
    _ = get_english_strings()
    keyboard = help_pannel(_)

    await message.reply_text(
        _["help_1"].format(SUPPORT_CHAT),
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True,
    )


@app.on_callback_query(
    filters.regex("^help_callback") & ~BANNED_USERS
)
async def helper_cb(client, CallbackQuery):
    """Load individual help pages from strings/langs/en.yml."""
    _ = get_english_strings()

    callback_data = CallbackQuery.data.strip()
    parts = callback_data.split(None, 1)

    if len(parts) < 2:
        await CallbackQuery.answer(
            "Invalid help option.",
            show_alert=True,
        )
        return

    cb = parts[1].strip()

    if not cb.startswith("hb") or not cb[2:].isdigit():
        await CallbackQuery.answer(
            "Help page not found.",
            show_alert=True,
        )
        return

    page = int(cb[2:])
    key = f"help_{page}"

    # Preserve the sudo-only restriction for page 7.
    if page == 7 and CallbackQuery.from_user.id not in SUDOERS:
        await CallbackQuery.answer(
            "This button is only for sudo users.",
            show_alert=True,
        )
        return

    # Check that the requested page exists in en.yml.
    if key not in _:
        await CallbackQuery.answer(
            f"{key} is missing from strings/langs/en.yml.",
            show_alert=True,
        )
        return

    keyboard = help_back_markup(_)

    await CallbackQuery.answer()
    await CallbackQuery.edit_message_text(
        _[key],
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )
