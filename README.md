# Spotify Downloader

A modern single-page web application to download Spotify tracks.

## Deployment on Railway

1. Provide `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET` in the environment variables.
2. The `Procfile` and `package.json` are already set up for Railway.

## Local Setup

1. Run `pip install -r requirements.txt`.
2. Run `npm run build` (to copy the frontend to the backend).
3. Run `python backend/main.py`.
4. Visit `http://localhost:8000`.
