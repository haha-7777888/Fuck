import asyncio
from logging import getLogger
from typing import Dict, Set
from datetime import datetime

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
        upsert=True
    )
    vc_logger_cache[chat_id] = status


# ================= PARTICIPANTS =================

async def get_group_call_participants(userbot, peer):
    try:
        full_chat = await userbot.invoke(functions.channels.GetFullChannel(channel=peer))

        if not hasattr(full_chat.full_chat, "call") or not full_chat.full_chat.call:
            return "NO_CALL"

        call = full_chat.full_chat.call

        participants = await userbot.invoke(
            functions.phone.GetGroupParticipants(
                call=call, ids=[], sources=[], offset="", limit=100
            )
        )
        return participants.participants

    except Exception as e:
        LOGGER.error(f"[VC] Participant fetch error: {e}")
        return "ERROR"


async def get_vc_members_count(userbot, chat_id):
    try:
        peer = await userbot.resolve_peer(chat_id)
        participants = await get_group_call_participants(userbot, peer)
        if isinstance(participants, list):
            return len(participants)
        return 0
    except:
        return 0


# ================= MONITOR =================

async def monitor_vc_chat(chat_id):
    userbot = await get_assistant(chat_id)
    if not userbot:
        return

    LOGGER.info(f"[VC] Monitor started for chat {chat_id}")

    while chat_id in active_vc_chats:
        try:
            peer = await userbot.resolve_peer(chat_id)
            participants_list = await get_group_call_participants(userbot, peer)

            if participants_list == "ERROR":
                await asyncio.sleep(5)
                continue
            elif participants_list == "NO_CALL":
                vc_active_users[chat_id] = set()
                await asyncio.sleep(5)
                continue

            new_users = {p.peer.user_id for p in participants_list if hasattr(p, "peer")}
            current_users = vc_active_users.get(chat_id, set())

            joined = new_users - current_users
            left = current_users - new_users

            for uid in joined:
                await handle_user_join(chat_id, uid, userbot)

            for uid in left:
                await handle_user_leave(chat_id, uid, userbot)

            vc_active_users[chat_id] = new_users

        except Exception as e:
            LOGGER.error(f"[VC] Monitor error: {e}")

        await asyncio.sleep(5)


async def check_and_monitor_vc(chat_id):
    if chat_id in active_vc_chats:
        return

    userbot = await get_assistant(chat_id)
    if not userbot:
        return

    active_vc_chats.add(chat_id)

    # Initialize with current users to avoid spamming join messages on monitor start
    try:
        peer = await userbot.resolve_peer(chat_id)
        participants_list = await get_group_call_participants(userbot, peer)
        if isinstance(participants_list, list):
            vc_active_users[chat_id] = {p.peer.user_id for p in participants_list if hasattr(p, "peer")}
        else:
            vc_active_users[chat_id] = set()
    except Exception:
        vc_active_users[chat_id] = set()

    asyncio.create_task(monitor_vc_chat(chat_id))
    LOGGER.info(f"[VC] Logger started for chat {chat_id}")


# ================= AUTO LOAD ALL ENABLED CHATS =================

async def load_vclogger_chats():
    global vclogger_loaded

    if vclogger_loaded:
        return

    vclogger_loaded = True
    chats = await mongodb.vclogger.find({"enabled": True}).to_list(length=1000)

    for data in chats:
        chat_id = data["chat_id"]
        asyncio.create_task(check_and_monitor_vc(chat_id))
        LOGGER.info(f"[VC] Auto-loaded logger for chat {chat_id}")


# ================= JOIN / LEAVE =================

async def handle_user_join(chat_id, user_id, userbot):
    if not await get_vclogger_status(chat_id):
        return

    try:
        user = await userbot.get_users(user_id)
        count = await get_vc_members_count(userbot, chat_id)

        username = f"@{user.username}" if user.username else "None"

        role = "Member"
        try:
            member = await app.get_chat_member(chat_id, user_id)
            if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                role = "Admin"
        except Exception:
            pass

        # Group message (styled exactly as requested)
        msg = (
            "╭───『 🎧 𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ 』───╮\n"
            f"│ ✦ 𝐍ᴀᴍᴇ ➛ {user.mention}\n"
            f"│ ✦ 𝐈ᴅ ➛ `{user.id}`\n"
            f"│ ✦ 𝐔sᴇʀɴᴀᴍᴇ ➛ @{username}\n"
            "╰────────────────────╯"
            
        )

        sent = await app.send_message(chat_id, msg)
        await asyncio.sleep(3)
        try:
            await sent.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"[VC] Join error: {e}")


