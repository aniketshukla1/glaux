"""User accounts — signup/login, password hashing, and signed session tokens.

Stdlib-only (no bcrypt/JWT deps): passwords are hashed with PBKDF2-HMAC-SHA256 +
a per-user salt; session tokens are HMAC-SHA256-signed `{payload}.{sig}` strings
carrying the user id, a token version (bump to sign out everywhere), and an
expiry. The signing secret lives outside this module (generated/persisted by the
API) so it never lands in the users file.

This is the identity of *who is using the API* — distinct from the agents'
Ed25519 ledger identities (which prove *which agent* signed a block).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_PBKDF2_ITERATIONS = 600_000  # OWASP-recommended floor for PBKDF2-SHA256
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8
DEFAULT_TOKEN_TTL = 30 * 24 * 3600  # 30 days


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match((email or "").strip()))


# --- password hashing -----------------------------------------------------

def hash_password(password: str, *, iterations: int = _PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


# --- session tokens (HMAC-signed) -----------------------------------------

def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(secret: str, user_id: str, version: int, *, ttl: int = DEFAULT_TOKEN_TTL) -> str:
    payload = {"uid": user_id, "ver": version, "exp": int(time.time()) + ttl}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(secret: str, token: str) -> Optional[dict]:
    """Return the token payload ({uid, ver, exp}) if the signature is valid and it
    hasn't expired, else None. Caller still checks `ver` against the user."""
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_unb64(body))
    except (ValueError, AttributeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    return payload


# --- model + store --------------------------------------------------------

@dataclass
class User:
    id: str
    email: str
    name: str
    password_hash: str
    created_at: str = ""
    token_version: int = 0
    settings: dict = field(default_factory=dict)  # theme, default_model, avatar, …

    def public(self) -> dict:
        """The user minus secrets, for sending to the client."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "created_at": self.created_at,
            "settings": self.settings or {},
        }


class UserError(Exception):
    """Bad signup/login/profile input (maps to a 400)."""


class UserStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else None
        self.users: dict[str, User] = {}
        self._by_email: dict[str, str] = {}  # lowercased email -> id
        self.load()

    # -- lookups --
    def count(self) -> int:
        return len(self.users)

    def by_id(self, user_id: Optional[str]) -> Optional[User]:
        return self.users.get(user_id) if user_id else None

    def by_email(self, email: str) -> Optional[User]:
        return self.users.get(self._by_email.get((email or "").strip().lower(), ""))

    # -- mutations --
    def create(self, email: str, password: str, name: str = "") -> User:
        email = (email or "").strip()
        if not valid_email(email):
            raise UserError("Enter a valid email address.")
        if len(password or "") < MIN_PASSWORD_LEN:
            raise UserError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
        if self.by_email(email) is not None:
            raise UserError("An account with that email already exists.")
        user = User(
            id=secrets.token_hex(8),
            email=email,
            name=(name or "").strip() or email.split("@")[0],
            password_hash=hash_password(password),
            created_at=_now(),
        )
        self.users[user.id] = user
        self._by_email[email.lower()] = user.id
        self.save()
        return user

    def authenticate(self, email: str, password: str) -> Optional[User]:
        user = self.by_email(email)
        if user is None or not verify_password(password or "", user.password_hash):
            return None
        return user

    def update_profile(self, user: User, *, name: Optional[str] = None, email: Optional[str] = None,
                       settings: Optional[dict] = None) -> User:
        if email is not None:
            email = email.strip()
            if not valid_email(email):
                raise UserError("Enter a valid email address.")
            existing = self.by_email(email)
            if existing is not None and existing.id != user.id:
                raise UserError("That email is already in use.")
            self._by_email.pop(user.email.lower(), None)
            user.email = email
            self._by_email[email.lower()] = user.id
        if name is not None:
            user.name = name.strip() or user.name
        if settings is not None:
            user.settings = {**(user.settings or {}), **settings}
        self.save()
        return user

    def change_password(self, user: User, current: str, new: str) -> None:
        if not verify_password(current or "", user.password_hash):
            raise UserError("Your current password is incorrect.")
        if len(new or "") < MIN_PASSWORD_LEN:
            raise UserError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
        user.password_hash = hash_password(new)
        user.token_version += 1  # invalidate existing sessions
        self.save()

    def bump_token_version(self, user: User) -> None:
        """Sign out everywhere by invalidating all previously issued tokens."""
        user.token_version += 1
        self.save()

    def delete(self, user_id: str) -> bool:
        user = self.users.pop(user_id, None)
        if user is None:
            return False
        self._by_email.pop(user.email.lower(), None)
        self.save()
        return True

    # -- persistence --
    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([asdict(u) for u in self.users.values()], indent=2))
        tmp.replace(self.path)

    def load(self) -> None:
        self.users.clear()
        self._by_email.clear()
        if not self.path or not self.path.exists():
            return
        try:
            rows = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        for row in rows:
            try:
                u = User(**{k: row.get(k) for k in User.__dataclass_fields__})
            except (TypeError, KeyError):
                continue
            self.users[u.id] = u
            self._by_email[u.email.lower()] = u.id
