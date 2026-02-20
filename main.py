import os
import json
import asyncio

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import downloader

# ── App ──────────────────────────────────────────────────────────────
app = FastAPI(title="Spotify Downloader")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ─────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return JSONResponse({"error": "Frontend not found"}, status_code=404)


# ── API ──────────────────────────────────────────────────────────────
@app.get("/metadata")
async def metadata(url: str = Query(...)):
    data = downloader.get_metadata(url)
    if data:
        return data
    return JSONResponse({"error": "Track not found"}, status_code=404)


@app.get("/health")
async def health():
    """Debug endpoint to check if credentials are loaded."""
    sp = downloader._get_spotify_client()
    error_msg = None
    if not sp:
        # Try to get the exact error
        try:
            cid = os.environ.get("SPOTIPY_CLIENT_ID", "").strip()
            csec = os.environ.get("SPOTIPY_CLIENT_SECRET", "").strip()
            if cid and csec and downloader.spotipy:
                from spotipy.oauth2 import SpotifyClientCredentials
                am = SpotifyClientCredentials(client_id=cid, client_secret=csec)
                test_sp = downloader.spotipy.Spotify(auth_manager=am)
                test_sp.search(q="test", limit=1)
            else:
                error_msg = f"spotipy={'installed' if downloader.spotipy else 'MISSING'}, id_len={len(cid)}, secret_len={len(csec)}"
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
    return {
        "status": "ok",
        "spotify_connected": sp is not None,
        "yt_dlp_available": downloader.yt_dlp is not None,
        "client_id_set": bool(os.environ.get("SPOTIPY_CLIENT_ID", "").strip()),
        "client_secret_set": bool(os.environ.get("SPOTIPY_CLIENT_SECRET", "").strip()),
        "auth_error": error_msg,
    }


@app.get("/download")
async def download(url: str = Query(...), quality: str = "mp3"):
    async def stream():
        queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def on_progress(data):
            asyncio.run_coroutine_threadsafe(queue.put(data), loop)

        task = loop.run_in_executor(
            None, downloader.download_track, url, quality, on_progress
        )

        while not task.done() or not queue.empty():
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=0.2)
                yield f"data: {json.dumps(msg)}\n\n"
            except asyncio.TimeoutError:
                continue

        yield 'data: {"status": "complete"}\n\n'

    return StreamingResponse(stream(), media_type="text/event-stream")


# ── Local dev entry point ────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
