
import os
import asyncio
import numpy as np
import re
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from collections import Counter

try:
    from unidecode import unidecode
except ImportError:
    def unidecode(text):
        return text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_TITLE_PATH = os.path.join(BASE_DIR, "font.ttf")
FONT_INFO_PATH = os.path.join(BASE_DIR, "font2.ttf")
TEMPLATE_PATH = os.path.join(BASE_DIR, "..", "assets", "template.jpg")

def safe_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

class Thumbnail:
    def __init__(self):
        self.size = (1280, 720)
        self.font_title = safe_font(FONT_TITLE_PATH, 26)
        self.font_info = safe_font(FONT_INFO_PATH, 20)

    async def start(self):
        os.makedirs("cache", exist_ok=True)
        return True

    async def save_thumb(self, output_path: str, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        for attempt in range(3):
            try:
                if url.startswith("http"):
                    import aiohttp
                    async with aiohttp.ClientSession(headers=headers) as session:
                        async with session.get(url, timeout=15) as resp:
                            if resp.status == 200:
                                content = await resp.read()
                                with open(output_path, "wb") as f:
                                    f.write(content)
                                return output_path
            except Exception as e:
                import asyncio
                await asyncio.sleep(1)
        return output_path

    async def generate(self, song, vidid=None) -> str:
        try:
            os.makedirs("cache", exist_ok=True)
            temp = f"cache/temp_{vidid or getattr(song, 'id', 'unknown')}.jpg"
            final_path = f"cache/{vidid or getattr(song, 'id', 'unknown')}.png"
            if os.path.exists(final_path):
                return final_path

            thumbnail_url = getattr(song, 'thumbnail', song) if not isinstance(song, str) else song
            await self.save_thumb(temp, thumbnail_url)

            try:
                src = Image.open(temp).convert("RGBA")
            except Exception:
                try:
                    src = Image.new("RGBA", (1280, 720), (30, 30, 30, 255))
                except Exception:
                    from config import YOUTUBE_IMG_URL
                    return YOUTUBE_IMG_URL

            W, H = self.size

            bg_ratio = W / H
            src_ratio = src.width / src.height
            if src_ratio > bg_ratio:
                new_w = int(src.height * bg_ratio)
                offset = (src.width - new_w) // 2
                bg = src.crop((offset, 0, offset + new_w, src.height))
            else:
                new_h = int(src.width / bg_ratio)
                offset = (src.height - new_h) // 2
                bg = src.crop((0, offset, src.width, offset + new_h))

            bg = bg.resize((W, H), Image.Resampling.LANCZOS)
            bg = bg.filter(ImageFilter.GaussianBlur(25))

            bg_overlay = Image.new("RGBA", (W, H), (0, 0, 0, 100))
            bg = Image.alpha_composite(bg, bg_overlay)

            if os.path.exists(TEMPLATE_PATH):
                tpl = Image.open(TEMPLATE_PATH).convert("RGBA")
                tpl = tpl.resize((W, H), Image.Resampling.LANCZOS)

                tpl_arr = np.array(tpl).astype(float)
                r, g, b = tpl_arr[:,:,0], tpl_arr[:,:,1], tpl_arr[:,:,2]

                d_bg = np.maximum(np.maximum(np.abs(r - 147.5), np.abs(g - 147.5)), np.abs(b - 147.5))
                alpha = np.clip((d_bg - 8) / 17.0 * 255, 0, 255)
                alpha[:, :640] = 0

                tpl_arr[:,:,3] = alpha
                tpl = Image.fromarray(tpl_arr.astype(np.uint8))

                bg = Image.alpha_composite(bg, tpl)

            cover_x, cover_y = 100, 104
            cover_w, cover_h = 512, 512
            cover_radius = 38

            shadow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow_layer)
            shadow_draw.rounded_rectangle(
                (cover_x + 6, cover_y + 8, cover_x + cover_w + 6, cover_y + cover_h + 8),
                radius=cover_radius + 4,
                fill=(0, 0, 0, 140),
            )
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(18))
            bg = Image.alpha_composite(bg, shadow_layer)

            cover_resized = src.resize((cover_w, cover_h), Image.Resampling.LANCZOS)
            cover_mask = Image.new("L", (cover_w, cover_h), 0)
            ImageDraw.Draw(cover_mask).rounded_rectangle(
                (0, 0, cover_w, cover_h), radius=cover_radius, fill=255
            )
            bg.paste(cover_resized, (cover_x, cover_y), cover_mask)

            draw = ImageDraw.Draw(bg)
            text_x = 715
            text_max_w = 320

            def ellipsize(s, font, max_w):
                if draw.textbbox((0, 0), s, font=font)[2] <= max_w:
                    return s
                lo, hi = 1, len(s)
                best = "..."
                while lo <= hi:
                    mid = (lo + hi) // 2
                    cand = s[:mid].rstrip() + "..."
                    if draw.textbbox((0, 0), cand, font=font)[2] <= max_w:
                        best = cand
                        lo = mid + 1
                    else:
                        hi = mid - 1
                return best

            title_str = ellipsize(unidecode(str(getattr(song, 'title', song))), self.font_title, text_max_w)
            title_y = cover_y + 12
            draw.text((text_x, title_y), title_str, fill=(255, 255, 255, 255), font=self.font_title)

            artist_str = ellipsize(unidecode(str(getattr(song, 'channel_name', 'Unknown Artist'))), self.font_info, text_max_w + 60)
            artist_y = title_y + 40
            draw.text((text_x, artist_y), artist_str, fill=(200, 200, 200, 255), font=self.font_info)

            out = bg.convert("RGB")
            out.save(final_path, "PNG")

            try:
                if os.path.exists(temp):
                    os.remove(temp)
            except Exception:
                pass

            return final_path

        except Exception as e:
            print(f"Error: {e}")
            from config import YOUTUBE_IMG_URL
            return YOUTUBE_IMG_URL


