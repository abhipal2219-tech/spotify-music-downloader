import os
from dotenv import load_dotenv

load_dotenv()

# ── Optional imports (fail gracefully so the worker always boots) ────
try:
    import yt_dlp
except ImportError:
    yt_dlp = None
    print("[WARN] yt-dlp not available")

try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    static_ffmpeg = None
    print("[WARN] static_ffmpeg not available")

import urllib.request
import urllib.parse
import json

def _spotify_meta(url: str):
    """Extract metadata from a public Spotify track using their public oEmbed API (Zero Config)."""
    if "open.spotify.com/track/" not in url:
        return None
    try:
        # The public oEmbed API doesn't require any auth/client_id
        oembed_url = f"https://open.spotify.com/oembed?url={urllib.parse.quote(url)}"
        req = urllib.request.Request(
            oembed_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        title = data.get("title", "Unknown Track")
        
        # oEmbed doesn't separate artist, title typically looks like "SongName - song and lyrics by ArtistName"
        # Since we just need it for a YouTube search, returning the full title is sufficient
        
        return {
            "title": title,
            "artist": "Spotify Track", # Fallback, not strictly needed since title has it all
            "thumbnail": data.get("thumbnail_url"),
            "duration": 0,
        }
    except Exception as e:
        print(f"[WARN] Spotify oEmbed metadata failed: {type(e).__name__}: {e}")
        return None


def _youtube_search_url(query: str) -> str | None:
    """Search YouTube and return the URL of the first result."""
    if not yt_dlp:
        return None
    try:
        with yt_dlp.YoutubeDL(
            {"quiet": True, "no_warnings": True, "extract_flat": True}
        ) as ydl:
            # yt-dlp requires 'ytsearch1:' prefix to actually search when using extract_info
            search_query = f"ytsearch1:{query}"
            info = ydl.extract_info(search_query, download=False)
            
            if info and "entries" in info and info["entries"]:
                entry = info["entries"][0]
                # extract_flat sometimes returns just the 'id' or 'url'
                if "url" in entry:
                    return entry["url"]
                elif "id" in entry:
                    return f"https://www.youtube.com/watch?v={entry['id']}"
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
            raise RuntimeError("Could not fetch Spotify metadata.")
        search_query = f"{meta['title']} audio"
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
        info_dict = ydl.extract_info(download_url, download=True)
        
        # Determine the final filename after FFmpeg post-processing
        if hasattr(ydl, 'prepare_filename') and info_dict:
            base_filename = ydl.prepare_filename(info_dict)
            base, _ = os.path.splitext(base_filename)
            final_filename = f"{base}.{quality}"
            return os.path.basename(final_filename)
            
    return None
