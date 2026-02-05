#!/usr/bin/env python3
import os
import time
import tempfile
import shutil
import logging
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message

load_dotenv()

# Config
MODE = os.getenv("MODE", "bot").lower()  # "bot" or "user"
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = os.getenv("API_ID", "")
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")
SESSION_FILE_PATH = os.getenv("SESSION_FILE_PATH", "")
SESSION_NAME = os.getenv("SESSION_NAME", "rename_user_session")
OWNER_IDS = [int(x.strip()) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip().isdigit()]
ALLOW_GROUP_IDS = [int(x.strip()) for x in os.getenv("ALLOW_GROUP_IDS", "").split(",") if x.strip().lstrip("-").isdigit()]

# Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("tg-rename-bot")

if MODE not in ("bot", "user"):
    raise SystemExit("MODE must be 'bot' or 'user'")

# Custom non-edited filter (some pyrogram versions lack filters.edited)
non_edited = filters.create(lambda _, __, msg: not bool(getattr(msg, "edit_date", None)))

# Create client (ensure app is defined BEFORE handlers)
if MODE == "bot":
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN required for bot mode")
    # Use in-memory session to avoid accidental user auth or .session file usage
    app = Client(":memory:", bot_token=BOT_TOKEN, workdir=".")
else:
    if not API_ID or not API_HASH:
        raise SystemExit("API_ID and API_HASH required for user mode")
    # Prefer session string (safe for Render secrets)
    if SESSION_STRING:
        app = Client(SESSION_NAME, api_id=int(API_ID), api_hash=API_HASH, session_string=SESSION_STRING, workdir=".")
    elif SESSION_FILE_PATH and os.path.exists(SESSION_FILE_PATH):
        dst = f"{SESSION_NAME}.session"
        try:
            shutil.copy(SESSION_FILE_PATH, dst)
        except Exception as e:
            log.warning("Failed to copy session file: %s", e)
        app = Client(SESSION_NAME, api_id=int(API_ID), api_hash=API_HASH, workdir=".")
    else:
        app = Client(SESSION_NAME, api_id=int(API_ID), api_hash=API_HASH, workdir=".")

# Helpers
def humanbytes(size: float) -> str:
    if not size:
        return "0B"
    power = 2 ** 10
    n = 0
    units = ["B", "KB", "MB", "GB", "TB"]
    while size >= power and n < len(units) - 1:
        size /= power
        n += 1
    return f"{size:.2f}{units[n]}"

def is_allowed_user(user_id: int) -> bool:
    if not OWNER_IDS:
        return True
    return user_id in OWNER_IDS

def is_allowed_chat(chat_id: int) -> bool:
    if not ALLOW_GROUP_IDS:
        return True
    return chat_id in ALLOW_GROUP_IDS

def extract_newname_and_flags(text: str):
    if not text:
        return None, []
    text = text.strip()
    tokens = text.split()
    lower = text.lower()
    flags = []
    name_tokens = []
    if "rename:" in lower:
        idx = lower.index("rename:") + len("rename:")
        tail = text[idx:].strip()
        tail_tokens = tail.split()
        flags = [t for t in tail_tokens if t.startswith("--")]
        name_tokens = [t for t in tail_tokens if not t.startswith("--")]
    elif tokens and tokens[0].lower().startswith("/rename"):
        tokens_tail = tokens[1:]
        flags = [t for t in tokens_tail if t.startswith("--")]
        name_tokens = [t for t in tokens_tail if not t.startswith("--")]
    elif lower.startswith("rename="):
        tail = text.split("=", 1)[1].strip()
        tail_tokens = tail.split()
        flags = [t for t in tail_tokens if t.startswith("--")]
        name_tokens = [t for t in tail_tokens if not t.startswith("--")]
    else:
        flags = [t for t in tokens if t.startswith("--")]
        name_tokens = [t for t in tokens if not t.startswith("--")]
    name = " ".join(name_tokens).strip()
    if not name:
        return None, flags
    return name, flags

async def edit_status_safe(msg: Message, txt: str):
    try:
        await msg.edit_text(txt)
    except Exception:
        pass

