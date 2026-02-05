#!/usr/bin/env python3
"""
Helper script to generate a Pyrogram session string locally.

Usage:
  1. Set API_ID and API_HASH in environment or enter them when prompted.
  2. Run: python generate_session.py
  3. Follow the login prompts. The script will print a session string.
  4. Copy the session string and store it as a secret (e.g., in Render as SESSION_STRING).
"""
import os
from pyrogram import Client
from dotenv import load_dotenv

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("SESSION_NAME", "rename_user_session")

if not API_ID:
    API_ID = input("Enter your API_ID: ").strip()
if not API_HASH:
    API_HASH = input("Enter your API_HASH: ").strip()

API_ID = int(API_ID)

print("Starting Pyrogram client to generate a session string.")
print("You will be asked to enter your phone number and the login code.")
print("This runs locally on your machine; do NOT share the printed session string with anyone.")

with Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH) as app:
    s = app.export_session_string()
    print("\n----- SESSION STRING -----\n")
    print(s)
    print("\n----- END SESSION STRING -----\n")
    print("Copy the session string and paste it into your Render environment variable SESSION_STRING (secret).")
    print("Alternatively, save the generated session file ({}.session) and upload it to secure storage.".format(SESSION_NAME))