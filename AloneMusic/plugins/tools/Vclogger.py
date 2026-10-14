
import asyncio
from logging import getLogger
from typing import Dict, Set

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.raw import functions
from pyrogram.enums import ChatType, ChatMemberStatus

from AloneMusic import app
from AloneMusic.helper.admin_check import admin_check
from AloneMusic.utils.database import get_assistant, get_lang
from AloneMusic.core.mongo import mongodb
from AloneMusic.utils import AloneBin
from strings import get_string

LOGGER = getLogger(__name__)

# ================= GLOBALS =================

vc_active_users: Dict[int, Set[int]] = {}
active_vc_chats: Set[int] = set()
vc_logger_cache: Dict[int, bool] = {}
vclogger_loaded = False
monitor_tasks: Dict[int, asyncio.Task] = {}


# ================= MONGO =================

async def get_vclogger_status(chat_id: int) -> bool:
    if chat_id in vc_logger_cache:
        return vc_logger_cache[chat_id]

    data = await mongodb.vclogger.find_one({"chat_id": chat_id})
    status = bool(data and data.get("enabled", False))
    vc_logger_cache[chat_id] = status
    return status


async def set_vclogger_status(chat_id: int, status: bool):
    await mongodb.vclogger.update_one(
        {"chat_id": chat_id},
        {"$set": {"enabled": status}},
        upsert=True,
    )
    vc_logger_cache[chat_id] = status


# ================= PARTICIPANTS =================

async def get_group_call_participants(userbot, peer):
    try:
        full_chat = await userbot.invoke(
            functions.channels.GetFullChannel(channel=peer)
        )

        call = getattr(full_chat.full_chat, "call", None)
        if not call:
            return "NO_CALL"

        participants = await userbot.invoke(
            functions.phone.GetGroupParticipants(
                call=call,
                ids=[],
                sources=[],
                offset="",
                limit=100,
            )
        )
        return participants.participants

    except Exception as e:
        LOGGER.error(f"[VC] Participant fetch error: {e}")
        return "ERROR"


def extract_user_ids(participants) -> Set[int]:
    """Extract user IDs safely from group-call participants."""
    user_ids = set()

    if not isinstance(participants, list):
        return user_ids

    for participant in participants:
        peer = getattr(participant, "peer", None)
        user_id = getattr(peer, "user_id", None)

        if user_id is not None:
            user_ids.add(user_id)

    return user_ids


async def get_vc_members_count(userbot, chat_id: int) -> int:
    try:
        peer = await userbot.resolve_peer(chat_id)
        participants = await get_group_call_participants(userbot, peer)

        if isinstance(participants, list):
            return len(participants)

        return 0

    except Exception as e:
        LOGGER.error(f"[VC] Member count error: {e}")
        return 0


# ================= MONITOR =================

async def monitor_vc_chat(chat_id: int):
    userbot = await get_assistant(chat_id)

    if not userbot:
        active_vc_chats.discard(chat_id)
        return

    LOGGER.info(f"[VC] Monitor started for chat {chat_id}")

    try:
        while chat_id in active_vc_chats:
            try:
                peer = await userbot.resolve_peer(chat_id)
                participants = await get_group_call_participants(
                    userbot, peer
                )

                if participants == "ERROR":
                    await asyncio.sleep(5)
                    continue

                if participants == "NO_CALL":
                    vc_active_users[chat_id] = set()
                    await asyncio.sleep(5)
                    continue

                new_users = extract_user_ids(participants)
                current_users = vc_active_users.get(chat_id, set())

                joined = new_users - current_users
                left = current_users - new_users

                for user_id in joined:
                    await handle_user_join(chat_id, user_id, userbot)

                for user_id in left:
                    await handle_user_leave(chat_id, user_id, userbot)

                vc_active_users[chat_id] = new_users

            except asyncio.CancelledError:
                raise
            except Exception as e:
                LOGGER.error(f"[VC] Monitor error for {chat_id}: {e}")

            await asyncio.sleep(5)

    finally:
        active_vc_chats.discard(chat_id)
        vc_active_users.pop(chat_id, None)
        monitor_tasks.pop(chat_id, None)
        LOGGER.info(f"[VC] Monitor stopped for chat {chat_id}")


