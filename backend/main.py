from fastapi import FastAPI, Query, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import downloader
import json
import asyncio
import os
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Serve static files from the 'static' directory
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def read_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"error": "Frontend not found"})

@app.get("/metadata")
async def get_metadata(url: str = Query(...)):
    data = downloader.get_metadata(url)
    if data:
        return data
    return JSONResponse(status_code=404, content={"error": "Track not found"})

@app.get("/download")
async def download(url: str = Query(...), quality: str = "mp3"):
    async def event_generator():
        queue = asyncio.Queue()

        def progress_callback(data):
            asyncio.run_coroutine_threadsafe(queue.put(data), asyncio.get_event_loop())

        # Start download in a separate thread to avoid blocking
        loop = asyncio.get_event_loop()
        download_task = loop.run_in_executor(None, downloader.download_track, url, quality, progress_callback)

        while not download_task.done() or not queue.empty():
            try:
                data = await asyncio.wait_for(queue.get(), timeout=0.1)
                yield f"data: {json.dumps(data)}\n\n"
            except asyncio.TimeoutError:
                continue
        
        yield "data: {\"status\": \"complete\"}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)


