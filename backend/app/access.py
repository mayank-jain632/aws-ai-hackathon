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

LOGIN = """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Agent canvas · Demo login</title></head>
<body style="font-family:system-ui;background:#f5f6fa;display:grid;place-items:center;min-height:90vh;color:#202530">
<form method="post" action="/login" style="background:white;padding:40px;border:1px solid #e2e6ed;border-radius:12px;width:320px;max-width:75vw">
<p style="font-size:12px;color:#78808f">AWS HACKATHON</p><h1 style="font-size:26px">Agent canvas</h1><p>Sign in to your team's shared demo.</p>
<label for="email">Demo account</label><select id="email" name="email" style="padding:12px;width:100%;margin:8px 0 20px">__ACCOUNTS__</select>
<label for="password">Password</label><input id="password" name="password" type="password" required autocomplete="current-password" style="padding:12px;box-sizing:border-box;width:100%;margin-top:8px">
<p style="color:#bd3a35">__ERROR__</p><button style="padding:12px;width:100%;border:0;border-radius:6px;background:#5265d9;color:white;font-size:14px">Open shared demo</button>
<p style="font-size:12px;color:#78808f">Your team shares agents, conversations, files, and the canvas.</p></form></body></html>"""


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