async def check_and_monitor_vc(chat_id: int):
    if chat_id in active_vc_chats:
        return

    if not await get_vclogger_status(chat_id):
        return

    userbot = await get_assistant(chat_id)

    if not userbot:
        LOGGER.warning(f"[VC] No assistant available for chat {chat_id}")
        return

    active_vc_chats.add(chat_id)

    # Initialize with current participants to avoid false join alerts.
    try:
        peer = await userbot.resolve_peer(chat_id)
        participants = await get_group_call_participants(
            userbot, peer
        )
        vc_active_users[chat_id] = extract_user_ids(participants)

    except Exception as e:
        LOGGER.error(f"[VC] Initial participant fetch error: {e}")
        vc_active_users[chat_id] = set()

    task = asyncio.create_task(monitor_vc_chat(chat_id))
    monitor_tasks[chat_id] = task

    LOGGER.info(f"[VC] Logger started for chat {chat_id}")


# ================= AUTO LOAD ENABLED CHATS =================

async def load_vclogger_chats():
    global vclogger_loaded

    if vclogger_loaded:
        return

    try:
        chats = await mongodb.vclogger.find(
            {"enabled": True}
        ).to_list(length=1000)

        for data in chats:
            chat_id = data.get("chat_id")

            if chat_id is None:
                continue

            vc_logger_cache[chat_id] = True

            if chat_id not in active_vc_chats:
                asyncio.create_task(check_and_monitor_vc(chat_id))

            LOGGER.info(f"[VC] Auto-loaded logger for {chat_id}")

        vclogger_loaded = True

    except Exception as e:
        LOGGER.error(f"[VC] Failed to load logger settings: {e}")


# ================= JOIN / LEAVE =================

async def get_user_role(chat_id: int, user_id: int) -> str:
    try:
        member = await app.get_chat_member(chat_id, user_id)

        if member.status in (
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR,
        ):
            return "Admin"

    except Exception:
        pass

    return "Member"


async def handle_user_join(chat_id: int, user_id: int, userbot):
    if not await get_vclogger_status(chat_id):
        return

    try:
        user = await userbot.get_users(user_id)
        username = f"@{user.username}" if user.username else "None"
        role = await get_user_role(chat_id, user_id)
        count = await get_vc_members_count(userbot, chat_id)

        msg = (
            "╭───『 🎧 𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ 』───╮\n"
            f"│ ✦ 𝐍ᴀᴍᴇ ➛ {user.mention}\n"
            f"│ ✦ 𝐈ᴅ ➛ `{user.id}`\n"
            f"│ ✦ 𝐔sᴇʀɴᴀᴍᴇ ➛ {username}\n"
            f"│ ✦ 𝐀ᴄᴛɪᴏɴ ➛ 𝐉ᴏɪɴᴇᴅ [{role}]\n"
            f"│ 🔁 𝐉ᴏɪɴ 𝐂ᴏᴜɴᴛ ➛ {count}\n"
            "╰────────────────────╯"
        )

        sent = await app.send_message(chat_id, msg)
        await asyncio.sleep(3)

        try:
            await sent.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"[VC] Join error in {chat_id}: {e}")


async def handle_user_leave(chat_id: int, user_id: int, userbot):
    if not await get_vclogger_status(chat_id):
        return

    try:
        user = await userbot.get_users(user_id)
        username = f"@{user.username}" if user.username else "None"
        role = await get_user_role(chat_id, user_id)

        msg = (
            "╭───『 🎧 𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ 』───╮\n"
            f"│ ✦ 𝐍ᴀᴍᴇ ➛ {user.mention}\n"
            f"│ ✦ 𝐈ᴅ ➛ `{user.id}`\n"
            f"│ ✦ 𝐔sᴇʀɴᴀᴍᴇ ➛ {username}\n"
            f"│ ✦ 𝐀ᴄᴛɪᴏɴ ➛ 𝐋ᴇғᴛ [{role}]\n"
            "╰────────────────────╯"
        )

        sent = await app.send_message(chat_id, msg)
        await asyncio.sleep(3)

        try:
            await sent.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"[VC] Leave error in {chat_id}: {e}")


