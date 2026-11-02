"""Social login via OAuth 2.0 (authorization-code flow), stdlib-only.

Providers (Google, GitHub) are enabled per-deployment by setting their client
credentials in the environment:

    GLAUX_OAUTH_GOOGLE_CLIENT_ID / _CLIENT_SECRET
    GLAUX_OAUTH_GITHUB_CLIENT_ID / _CLIENT_SECRET

A provider with no credentials is simply hidden — the rest of auth works without
it. The API builds the authorize URL, the provider redirects back to our
callback, we exchange the code for an access token and read the verified email,
then find-or-create the matching account.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

PROVIDERS = {
    "google": {
        "label": "Google",
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
    "github": {
        "label": "GitHub",
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "userinfo": "https://api.github.com/user",
        "emails": "https://api.github.com/user/emails",
        "scope": "read:user user:email",
    },
}


class OAuthError(Exception):
    pass


def client_id(provider: str) -> Optional[str]:
    return os.environ.get(f"GLAUX_OAUTH_{provider.upper()}_CLIENT_ID")


def client_secret(provider: str) -> Optional[str]:
    return os.environ.get(f"GLAUX_OAUTH_{provider.upper()}_CLIENT_SECRET")


def is_configured(provider: str) -> bool:
    return provider in PROVIDERS and bool(client_id(provider) and client_secret(provider))


def configured_providers() -> list:
    return [{"id": p, "label": PROVIDERS[p]["label"]} for p in PROVIDERS if is_configured(p)]


def authorize_url(provider: str, redirect_uri: str, state: str) -> str:
    cfg = PROVIDERS[provider]
    params = {
        "client_id": client_id(provider),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    if provider == "google":
        params["access_type"] = "online"
        params["prompt"] = "select_account"
    return cfg["authorize"] + "?" + urllib.parse.urlencode(params)


def _post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _get_json(url: str, access_token: str):
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json", "User-Agent": "Glaux"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def exchange_code(provider: str, code: str, redirect_uri: str) -> str:
    cfg = PROVIDERS[provider]
    try:
        tok = _post_form(cfg["token"], {
            "client_id": client_id(provider),
            "client_secret": client_secret(provider),
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        })
    except (urllib.error.URLError, ValueError) as e:
        raise OAuthError(f"token exchange failed: {e}")
    access = tok.get("access_token")
    if not access:
        raise OAuthError(tok.get("error_description") or "no access token returned")
    return access


def fetch_identity(provider: str, access_token: str) -> tuple:
    """Return (subject, email, name) for the authenticated provider user."""
    cfg = PROVIDERS[provider]
    info = _get_json(cfg["userinfo"], access_token)
    if provider == "google":
        return str(info.get("sub")), info.get("email"), info.get("name")
    # github: email may be private — fall back to the verified primary email
    subject = str(info.get("id"))
    name = info.get("name") or info.get("login")
    email = info.get("email")
    if not email and cfg.get("emails"):
        try:
            emails = _get_json(cfg["emails"], access_token)
            primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
            email = (primary or (emails[0] if emails else {})).get("email")
        except (urllib.error.URLError, ValueError, KeyError):
            email = None
    return subject, email, name
