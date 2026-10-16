"""
YouTube.py — YouTube platform for AloneMusic (Yuki API Version)
License: GNU GPL v3.0
"""

import asyncio
import copy
import glob
import logging
import os
import random
import re
import shutil
import time
import urllib.parse
from typing import Union

import yt_dlp

try:
    import config
except ImportError:
    class config:
        DURATION_LIMIT = 600

try:
    import httpx
except ImportError:
    httpx = None

try:
    from pyrogram.enums import MessageEntityType
except ImportError:
    class MessageEntityType:
        URL = "url"
        TEXT_LINK = "text_link"

try:
    from pyrogram.types import Message
except ImportError:
    class Message:
        pass

try:
    from AloneMusic.utils.database import is_on_off
except ImportError:
    async def is_on_off(*args, **kwargs):
        return True

try:
    from AloneMusic.utils.formatters import time_to_seconds
except ImportError:
    def time_to_seconds(value):
        if not value:
            return 0
        try:
            parts = list(map(int, str(value).split(":")))
            if len(parts) == 3:
                return parts[0] * 3600 + parts[1] * 60 + parts[2]
            if len(parts) == 2:
                return parts[0] * 60 + parts[1]
            return parts[0]
        except (ValueError, TypeError):
            return 0


# Yuki API Configuration
YUKI_API_KEY = "yuki_2f4ece93cd8cc9662f80ae6ab866a677"
PRIMARY_STREAM_URL = "https://music.yukiapi.site/stream"
BACKUP_STREAM_URL = "https://play.yukiapi.site/stream"

LOGGER = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio/best"
VIDEO_FORMAT = "best[height<=720][width<=1280]/best[height<=720]/best"
MAX_PREFETCH_PARALLEL = 2
HAS_ARIA2C = shutil.which("aria2c") is not None
AUDIO_EXTS = ("m4a", "opus", "ogg", "mp3", "aac", "webm")
_PARTIAL_RE = re.compile(r"(\.(part|ytdl|temp|tmp)$)|(\.f\d+\.)", re.I)

BASE_URL = "https://www.youtube.com/watch?v="
PLAYLIST_URL = "https://www.youtube.com/playlist?list="


def extract_vidid(query):
    """Extract a YouTube video ID from a URL or ID."""
    if not query:
        return None

    query = str(query).strip()

    if re.fullmatch(r"[A-Za-z0-9_-]{11}", query):
        return query

    patterns = (
        r"(?:youtube\.com|youtube-nocookie\.com)/(?:watch\?.*?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com|youtube-nocookie\.com)/(?:shorts|embed|live|v)/([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
    )

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def _ydl_options(**overrides):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 15,
        "retries": 1,
        "extractor_retries": 1,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "mweb"]
            }
        },
    }
    options.update(overrides)
    return options