# ================= COMMANDS =================

@app.on_message(
    filters.command(["vclogger", "Vclogger"]) & filters.group
)
async def vclogger_command(_, message: Message):
    await load_vclogger_chats()

    if not await admin_check(message):
        return await message.reply_text(
            "❌ Only admins can use this command!"
        )

    if len(message.command) < 2:
        return await message.reply_text(
            "Usage:\n/vclogger on\n/vclogger off\n"
            "/vclogger enable\n/vclogger disable"
        )

    cmd = message.command[1].lower()
    chat_id = message.chat.id

    if cmd in ("on", "enable"):
        await set_vclogger_status(chat_id, True)
        await message.reply_text("✅ VC Logger Enabled")
        await check_and_monitor_vc(chat_id)

    elif cmd in ("off", "disable"):
        await set_vclogger_status(chat_id, False)

        active_vc_chats.discard(chat_id)
        vc_active_users.pop(chat_id, None)

        task = monitor_tasks.get(chat_id)
        if task and not task.done():
            task.cancel()

        await message.reply_text("🚫 VC Logger Disabled")

    else:
        await message.reply_text(
            "Usage:\n/vclogger on\n/vclogger off\n"
            "/vclogger enable\n/vclogger disable"
        )


@app.on_message(filters.command("vcstats") & filters.group)
async def vcstats_command(_, message: Message):
    await load_vclogger_chats()

    chat_id = message.chat.id
    status = await get_vclogger_status(chat_id)

    await message.reply_text(
        f"🎥 **VC Logger Stats**\n\n"
        f"📌 Status: {'Enabled' if status else 'Disabled'}\n"
        f"📡 Monitor: "
        f"{'Running' if chat_id in active_vc_chats else 'Stopped'}\n"
        f"🆔 Chat ID: `{chat_id}`"
    )


@app.on_message(
    filters.command(
        ["vcuser", "vcusers", "vcmember", "vcmembers"]
    ) & filters.group
)
async def vc_members(client, message: Message):
    if not await admin_check(message):
        return await message.reply_text(
            "❌ Only admins can use this command!"
        )

    try:
        language = await get_lang(message.chat.id)
        _ = get_string(language)
    except Exception:
        _ = get_string("en")

    msg = await message.reply_text(_["V_C_1"])
    userbot = await get_assistant(message.chat.id)

    if not userbot:
        return await msg.edit("❌ Assistant is not available.")

    text = ""

    try:
        async for member in userbot.get_call_members(message.chat.id):
            user_id = member.chat.id
            username = member.chat.username
            is_hand_raised = member.is_hand_raised
            is_video_enabled = member.is_video_enabled
            is_left = member.is_left
            is_screen_sharing_enabled = (
                member.is_screen_sharing_enabled
            )
            is_muted = bool(
                member.is_muted and not member.can_self_unmute
            )
            is_speaking = not member.is_muted

            if member.chat.type != ChatType.PRIVATE:
                title = member.chat.title
            else:
                try:
                    title = (await client.get_users(user_id)).mention
                except Exception:
                    title = member.chat.first_name

            text += _["V_C_2"].format(
                title,
                user_id,
                username,
                is_video_enabled,
                is_screen_sharing_enabled,
                is_hand_raised,
                is_muted,
                is_speaking,
                is_left,
            )
            text += "\n\n"

        if len(text) < 4000:
            await msg.edit(text or _["V_C_3"])
        else:
            link = await AloneBin(text)
            await msg.edit(
                _["V_C_4"].format(link),
                disable_web_page_preview=True,
            )

    except ValueError:
        await msg.edit(_["V_C_5"])

    except Exception as e:
        LOGGER.error(f"[VC] Failed to fetch members: {e}")
        await msg.edit("❌ Failed to fetch voice chat members.")


# ================= AUTO BOOT =================

async def auto_boot_vclogger():
    await asyncio.sleep(10)
    await load_vclogger_chats()
    LOGGER.info("[VC] Auto boot VC Logger completed")


# Schedule startup task when this module is imported.
asyncio.get_event_loop().create_task(auto_boot_vclogger())
