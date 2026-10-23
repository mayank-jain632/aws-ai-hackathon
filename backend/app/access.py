"""Demo accounts, signed sessions, and CloudFront origin protection."""

import base64
import hashlib
import hmac
import html
import json
import os
import time
from urllib.parse import parse_qs

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

LOGIN = """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fund desk · Sign in</title>
<style>*{box-sizing:border-box}body{margin:0;font:14px system-ui,sans-serif;background:#f3f1ed;color:#292622;min-height:100dvh;display:grid;place-items:center;padding:24px}form{width:360px;max-width:100%;padding:32px;border:1px solid #ddd7cf;background:#faf9f6}h1{font:400 32px Georgia,serif;margin:0 0 12px}p{font-size:13px;color:#756c62;line-height:1.6}label{display:block;margin:24px 0 8px;font-size:12px}input,select,button{font:inherit;width:100%;padding:12px;border:1px solid #cfc4b7;background:#faf9f6;color:#292622;border-radius:2px}button{margin-top:8px;background:#874e4c;color:#fffaf5;border-color:#874e4c;cursor:pointer}button:hover{background:#74413f}input:focus-visible,select:focus-visible,button:focus-visible{outline:2px solid #874e4c;outline-offset:3px}.error{color:#9b4036}.aws{margin-top:24px;font-size:11px;text-align:center}</style></head><body>
<form method="post" action="/login"><h1>Fund desk</h1><p>Sign in to your shared team workspace.</p>
<label for="email">Demo account</label><select id="email" name="email">__ACCOUNTS__</select>
<label for="password">Password</label><input id="password" name="password" type="password" required autocomplete="current-password">
<p class="error">__ERROR__</p><button>Sign in</button><p class="aws">Built on AWS</p></form></body></html>"""


class HostedAccess:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        secret = os.getenv("APP_ACCESS_PASSWORD", "")
        if scope["type"] != "http" or not secret:
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        local = request.client and request.client.host in {"127.0.0.1", "::1"}
        origin = os.getenv("APP_ORIGIN_TOKEN", "")
        if (
            origin
            and not local
            and not hmac.compare_digest(
                request.headers.get("x-origin-token", ""), origin
            )
        ):
            return await Response("Forbidden", status_code=403)(scope, receive, send)
        if request.url.path == "/api/health" or (
            local and request.url.path.startswith("/api/internal/")
        ):
            return await self.app(scope, receive, send)
        accounts = json.loads(os.getenv("APP_DEMO_ACCOUNTS", "{}"))

        def signature(payload):
            return hmac.new(
                secret.encode(), payload.encode(), hashlib.sha256
            ).hexdigest()

        def login(error="", status=200):
            options = "".join(
                f'<option value="{html.escape(email)}">{html.escape(email)}</option>'
                for email in accounts
            )
            return HTMLResponse(
                LOGIN.replace("__ACCOUNTS__", options).replace("__ERROR__", error),
                status_code=status,
                headers={"Cache-Control": "no-store"},
            )

        if request.url.path == "/login":
            response = login()
            if request.method == "POST":
                body = await request.body()
                form = parse_qs(body.decode(errors="replace"))
                email = form.get("email", [""])[0].lower().strip()
                supplied = form.get("password", [""])[0]
                expected = accounts.get(email, "")
                if (
                    len(body) <= 4096
                    and expected
                    and hmac.compare_digest(supplied.encode(), expected.encode())
                ):
                    payload = base64.urlsafe_b64encode(
                        f"{int(time.time())}|{email}".encode()
                    ).decode()
                    response = RedirectResponse("/", status_code=303)
                    response.set_cookie(
                        "canvas_session",
                        f"{payload}.{signature(payload)}",
                        secure=True,
                        httponly=True,
                        samesite="strict",
                        max_age=28800,
                    )
                else:
                    response = login("Incorrect account or password.", 401)
            return await response(scope, receive, send)
        payload, _, digest = request.cookies.get("canvas_session", "").partition(".")
        email = ""
        if hmac.compare_digest(digest, signature(payload)):
            try:
                stamp, email = base64.urlsafe_b64decode(payload).decode().split("|", 1)
                if (
                    not stamp.isdigit()
                    or not 0 <= time.time() - int(stamp) < 28800
                    or email not in accounts
                ):
                    email = ""
            except (ValueError, UnicodeError):
                pass
        if not email:
            response = (
                Response("Sign in required", status_code=401)
                if request.url.path.startswith("/api/")
                else RedirectResponse("/login", status_code=303)
            )
            return await response(scope, receive, send)
        if request.url.path == "/logout":
            response = RedirectResponse("/login", status_code=303)
            response.delete_cookie(
                "canvas_session", secure=True, httponly=True, samesite="strict"
            )
            return await response(scope, receive, send)
        scope.setdefault("state", {})["user"] = email
        return await self.app(scope, receive, send)
