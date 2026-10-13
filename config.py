#
# Copyright (C) 2021-2022 by TheAloneteam@Github, < https://github.com/TheAloneTeam >.
#
# This file is part of < https://github.com/TheAloneTeam/TheAloneMusic > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/TheAloneTeam/TheAloneMusic/blob/master/LICENSE >
# All rights reserved.

import re
from os import getenv

from dotenv import load_dotenv
from pyrogram import filters
from os import getenv
import random

RANDOM_THUMBS = [
    "https://files.catbox.moe/ikxb96.jpg",
    "https://files.catbox.moe/dqxsjh.jpg",
    "https://files.catbox.moe/lnaqxk.jpg",
    "https://files.catbox.moe/0qzssp.jpg",
    "https://files.catbox.moe/lz57vi.jpg",
    "https://files.catbox.moe/x1fcb6.jpg",
    "https://files.catbox.moe/32ghsc.jpg",
]

def get_thumb():
    return random.choice(RANDOM_THUMBS)


START_IMG_URL = getenv("START_IMG_URL", get_thumb())
PING_IMG_URL = getenv("PING_IMG_URL", get_thumb())

PLAYLIST_IMG_URL = get_thumb()
STATS_IMG_URL = get_thumb()
TELEGRAM_AUDIO_URL = get_thumb()
TELEGRAM_VIDEO_URL = get_thumb()
STREAM_IMG_URL = get_thumb()
SOUNCLOUD_IMG_URL = get_thumb()
YOUTUBE_IMG_URL = get_thumb()
SPOTIFY_ARTIST_IMG_URL = get_thumb()
SPOTIFY_ALBUM_IMG_URL = get_thumb()
SPOTIFY_PLAYLIST_IMG_URL = get_thumb()

load_dotenv()
YTPROXY_URL = getenv("YTPROXY_URL", 'https://tgapi.xbitcode.com') ## xBit Music Endpoint.
YT_API_KEY = getenv("YT_API_KEY" , "xbit_KiY0HWimxyDMVxjg6R7-7UtJKyPW9kSD")

# Gethis value from my.telegram.org/apps
API_ID = getenv("API_ID", "25742938")
API_HASH = getenv("API_HASH", "b35b715fe8dc0a58e8048988286fc5b6")

# Get your token from @BotFather on Telegram.
BOT_TOKEN = getenv("8806982181:AAEVjkruo78UVzZUYwhRWoMyQhanFaojlII")

# Get your mongo url from cloud.mongodb.com
MONGO_DB_URI = getenv("MONGO_DB_URI", "mongodb+srv://lollolopp0900_db_user:xbaj05RPixvCXNMS@zero.rqsozug.mongodb.net/?appName=Zero")

DURATION_LIMIT_MIN = int(getenv("DURATION_LIMIT", 600))
CODE_CREW_CHANNEL = "https://t.me/thecodecrew"
# Set this to true if you want post ads automatically
ADS_MODE = getenv("ADS_MODE", None)

# Chat id of a group for logging bot's activities
LOGGER_ID = int(getenv("LOGGER_ID", -1003972764819))

DEBUG_IGNORE_LOG = True
# Get this value from  on Telegram by /id
OWNER_ID = int(getenv("OWNER_ID", 6018803920))

## Fill these variables if you're deploying on heroku.
# Your heroku app name
HEROKU_APP_NAME = getenv("HEROKU_APP_NAME")
# Get it from http://dashboard.heroku.com/account
HEROKU_API_KEY = getenv("HEROKU_API_KEY")

UPSTREAM_REPO = getenv(
    "UPSTREAM_REPO",
    "https://github.com/riteshxcoder/AloneMusicc",
)
UPSTREAM_BRANCH = getenv("UPSTREAM_BRANCH", "master")
GIT_TOKEN = getenv(
    "GIT_TOKEN", None
)  # Fill this variable if your upstream repository is private


SUPPORT_CHANNEL = getenv("SUPPORT_CHANNEL", "https://t.me/MeowCloner")
SUPPORT_CHAT = getenv("SUPPORT_CHAT", "https://t.me/MeowClone")
# Set this to True if you want the assistant to automatically leave chats after an interval
AUTO_LEAVING_ASSISTANT = bool(getenv("AUTO_LEAVING_ASSISTANT", None))


# Get this credentials from https://developer.spotify.com/dashboard
SPOTIFY_CLIENT_ID = getenv("SPOTIFY_CLIENT_ID", None)
SPOTIFY_CLIENT_SECRET = getenv("SPOTIFY_CLIENT_SECRET", None)


