# Telegram Fast Rename Bot

A Telegram rename bot/userbot that re-sends files with a new filename quickly.

Supports two modes:
- BOT mode: uses a bot token (BOT_TOKEN). Downloads and re-uploads files (subject to Bot API limits).
- USER mode (recommended for large files up to ~4GB): uses a user session (API_ID/API_HASH + session string or session file). Tries to copy files server-side (no re-upload), which is faster and supports very large files.

This repository includes:
- main.py — the bot logic (rename, thumbnail support, video/document options, progress edits)
- generate_session.py — helper to generate a Pyrogram session string locally (safe)
- Dockerfile, render.yaml — deploy to Render via Docker
- requirements.txt, .env.example

Features
- Reply to a file with:
  /rename new_filename.ext [--thumb] [--as-video]
- Upload a file with caption:
  rename: new_filename.ext [--thumb] [--as-video]
- Preserves thumbnail when `--thumb` is used (if available).
- `--as-video` attempts to send the file as a video (useful for playback).
- Fast server-side copy in USER mode (no re-upload) when possible.
- Progress feedback: edits a status message showing percentage, transferred bytes, speed and ETA both for download and upload.
- Admin-only access control via OWNER_IDS and optional allowed group list via ALLOW_GROUP_IDS.
- Safe session handling: generate session string locally and store as Render secret (SESSION_STRING) — DO NOT commit session strings to repo.

Important notes about large files (4GB)
- For reliable support of very large files (~4GB), use MODE=user and provide a user session (SESSION_STRING is recommended). Bot-mode likely cannot handle >2GB because of Bot API limits and re-upload constraints.
- Render ephemeral filesystem: do not rely on storing large files long-term. The app uses temporary files and cleans them up.

Session string generation & safe upload to Render (recommended)
1. Generate session string locally (on your laptop).
   - Install dependencies: pip install -r requirements.txt
   - Run:
     python generate_session.py
   - Follow the login prompts. The script will print a session string.

2. Add the session string to Render securely:
   - In Render dashboard, go to your Service > Environment > New Secret.
   - Name it `SESSION_STRING` and paste the session string.
   - Deploy the service. The bot will use SESSION_STRING to start without interactive login.

Alternative: upload session file
- Generate the local session file (will create `<SESSION_NAME>.session`).
- Upload it to a secure location and set `SESSION_FILE_PATH` to the path where it will be available inside the container.

Environment variables (.env.example)
- MODE: "bot" or "user" (default "bot")
- BOT_TOKEN: required if MODE=bot
- API_ID, API_HASH: required if MODE=user (unless you use only BOT mode)
- SESSION_STRING: optional; preferred for Render in user mode
- SESSION_FILE_PATH: optional path to a session file mounted into container
- SESSION_NAME: fallback session name (default: rename_user_session)
- OWNER_IDS: optional comma-separated list of Telegram user IDs allowed to run commands (if empty, anyone can use)
- ALLOW_GROUP_IDS: optional comma-separated list of allowed group chat IDs (if empty, all groups allowed)
- TZ: timezone for container logs

Deploy to Render
1. Push this repo to GitHub.
2. Create a new Web Service in Render using the GitHub repo and Docker.
3. Add environment variables and secrets in Render dashboard:
   - MODE=user (recommended for large files)
   - API_ID / API_HASH (Required in user mode)
   - SESSION_STRING (recommended): paste the string you generated locally (secret)
   - OWNER_IDS (optional)
4. Deploy.

Security tips
- Never commit SESSION_STRING or session files into source control.
- Use Render secrets to store session strings and tokens.
- Limit OWNER_IDS to your own Telegram numeric user ID(s).

If you want:
- I can add an admin-only `/shutdown` and `/stats` command.
- Add external log forwarding (LogDNA/Sentry) or notifications on errors.