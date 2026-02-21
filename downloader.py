import os
from dotenv import load_dotenv

load_dotenv()

# ── Optional imports (fail gracefully so the worker always boots) ────
try:
    import yt_dlp
except ImportError:
    yt_dlp = None
    print("[WARN] yt-dlp not available")

import urllib.request
import re
import html

def _spotify_meta(url: str):
    """Extract metadata from a public Spotify track URL via OpenGraph HTML tags (Zero Config)."""
    if "open.spotify.com/track/" not in url:
        return None
    try:
        # Fetch the public HTML of the Spotify track page
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode('utf-8')
        
        # Regex to find <meta property="og:title" content="...">
        title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html_content)
        desc_match = re.search(r'<meta property="og:description" content="([^"]+)"', html_content)
        image_match = re.search(r'<meta property="og:image" content="([^"]+)"', html_content)
        
        if not title_match or not desc_match:
            print("[WARN] Could not find OpenGraph tags in Spotify HTML")
            return None
            
        title = html.unescape(title_match.group(1))
        desc = html.unescape(desc_match.group(1))
        image = html.unescape(image_match.group(1)) if image_match else None
        
        # The description is usually formatted like "ArtistName · Song · 2023"
        artist = desc.split(" · ")[0] if " · " in desc else "Unknown Artist"
        
        return {
            "title": title,
            "artist": artist,
            "thumbnail": image,
            "duration": 0, # Duration isn't reliably in the OG tags, but yt-dlp doesn't strictly need it to search
        }
    except Exception as e:
        print(f"[WARN] Zero-config Spotipy metadata failed: {type(e).__name__}: {e}")
        return None


def _youtube_search_url(query: str) -> str | None:
    """Search YouTube and return the URL of the first result."""
    if not yt_dlp:
        return None
    try:
        with yt_dlp.YoutubeDL(
            {"quiet": True, "no_warnings": True, "extract_flat": True, "default_search": "ytsearch1"}
        ) as ydl:
            info = ydl.extract_info(query, download=False)
            if info and "entries" in info and info["entries"]:
                return info["entries"][0].get("url") or info["entries"][0].get("webpage_url")
            elif info and info.get("webpage_url"):
                return info["webpage_url"]
    except Exception as e:
        print(f"[WARN] YouTube search failed: {e}")
    return None


def get_metadata(url: str):
    """Fetch track metadata. Spotify URLs use the API; others use yt-dlp."""
    # Try Spotify API first
    meta = _spotify_meta(url)
    if meta:
        return meta

    # If it's a Spotify URL but scraping failed, don't fall back to yt-dlp (it will timeout)
    if "open.spotify.com" in url:
        return None

    # For non-Spotify URLs (e.g. YouTube), try yt-dlp directly
    if not yt_dlp:
        return None
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            return {
                "title": info.get("title", info.get("track", "Unknown Track")),
                "artist": info.get("uploader", info.get("artist", "Unknown Artist")),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
            }
    except Exception as e:
        print(f"[WARN] yt-dlp metadata fallback failed: {e}")
        return None


class ProgressHook:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, d):
        if d["status"] == "downloading":
            raw = d.get("_percent_str", "0%").replace("%", "").strip()
            try:
                percent = float(raw)
            except ValueError:
                percent = 0
            self.callback({"status": "downloading", "progress": percent})
        elif d["status"] == "finished":
            self.callback({"status": "finished", "progress": 100})


def download_track(url: str, quality: str = "mp3", progress_callback=None):
    """Download track audio. Spotify URLs are resolved to YouTube first."""
    if not yt_dlp:
        raise RuntimeError("yt-dlp is not available")

    # If it's a Spotify URL, find the track on YouTube instead
    download_url = url
    if "open.spotify.com" in url:
        meta = _spotify_meta(url)
        if not meta:
            raise RuntimeError("Could not fetch Spotify track info. Ensure the URL is public and valid.")
        search_query = f"{meta['artist']} - {meta['title']} audio"
        yt_url = _youtube_search_url(search_query)
        if yt_url:
            download_url = yt_url
            print(f"[OK] Resolved Spotify → YouTube: {yt_url}")
        else:
            raise RuntimeError(f"Could not find '{meta['title']}' on YouTube")

    output_dir = "/tmp/downloads"
    os.makedirs(output_dir, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": quality,
                "preferredquality": "192" if quality == "mp3" else "0",
            }
        ],
        "progress_hooks": (
            [ProgressHook(progress_callback)] if progress_callback else []
        ),
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([download_url])
