#!/usr/bin/env python3
"""
One-time script to obtain a Google OAuth refresh token for the Calendar API.

Run once in the Replit shell. You will never need to run this again.
The refresh token it prints should be stored as a Replit Secret and
can then be used by the booking app indefinitely.

Usage:
    python booking-app/get_refresh_token.py

Requirements: only uses 'requests', which is already installed.
"""
import sys
import urllib.parse
import requests

SCOPE        = "https://www.googleapis.com/auth/calendar.events"
REDIRECT_URI = "http://localhost"
TOKEN_URL    = "https://oauth2.googleapis.com/token"
AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"

def main():
    print()
    print("=" * 68)
    print("  Google OAuth Refresh Token Generator")
    print("=" * 68)
    print()

    client_id     = input("Paste your Google Client ID:     ").strip()
    client_secret = input("Paste your Google Client Secret: ").strip()

    if not client_id or not client_secret:
        print("\n[ERROR] Client ID and Client Secret are required.")
        sys.exit(1)

    params = {
        "client_id":     client_id,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPE,
        "access_type":   "offline",
        "prompt":        "consent",
    }
    auth_link = AUTH_URL + "?" + urllib.parse.urlencode(params)

    print()
    print("=" * 68)
    print("  STEP 1 — Open this URL in your browser")
    print("=" * 68)
    print()
    print(auth_link)
    print()
    print("  Sign in with your Google account and click 'Allow'.")
    print()
    print("  After you approve, your browser will try to load")
    print("  'localhost' and show a connection error — that is")
    print("  expected. Look at the address bar. It will contain")
    print("  a URL like:")
    print()
    print("    http://localhost/?code=4/0AXXXXXXyour-code-hereXXXX&scope=...")
    print()
    print("  Copy everything after 'code=' and before '&scope'.")
    print("=" * 68)
    print()

    auth_code = input("  STEP 2 — Paste the authorization code here: ").strip()

    if not auth_code:
        print("\n[ERROR] No authorization code provided.")
        sys.exit(1)

    print()
    print("  Exchanging code for tokens ...")

    resp = requests.post(
        TOKEN_URL,
        data={
            "code":          auth_code,
            "client_id":     client_id,
            "client_secret": client_secret,
            "redirect_uri":  REDIRECT_URI,
            "grant_type":    "authorization_code",
        },
        timeout=15,
    )

    data = resp.json()

    if resp.status_code != 200 or "refresh_token" not in data:
        print()
        print("[ERROR] Token exchange failed.")
        print("Google response:", data)
        print()
        print("Common causes:")
        print("  - Authorization code already used (codes are single-use)")
        print("  - Wrong client_id or client_secret")
        print("  - The code was not copied correctly from the URL")
        sys.exit(1)

    refresh_token = data["refresh_token"]

    print()
    print("=" * 68)
    print("  SUCCESS")
    print("=" * 68)
    print()
    print("  Your refresh token:")
    print()
    print(f"  {refresh_token}")
    print()
    print("=" * 68)
    print("  What to do next:")
    print()
    print("  1. In Replit, open the Secrets tab (padlock icon)")
    print("  2. Add a new secret:")
    print("       Key:   GOOGLE_REFRESH_TOKEN")
    print("       Value: (the token printed above)")
    print("  3. Also add these two secrets from your OAuth client JSON:")
    print("       Key:   GOOGLE_CLIENT_ID")
    print("       Value: (the client_id you just entered)")
    print("       Key:   GOOGLE_CLIENT_SECRET")
    print("       Value: (the client_secret you just entered)")
    print("  4. Add one more secret:")
    print("       Key:   GOOGLE_CALENDAR_ID")
    print("       Value: your Gmail address (e.g. you@gmail.com)")
    print()
    print("  You can then delete this script or leave it — it contains")
    print("  no secrets and is safe to keep.")
    print("=" * 68)
    print()

if __name__ == "__main__":
    main()
