#!/usr/bin/env python3
"""One-time OAuth flow to capture an Amazon Ads API refresh_token.

Usage:
    python3 scripts/ads_oauth_helper.py

Reads ADS_API_CLIENT_ID + ADS_API_CLIENT_SECRET + ADS_API_REDIRECT_URI from .env,
opens browser to LWA consent page, runs a tiny localhost server to capture the
authorization code, then exchanges code for refresh_token. Prints the refresh
token + auto-patches .env if user confirms.

Refresh tokens do NOT expire (Amazon docs) — so this is a one-time setup.
"""

from __future__ import annotations

import http.server
import socketserver
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from env_loader import env, ENV_PATH  # noqa: E402

try:
    import requests
except ImportError:
    print("ERROR: pip install requests", file=sys.stderr)
    sys.exit(1)

LWA_AUTH_URL = "https://www.amazon.com/ap/oa"
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
SCOPE = "advertising::campaign_management"

# Captured by the local HTTP server callback
_captured: dict[str, str] = {}
_event = threading.Event()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _captured["code"] = params["code"][0]
            body = b"<h1>OK - you can close this tab.</h1><p>Return to terminal.</p>"
        elif "error" in params:
            _captured["error"] = params.get("error", ["unknown"])[0]
            _captured["error_description"] = params.get("error_description", [""])[0]
            body = f"<h1>Error: {_captured['error']}</h1><p>{_captured['error_description']}</p>".encode()
        else:
            body = b"<h1>No code in callback.</h1>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)
        _event.set()

    def log_message(self, *_args):  # silence default access log
        pass


def _start_callback_server(port: int) -> socketserver.TCPServer:
    httpd = socketserver.TCPServer(("127.0.0.1", port), _CallbackHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    resp = requests.post(
        LWA_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _patch_env_file(refresh_token: str) -> bool:
    if not ENV_PATH.exists():
        return False
    text = ENV_PATH.read_text()
    if "ADS_API_REFRESH_TOKEN=" in text:
        new_text = "\n".join(
            (f"ADS_API_REFRESH_TOKEN={refresh_token}" if line.strip().startswith("ADS_API_REFRESH_TOKEN=") else line)
            for line in text.splitlines()
        )
        if not new_text.endswith("\n"):
            new_text += "\n"
        ENV_PATH.write_text(new_text)
        return True
    return False


def main() -> int:
    client_id = env("ADS_API_CLIENT_ID")
    client_secret = env("ADS_API_CLIENT_SECRET")
    redirect_uri = env("ADS_API_REDIRECT_URI", "http://localhost:8765/callback")

    if not client_id or not client_secret:
        print("ERROR: ADS_API_CLIENT_ID and ADS_API_CLIENT_SECRET must be set in .env", file=sys.stderr)
        print("       Create them at developer.amazon.com → Settings → Security Profiles", file=sys.stderr)
        return 1

    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        print(f"ERROR: redirect_uri must be localhost for this helper, got {redirect_uri}", file=sys.stderr)
        return 1
    port = parsed.port or 8765

    auth_url = LWA_AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "scope": SCOPE,
        "response_type": "code",
        "redirect_uri": redirect_uri,
    })

    httpd = _start_callback_server(port)
    print("─" * 60)
    print("Opening browser for Amazon LWA consent...")
    print("If browser doesn't open, paste this URL manually:")
    print(f"  {auth_url}")
    print("─" * 60)
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print(f"Waiting for callback on http://localhost:{port}/callback ...")
    if not _event.wait(timeout=300):
        print("ERROR: timeout waiting for callback (5 min)", file=sys.stderr)
        httpd.shutdown()
        return 1
    httpd.shutdown()

    if "error" in _captured:
        print(f"ERROR from Amazon: {_captured['error']} — {_captured.get('error_description','')}", file=sys.stderr)
        return 1
    if "code" not in _captured:
        print("ERROR: no auth code captured", file=sys.stderr)
        return 1

    print("✓ Got authorization code, exchanging for refresh_token...")
    try:
        tokens = _exchange_code(_captured["code"], client_id, client_secret, redirect_uri)
    except requests.HTTPError as e:
        print(f"ERROR: token exchange failed: {e.response.status_code} {e.response.text}", file=sys.stderr)
        return 1

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print(f"ERROR: response missing refresh_token: {tokens}", file=sys.stderr)
        return 1

    print()
    print("=" * 60)
    print("✅ SUCCESS")
    print("=" * 60)
    print(f"refresh_token: {refresh_token}")
    print(f"access_token (1h TTL, ignored): {tokens.get('access_token','')[:20]}...")
    print()

    if _patch_env_file(refresh_token):
        print(f"✓ Auto-patched {ENV_PATH} with ADS_API_REFRESH_TOKEN")
    else:
        print(f"⚠ Could not auto-patch .env — paste this line into {ENV_PATH}:")
        print(f"   ADS_API_REFRESH_TOKEN={refresh_token}")

    print()
    print("Next: python3 scripts/amazon_ads_api.py list-profiles")
    print("      → copy US profileId → set ADS_API_PROFILE_ID in .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
