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
    """Debug endpoint."""
    return {
        "status": "ok",
        "yt_dlp_available": downloader.yt_dlp is not None,
        "mode": "zero-config (no Spotify API credentials needed)"
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
