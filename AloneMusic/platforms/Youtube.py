
"""
YouTube.py — YouTube platform for AloneMusic
Original project: TheAloneTeam/AloneMusic
License: GNU GPL v3.0

Uses yt-dlp for YouTube search, metadata, playlists, and downloads.
No official YouTube Data API or external metadata API is required.
"""

import asyncio
import glob
import json
import logging
import os
import random
import re
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


# Leave empty to use yt-dlp directly.
API_URL = ""
API_KEY = ""

LOGGER = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"

BASE_URL = "https://www.youtube.com/watch?v="
PLAYLIST_URL = "https://www.youtube.com/playlist?list="


def extract_vidid(query):
    """Extract an 11-character YouTube video ID from a URL or ID."""
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


async def check_file_size(link):
    """Return the sum of reported format sizes, or None on failure."""

    def extract():
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 20,
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(link, download=False)

    try:
        info = await asyncio.to_thread(extract)

        if not info:
            return None

        formats = info.get("formats") or []

        sizes = [
            item.get("filesize") or item.get("filesize_approx") or 0
            for item in formats
        ]

        total = sum(sizes)

        return total or None

    except Exception as error:
        LOGGER.warning("Could not check YouTube file size: %s", error)
        return None


async def download_assistant(query, dl_type):
    """
    Return an external download URL only when a custom API is configured.

    This bot's normal playback does not require this helper.
    """
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
        self.reg = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

        self._client = None
        self._recent_prefetches = {}

    async def get_client(self):
        """Create an HTTP client if an external API is configured."""
        if httpx is None:
            raise RuntimeError("httpx is not installed")

        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
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
        """Extract a URL entity from a Telegram message or its reply."""
        messages = [message_1]

        reply = getattr(message_1, "reply_to_message", None)

        if reply:
            messages.append(reply)

        for message in messages:
            text = getattr(message, "text", None)
            caption = getattr(message, "caption", None)
            body = text or caption or ""

            entities = getattr(message, "entities", None) or []

            if text:
                for entity in entities:
                    if entity.type == MessageEntityType.URL:
                        return body[
                            entity.offset:entity.offset + entity.length
                        ]

                    if entity.type == MessageEntityType.TEXT_LINK:
                        return getattr(entity, "url", None)

            caption_entities = (
                getattr(message, "caption_entities", None) or []
            )

            if caption:
                for entity in caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return getattr(entity, "url", None)

                    if entity.type == MessageEntityType.URL:
                        return body[
                            entity.offset:entity.offset + entity.length
                        ]

        return None

    def _clean_link(self, link):
        """Remove common tracking parameters without breaking playlist URLs."""
        if not link:
            return ""

        link = str(link).strip()

        if not link.startswith(("http://", "https://")):
            return link

        try:
            parsed = urllib.parse.urlsplit(link)

            if not parsed.query:
                return link.split("#", 1)[0]

            query_items = urllib.parse.parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )

            ignored = {
                "si",
                "feature",
                "pp",
                "embeds_referring_euri",
                "source_ve_path",
            }

            cleaned = [
                (key, value)
                for key, value in query_items
                if key.lower() not in ignored
            ]

            return urllib.parse.urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    urllib.parse.urlencode(cleaned),
                    "",
                )
            )

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
        Get metadata from a YouTube URL or perform a yt-dlp search.

        Queries without an HTTP URL are treated as search terms.
        """
        query = str(query or "").strip()

        if not query:
            return None

        is_url = query.startswith(("https://", "http://"))

        if not is_url:
            query = f"ytsearch{max(1, int(limit))}:{query}"

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": not flat,
            "extract_flat": "in_playlist" if flat else False,
            "ignoreerrors": True,
            "socket_timeout": 25,
            "retries": 2,
        }

        def extract():
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(query, download=False)

        try:
            return await asyncio.to_thread(extract)

        except Exception as error:
            LOGGER.warning(
                "yt-dlp metadata error for %s: %s",
                query,
                error,
            )
            return None

    async def _search_results(self, query, limit=10):
        info = await self._yt_info(query, limit=limit)

        if not info:
            return []

        entries = info.get("entries")

        if entries is not None:
            return [entry for entry in entries if entry]

        if info.get("id"):
            return [info]

        return []

    @staticmethod
    def _normalise_video(item):
        """Normalize yt-dlp metadata to the bot's expected format."""
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
            thumbnail = (
                f"https://i.ytimg.com/vi/{vidid}/hqdefault.jpg"
            )

        duration_seconds = item.get("duration")
        duration_text = YouTubeAPI._format_duration(duration_seconds)

        link = (
            item.get("webpage_url")
            or item.get("original_url")
            or f"https://www.youtube.com/watch?v={vidid}"
        )

        return {
            "title": item.get("title") or "Unknown title",
            "link": link,
            "vidid": vidid,
            "duration_min": duration_text,
            "duration_sec": int(duration_seconds or 0),
            "thumb": thumbnail.split("?")[0],
        }

    async def _fetch_details(self, link):
        """Optional compatibility with a configured custom metadata API."""
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
        result = await self.details(link, videoid)
        return result[0]

    async def duration(self, link, videoid=None):
        result = await self.details(link, videoid)
        return result[1]

    async def thumbnail(self, link, videoid=None):
        result = await self.details(link, videoid)
        return result[3]

    async def track(self, link, videoid=None):
        """Return the track dictionary and video ID used by AloneMusic."""
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
                "best[height<=?720][width<=?1280]",
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
        """Extract playlist entries locally with yt-dlp."""
        if videoid:
            link = self.listbase + str(link)

        link = self._clean_link(link)

        try:
            limit = max(1, int(limit))
            info = await self._yt_info(link, limit=limit, flat=True)

            if not info:
                return None

            entries = info.get("entries")

            if entries is None:
                return None

            videos = []

            for entry in entries:
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
        """Return related video IDs for autoplay."""
        autoplay_limit = min(
            getattr(config, "DURATION_LIMIT", 600),
            600,
        )

        # First attempt: YouTube radio mix.
        radio_url = (
            f"https://www.youtube.com/watch?v={vidid}&list=RD{vidid}"
        )

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "playlist_items": "2-20",
            "ignoreerrors": True,
            "socket_timeout": 20,
        }

        def extract_radio():
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(radio_url, download=False)

        try:
            info = await asyncio.to_thread(extract_radio)
            entries = (info or {}).get("entries") or []
            ids = []

            for entry in entries:
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

        # Second attempt: search using the current video's title.
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

        # Final fallback: general music searches.
        categories = [
            "Latest Hindi Songs",
            "Top Bollywood Hits",
            "Indian Pop Songs",
            "New English Songs",
            "Trending Music India",
        ]

        try:
            query = random.choice(categories)
            results = await self._search_results(query, limit=20)
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
            options = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "socket_timeout": 25,
            }

            with yt_dlp.YoutubeDL(options) as ydl:
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

        return (
            item["title"],
            item["duration_min"],
            item["thumb"],
            item["vidid"],
        )

    async def prefetch(self, link, video=False):
        """Compatibility hook; local yt-dlp does not need remote prefetch."""
        if not API_URL:
            return False

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

        try:
            params = {
                "query": link,
                "dl_type": "video" if video else "audio",
                "prefetch": "true",
            }

            if API_KEY:
                params["api_key"] = API_KEY

            client = await self.get_client()
            await client.get(f"{API_URL}/download", params=params)
            return True

        except Exception as error:
            LOGGER.warning("Remote prefetch failed: %s", error)
            return False

    async def prefetch_queue(self, queries, video=False):
        if not API_URL or not queries:
            return False

        params = {}

        if API_KEY:
            params["api_key"] = API_KEY

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
        """Find the actual downloaded file, including merged MP4 files."""
        candidates = glob.glob(
            os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
        )

        candidates = [
            path for path in candidates
            if os.path.isfile(path) and os.path.getsize(path) > 0
        ]

        if not candidates:
            return None

        if preferred_ext:
            for path in candidates:
                if path.lower().endswith(f".{preferred_ext.lower()}"):
                    return path

        return max(candidates, key=os.path.getsize)

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
    ):
        """
        Download media with yt-dlp.

        Existing return conventions are preserved:
        - Normal audio: (file_path, True)
        - Normal video: (file_path, True)
        - Selected audio/video formats: file_path
        """
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
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "outtmpl": os.path.join(
                DOWNLOAD_DIR,
                "%(id)s.%(ext)s",
            ),
        }

        # Download an explicitly selected audio format and convert it to MP3.
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
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }
                    ],
                }

                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.extract_info(link, download=True)

            try:
                await asyncio.to_thread(download_selected_audio)

                target = os.path.join(
                    DOWNLOAD_DIR,
                    safe_title + ".mp3",
                )

                if os.path.isfile(target) and os.path.getsize(target) > 0:
                    return target

                return None

            except Exception as error:
                LOGGER.exception("Selected audio download failed: %s", error)
                raise

        # Download an explicitly selected video format.
        if songvideo:
            safe_title = self._safe_filename(title)

            def download_selected_video():
                selected_format = str(format_id or "best[height<=720]")

                options = {
                    **base_options,
                    "format": selected_format,
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

                target = os.path.join(
                    DOWNLOAD_DIR,
                    safe_title + ".mp4",
                )

                if os.path.isfile(target) and os.path.getsize(target) > 0:
                    return target

                matches = glob.glob(
                    os.path.join(DOWNLOAD_DIR, safe_title + ".*")
                )

                return matches[0] if matches else None

            except Exception as error:
                LOGGER.exception("Selected video download failed: %s", error)
                raise

        # Normal audio or video download.
        is_video = bool(video)

        if is_video:
            base_options.update({
                "format": (
                    "best[height<=720][width<=1280]"
                    "/best[height<=720]"
                    "/best"
                ),
                "merge_output_format": "mp4",
            })
        else:
            base_options["format"] = "bestaudio/best"

        def download_media():
            with yt_dlp.YoutubeDL(base_options) as ydl:
                info = ydl.extract_info(link, download=True)

                if not info:
                    return None

                video_id = info.get("id")

                if not video_id:
                    return ydl.prepare_filename(info)

                preferred_ext = "mp4" if is_video else None

                actual_path = self._find_downloaded_file(
                    video_id,
                    preferred_ext=preferred_ext,
                )

                if actual_path:
                    return actual_path

                prepared_path = ydl.prepare_filename(info)

                if (
                    os.path.isfile(prepared_path)
                    and os.path.getsize(prepared_path) > 0
                ):
                    return prepared_path

                # yt-dlp can merge into a different extension.
                matches = glob.glob(
                    os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
                )

                matches = [
                    path for path in matches
                    if os.path.isfile(path)
                    and os.path.getsize(path) > 0
                ]

                return matches[0] if matches else None

        try:
            file_path = await asyncio.to_thread(download_media)

            if not file_path:
                LOGGER.warning("yt-dlp did not produce a download for %s", link)
                return None

            if video:
                # Keep the original video return shape.
                return file_path, True

            return file_path, True

        except Exception as error:
            LOGGER.exception("YouTube download failed for %s: %s", link, error)
            raise

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


YouTube = YouTubeAPI()
