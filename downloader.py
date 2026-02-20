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
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except ImportError:
    spotipy = None
    print("[WARN] spotipy not available")

# ── Lazy Spotify client (re-reads env vars on first call) ────────────
_sp_client = None


def _get_spotify_client():
    """Initialize the Spotify client. Retries if not yet connected."""
    global _sp_client
    if _sp_client is not None:
        return _sp_client

    if not spotipy:
        print("[WARN] spotipy library not installed")
        return None

    client_id = os.environ.get("SPOTIPY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SPOTIPY_CLIENT_SECRET", "").strip()

    print(f"[DEBUG] Attempting Spotify auth. ID length={len(client_id)}, Secret length={len(client_secret)}")

    if not client_id or not client_secret:
        print("[WARN] Spotify credentials are empty")
        return None

    try:
        auth_manager = SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
        )
        client = spotipy.Spotify(auth_manager=auth_manager)
        # Quick test to verify credentials work
        client.search(q="test", limit=1)
        _sp_client = client
        print("[OK] Spotify client initialized and verified")
        return _sp_client
    except Exception as e:
        print(f"[ERROR] Spotify Auth failed: {type(e).__name__}: {e}")
        return None

def _spotify_meta(url: str):
    """Extract metadata from a Spotify track URL via the API."""
    sp = _get_spotify_client()
    if not sp or "open.spotify.com/track/" not in url:
        return None
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

    # If it's a Spotify URL but we have no credentials, return a helpful error
    if "open.spotify.com" in url:
        if not _get_spotify_client():
            return {"title": "Spotify credentials required", "artist": "Add SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in Railway Variables", "thumbnail": None, "duration": 0}
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
            raise RuntimeError("Spotify credentials required. Add SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET in Railway Variables.")
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
