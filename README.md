# Spotify Downloader

A modern web app to download Spotify tracks in MP3 or FLAC.

## Local Setup

```bash
pip install -r requirements.txt
python main.py
# Open http://localhost:8080
```

## Deploy to Railway

1. Push this repo to GitHub.
2. Create a new Railway project linked to the repo.
3. Add environment variables in the Railway dashboard:
   - `SPOTIPY_CLIENT_ID`
   - `SPOTIPY_CLIENT_SECRET`
4. Railway auto-deploys using the `Procfile`.