# Maximum limit for fetching playlist's track from youtube, spotify, apple links.
PLAYLIST_FETCH_LIMIT = int(getenv("PLAYLIST_FETCH_LIMIT", 25))


# Telegram audio and video file size limit (in bytes)
TG_AUDIO_FILESIZE_LIMIT = int(getenv("TG_AUDIO_FILESIZE_LIMIT", 104857600))
TG_VIDEO_FILESIZE_LIMIT = int(getenv("TG_VIDEO_FILESIZE_LIMIT", 1073741824))
# Checkout https://www.gbmb.org/mb-to-bytes for converting mb to bytes


# Get your pyrogram v2 session from @StringFatherBot on Telegram
STRING1 = getenv("STRING_SESSION", "BQHu1LMAwLf-POAYDKRRVb4GBzy4--33i3YsUwKL4PO_zAuIzgT_xJkkB6y5Xe_-Uq9fTdznO4D92JqeVuooroKugXvDrVUS4lzgr0dkqdGUzLD3ySzSj0gHMEc9RdPc7u9wY3JAfu9FRu6Zg3ep5EYzG57GD0FdwDpyRh7YJ61ZrnA6uRkPjIudGADRpRS_XwPE9Sv8tTpLhVwh68c6_ODsY-LAH5-lRy_-8VCa2ZpMdL6mX7CJc_z3MYBNkhOxqySBWPfG9N6IUz6KVMUw3RsOK2Pty8fUM9R5EIXVwAj8i3YAXJ8OtzKv1s1qc368ShF5uXC0pA1GJff9j8o4N8OfeLGHKwAAAAIGzIVnAA")
STRING2 = getenv("STRING_SESSION2", None)
STRING3 = getenv("STRING_SESSION3", None)
STRING4 = getenv("STRING_SESSION4", None)
STRING5 = getenv("STRING_SESSION5", None)


BANNED_USERS = filters.user()
adminlist = {}
lyrical = {}
votemode = {}
autoclean = []
confirmer = {}

START_IMG_URL = getenv(
    "START_IMG_URL",
    "https://i.ibb.co/99NrkQjn/photo-2026-10-13-06-09-53-7696030749559881736.jpg",
)

PING_IMG_URL = getenv(
    "PING_IMG_URL",
    "https://i.ibb.co/99NrkQjn/photo-2026-10-13-06-09-53-7696030749559881736.jpg",
)

PLAYLIST_IMG_URL = (
    "https://repgyetdcodkynrbxocg.supabase.co/storage/v1/object/public/"
    "https://image-link.edgeone.app/1791871688204-wrcgkl.jpg"
)

STATS_IMG_URL = (
    "https://repgyetdcodkynrbxocg.supabase.co/storage/v1/object/public/"
    "https://i.ibb.co/0V89tqgs/photo-2026-10-13-06-08-59-7696030517631647780.jpg"
)

TELEGRAM_AUDIO_URL = (
    "https://repgyetdcodkynrbxocg.supabase.co/storage/v1/object/public/"
    "https://image-link.edgeone.app/1791871688204-wrcgkl.jpg"
)

TELEGRAM_VIDEO_URL = TELEGRAM_AUDIO_URL

STREAM_IMG_URL = "https://image-link.edgeone.app/1791871688204-wrcgkl.jpg"
SOUNCLOUD_IMG_URL = "https://image-link.edgeone.app/1791871688204-wrcgkl.jpg"
YOUTUBE_IMG_URL = "https://image-link.edgeone.app/1791871688204-wrcgkl.jpg"
SPOTIFY_ARTIST_IMG_URL = "https://image-link.edgeone.app/1791871688204-wrcgkl.jpg"
SPOTIFY_ALBUM_IMG_URL = "https://image-link.edgeone.app/1791871688204-wrcgkl.jpg"
SPOTIFY_PLAYLIST_IMG_URL = "https://image-link.edgeone.app/1791871688204-wrcgkl.jpg"


def time_to_seconds(time):
    stringt = str(time)
    return sum(int(x) * 60**i for i, x in enumerate(reversed(stringt.split(":"))))


DURATION_LIMIT = int(time_to_seconds(f"{DURATION_LIMIT_MIN}:00"))


if SUPPORT_CHANNEL:
    if not re.match("(?:http|https)://", SUPPORT_CHANNEL):
        raise SystemExit(
            "[ERROR] - Your SUPPORT_CHANNEL url is wrong. Please ensure that it starts with https://"
        )

if SUPPORT_CHAT:
    if not re.match("(?:http|https)://", SUPPORT_CHAT):
        raise SystemExit(
            "[ERROR] - Your SUPPORT_CHAT url is wrong. Please ensure that it starts with https://"
        )
