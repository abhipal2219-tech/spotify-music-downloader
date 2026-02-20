import os
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()

# Spotify Setup (Optional — works without credentials but metadata won't load)
SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")

sp = None
if SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET:
    try:
        auth_manager = SpotifyClientCredentials(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
        )
        sp = spotipy.Spotify(auth_manager=auth_manager)
    except Exception as e:
        print(f"[WARN] Spotify Auth failed: {e}")


def get_metadata(url: str):
    """Fetch track metadata via Spotipy, falling back to yt-dlp."""
    if sp and "open.spotify.com/track/" in url:
        try:
            track_id = url.split("track/")[1].split("?")[0]
            track = sp.track(track_id)
            return {
                "title": track["name"],
                "artist": track["artists"][0]["name"],
                "thumbnail": (
                    track["album"]["images"][0]["url"]
                    if track["album"]["images"]
                    else None
                ),
                "duration": track["duration_ms"] // 1000,
            }
        except Exception as e:
            print(f"[WARN] Spotipy metadata failed: {e}")

    # yt-dlp fallback
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
    """Download track audio using yt-dlp."""
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
        ydl.download([url])
