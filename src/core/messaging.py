"""Messaging gateways — config catalog + per-instance storage.

A registry of chat platforms Athena can run on (Telegram, Discord, Slack, …),
each described by a small schema the UI renders into a config form. This module
owns the *configuration* layer: the platform catalog, the per-instance settings
(persisted to ``~/.athena/messaging.json``), and a derived status per platform.
The live bot runtimes (long-poll / webhook loops that route messages into the
swarm) are wired on top of this in a follow-up; until then a configured gateway
reports ``ready`` rather than ``running``.

Secrets (bot tokens, API keys) are never returned to the client: GET masks them
and reports which are set; POST keeps an existing secret when its field is blank.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


def _f(key, label, hint="", required=False, recommended=False, secret=False, placeholder=""):
    return {"key": key, "label": label, "hint": hint, "required": required,
            "recommended": recommended, "secret": secret, "placeholder": placeholder or label}


# Platform catalog — drives the UI. Order = display order.
CATALOG = [
    {"id": "telegram", "label": "Telegram", "blurb": "Run Athena from Telegram DMs, groups, and topics.",
     "guide": "https://core.telegram.org/bots#how-do-i-create-a-bot", "fields": [
        _f("bot_token", "Bot token", "Create a bot with @BotFather, then paste the token it gives you.", required=True, secret=True),
        _f("allowed_ids", "Allowed user IDs", "Comma-separated numeric IDs from @userinfobot. Without this, anyone can DM your bot.", recommended=True),
        _f("home_chat_id", "Home chat ID", "Default chat for scheduled / notification delivery."),
     ]},
    {"id": "discord", "label": "Discord", "blurb": "A Discord bot for servers and DMs.",
     "guide": "https://discord.com/developers/applications", "fields": [
        _f("bot_token", "Bot token", "From the Discord Developer Portal → your app → Bot.", required=True, secret=True),
        _f("allowed_ids", "Allowed user IDs", "Comma-separated Discord user IDs allowed to use the bot.", recommended=True),
        _f("guild_id", "Server (guild) ID", "Restrict the bot to one server."),
     ]},
    {"id": "slack", "label": "Slack", "blurb": "A Slack app for channels and DMs.",
     "guide": "https://api.slack.com/apps", "fields": [
        _f("bot_token", "Bot token (xoxb-…)", "OAuth & Permissions → Bot User OAuth Token.", required=True, secret=True),
        _f("app_token", "App-level token (xapp-…)", "For Socket Mode.", secret=True),
        _f("signing_secret", "Signing secret", "Basic Information → App Credentials.", secret=True),
     ]},
    {"id": "mattermost", "label": "Mattermost", "blurb": "Self-hosted team chat.",
     "guide": "https://developers.mattermost.com/integrate/reference/bot-accounts/", "fields": [
        _f("server_url", "Server URL", "https://mattermost.example.com", required=True),
        _f("bot_token", "Bot access token", "", required=True, secret=True),
     ]},
    {"id": "matrix", "label": "Matrix", "blurb": "Open, federated chat (Element, etc.).",
     "guide": "https://matrix.org/", "fields": [
        _f("homeserver", "Homeserver", "https://matrix.org", required=True),
        _f("user_id", "Bot user ID", "@athena:matrix.org", required=True),
        _f("access_token", "Access token", "", required=True, secret=True),
     ]},
    {"id": "whatsapp", "label": "WhatsApp", "blurb": "WhatsApp Cloud API (Meta).",
     "guide": "https://developers.facebook.com/docs/whatsapp/cloud-api", "fields": [
        _f("access_token", "Access token", "From the Meta App dashboard.", required=True, secret=True),
        _f("phone_number_id", "Phone number ID", "", required=True),
        _f("verify_token", "Webhook verify token", "Any secret you choose for webhook verification.", secret=True),
     ]},
    {"id": "signal", "label": "Signal", "blurb": "Signal via signal-cli / signald.",
     "guide": "https://github.com/AsamK/signal-cli", "fields": [
        _f("service_url", "signal-cli REST URL", "http://localhost:8080", required=True),
        _f("number", "Bot phone number", "+15551234567", required=True),
     ]},
    {"id": "email", "label": "Email", "blurb": "Talk to Athena over email (IMAP in, SMTP out).",
     "guide": "", "fields": [
        _f("imap_host", "IMAP host", "imap.gmail.com", required=True),
        _f("smtp_host", "SMTP host", "smtp.gmail.com", required=True),
        _f("username", "Username", "", required=True),
        _f("password", "Password / app password", "", required=True, secret=True),
        _f("allowed_senders", "Allowed senders", "Comma-separated email addresses.", recommended=True),
     ]},
    {"id": "sms_twilio", "label": "SMS (Twilio)", "blurb": "Text Athena over SMS via Twilio.",
     "guide": "https://www.twilio.com/docs/sms", "fields": [
        _f("account_sid", "Account SID", "", required=True),
        _f("auth_token", "Auth token", "", required=True, secret=True),
        _f("from_number", "From number", "+15551234567", required=True),
     ]},
    {"id": "dingtalk", "label": "DingTalk", "blurb": "DingTalk robot for groups.",
     "guide": "https://open.dingtalk.com/", "fields": [
        _f("app_key", "App key", "", required=True),
        _f("app_secret", "App secret", "", required=True, secret=True),
     ]},
    {"id": "feishu", "label": "Feishu / Lark", "blurb": "Feishu / Lark bot.",
     "guide": "https://open.feishu.cn/", "fields": [
        _f("app_id", "App ID", "", required=True),
        _f("app_secret", "App secret", "", required=True, secret=True),
     ]},
    {"id": "wecom", "label": "WeCom", "blurb": "WeCom (Work WeChat) group bot.",
     "guide": "https://work.weixin.qq.com/", "fields": [
        _f("webhook_key", "Webhook key", "From the group bot's webhook URL.", required=True, secret=True),
     ]},
]

_BY_ID = {p["id"]: p for p in CATALOG}


class MessagingRegistry:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else None
        self._configs: dict[str, dict] = {}  # id -> {enabled, config}
        self.load()

    # -- catalog --
    @staticmethod
    def catalog() -> list:
        return CATALOG

    def _platform(self, pid: str) -> Optional[dict]:
        return _BY_ID.get(pid)

    # -- per-platform views --
    def _secret_keys(self, pid: str) -> set:
        return {f["key"] for f in _BY_ID[pid]["fields"] if f.get("secret")}

    def status(self, pid: str) -> str:
        cfg = self._configs.get(pid, {})
        if not cfg.get("enabled"):
            return "disabled"
        cur = cfg.get("config", {})
        required = [f["key"] for f in _BY_ID[pid]["fields"] if f.get("required")]
        if any(not str(cur.get(k, "")).strip() for k in required):
            return "needs_setup"
        return "ready"  # configured; live runtime arrives in a follow-up

    def public(self, pid: str) -> dict:
        cfg = self._configs.get(pid, {})
        cur = cfg.get("config", {})
        secrets = self._secret_keys(pid)
        shown = {k: v for k, v in cur.items() if k not in secrets}
        return {
            "enabled": bool(cfg.get("enabled")),
            "config": shown,
            "configured_secrets": sorted(k for k in secrets if str(cur.get(k, "")).strip()),
            "status": self.status(pid),
        }

    def all_public(self) -> dict:
        return {p["id"]: self.public(p["id"]) for p in CATALOG}

    # -- mutate --
    def set_config(self, pid: str, config: dict, enabled: bool) -> Optional[dict]:
        if pid not in _BY_ID:
            return None
        existing = self._configs.get(pid, {}).get("config", {})
        secrets = self._secret_keys(pid)
        merged = dict(existing)
        for k, v in (config or {}).items():
            if k in secrets and not str(v).strip():
                continue  # blank secret => keep the saved one (UI never re-sends it)
            merged[k] = v
        self._configs[pid] = {"enabled": bool(enabled), "config": merged}
        self.save()
        return self.public(pid)

    # -- persistence --
    def save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._configs, indent=2))
            tmp.replace(self.path)
            os.chmod(self.path, 0o600)  # holds bot tokens
        except OSError:
            pass

    def load(self) -> None:
        self._configs.clear()
        if not self.path or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(data, dict):
            self._configs = {k: v for k, v in data.items() if k in _BY_ID and isinstance(v, dict)}
