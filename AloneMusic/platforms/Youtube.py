"""
YouTube.py — YouTube platform for AloneMusic
License: GNU GPL v3.0

YouTube search, metadata, playlists, related videos and downloads via yt-dlp.
No YouTube Data API key required.
"""

import asyncio
import copy
import glob
import logging
import os
import random
import re
import shutil
import threading
import time
import urllib.parse
from typing import Union

import yt_dlp
import config

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


API_URL = ""
API_KEY = ""

LOGGER = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
# --- Speed settings -------------------------------------------------------
# m4a (AAC) is small and starts fast; falls back to anything else.
AUDIO_FORMAT = "bestaudio[ext=m4a]/bestaudio/best"
VIDEO_FORMAT = "best[height<=720][width<=1280]/best[height<=720]/best"
# Max simultaneous background (prefetch) downloads.
MAX_PREFETCH_PARALLEL = 1
# aria2c (if installed) opens many connections per file = much faster.
HAS_ARIA2C = shutil.which("aria2c") is not None
AUDIO_EXTS = ("m4a", "opus", "ogg", "mp3", "aac", "webm")
_PARTIAL_RE = re.compile(r"(\.(part|ytdl|temp|tmp)$)|(\.f\d+\.)", re.I)

# Fast single-video lookups: one player request with the android_vr client
# (no web page, no JS player). Falls back to normal extraction on failure and
# switches itself off for 10 min after 3 failures in a row.
FAST_EXTRACT = True
FAST_EXTRACTOR_ARGS = {
    "youtube": {
        "player_client": ["android_vr"],
        "player_skip": ["webpage", "configs"],
    }
}
_tls = threading.local()

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
    """Shared lightweight yt-dlp options."""
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 15,
        "retries": 1,
        "extractor_retries": 1,
    }
    options.update(overrides)
    return options


def _fast_extract(query):
    """Single-video lookup on a per-thread, reused yt-dlp instance
    (keeps connections warm and skips setup cost). Returns info or None."""
    ydl = getattr(_tls, "ydl", None)
    try:
        if ydl is None:
            ydl = yt_dlp.YoutubeDL(
                _ydl_options(
                    noplaylist=True,
                    extractor_args=FAST_EXTRACTOR_ARGS,
                    socket_timeout=8,
                )
            )
            _tls.ydl = ydl
        return ydl.extract_info(query, download=False)
    except Exception as error:
        LOGGER.debug("Fast extract failed for %s: %s", query, error)
        _tls.ydl = None
        return None


async def check_file_size(link):
    """Return the total reported format size, or None."""
    def extract():
        with yt_dlp.YoutubeDL(
            _ydl_options(noplaylist=True)
        ) as ydl:
            return ydl.extract_info(link, download=False)

    try:
        info = await asyncio.to_thread(extract)
        if not info:
            return None

        total = sum(
            item.get("filesize") or item.get("filesize_approx") or 0
            for item in info.get("formats", [])
        )
        return total or None

    except Exception as error:
        LOGGER.warning("Could not check YouTube file size: %s", error)
        return None


async def download_assistant(query, dl_type):
    """Build an external download URL only if configured."""
    if not API_URL:
        return None

    safe_query = urllib.parse.quote(str(query))
    extension = "mp3" if dl_type == "audio" else "mp4"

    if API_KEY:
        return f"{API_URL}/downloads/{API_KEY}/{safe_query}.{extension}"

    return (
        f"{API_URL}/downloads/stream"
        f"?query={safe_query}&dl_type={dl_type}"
    )


