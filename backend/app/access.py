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
<label for="email">Email</label><input id="email" name="email" type="email" required autocomplete="username" list="team-accounts"><datalist id="team-accounts">__ACCOUNTS__</datalist>
<label for="password">Password</label><input id="password" name="password" type="password" required autocomplete="current-password">
<p class="error">__ERROR__</p><button>Sign in</button><p class="aws">Invited teammates can use their invitation link to join.</p><p class="aws">Built on AWS</p></form></body></html>"""


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
        accounts = {
            email.lower(): password
            for email, password in json.loads(
                os.getenv("APP_DEMO_ACCOUNTS", "{}")
            ).items()
        }
        sharing = getattr(request.app.state, "sharing", None)

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

        def signed_in(email):
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
            return response

        if request.url.path.startswith("/join/"):
            token = request.url.path.removeprefix("/join/")
            invited = sharing.invitation(token) if sharing else None
            error = ""
            status = 200
            if not invited:
                response = HTMLResponse(
                    '<p>This invitation is invalid or has expired.</p><a href="/login">Sign in</a>',
                    status_code=410,
                )
                return await response(scope, receive, send)
            if request.method == "POST":
                body = await request.body()
                form = parse_qs(body.decode(errors="replace"))
                try:
                    if len(body) > 4096:
                        raise ValueError("Form is too large")
                    email = sharing.join(token, form.get("password", [""])[0])
                    return await signed_in(email)(scope, receive, send)
                except ValueError as problem:
                    error, status = str(problem), 400
            page = (
                LOGIN.replace('action="/login"', f'action="/join/{html.escape(token)}"')
                .replace("Fund desk</h1>", "Join Fund desk</h1>")
                .replace(
                    "Sign in to your shared team workspace.",
                    "Set a password to access funds shared with you.",
                )
                .replace("<button>Sign in</button>", "<button>Join workspace</button>")
                .replace(
                    'autocomplete="current-password"',
                    'autocomplete="new-password" minlength="8" maxlength="256"',
                )
                .replace(
                    'required autocomplete="username"',
                    f'readonly value="{html.escape(invited)}"',
                )
                .replace("__ACCOUNTS__", "")
                .replace("__ERROR__", html.escape(error))
            )
            return await HTMLResponse(
                page,
                status_code=status,
                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
            )(scope, receive, send)

        if request.url.path == "/login":
            response = login()
            if request.method == "POST":
                body = await request.body()
                form = parse_qs(body.decode(errors="replace"))
                email = form.get("email", [""])[0].lower().strip()
                supplied = form.get("password", [""])[0]
                expected = accounts.get(email, "")
                valid = bool(
                    expected
                    and hmac.compare_digest(supplied.encode(), expected.encode())
                )
                if not valid and sharing and len(body) <= 4096:
                    valid = sharing.authenticate(email, supplied)
                response = (
                    signed_in(email)
                    if len(body) <= 4096 and valid
                    else login("Incorrect email or password.", 401)
                )
            return await response(scope, receive, send)
        payload, _, digest = request.cookies.get("canvas_session", "").partition(".")
        email = ""
        if hmac.compare_digest(digest, signature(payload)):
            try:
                stamp, email = base64.urlsafe_b64decode(payload).decode().split("|", 1)
                if (
                    not stamp.isdigit()
                    or not 0 <= time.time() - int(stamp) < 28800
                    or not (email in accounts or sharing and sharing.registered(email))
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
        if sharing and request.url.path.startswith("/api/"):
            parts = request.url.path.split("/")
            if len(parts) > 3 and parts[2] == "funds":
                if not sharing.can_access(parts[3], email):
                    return await Response("Fund access denied", status_code=403)(
                        scope, receive, send
                    )
            elif (
                request.url.path.startswith(
                    ("/api/agents", "/api/events", "/api/board", "/api/desk")
                )
                and not sharing.can_access("general", email)
                or email not in accounts
                and request.url.path
                not in {
                    "/api/me",
                    "/api/funds",
                    "/api/agent-models",
                    "/api/agent-roles",
                }
            ):
                return await Response("Fund access required", status_code=403)(
                    scope, receive, send
                )
        return await self.app(scope, receive, send)
