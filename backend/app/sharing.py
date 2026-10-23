"""Persistent fund membership and invitation-only teammate accounts."""

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s.]+(?:\.[^@\s.]+)+$")


def email_address(value):
    value = value.strip().lower()
    if len(value) > 254 or not EMAIL.fullmatch(value):
        raise ValueError("Enter a valid email address")
    return value


def hash_password(password):
    if not 8 <= len(password) <= 256:
        raise ValueError("Use a password between 8 and 256 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + ":" + digest.hex()


def verify_password(password, stored):
    if len(password) > 256:
        return False
    salt, digest = stored.split(":")
    actual = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1
    )
    return hmac.compare_digest(actual.hex(), digest)


class ShareStore:
    def __init__(self, root, demo_accounts):
        self.path = root / "sharing.sqlite3"
        self.demo = {email.lower() for email in demo_accounts}
        self.primary = next(iter(demo_accounts), "local").lower()
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS accounts(email TEXT PRIMARY KEY, password TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS funds(id TEXT PRIMARY KEY, owner TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS members(fund TEXT, email TEXT, PRIMARY KEY(fund,email));
                CREATE TABLE IF NOT EXISTS invitations(token TEXT PRIMARY KEY, email TEXT NOT NULL, expires INTEGER NOT NULL);
            """)
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def migrate(self, records):
        """Keep existing team access; new funds are shared explicitly."""
        with self.db() as db:
            legacy = not db.execute(
                "SELECT 1 FROM metadata WHERE key='migrated'"
            ).fetchone()
            for fund_id, record in records.items():
                if db.execute("SELECT 1 FROM funds WHERE id=?", (fund_id,)).fetchone():
                    continue
                owner = record.get("owner", "").lower()
                if owner not in self.demo and "@" not in owner:
                    owner = self.primary
                self._create(db, fund_id, owner)
                if legacy:
                    db.executemany(
                        "INSERT OR IGNORE INTO members VALUES(?,?)",
                        [(fund_id, email) for email in self.demo],
                    )
            db.execute("INSERT OR IGNORE INTO metadata VALUES('migrated','yes')")

    def _create(self, db, fund_id, owner):
        db.execute("INSERT INTO funds VALUES(?,?)", (fund_id, owner))
        db.execute("INSERT INTO members VALUES(?,?)", (fund_id, owner))

    def create(self, fund_id, owner):
        with self.db() as db:
            self._create(db, fund_id, owner.lower())

    def registered(self, email):
        with self.db() as db:
            return (
                email == "local"
                or email in self.demo
                or bool(
                    db.execute(
                        "SELECT 1 FROM accounts WHERE email=?", (email,)
                    ).fetchone()
                )
            )

    def authenticate(self, email, password):
        with self.db() as db:
            row = db.execute(
                "SELECT password FROM accounts WHERE email=?", (email,)
            ).fetchone()
        return bool(row and verify_password(password, row["password"]))

    def can_access(self, fund_id, email):
        with self.db() as db:
            return bool(
                db.execute(
                    "SELECT 1 FROM members WHERE fund=? AND email=?", (fund_id, email)
                ).fetchone()
            )

    def members(self, fund_id):
        with self.db() as db:
            owner = db.execute(
                "SELECT owner FROM funds WHERE id=?", (fund_id,)
            ).fetchone()
            rows = db.execute(
                "SELECT email FROM members WHERE fund=? ORDER BY email", (fund_id,)
            ).fetchall()
        return [
            {
                "email": row["email"],
                "role": "owner"
                if owner and row["email"] == owner["owner"]
                else "editor",
                "status": "active" if self.registered(row["email"]) else "invited",
            }
            for row in rows
        ]

    def invite(self, fund_id, email):
        email = email_address(email)
        registered = self.registered(email)
        token = None if registered else secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("INSERT OR IGNORE INTO members VALUES(?,?)", (fund_id, email))
            if token:
                db.execute(
                    "DELETE FROM invitations WHERE expires < ?", (int(time.time()),)
                )
                db.execute(
                    "INSERT INTO invitations VALUES(?,?,?)",
                    (
                        hashlib.sha256(token.encode()).hexdigest(),
                        email,
                        int(time.time()) + 7 * 86400,
                    ),
                )
        return token

    def invitation(self, token):
        with self.db() as db:
            row = db.execute(
                "SELECT email FROM invitations WHERE token=? AND expires>?",
                (hashlib.sha256(token.encode()).hexdigest(), int(time.time())),
            ).fetchone()
            if (
                not row
                or not db.execute(
                    "SELECT 1 FROM members WHERE email=?", (row["email"],)
                ).fetchone()
            ):
                return None
            return row["email"]

    def join(self, token, password):
        # Expensive hashing happens before the write transaction.
        hashed = hash_password(password)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT email FROM invitations WHERE token=? AND expires>?",
                (hashlib.sha256(token.encode()).hexdigest(), int(time.time())),
            ).fetchone()
            if (
                not row
                or not db.execute(
                    "SELECT 1 FROM members WHERE email=?", (row["email"],)
                ).fetchone()
            ):
                raise ValueError("This invitation is invalid or has expired")
            email = row["email"]
            if (
                email in self.demo
                or db.execute(
                    "SELECT 1 FROM accounts WHERE email=?", (email,)
                ).fetchone()
            ):
                raise ValueError("This account already exists. Sign in instead.")
            db.execute("INSERT INTO accounts VALUES(?,?)", (email, hashed))
            db.execute("DELETE FROM invitations WHERE email=?", (email,))
        return email

    def remove(self, fund_id, email, actor):
        with self.db() as db:
            owner = db.execute(
                "SELECT owner FROM funds WHERE id=?", (fund_id,)
            ).fetchone()
            if not owner or actor != owner["owner"]:
                raise PermissionError("Only the fund owner can remove access")
            if email == actor:
                raise ValueError("The owner cannot remove their own access")
            db.execute("DELETE FROM members WHERE fund=? AND email=?", (fund_id, email))