class YouTubeAPI:
    def __init__(self):
        self.base = BASE_URL
        self.listbase = PLAYLIST_URL
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.status = "https://www.youtube.com/oembed?url="
        self.reg = re.compile(
            r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
        )

        self._client = None
        self._recent_prefetches = {}

        # Metadata cache: 3 minutes.
        self._info_cache = {}
        self._cache_ttl = 600
        self._cache_limit = 200

        # Prevent multiple simultaneous lookups for the same query.
        self._info_locks = {}
        self._lock_guard = asyncio.Lock()

        # Fast-extract circuit breaker.
        self._fast_fails = 0
        self._fast_off_until = 0.0

        # Download dedupe + background prefetch.
        self._inflight = {}
        self._bg_tasks = set()
        self._prefetch_sem = asyncio.Semaphore(MAX_PREFETCH_PARALLEL)

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
        """Extract a URL from a Telegram message or its reply."""
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
        """
        Fetch metadata with caching and duplicate-request prevention.
        Repeated requests for the same query reuse the cached result.
        """
        query = str(query or "").strip()
        if not query:
            return None

        is_url = query.startswith(("https://", "http://"))

        if not is_url:
            query = f"ytsearch{max(1, int(limit))}:{query}"
            # Title/duration/thumb are enough for results; the heavy
            # per-video extraction happens later via warm()/stream_url().
            flat = True

        cache_key = f"{query}|{limit}|{flat}"
        now = time.monotonic()

        cached = self._info_cache.get(cache_key)
        if cached and now - cached[0] < self._cache_ttl:
            return cached[1]

        # Reuse a lock when another coroutine is already fetching this query.
        async with self._lock_guard:
            lock = self._info_locks.setdefault(
                cache_key, asyncio.Lock()
            )

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

            use_fast = FAST_EXTRACT and is_url and not flat

            def extract():
                if use_fast and time.monotonic() >= self._fast_off_until:
                    info = _fast_extract(query)
                    if info and info.get("formats") and not info.get("entries"):
                        self._fast_fails = 0
                        return info
                    self._fast_fails += 1
                    if self._fast_fails >= 3:
                        self._fast_fails = 0
                        self._fast_off_until = time.monotonic() + 600
                        LOGGER.warning(
                            "Fast YouTube extract failing; using normal "
                            "extraction for 10 minutes."
                        )

                with yt_dlp.YoutubeDL(options) as ydl:
                    return ydl.extract_info(query, download=False)

            try:
                info = await asyncio.to_thread(extract)

                if info:
                    self._info_cache[cache_key] = (
                        time.monotonic(),
                        info,
                    )

                    # Pasted links come in many shapes (youtu.be, &si=,
                    # m.youtube...). Also store under the canonical URL so
                    # warm()/stream_url()/download() never look it up twice.
                    if (
                        not flat
                        and info.get("id")
                        and info.get("entries") is None
                    ):
                        self._info_cache[
                            f"{BASE_URL}{info['id']}|1|False"
                        ] = (time.monotonic(), info)

                    if len(self._info_cache) > self._cache_limit:
                        now = time.monotonic()
                        self._info_cache = {
                            key: value
                            for key, value in self._info_cache.items()
                            if now - value[0] < self._cache_ttl
                        }

                return info

            except Exception as error:
                LOGGER.warning(
                    "yt-dlp metadata error for %s: %s",
                    query,
                    error,
                )
                return None

            finally:
                async with self._lock_guard:
                    self._info_locks.pop(cache_key, None)

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

    async def _fetch_details(self, link):
        if not API_URL:
            return None

        params = {"link": self._clean_link(link)}
        if API_KEY:
            params["api_key"] = API_KEY

        try:
            client = await self.get_client()
            response = await client.get(
                f"{API_URL}/details",
                params=params,
            )
            if response.status_code == 200:
                return response.json()

        except Exception as error:
            LOGGER.warning("Custom details API failed: %s", error)

        return None

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

        # Quick search results can omit the duration, and play.py treats a
        # missing duration as a live stream. Check the real video first.
        if item["duration_min"] is None:
            full = await self._yt_info(item["link"])
            if full and full.get("entries") is None:
                full_item = self._normalise_video(full)
                if full_item:
                    item = full_item

        if item["vidid"]:
            warm_task = asyncio.create_task(self.warm(item["link"]))
            self._bg_tasks.add(warm_task)
            warm_task.add_done_callback(self._bg_tasks.discard)

        track = {
            "title": item["title"],
            "link": item["link"],
            "vidid": item["vidid"],
            "duration_min": item["duration_min"],
            "thumb": item["thumb"],
        }

        return track, item["vidid"]

    async def video(self, link, videoid=None):
        if videoid:
            link = self.base + str(link)

        link = self._clean_link(link)

        try:
            result = await self.download(link, None, video=True)
            if result and isinstance(result, tuple) and result[0]:
                return 1, result[0]
        except Exception as error:
            LOGGER.warning("YouTube video download failed: %s", error)

        try:
            process = await asyncio.create_subprocess_exec(
                "yt-dlp",
                "-g",
                "-f",
                "best[height<=?720][width<=?1280]/best",
                link,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            output, error = await process.communicate()

            if process.returncode == 0 and output:
                return 1, output.decode().strip().splitlines()[0]

            return 0, error.decode(errors="replace")

        except Exception as error:
            return 0, str(error)

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

    async def get_related_videos(self, vidid: str):
        autoplay_limit = min(
            getattr(config, "DURATION_LIMIT", 600),
            600,
        )

        radio_url = f"https://www.youtube.com/watch?v={vidid}&list=RD{vidid}"

        options = _ydl_options(
            noplaylist=False,
            extract_flat="in_playlist",
            playlist_items="2-20",
            ignoreerrors=True,
            socket_timeout=12,
        )

        def extract_radio():
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(radio_url, download=False)

        try:
            info = await asyncio.to_thread(extract_radio)
            ids = []

            for entry in (info or {}).get("entries") or []:
                if not entry:
                    continue

                video_id = entry.get("id")
                if not video_id or video_id == vidid:
                    continue

                duration = entry.get("duration")
                if duration and duration > autoplay_limit:
                    continue

                ids.append(video_id)

            if ids:
                return ids

        except Exception as error:
            LOGGER.debug("YouTube radio mix failed: %s", error)

        title = await self.title(vidid, True)

        if title:
            results = await self._search_results(
                f"{title} related songs",
                limit=10,
            )
            related = []

            for entry in results:
                item = self._normalise_video(entry)
                if not item or item["vidid"] == vidid:
                    continue
                duration = item["duration_sec"]
                if duration and duration > autoplay_limit:
                    continue
                related.append(item["vidid"])

            if related:
                return related

        categories = [
            "Latest Hindi Songs",
            "Top Bollywood Hits",
            "Indian Pop Songs",
            "New English Songs",
            "Trending Music India",
        ]

        try:
            results = await self._search_results(
                random.choice(categories),
                limit=20,
            )
            related = []

            for entry in results:
                item = self._normalise_video(entry)
                if not item or item["vidid"] == vidid:
                    continue
                duration = item["duration_sec"]
                if duration and duration > autoplay_limit:
                    continue
                related.append(item["vidid"])

            return related

        except Exception as error:
            LOGGER.warning("Related video search failed: %s", error)
            return []

    async def formats(self, link, videoid=None):
        if videoid:
            link = self.base + str(link)

        link = self._clean_link(link)

        def extract():
            with yt_dlp.YoutubeDL(
                _ydl_options(noplaylist=True, socket_timeout=15)
            ) as ydl:
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
                    "filesize": (
                        item.get("filesize")
                        or item.get("filesize_approx")
                    ),
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

        warm_task = asyncio.create_task(self.warm(item["link"]))
        self._bg_tasks.add(warm_task)
        warm_task.add_done_callback(self._bg_tasks.discard)

        return (
            item["title"],
            item["duration_min"],
            item["thumb"],
            item["vidid"],
        )

    def _start_local_prefetch(self, link, video=False):
        task = asyncio.create_task(self._prefetch_local(link, bool(video)))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _prefetch_local(self, link, video):
        async with self._prefetch_sem:
            try:
                await self.download(link, None, video=video)
            except Exception as error:
                LOGGER.debug("Local prefetch failed for %s: %s", link, error)

    async def prefetch(self, link, video=False):
        link = self._clean_link(link)
        now = time.time()
        vidid = extract_vidid(link) or link
        key = f"{vidid}_{'video' if video else 'audio'}"

        if (
            key in self._recent_prefetches
            and now - self._recent_prefetches[key] < 30
        ):
            return True

        self._recent_prefetches[key] = now

        if len(self._recent_prefetches) > 100:
            self._recent_prefetches = {
                k: v
                for k, v in self._recent_prefetches.items()
                if now - v < 300
            }

        # No remote API: download to disk in the background instead.
        if not API_URL:
            self._start_local_prefetch(link, video)
            return True

        params = {
            "query": link,
            "dl_type": "video" if video else "audio",
            "prefetch": "true",
        }
        if API_KEY:
            params["api_key"] = API_KEY

        try:
            client = await self.get_client()
            await client.get(f"{API_URL}/download", params=params)
            return True
        except Exception as error:
            LOGGER.warning("Remote prefetch failed: %s", error)
            return False

    async def prefetch_queue(self, queries, video=False):
        if not queries:
            return False

        if not API_URL:
            for item in list(queries)[:3]:
                item = str(item)
                if not extract_vidid(item):
                    continue
                if not item.startswith("http"):
                    item = self.base + item
                self._start_local_prefetch(self._clean_link(item), video)
            return True

        params = {"api_key": API_KEY} if API_KEY else {}

        try:
            client = await self.get_client()
            await client.post(
                f"{API_URL}/prefetch_bulk",
                json={
                    "queries": queries,
                    "dl_type": "video" if video else "audio",
                },
                params=params,
            )
            return True
        except Exception as error:
            LOGGER.warning("Remote bulk prefetch failed: %s", error)
            return False

    @staticmethod
    def _safe_filename(value):
        value = os.path.basename(str(value or "youtube_download"))
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
        value = value.strip(" .")
        return value or "youtube_download"

    @staticmethod
    def _find_downloaded_file(video_id, preferred_ext=None):
        candidates = glob.glob(
            os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
        )
        candidates = [
            path for path in candidates
            if os.path.isfile(path)
            and os.path.getsize(path) > 0
            and not _PARTIAL_RE.search(os.path.basename(path))
        ]

        if not candidates:
            return None

        if preferred_ext:
            for path in candidates:
                if path.lower().endswith(f".{preferred_ext.lower()}"):
                    return path

        return max(candidates, key=os.path.getsize)

    @staticmethod
    def _cached_file(video_id, is_video):
        """Return an already-downloaded, complete file for this video."""
        exts = ("mp4",) if is_video else AUDIO_EXTS
        for ext in exts:
            path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                return path
        return None

    def _get_cached_info(self, link):
        """Reuse metadata fetched by details()/track() (skips ~1-3s)."""
        cached = self._info_cache.get(f"{link}|1|False")
        if not cached or time.monotonic() - cached[0] > self._cache_ttl:
            return None
        info = cached[1]
        if info and info.get("formats") and info.get("entries") is None:
            return info
        return None

    def _resolve_path(self, ydl, info, is_video):
        if not info:
            return None

        video_id = info.get("id")
        if video_id:
            path = self._find_downloaded_file(
                video_id,
                preferred_ext="mp4" if is_video else None,
            )
            if path:
                return path

        try:
            prepared = ydl.prepare_filename(info)
            if os.path.isfile(prepared) and os.path.getsize(prepared) > 0:
                return prepared
        except Exception:
            pass

        return None

    @staticmethod
    def _pick_audio_url(info):
        """Best direct audio-only URL from extracted info."""
        best = None
        for f in (info or {}).get("formats") or []:
            if not f.get("url"):
                continue
            if f.get("vcodec") not in (None, "none"):
                continue
            if f.get("acodec") in (None, "none"):
                continue
            if f.get("protocol") not in (None, "https", "http"):
                continue
            score = (f.get("ext") == "m4a", min(f.get("abr") or 0, 160))
            if best is None or score > best[0]:
                best = (score, f["url"])
        if best:
            return best[1]
        return (info or {}).get("url")

    async def stream_url(self, link, videoid=None):
        """Direct playable audio URL. Instant when metadata is cached."""
        if videoid:
            link = self.base + str(link)
        link = self._clean_link(link)
        info = self._get_cached_info(link)
        if info is None:
            await self._yt_info(link)
            info = self._get_cached_info(link)
        return self._pick_audio_url(info)

    async def warmup(self):
        """Call once at bot start: loads yt-dlp extractors + player cache."""
        await self.warm(self.base + "dQw4w9WgXcQ")

    async def warm(self, link, videoid=None):
        """Pre-extract stream info so the next play is instant."""
        try:
            await self.stream_url(link, videoid)
        except Exception as error:
            LOGGER.debug("Warm-up failed: %s", error)

    async def _download_plain(self, link, is_video, base_options):
        options = dict(base_options)
        if is_video:
            options.update({
                "format": VIDEO_FORMAT,
                "merge_output_format": "mp4",
            })
        else:
            options["format"] = AUDIO_FORMAT

        cached_info = self._get_cached_info(link)
        if cached_info is None and link.startswith("http"):
            await self._yt_info(link)
            cached_info = self._get_cached_info(link)

        def run():
            with yt_dlp.YoutubeDL(options) as ydl:
                info = None
                if cached_info is not None:
                    try:
                        info = ydl.process_ie_result(
                            copy.deepcopy(cached_info), download=True
                        )
                    except Exception as error:
                        # Expired stream URL etc. -> fresh extraction.
                        LOGGER.debug("Cached-info download failed: %s", error)
                        info = None

                if not info:
                    info = ydl.extract_info(link, download=True)

                return self._resolve_path(ydl, info, is_video)

        return await asyncio.to_thread(run)

    async def download(
        self,
        link,
        mystic,
        video=None,
        videoid=None,
        songaudio=None,
        songvideo=None,
        format_id=None,
        title=None,
        instant=False,
    ):
        if videoid:
            link = self.base + str(link)

        link = self._clean_link(link)
        if not link:
            return None

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        base_options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "socket_timeout": 25,
            "retries": 2,
            "fragment_retries": 2,
            "concurrent_fragment_downloads": 16,
            "http_chunk_size": 10 * 1024 * 1024,  # avoids YouTube throttling
            "noprogress": True,
            "updatetime": False,
            "outtmpl": os.path.join(
                DOWNLOAD_DIR,
                "%(id)s.%(ext)s",
            ),
        }

        if HAS_ARIA2C:
            base_options["external_downloader"] = "aria2c"
            base_options["external_downloader_args"] = {
                "aria2c": ["-x16", "-s16", "-k1M", "--file-allocation=none"]
            }

        if songaudio:
            safe_title = self._safe_filename(title)

            def download_selected_audio():
                options = {
                    **base_options,
                    "format": str(format_id or "bestaudio/best"),
                    "outtmpl": os.path.join(
                        DOWNLOAD_DIR,
                        safe_title + ".%(ext)s",
                    ),
                    "prefer_ffmpeg": True,
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }],
                }
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.extract_info(link, download=True)

            try:
                await asyncio.to_thread(download_selected_audio)
                target = os.path.join(DOWNLOAD_DIR, safe_title + ".mp3")
                if os.path.isfile(target) and os.path.getsize(target) > 0:
                    return target
                return None
            except Exception as error:
                LOGGER.exception("Selected audio download failed: %s", error)
                raise

        if songvideo:
            safe_title = self._safe_filename(title)

            def download_selected_video():
                options = {
                    **base_options,
                    "format": str(format_id or "best[height<=720]/best"),
                    "outtmpl": os.path.join(
                        DOWNLOAD_DIR,
                        safe_title + ".%(ext)s",
                    ),
                    "merge_output_format": "mp4",
                    "prefer_ffmpeg": True,
                }
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.extract_info(link, download=True)

            try:
                await asyncio.to_thread(download_selected_video)
                target = os.path.join(DOWNLOAD_DIR, safe_title + ".mp4")
                if os.path.isfile(target) and os.path.getsize(target) > 0:
                    return target

                matches = glob.glob(
                    os.path.join(DOWNLOAD_DIR, safe_title + ".*")
                )
                return matches[0] if matches else None
            except Exception as error:
                LOGGER.exception("Selected video download failed: %s", error)
                raise

        is_video = bool(video)
        vid = extract_vidid(link)

        # 1) Already on disk -> instant.
        if vid:
            cached_file = self._cached_file(vid, is_video)
            if cached_file:
                return cached_file, True

        # 1b) instant mode: hand back a direct stream URL right away and
        # save the file in the background for replays.
        if instant and not is_video:
            url = await self.stream_url(link)
            if url:
                self._start_local_prefetch(link, False)
                return url, True

        # 2) Same track already downloading (e.g. prefetch) -> share it.
        key = f"{vid or link}:{'v' if is_video else 'a'}"
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(
                self._download_plain(link, is_video, base_options)
            )
            self._inflight[key] = task
            task.add_done_callback(
                lambda _t, k=key: self._inflight.pop(k, None)
            )

        try:
            file_path = await asyncio.shield(task)
        except Exception as error:
            LOGGER.exception("YouTube download failed for %s: %s", link, error)
            raise

        if not file_path:
            LOGGER.warning("yt-dlp produced no file for %s", link)
            return None

        return file_path, True

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


YouTube = YouTubeAPI()
