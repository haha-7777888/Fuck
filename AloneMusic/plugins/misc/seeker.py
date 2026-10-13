#
# Copyright (C) 2021-2022 by TheAloneteam@Github, < https://github.com/TheAloneTeam >.
#
# This file is part of < https://github.com/TheAloneTeam/AloneMusic > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/TheAloneTeam/AloneMusic/blob/master/LICENSE >
#
# All rights reserved.

import asyncio
import random

from AloneMusic import YouTube
from AloneMusic.misc import db
from AloneMusic.utils.database import get_active_chats, is_music_playing, is_autoplay_on

active_autofill_tasks = set()

async def maintain_autoplay(chat_id):
    if chat_id in active_autofill_tasks:
        return
    active_autofill_tasks.add(chat_id)
    try:
        while await is_autoplay_on(chat_id) and await is_music_playing(chat_id):
            queue = db.get(chat_id, [])
            if not queue:
                break

            # Fill queue up to 50 songs
            if len(queue) < 50:
                last_song = queue[-1]
                vidid = last_song.get("vidid")
                if vidid:
                    try:
                        related = await YouTube.get_related_videos(vidid)
                        if related:
                            for video_id in related:
                                if len(db.get(chat_id, [])) >= 50:
                                    break
                                # check if already in queue
                                if any(q.get("vidid") == video_id for q in db.get(chat_id, [])):
                                    continue

                                details, _ = await YouTube.track(video_id, True)
                                if details and details.get("title"):
                                    # Add to queue
                                    from AloneMusic.utils.stream.queue import put_queue
                                    await put_queue(
                                        chat_id,
                                        last_song.get("chat_id"),
                                        f"vid_{video_id}",
                                        details["title"],
                                        details["duration_min"],
                                        last_song.get("by"),
                                        video_id,
                                        last_song.get("user_id"),
                                        last_song.get("streamtype", "audio"),
                                        forceplay=False,
                                    )
                                    # Mark as auto-added
                                    if len(db.get(chat_id, [])) > 0:
                                        db[chat_id][-1]["is_autoplay"] = True
                    except Exception:
                        pass

            # Pre-download the next 3 songs
            queue = db.get(chat_id, [])
            for i in range(1, min(4, len(queue))):
                song = queue[i]
                if str(song.get("file")).startswith("vid_"):
                    video_id = song.get("vidid")
                    if video_id:
                        try:
                            streamtype = song.get("streamtype", "audio")
                            is_video = True if streamtype == "video" else False
                            file_path, direct = await YouTube.download(
                                video_id,
                                None,
                                videoid=True,
                                video=is_video,
                            )
                            if file_path:
                                song["file"] = file_path
                        except Exception:
                            pass

            await asyncio.sleep(5)
    finally:
        active_autofill_tasks.discard(chat_id)


async def timer():
    while not await asyncio.sleep(1):
        active_chats = await get_active_chats()
        for chat_id in active_chats:
            if not await is_music_playing(chat_id):
                continue
            playing = db.get(chat_id)
            if not playing:
                continue

            # Start maintainer if autoplay is on
            if await is_autoplay_on(chat_id):
                if chat_id not in active_autofill_tasks:
                    asyncio.create_task(maintain_autoplay(chat_id))

            duration = int(playing[0]["seconds"])
            if duration == 0:
                continue
            if db[chat_id][0]["played"] >= duration:
                continue
            db[chat_id][0]["played"] += 1

            # Autoplay Next Song Ready Notification
            played = db[chat_id][0]["played"]
            remaining = duration - played
            if remaining <= 20 and remaining > 15:
                if await is_autoplay_on(chat_id) and len(db[chat_id]) > 1:
                    if not db[chat_id][0].get("ready_notified"):
                        db[chat_id][0]["ready_notified"] = True
                        from AloneMusic import app

                        async def send_autoplay_msg():
                            try:
                                msg = await app.send_message(chat_id, "» ʌᴜᴛᴏᴘʟʌʏ ɴєxᴛ sᴏɴɢ ʀєʌᴅʏ !")
                                if db.get(chat_id) and len(db[chat_id]) > 0:
                                    db[chat_id][0]["autoplay_msg"] = msg
                            except Exception:
                                pass

                        asyncio.create_task(send_autoplay_msg())


asyncio.create_task(timer())