def progress_callback_factory(status_message: Message, start_time: float, prefix: str = ""):
    last_update = {"time": 0}
    def _progress(current, total):
        now = time.time()
        if now - last_update["time"] < 1 and current != total:
            return
        last_update["time"] = now
        diff = now - start_time
        if diff <= 0:
            diff = 1e-6
        speed = current / diff
        eta_seconds = (total - current) / speed if speed > 0 else 0
        pct = (current * 100 / total) if total else 0
        text = (
            f"{prefix}\n"
            f"{pct:.1f}% — {humanbytes(current)}/{humanbytes(total)}\n"
            f"Speed: {humanbytes(speed)}/s — ETA: {int(eta_seconds)}s"
        )
        try:
            asyncio.get_event_loop().create_task(edit_status_safe(status_message, text))
        except Exception:
            pass
    return _progress

# Core send logic
async def send_with_filename(client: Client, chat_id: int, media_message: Message, new_filename: str, reply_to_message_id: int = None, keep_thumb: bool = False, as_video: bool = False):
    status = await client.send_message(chat_id, "Preparing rename...", reply_to_message_id=reply_to_message_id)
    # collect thumb file_id if requested and available
    thumb_file_id = None
    try:
        if getattr(media_message, "document", None) and media_message.document.thumbs:
            try:
                thumb_file_id = media_message.document.thumbs[-1].file_id
            except Exception:
                thumb_file_id = None
        if getattr(media_message, "video", None) and getattr(media_message.video, "thumb", None):
            try:
                thumb_file_id = media_message.video.thumb.file_id
            except Exception:
                thumb_file_id = None
        if getattr(media_message, "photo", None):
            try:
                thumb_file_id = media_message.photo.file_id
            except Exception:
                thumb_file_id = None
    except Exception:
        thumb_file_id = None

    # Try server-side copy in user mode (fast)
    if MODE == "user":
        try:
            file_id = None
            if getattr(media_message, "document", None):
                file_id = media_message.document.file_id
            elif getattr(media_message, "video", None):
                file_id = media_message.video.file_id
            elif getattr(media_message, "audio", None):
                file_id = media_message.audio.file_id
            elif getattr(media_message, "voice", None):
                file_id = media_message.voice.file_id
            elif getattr(media_message, "photo", None):
                file_id = media_message.photo.file_id

            if file_id:
                await status.edit_text("Copying file on Telegram servers (fast)...")
                if as_video and getattr(media_message, "video", None):
                    await client.send_video(
                        chat_id,
                        file_id,
                        caption=media_message.caption or "",
                        thumb=(thumb_file_id if (keep_thumb and thumb_file_id) else None),
                        reply_to_message_id=reply_to_message_id,
                    )
                else:
                    await client.send_document(
                        chat_id,
                        file_id,
                        file_name=new_filename,
                        caption=media_message.caption or "",
                        thumb=(thumb_file_id if (keep_thumb and thumb_file_id) else None),
                        reply_to_message_id=reply_to_message_id,
                    )
                await status.edit_text(f"Copied and sent as `{new_filename}`")
                await asyncio.sleep(1)
                await status.delete()
                return
        except Exception as e:
            log.warning("Server-side copy failed, falling back to download/upload: %s", e)

    # Fallback: download and upload with progress
    tmp_dir = tempfile.mkdtemp(prefix="tg_rename_")
    downloaded_path = None
    try:
        await status.edit_text("Downloading file to temporary storage...")
        start_dl = time.time()
        progress_cb = progress_callback_factory(status, start_dl, prefix="Downloading...")
        downloaded_path = await client.download_media(media_message, file_name=Path(tmp_dir) / new_filename, progress=progress_cb)
        if not downloaded_path:
            raise RuntimeError("download_media returned empty")
        await status.edit_text("Upload: starting...")
        start_ul = time.time()
        progress_cb_up = progress_callback_factory(status, start_ul, prefix="Uploading...")
        try:
            if getattr(media_message, "video", None) and as_video:
                await client.send_video(
                    chat_id,
                    downloaded_path,
                    caption=media_message.caption or "",
                    thumb=(thumb_file_id if (keep_thumb and thumb_file_id) else None),
                    progress=progress_cb_up,
                    reply_to_message_id=reply_to_message_id,
                )
            else:
                await client.send_document(
                    chat_id,
                    downloaded_path,
                    caption=media_message.caption or "",
                    file_name=new_filename,
                    thumb=(thumb_file_id if (keep_thumb and thumb_file_id) else None),
                    progress=progress_cb_up,
                    reply_to_message_id=reply_to_message_id,
                )
        except Exception as e:
            log.warning("Upload failed with chosen method, trying fallback send_document: %s", e)
            await client.send_document(
                chat_id,
                downloaded_path,
                caption=media_message.caption or "",
                file_name=new_filename,
                thumb=(thumb_file_id if (keep_thumb and thumb_file_id) else None),
                progress=progress_cb_up,
                reply_to_message_id=reply_to_message_id,
            )
        await status.edit_text(f"Sent renamed file: `{new_filename}`")
        await asyncio.sleep(1)
        await status.delete()
    finally:
        try:
            if downloaded_path and os.path.exists(downloaded_path):
                os.remove(downloaded_path)
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