#
# Copyright (C) 2021-2022 by TheAloneteam@Github, < https://github.com/TheAloneTeam >.
#
# This file is part of < https://github.com/TheAloneTeam/AloneMusic > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/TheAloneTeam/AloneMusic/blob/master/LICENSE >
#
# All rights reserved.

import os
import re

import aiofiles
import aiohttp
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from py_yt import VideosSearch

from config import YOUTUBE_IMG_URL


def changeImageSize(maxWidth, maxHeight, image):
    widthRatio = maxWidth / image.size[0]
    heightRatio = maxHeight / image.size[1]
    newWidth = int(widthRatio * image.size[0])
    newHeight = int(heightRatio * image.size[1])
    newImage = image.resize((newWidth, newHeight))
    return newImage


async def get_thumb(videoid, user_name=None, next_title=None):
    if os.path.isfile(f"cache/{videoid}.png"):
        return f"cache/{videoid}.png"

    url = f"https://www.youtube.com/watch?v={videoid}"
    try:
        results = VideosSearch(url, limit=1)
        res = await results.next()
        if not res or "result" not in res or not res["result"]:
            raise Exception("No results found for videoid")

        result = res["result"][0]

        class Song:
            pass

        song = Song()
        song.id = videoid
        song.title = result.get("title", "Unsupported Title")
        song.channel_name = result.get("channel", {}).get("name", "Unknown Artist")
        song.thumbnail = result.get("thumbnails", [{}])[0].get("url", "").split("?")[0]

        thumb_gen = Thumbnail()
        await thumb_gen.start()
        return await thumb_gen.generate(song, vidid=videoid)
    except Exception as e:
        print(e)
        from config import YOUTUBE_IMG_URL
        return YOUTUBE_IMG_URL