async def handle_user_leave(chat_id, user_id, userbot):
    if not await get_vclogger_status(chat_id):
        return

    try:
        user = await userbot.get_users(user_id)

        username = f"@{user.username}" if user.username else "None"

        role = "Member"
        try:
            member = await app.get_chat_member(chat_id, user_id)
            if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                role = "Admin"
        except Exception:
            pass

        # Group message (styled exactly as requested)
       msg = (
            "╭───『 🎧 𝐕ɪᴅᴇᴏ 𝐂ʜᴀᴛ 』───╮\n"
            f"│ ✦ 𝐍ᴀᴍᴇ ➛ {user.mention}\n"
            f"│ ✦ 𝐈ᴅ ➛ `{user.id}`\n"
            f"│ ✦ 𝐔sᴇʀɴᴀᴍᴇ ➛ @{username}\n"
            "╰────────────────────╯"
            
        )
        sent = await app.send_message(chat_id, msg)
        await asyncio.sleep(3)
        try:
            await sent.delete()
        except Exception:
            pass

    except Exception as e:
        LOGGER.error(f"[VC] Leave error: {e}")


# ================= COMMANDS =================

@app.on_message(filters.command(["vclogger", "Vclogger"]) & filters.group)
async def vclogger_command(_, message: Message):
    await load_vclogger_chats()

    if not await admin_check(message):
        return await message.reply_text("❌ Only admins can use this command!")

    if len(message.command) < 2:
        return await message.reply_text("Usage:\n/vclogger on\n/vclogger off\n/vclogger enable\n/vclogger disable")

    cmd = message.command[1].lower()
    chat_id = message.chat.id

    if cmd in ["on", "enable"]:
        await set_vclogger_status(chat_id, True)
        await message.reply_text("✅ VC Logger Enabled")
        asyncio.create_task(check_and_monitor_vc(chat_id))

    elif cmd in ["off", "disable"]:
        await set_vclogger_status(chat_id, False)
        active_vc_chats.discard(chat_id)
        vc_active_users.pop(chat_id, None)
        await message.reply_text("🚫 VC Logger Disabled")

    else:
        await message.reply_text("Usage:\n/vclogger on\n/vclogger off\n/vclogger enable\n/vclogger disable")


@app.on_message(filters.command("vcstats") & filters.group)
async def vcstats_command(_, message: Message):
    await load_vclogger_chats()

    chat_id = message.chat.id
    status = await get_vclogger_status(chat_id)

    await message.reply_text(
        f"🎥 **VC Logger Stats**\n\n"
        f"📌 Status: {'Enabled' if status else 'Disabled'}\n"
        f"📡 Monitor: {'Running' if chat_id in active_vc_chats else 'Stopped'}\n"
        f"🆔 Chat ID: `{chat_id}`"
    )


@app.on_message(filters.command(["vcuser", "vcusers", "vcmember", "vcmembers"]) & filters.group)
async def vc_members(client, message):
    if not await admin_check(message):
        return await message.reply_text("❌ Only admins can use this command!")

    try:
        language = await get_lang(message.chat.id)
        _ = get_string(language)
    except:
        _ = get_string("en")

    msg = await message.reply_text(_["V_C_1"])
    userbot = await get_assistant(message.chat.id)
    TEXT = ""

    try:
        async for m in userbot.get_call_members(message.chat.id):
            chat_id = m.chat.id
            username = m.chat.username
            is_hand_raised = m.is_hand_raised
            is_video_enabled = m.is_video_enabled
            is_left = m.is_left
            is_screen_sharing_enabled = m.is_screen_sharing_enabled
            is_muted = bool(m.is_muted and not m.can_self_unmute)
            is_speaking = not m.is_muted

            if m.chat.type != ChatType.PRIVATE:
                title = m.chat.title
            else:
                try:
                    title = (await client.get_users(chat_id)).mention
                except:
                    title = m.chat.first_name

            TEXT += _["V_C_2"].format(
                title,
                chat_id,
                username,
                is_video_enabled,
                is_screen_sharing_enabled,
                is_hand_raised,
                is_muted,
                is_speaking,
                is_left,
            )
            TEXT += "\n\n"

        if len(TEXT) < 4000:
            await msg.edit(TEXT or _["V_C_3"])
        else:
            link = await AloneBin(TEXT)
            await msg.edit(
                _["V_C_4"].format(link),
                disable_web_page_preview=True,
            )

    except ValueError:
        await msg.edit(_["V_C_5"])


# ================= AUTO BOOT VC LOGGER =================

async def auto_boot_vclogger():
    await asyncio.sleep(10)  # bot ko fully start hone ka time
    await load_vclogger_chats()
    LOGGER.info("[VC] Auto boot VC Logger completed")


# start background task
asyncio.get_event_loop().create_task(auto_boot_vclogger())