class YouTubeAPI:
    def __init__(self):
        self.base = BASE_URL
        self.listbase = PLAYLIST_URL
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

        self._client = None
        self._recent_prefetches = {}
        self._info_cache = {}
        self._cache_ttl = 600
        self._info_locks = {}
        self._lock_guard = asyncio.Lock()
        self._bg_tasks = set()
        self._prefetch_sem = asyncio.Semaphore(MAX_PREFETCH_PARALLEL)

    async def warmup(self):
        try:
            if httpx is not None:
                await self.get_client()
            LOGGER.info("YouTubeAPI warmup completed successfully.")
        except Exception as err:
            LOGGER.warning("YouTubeAPI warmup notice: %s", err)

    async def get_client(self):
        if httpx is None:
            raise RuntimeError("httpx is not installed")

        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=5.0),
                follow_redirects=True,
            )
        return self._client

    async def exists(self, link, videoid: Union[bool, str] = None):
        if not link:
            return False
        if videoid:
            link = self.base + str(link)
        return bool(re.search(self.regex, str(link), re.IGNORECASE))

    async def url(self, message_1):
        messages = [message_1]
        reply = getattr(message_1, "reply_to_message", None)

        if reply:
            messages.append(reply)

        for message in messages:
            body = (
                getattr(message, "text", None)
                or getattr(message, "caption", None)
                or ""
            )
            entities = getattr(message, "entities", None) or []
            caption_entities = (
                getattr(message, "caption_entities", None) or []
            )

            for entity in entities:
                if entity.type == MessageEntityType.URL:
                    return body[entity.offset:entity.offset + entity.length]
                if entity.type == MessageEntityType.TEXT_LINK:
                    return getattr(entity, "url", None)

            for entity in caption_entities:
                if entity.type == MessageEntityType.TEXT_LINK:
                    return getattr(entity, "url", None)
                if entity.type == MessageEntityType.URL:
                    return body[entity.offset:entity.offset + entity.length]

        return None

    def _clean_link(self, link):
        if not link:
            return ""

        link = str(link).strip()

        if not link.startswith(("http://", "https://")):
            return link

        try:
            parsed = urllib.parse.urlsplit(link)

            if not parsed.query:
                return link.split("#", 1)[0]

            ignored = {
                "si",
                "feature",
                "pp",
                "embeds_referring_euri",
                "source_ve_path",
            }

            items = urllib.parse.parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
            cleaned = [
                (key, value)
                for key, value in items
                if key.lower() not in ignored
            ]

            return urllib.parse.urlunsplit((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urllib.parse.urlencode(cleaned),
                "",
            ))

        except Exception:
            return link.split("#", 1)[0]

    @staticmethod
    def _format_duration(seconds):
        if seconds is None:
            return None

        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            return None

        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)

        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    async def _yt_info(self, query, limit=1, flat=False):
        query = str(query or "").strip()
        if not query:
            return None

        is_url = query.startswith(("https://", "http://"))

        if not is_url:
            query_str = f"ytsearch{max(1, int(limit))}:{query}"
        else:
            query_str = query

        cache_key = f"{query_str}|{limit}|{flat}"
        now = time.monotonic()

        cached = self._info_cache.get(cache_key)
        if cached and now - cached[0] < self._cache_ttl:
            return cached[1]

        async with self._lock_guard:
            lock = self._info_locks.setdefault(cache_key, asyncio.Lock())

        async with lock:
            now = time.monotonic()
            cached = self._info_cache.get(cache_key)
            if cached and now - cached[0] < self._cache_ttl:
                return cached[1]

            options = _ydl_options(
                noplaylist=not flat,
                extract_flat="in_playlist" if flat else False,
                ignoreerrors=True,
                socket_timeout=12,
                retries=1,
                extractor_retries=1,
            )

            def extract():
                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(query_str, download=False)

            try:
                info = await asyncio.to_thread(extract)
                if info:
                    self._info_cache[cache_key] = (time.monotonic(), info)
                    return info
            except Exception as error:
                LOGGER.warning("Local yt-dlp metadata error for %s: %s", query, error)

            return None

    async def _search_results(self, query, limit=10):
        info = await self._yt_info(query, limit=limit)
        if not info:
            return []

        entries = info.get("entries")
        if entries is not None:
            return [entry for entry in entries if entry]

        return [info] if info.get("id") else []

    @staticmethod
    def _normalise_video(item):
        if not item:
            return None

        vidid = item.get("id")
        if not vidid:
            return None

        thumbnails = item.get("thumbnails") or []
        thumbnail = item.get("thumbnail")

        if not thumbnail and thumbnails:
            thumbnail = thumbnails[-1].get("url")

        if not thumbnail:
            thumbnail = f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg"

        duration = item.get("duration")
        link = (
            item.get("webpage_url")
            or item.get("original_url")
            or f"https://www.youtube.com/watch?v={vidid}"
        )

        return {
            "title": item.get("title") or "Unknown title",
            "link": link,
            "vidid": vidid,
            "duration_min": YouTubeAPI._format_duration(duration),
            "duration_sec": int(duration or 0),
            "thumb": thumbnail.split("?")[0],
        }

    async def details(self, link, videoid=None):
        if videoid:
            link = self.base + str(link)

        link = self._clean_link(link)
        info = await self._yt_info(link)

        if info and info.get("entries") is not None:
            entries = info.get("entries") or []
            info = entries[0] if entries else None

        item = self._normalise_video(info)
        if not item:
            return None, None, 0, None, None

        return (
            item["title"],
            item["duration_min"],
            item["duration_sec"],
            item["thumb"],
            item["vidid"],
        )

    async def title(self, link, videoid=None):
        return (await self.details(link, videoid))[0]

    async def duration(self, link, videoid=None):
        return (await self.details(link, videoid))[1]

    async def thumbnail(self, link, videoid=None):
        return (await self.details(link, videoid))[3]

    async def track(self, link, videoid=None):
        if videoid:
            link = self.base + str(link)

        link = self._clean_link(link)
        results = await self._search_results(link, limit=1)

        if not results:
            LOGGER.warning("No YouTube search results for: %s", link)
            return None, None

        item = self._normalise_video(results[0])
        if not item:
            return None, None

        track = {
            "title": item["title"],
            "link": item["link"],
            "vidid": item["vidid"],
            "duration_min": item["duration_min"],
            "thumb": item["thumb"],
        }

        return track, item["vidid"]

    async def video(self, link, videoid=None):
        """Yuki API Stream Gateway integration for fast playback without local heavy downloads."""
        if videoid:
            link = self.base + str(link)

        link = self._clean_link(link)
        vid_extracted = extract_vidid(link)

        if vid_extracted:
            # Use Yuki API Primary Stream Gateway
            stream_url = f"{PRIMARY_STREAM_URL}/{vid_extracted}?key={YUKI_API_KEY}"
            LOGGER.info("Generated Yuki API stream URL for %s", vid_extracted)
            return 1, stream_url

        try:
            result = await self.download(link, None, video=True)
            if result and isinstance(result, tuple) and result[0]:
                return 1, result[0]
        except Exception as error:
            LOGGER.warning("YouTube video download failed: %s", error)

        return 0, "Could not generate Yuki stream URL"

    async def playlist(self, link, limit, user_id, videoid=None):
        if videoid:
            link = self.listbase + str(link)

        link = self._clean_link(link)

        try:
            limit = max(1, int(limit))
            info = await self._yt_info(link, limit=limit, flat=True)

            if not info or info.get("entries") is None:
                return None

            videos = []

            for entry in info.get("entries") or []:
                if not entry or not entry.get("id"):
                    continue

                item = self._normalise_video(entry)
                if not item:
                    continue

                videos.append({
                    "title": item["title"],
                    "link": item["link"],
                    "vidid": item["vidid"],
                    "duration_min": item["duration_min"],
                    "thumb": item["thumb"],
                })

                if len(videos) >= limit:
                    break

            return videos or None

        except Exception as error:
            LOGGER.warning("YouTube playlist extraction failed: %s", error)
            return None

    async def formats(self, link, videoid=None):
        if videoid:
            link = self.base + str(link)

        link = self._clean_link(link)

        def extract():
            with yt_dlp.YoutubeDL(_ydl_options(noplaylist=True, socket_timeout=15)) as ydl:
                return ydl.extract_info(link, download=False)

        try:
            info = await asyncio.to_thread(extract)
            output = []

            for item in (info or {}).get("formats") or []:
                format_name = str(item.get("format") or "")
                if "dash" in format_name.lower():
                    continue

                output.append({
                    "format": item.get("format"),
                    "filesize": item.get("filesize") or item.get("filesize_approx"),
                    "format_id": item.get("format_id"),
                    "ext": item.get("ext"),
                    "format_note": item.get("format_note"),
                    "yturl": link,
                })

            return output, link

        except Exception as error:
            LOGGER.warning("YouTube formats extraction failed: %s", error)
            return [], link

    async def slider(self, link, query_type, videoid=None):
        if videoid:
            link = self.base + str(link)

        results = await self._search_results(link, limit=10)

        if (
            not isinstance(query_type, int)
            or query_type < 0
            or query_type >= len(results)
        ):
            return None, None, None, None

        item = self._normalise_video(results[query_type])
        if not item:
            return None, None, None, None

        return (
            item["title"],
            item["duration_min"],
            item["thumb"],
            item["vidid"],
        )

    def _start_local_prefetch(self, link, video=False):
        pass

    async def prefetch(self, link, video=False):
        return True

    async def prefetch_queue(self, queries, video=False):
        return True

    async def get_related_videos(self, vidid: str):
        try:
            results = await self._search_results(f"related songs", limit=10)
            related = []
            for entry in results:
                item = self._normalise_video(entry)
                if not item or item["vidid"] == vidid:
                    continue
                related.append(item["vidid"])
            return related
        except Exception:
            return []

    @staticmethod
    def _cached_file(video_id, is_video):
        return None

    async def download(
        self,
        link,
        mystic,
        video=None,
        videoid=None,
        *args,
        **kwargs,
    ):
        """Directly returns the Yuki API Stream URL instead of heavy local downloading, avoiding intro audio issues."""
        if videoid:
            link = self.base + str(link)

        link = self._clean_link(link)
        if not link:
            return None

        vid = extract_vidid(link)
        if not vid:
            return None

        # Return Yuki API primary stream link directly
        stream_url = f"{PRIMARY_STREAM_URL}/{vid}?key={YUKI_API_KEY}"
        return stream_url, True

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


YouTube = YouTubeAPI()