async def _old_get_thumb(videoid, user_name=None, next_title=None):

    if os.path.isfile(f"cache/{videoid}.png"):
        return f"cache/{videoid}.png"

    url = f"https://www.youtube.com/watch?v={videoid}"
    try:
        results = VideosSearch(url, limit=1)
        res = await results.next()
        if not res or "result" not in res or not res["result"]:
            raise Exception("No results found for videoid")
        
        for result in res["result"]:
            try:
                title = result["title"]
                title = re.sub(r"\W+", " ", title)
                title = title.title()
            except:
                title = "Unsupported Title"
            try:
                duration = result["duration"]
            except:
                duration = "Unknown"
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
            try:
                channel = result["channel"]["name"]
            except:
                channel = "Unknown Artist"

        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail) as resp:
                if resp.status == 200:
                    f = await aiofiles.open(f"cache/thumb{videoid}.png", mode="wb")
                    await f.write(await resp.read())
                    await f.close()

        youtube = Image.open(f"cache/thumb{videoid}.png")

        # Background: Blurred and darkened version of the thumbnail
        image1 = changeImageSize(1280, 720, youtube)
        image1 = image1.filter(ImageFilter.GaussianBlur(50))
        image1 = ImageEnhance.Brightness(image1).enhance(0.15)
        
        # Player Widget Dimensions (Mobile Notification Style)
        widget_width = 1100
        widget_height = 400
        widget_x = (1280 - widget_width) // 2
        widget_y = (720 - widget_height) // 2
        
        # Create Widget Overlay (semi-transparent dark background)
        overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        
        # Main Widget
        draw_overlay.rounded_rectangle(
            [(widget_x, widget_y), (widget_x + widget_width, widget_y + widget_height)],
            radius=60,
            fill=(15, 15, 15, 250)
        )
        
        # Media output pill
        pill_w, pill_h = 240, 60
        pill_x = widget_x + widget_width - pill_w - 40
        pill_y = widget_y + 50
        draw_overlay.rounded_rectangle([(pill_x, pill_y), (pill_x + pill_w, pill_y + pill_h)], radius=30, fill=(255, 255, 255, 40))
        
        # Progress Bar Background Line
        bar_x = widget_x + 50
        bar_y = widget_y + widget_height - 80
        bar_width = widget_width - 100
        bar_bg_height = 4
        draw_overlay.rectangle([(bar_x, bar_y + 2), (bar_x + bar_width, bar_y + 2 + bar_bg_height)], fill=(255, 255, 255, 40))

        image1 = image1.convert('RGBA')
        image1 = Image.alpha_composite(image1, overlay)
        draw = ImageDraw.Draw(image1)
        
        # Album Art (Square with rounded corners) - Mobile Notification Style
        album_size = 140
        album_x = widget_x + 40
        album_y = widget_y + 40
        
        # Use ImageOps.fit to crop to square without squashing
        youtube_thumb = ImageOps.fit(youtube, (album_size, album_size), centering=(0.5, 0.5))
        mask = Image.new("L", (album_size, album_size), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.rounded_rectangle([(0, 0), (album_size, album_size)], radius=20, fill=255)
        youtube_thumb.putalpha(mask)
        image1.paste(youtube_thumb, (album_x, album_y), youtube_thumb)
        
        # Load Fonts
        def get_font(path, size):
            try:
                return ImageFont.truetype(path, size)
            except:
                try:
                    return ImageFont.truetype("arial.ttf", size)
                except:
                    return ImageFont.load_default()

        font_title = get_font("AloneMusic/assets/font.ttf", 60)
        font_artist = get_font("AloneMusic/assets/font2.ttf", 35)
        font_label = get_font("AloneMusic/assets/font2.ttf", 30)
        font_time = get_font("AloneMusic/assets/font3.ttf", 25)
        font_watermark = get_font("AloneMusic/assets/font2.ttf", 30)

        def get_text_width(text, font):
            if hasattr(draw, "textlength"):
                return draw.textlength(text, font=font)
            else:
                return draw.textsize(text, font=font)[0]

        # Draw Spotify-style icon and "This phone" label
        label_x = album_x + album_size + 40
        label_y = album_y + 10
        
        # Draw Spotify Circle
        draw.ellipse([(label_x, label_y), (label_x + 35, label_y + 35)], fill="white")
        # Draw Three Curved Lines inside (Spotify style)
        for i in range(3):
            draw.arc([(label_x+6, label_y+6+i*7), (label_x+29, label_y+14+i*7)], start=190, end=350, fill="black", width=3)
            
        draw.text((label_x + 50, label_y + 2), text="This phone", fill="white", font=font_label)

        # Draw Title and Artist
        text_x = label_x
        text_y_base = label_y + 80
        
        # Truncate title if too long
        display_title = title
        if len(display_title) > 35:
            display_title = display_title[:32] + "..."
            
        draw.text((text_x, text_y_base - 10), text=display_title, fill="white", font=font_title)
        draw.text((text_x, text_y_base + 75), text=channel, fill="#b3b3b3", font=font_artist)
        
        # Draw Media Controls (Centered and Enlarged)
        controls_y = widget_y + 265
        icon_color = "white"
        
        # Heart Icon (Standard Heart Shape - refined)
        hx, hy = widget_x + 340, controls_y
        draw.ellipse([(hx-18, hy-18), (hx+2, hy+2)], fill=icon_color)
        draw.ellipse([(hx-2, hy-18), (hx+18, hy+2)], fill=icon_color)
        draw.polygon([(hx-18, hy-3), (hx+18, hy-3), (hx, hy+20)], fill=icon_color)
        
        # Prev Icon
        px, py = widget_x + 480, controls_y
        draw.polygon([(px+18, py-20), (px-6, py), (px+18, py+20)], fill=icon_color)
        draw.rectangle([(px-16, py-20), (px-10, py+20)], fill=icon_color)
        
        # Pause Icon
        pax, pay = widget_x + 620, controls_y
        draw.rectangle([(pax-14, pay-22), (pax-4, pay+22)], fill=icon_color)
        draw.rectangle([(pax+4, pay-22), (pax+14, pay+22)], fill=icon_color)
        
        # Next Icon
        nx, ny = widget_x + 760, controls_y
        draw.polygon([(nx-18, ny-20), (nx+6, ny), (nx-18, ny+20)], fill=icon_color)
        draw.rectangle([(nx+10, ny-20), (nx+16, ny+20)], fill=icon_color)
        
        # Media output pill text
        label_mo = "Media output"
        w_mo = get_text_width(label_mo, font_label)
        draw.text((pill_x + (pill_w - w_mo)//2, pill_y + (pill_h - 45)//2), text=label_mo, fill="white", font=font_label)
        
        # Progress Bar
        bar_x = widget_x + 50
        bar_y = widget_y + widget_height - 80
        bar_width = widget_width - 100
        bar_fg_height = 8
        
        # Progress (Fixed at 20% to match reference exactly for verification)
        progress = 0.20
        draw.rectangle([(bar_x, bar_y), (bar_x + bar_width * progress, bar_y + bar_fg_height)], fill="white")
        # Slider Dot
        dot_x = bar_x + bar_width * progress
        draw.ellipse([(dot_x - 14, bar_y + bar_fg_height//2 - 14), (dot_x + 14, bar_y + bar_fg_height//2 + 14)], fill="white")
        
        # Timestamps
        draw.text((bar_x, bar_y + 20), text="00:00", fill="#b3b3b3", font=font_time)
        w_dur = get_text_width(duration, font_time)
        draw.text((bar_x + bar_width - w_dur, bar_y + 20), text=duration, fill="#b3b3b3", font=font_time)
        
        # Watermark
        draw.text((1280 - 180, 40), text="Alone Music", fill=(255, 255, 255, 150), font=font_watermark)

        try:
            os.remove(f"cache/thumb{videoid}.png")
        except:
            pass

        file_name = f"cache/{videoid}.png"
        image1.save(file_name)
        return file_name

    except Exception as e:
        print(e)
        return YOUTUBE_IMG_URL


async def get_qthumb(vidid):
    try:
        url = f"https://www.youtube.com/watch?v={vidid}"
        results = VideosSearch(url, limit=1)
        for result in (await results.next())["result"]:
            thumbnail = result["thumbnails"][0]["url"].split("?")[0]
        return thumbnail
    except Exception as e:
        print(e)
        return YOUTUBE_IMG_URL
        