# Handlers (app is already created)
@app.on_message(filters.command("start") & filters.private)
async def start_private(_, message: Message):
    await message.reply_text("Send a file and reply to it with /rename new_name.ext\nOr send a file with caption: rename: new_name.ext")

@app.on_message(filters.command("rename") & (filters.private | filters.group))
async def cmd_rename(client: Client, message: Message):
    from_user = message.from_user.id if message.from_user else None
    if not is_allowed_user(from_user):
        await message.reply_text("You are not authorized to use this bot.")
        return
    if message.chat.type in ("group", "supergroup") and not is_allowed_chat(message.chat.id):
        await message.reply_text("This group is not allowed to use the bot.")
        return
    if not message.reply_to_message:
        await message.reply_text("Please reply to the file you want to rename with `/rename new_name.ext`.", quote=True)
        return
    newname, flags = extract_newname_and_flags(message.text or "")
    if not newname:
        await message.reply_text("Usage: `/rename new_name.ext [--thumb] [--as-video]` (reply to the file)", quote=True)
        return
    keep_thumb = "--thumb" in flags
    as_video = "--as-video" in flags
    media_msg = message.reply_to_message
    if not media_msg.media:
        await message.reply_text("The replied message does not contain a file/media.", quote=True)
        return
    await message.chat.do("typing")
    try:
        await send_with_filename(client, message.chat.id, media_msg, newname, reply_to_message_id=message.reply_to_message.message_id, keep_thumb=keep_thumb, as_video=as_video)
        await message.reply_text(f"Renamed and sent as `{newname}`", quote=True)
    except Exception as e:
        log.exception("Failed to rename/send: %s", e)
        await message.reply_text(f"Failed to rename/send file: {e}", quote=True)

@app.on_message(filters.all & non_edited)
async def auto_caption_rename(client: Client, message: Message):
    if not message.media:
        return
    caption = message.caption or ""
    if "rename:" not in caption.lower():
        return
    from_user = message.from_user.id if message.from_user else None
    if not is_allowed_user(from_user):
        await message.reply_text("You are not authorized to use this bot.")
        return
    if message.chat.type in ("group", "supergroup") and not is_allowed_chat(message.chat.id):
        await message.reply_text("This group is not allowed to use the bot.")
        return
    newname, flags = extract_newname_and_flags(caption)
    if not newname:
        return
    keep_thumb = "--thumb" in flags
    as_video = "--as-video" in flags
    try:
        await send_with_filename(client, message.chat.id, message, newname, reply_to_message_id=message.message_id, keep_thumb=keep_thumb, as_video=as_video)
        await message.reply_text(f"Renamed and sent as `{newname}`", quote=True)
    except Exception as e:
        log.exception("Auto-caption rename failed: %s", e)
        await message.reply_text(f"Failed to rename/send file: {e}", quote=True)

# Optional admin-only shutdown
@app.on_message(filters.command("shutdown") & (filters.private | filters.group))
async def shutdown_cmd(client: Client, message: Message):
    from_user = message.from_user.id if message.from_user else None
    if not is_allowed_user(from_user):
        await message.reply_text("You are not authorized to use this command.")
        return
    await message.reply_text("Shutting down...")
    await client.stop()

if __name__ == "__main__":
    log.info("Starting Telegram rename bot in %s mode", MODE)
    app.run()
