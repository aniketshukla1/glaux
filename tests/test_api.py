"""Phase 5 (backend): the FastAPI dashboard API, in offline demo mode."""

from __future__ import annotations

import pytest

pytest.importorskip("athena_ledger")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from core.api import STATE, app  # noqa: E402
from core.observability import METRICS  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_state():
    client.delete("/api/ledger")
    client.delete("/api/memory")
    STATE.eval_runs.clear()
    METRICS.reset()
    # isolate the workspace: no disk persistence, a clean session per test
    STATE.sessions.store_path = None
    STATE.sessions.projects.clear()
    STATE.sessions.sessions.clear()
    STATE.sessions.active_id = None
    STATE.sessions.ensure_active()
    # reset accounts so each test starts with an open (no-users) API; auth tests
    # create their own users and carry their own tokens
    STATE.users.users.clear()
    STATE.users._by_email.clear()
    STATE._user_stores.clear()
    STATE.messaging._configs.clear()
    client.headers.pop("Authorization", None)
    client.post("/api/safety", json={"mode": "live"})
    client.post("/api/approval", json={"mode": "auto"})
    client.post("/api/llm", json={"backend": "demo"})
    yield
    client.post("/api/safety", json={"mode": "live"})
    client.post("/api/approval", json={"mode": "auto"})
    client.post("/api/llm", json={"backend": "demo"})


def test_health_reports_demo_mode():
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert h["llm"] == "demo-offline"  # no API key in tests
    assert h["safety"] == "live"
    assert set(h["memory"]) == {"semantic", "episodic", "procedural"}


def test_dispatch_builds_a_verifiable_signed_chain():
    r = client.post("/api/task", json={"directive": "build a thing and summarize it"})
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["verification"]["valid"] is True
    # the plan and signed trace came back — a build pairs the coder with a verifier
    assert [s["role"] for s in data["plan"]] == ["coder", "tester"]
    assert len(data["new_blocks"]) > 0
    types = {b["action_type"] for b in data["new_blocks"]}
    assert {"PLAN", "CALL_AGENT", "CAPABILITY_GRANT", "THINK"} <= types

    # ledger endpoint reflects the same chain and verifies
    led = client.get("/api/ledger").json()
    assert led["count"] == len(data["new_blocks"])
    assert led["verification"]["valid"] is True


def test_task_surfaces_backend_failure_as_502(monkeypatch):
    """A failing LLM backend (e.g. Ollama can't load the model) must come back as a
    clean 502 with the real reason — not an opaque HTTP 500."""

    class _BoomSwarm:
        def run(self, *a, **k):
            raise RuntimeError("Ollama returned HTTP 500 for model 'x': boom")

    monkeypatch.setattr(STATE, "build_swarm", lambda: _BoomSwarm())
    r = client.post("/api/task", json={"directive": "say hi"})
    assert r.status_code == 502
    assert "boom" in r.json()["detail"]


def test_messaging_catalog_config_and_secret_masking():
    data = client.get("/api/messaging").json()
    assert any(p["id"] == "telegram" for p in data["platforms"])
    assert data["gateways"]["telegram"]["status"] == "disabled"
    # configure telegram (a token is required); enabling without it => needs_setup
    g = client.post("/api/messaging/telegram", json={"enabled": True, "config": {"allowed_ids": "123"}}).json()["gateway"]
    assert g["status"] == "needs_setup"
    g = client.post("/api/messaging/telegram", json={"enabled": True, "config": {"bot_token": "secret123"}}).json()["gateway"]
    assert g["status"] == "ready"
    # the secret is never returned, but is reported as configured
    assert "bot_token" not in g["config"] and "bot_token" in g["configured_secrets"]
    assert g["config"]["allowed_ids"] == "123"  # non-secret kept across saves
    # re-saving with a blank token keeps the stored one
    g = client.post("/api/messaging/telegram", json={"enabled": True, "config": {"bot_token": ""}}).json()["gateway"]
    assert "bot_token" in g["configured_secrets"]
    assert client.post("/api/messaging/nope", json={"enabled": True}).status_code == 404


def test_personas_crud_and_applied_to_session():
    a = _signup(email="persona@x.com")
    h = _auth(a["token"])
    # create a persona
    p = client.post("/api/personas", json={"name": "Pirate", "instructions": "Answer like a pirate.", "emoji": "🏴‍☠️"}, headers=h).json()["persona"]
    assert p["name"] == "Pirate"
    assert any(x["id"] == p["id"] for x in client.get("/api/workspace", headers=h).json()["personas"])
    # apply it to the active session
    sid = client.get("/api/workspace", headers=h).json()["active_id"]
    meta = client.patch(f"/api/sessions/{sid}", json={"persona_id": p["id"]}, headers=h).json()["session"]
    assert meta["persona_id"] == p["id"]
    # edit + delete
    client.patch(f"/api/personas/{p['id']}", json={"name": "Pirate", "instructions": "Arrr."}, headers=h)
    res = client.delete(f"/api/personas/{p['id']}", headers=h).json()
    assert res["ok"] and res["personas"] == []
    # deleting detaches it from the session
    assert client.get(f"/api/sessions/{sid}", headers=h).json()["session"]["persona_id"] is None


def test_comparison_task_returns_a_canvas():
    data = client.post("/api/task", json={"directive": "Compare Postgres and Mongo and recommend one"}).json()
    canvas = data["canvas"]
    assert canvas and isinstance(canvas["blocks"], list)
    assert any(b["type"] == "table" for b in canvas["blocks"])
    assert "```canvas" not in (data["final"] or "")  # the block is stripped from the prose


def test_task_reports_model_and_stop_endpoint():
    data = client.post("/api/task", json={"directive": "say hi"}).json()
    assert data["model"] == "demo-offline"  # which model produced the turn
    assert data["cancelled"] is False
    # the run remembers its model for per-turn metadata
    runs = client.get("/api/workspace").json()
    sid = runs["active_id"]
    full = client.get(f"/api/sessions/{sid}").json()["session"]
    assert full["runs"][-1]["model"] == "demo-offline"
    # stop endpoint is reachable (no task in flight here, but it must not error)
    assert client.post("/api/task/stop").json()["ok"] is True


def test_pin_and_search_conversations():
    a = _signup(email="search@x.com")
    h = _auth(a["token"])
    sid = client.post("/api/task", json={"directive": "Explain quantum tunneling"}, headers=h).json()["session_id"]
    # content/title search finds it
    res = client.get("/api/search", params={"q": "quantum"}, headers=h).json()["results"]
    assert any(r["id"] == sid for r in res)
    assert client.get("/api/search", params={"q": "zzznomatch"}, headers=h).json()["results"] == []
    # pin it, and it sorts to the top of the tree
    pinned = client.post(f"/api/sessions/{sid}/pin", json={"pinned": True}, headers=h).json()["session"]
    assert pinned["pinned"] is True
    assert client.get("/api/workspace", headers=h).json()["sessions"][0]["pinned"] is True
    # unpin
    assert client.post(f"/api/sessions/{sid}/pin", json={"pinned": False}, headers=h).json()["session"]["pinned"] is False


def test_block_detail_and_404():
    client.post("/api/task", json={"directive": "do something"})
    b0 = client.get("/api/block/0").json()
    assert "signature" in b0 and "payload" in b0
    assert client.get("/api/block/99999").status_code == 404


def test_empty_directive_rejected():
    assert client.post("/api/task", json={"directive": "   "}).status_code == 400


# --- roster --------------------------------------------------------------


def test_agents_roster_exposes_identities():
    data = client.get("/api/agents").json()
    roles = {a["role"] for a in data["agents"]}
    # router + reflector + the full specialist roster
    assert {"router", "reflector", "coder", "researcher"} <= roles
    assert {"web", "scientist", "analyst", "engineer", "tester", "writer"} <= roles
    for a in data["agents"]:
        # agent_id is base58(public key) — they match for a non-rotated identity
        assert a["agent_id"] == a["public_key"]
        assert a["namespace"] == "default"


# --- accounts / auth -----------------------------------------------------


def _signup(email="ada@example.com", password="password123", name="Ada"):
    r = client.post("/api/auth/signup", json={"email": email, "password": password, "name": name})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_auth_state_starts_open_then_signup_locks_it():
    state = client.get("/api/auth/state").json()
    assert state["has_users"] is False and state["authenticated"] is False and state["user"] is None
    assert "oauth" in state and "signup" in state  # login options for the client
    # open before any account exists: a protected route works without a token
    assert client.get("/api/agents").status_code == 200

    out = _signup()
    assert out["token"] and out["user"]["email"] == "ada@example.com"
    assert "password" not in str(out["user"]) and "hash" not in str(out["user"])

    # now that an account exists, the same route needs a token
    assert client.get("/api/agents").status_code == 401
    assert client.get("/api/agents", headers=_auth(out["token"])).status_code == 200
    assert client.get("/api/auth/state").json()["has_users"] is True


def test_login_and_me():
    _signup(email="b@b.com", password="password123", name="Bee")
    assert client.post("/api/auth/login", json={"email": "b@b.com", "password": "nope"}).status_code == 401
    out = client.post("/api/auth/login", json={"email": "b@b.com", "password": "password123"}).json()
    me = client.get("/api/auth/me", headers=_auth(out["token"])).json()
    assert me["user"]["name"] == "Bee"


def test_signup_validation_and_duplicates():
    assert client.post("/api/auth/signup", json={"email": "bad", "password": "password123"}).status_code == 400
    assert client.post("/api/auth/signup", json={"email": "a@b.com", "password": "short"}).status_code == 400
    _signup(email="dup@b.com")
    assert client.post("/api/auth/signup", json={"email": "dup@b.com", "password": "password123"}).status_code == 400


def test_workspaces_are_isolated_per_user():
    a = _signup(email="a@x.com")
    b = _signup(email="b@x.com")
    client.post("/api/projects", json={"name": "A-only project"}, headers=_auth(a["token"]))
    a_names = [p["name"] for p in client.get("/api/workspace", headers=_auth(a["token"])).json()["projects"]]
    b_names = [p["name"] for p in client.get("/api/workspace", headers=_auth(b["token"])).json()["projects"]]
    assert "A-only project" in a_names
    assert "A-only project" not in b_names  # B can't see A's workspace


def test_update_profile_and_preferences():
    out = _signup(email="p@x.com")
    h = _auth(out["token"])
    client.patch("/api/auth/me", json={"name": "Ada L.", "settings": {"theme": "oled"}}, headers=h)
    client.patch("/api/auth/me", json={"settings": {"default_model": "qwen"}}, headers=h)
    me = client.get("/api/auth/me", headers=h).json()["user"]
    assert me["name"] == "Ada L."
    assert me["settings"] == {"theme": "oled", "default_model": "qwen"}  # merged


def test_change_password_rotates_token():
    out = _signup(email="pw@x.com")
    old = out["token"]
    r = client.post("/api/auth/password", json={"current": "password123", "new": "newpassword1"}, headers=_auth(old))
    assert r.status_code == 200
    new = r.json()["token"]
    assert client.get("/api/auth/me", headers=_auth(old)).status_code == 401   # old token invalidated
    assert client.get("/api/auth/me", headers=_auth(new)).status_code == 200   # fresh token works


def test_logout_everywhere_and_delete_account():
    out = _signup(email="z@x.com")
    h = _auth(out["token"])
    assert client.post("/api/auth/logout", headers=h).json()["ok"] is True
    assert client.get("/api/auth/me", headers=h).status_code == 401  # token revoked
    # log back in, then delete the account
    tok = client.post("/api/auth/login", json={"email": "z@x.com", "password": "password123"}).json()["token"]
    assert client.delete("/api/auth/me", headers=_auth(tok)).json()["ok"] is True
    assert client.post("/api/auth/login", json={"email": "z@x.com", "password": "password123"}).status_code == 401


def _token_from_link(link, key):
    from urllib.parse import urlparse, parse_qs
    return parse_qs(urlparse(link).query)[key][0]


def test_email_verification_flow():
    _signup(email="admin@x.com")                       # first user: auto-verified admin
    out = _signup(email="member@x.com", name="Mem")    # second user: must verify
    assert out["user"]["email_verified"] is False
    assert out["dev_link"]                              # link surfaced in dev mode
    token = _token_from_link(out["dev_link"], "verify")
    res = client.post("/api/auth/verify", json={"token": token}).json()
    assert res["ok"] and res["user"]["email_verified"] is True
    assert client.post("/api/auth/verify", json={"token": "bad"}).status_code == 400


def test_password_reset_flow():
    _signup(email="r@x.com", password="password123")
    # forgot always returns ok, even for an unknown email
    assert client.post("/api/auth/forgot", json={"email": "nobody@x.com"}).json()["ok"] is True
    out = client.post("/api/auth/forgot", json={"email": "r@x.com"}).json()
    token = _token_from_link(out["dev_link"], "reset")
    reset = client.post("/api/auth/reset", json={"token": token, "password": "freshpass123"}).json()
    assert reset["token"]  # signed straight in
    assert client.post("/api/auth/login", json={"email": "r@x.com", "password": "freshpass123"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "r@x.com", "password": "password123"}).status_code == 401


def test_oauth_providers_hidden_when_unconfigured():
    state = client.get("/api/auth/state").json()
    assert state["oauth"] == []  # no client creds in the env => no buttons
    assert client.get("/api/auth/oauth/google/start").status_code == 404


def test_signup_policy_invite_only(monkeypatch):
    monkeypatch.setenv("ATHENA_SIGNUP", "invite")
    a = _signup(email="admin@x.com")  # bootstrap is always allowed
    # a second open signup is now blocked …
    assert client.post("/api/auth/signup", json={"email": "x@x.com", "password": "password123"}).status_code == 403
    # … unless it carries a valid invite from an admin
    invite = client.post("/api/admin/invites", headers=_auth(a["token"])).json()["link"]
    tok = _token_from_link(invite, "invite")
    assert client.post("/api/auth/signup", json={"email": "x@x.com", "password": "password123", "invite": tok}).status_code == 200


def test_admin_user_management_and_guards():
    admin = _signup(email="admin@x.com")
    member = _signup(email="member@x.com")
    ah = _auth(admin["token"])
    member_id = member["user"]["id"]

    listing = client.get("/api/admin/users", headers=ah).json()["users"]
    assert len(listing) == 2 and any(u["is_admin"] for u in listing)
    # a non-admin can't reach the admin API
    assert client.get("/api/admin/users", headers=_auth(member["token"])).status_code == 403

    # promote, then deactivate the member
    assert client.patch(f"/api/admin/users/{member_id}", json={"is_admin": True}, headers=ah).json()["user"]["is_admin"]
    client.patch(f"/api/admin/users/{member_id}", json={"is_admin": False}, headers=ah)
    client.patch(f"/api/admin/users/{member_id}", json={"is_active": False}, headers=ah)
    # a deactivated user's token is rejected
    assert client.get("/api/auth/me", headers=_auth(member["token"])).status_code == 401

    # guards: can't drop the last admin or delete yourself via the admin route
    assert client.patch(f"/api/admin/users/{admin['user']['id']}", json={"is_admin": False}, headers=ah).status_code == 400
    assert client.delete(f"/api/admin/users/{admin['user']['id']}", headers=ah).status_code == 400
    assert client.delete(f"/api/admin/users/{member_id}", headers=ah).json()["ok"] is True


# --- safety / kill switch ------------------------------------------------


def test_safety_get_and_set():
    assert client.get("/api/safety").json()["mode"] == "live"
    assert client.post("/api/safety", json={"mode": "halted"}).json()["mode"] == "halted"
    assert client.get("/api/safety").json()["mode"] == "halted"


def test_invalid_safety_mode_rejected():
    assert client.post("/api/safety", json={"mode": "banana"}).status_code == 400


def test_halted_dispatch_short_circuits_specialists():
    # baseline: a live dispatch produces specialist THINK blocks
    live = client.post("/api/task", json={"directive": "do real work"}).json()
    assert any(b["action_type"] == "THINK" for b in live["new_blocks"])

    client.delete("/api/ledger")
    client.post("/api/safety", json={"mode": "halted"})
    halted = client.post("/api/task", json={"directive": "do work while halted"}).json()
    # specialists short-circuit -> zero THINK blocks; the chain still verifies
    assert halted["verification"]["valid"] is True
    assert not any(b["action_type"] == "THINK" for b in halted["new_blocks"])


# --- memory --------------------------------------------------------------


def test_memory_add_list_search():
    add = client.post(
        "/api/memory/semantic", json={"text": "Athena signs every action with Ed25519"}
    ).json()
    assert add["count"] == 1

    listing = client.get("/api/memory/semantic").json()
    assert listing["layer"] == "semantic"
    assert any("Ed25519" in it["text"] for it in listing["items"])

    found = client.get("/api/memory/semantic", params={"q": "what signs actions"}).json()
    assert found["items"] and "Ed25519" in found["items"][0]["text"]


def test_memory_layers_are_isolated():
    client.post("/api/memory/semantic", json={"text": "a semantic fact about gravity"})
    client.post("/api/memory/episodic", json={"text": "deployed the service yesterday"})
    assert len(client.get("/api/memory/semantic").json()["items"]) == 1
    assert len(client.get("/api/memory/episodic").json()["items"]) == 1
    assert client.get("/api/memory/procedural").json()["items"] == []


def test_unknown_memory_layer_404():
    assert client.get("/api/memory/nonsense").status_code == 404


# --- cost / budget guard -------------------------------------------------


def test_dispatch_reports_cost():
    data = client.post("/api/task", json={"directive": "do a thing"}).json()
    assert data["cost"]["llm_calls"] > 0
    assert data["cost"]["total_tokens"] > 0
    assert data["budget_halt"] is None


def test_tight_budget_halts_dispatch():
    data = client.post(
        "/api/task",
        json={"directive": "do a multi-step thing", "budget": {"max_llm_calls": 1}},
    ).json()
    # router consumes the 1 allowed call; specialists are never dispatched
    assert data["budget_halt"] is not None
    assert data["cost"]["llm_calls"] == 1
    assert not any(s["accepted"] for s in data["steps"])


# --- skills (synthesis + curation) ---------------------------------------


def test_synthesize_stores_quarantined_skill():
    r = client.post("/api/skills/synthesize", json={"task": "reverse a string"}).json()
    assert r["ok"] is True
    assert r["stored"]["status"] == "quarantined"
    assert r["stored"]["name"] == "reverse_string"
    # it shows up in the library listing
    skills = client.get("/api/skills").json()["skills"]
    assert any(s["name"] == "reverse_string" for s in skills)


def test_skill_promotes_after_uses():
    synth = client.post("/api/skills/synthesize", json={"task": "reverse"}).json()
    sid = synth["stored"]["id"]
    last = None
    for _ in range(3):
        last = client.post(f"/api/skills/{sid}/use", json={"success": True}).json()
    assert last["status"] == "promoted"
    assert last["success_rate"] == 1.0


def test_use_unknown_skill_404():
    assert client.post("/api/skills/nope/use", json={"success": True}).status_code == 404


# --- eval harness --------------------------------------------------------


def test_eval_run_and_lift_from_synthesized_skill():
    # baseline: reverse_* cases fail (no skill), inline baselines pass
    base = client.post("/api/eval/run").json()
    base_passed = base["run"]["passed"]
    assert base["run"]["total"] >= 4
    assert any(not c["passed"] for c in base["run"]["cases"])  # reverse_* missing

    # synthesize the reverse_string skill, then re-run -> lift
    client.post("/api/skills/synthesize", json={"task": "reverse a string"})
    after = client.post("/api/eval/run").json()
    assert after["run"]["passed"] > base_passed
    assert after["lift"]["delta_pass_rate"] > 0
    assert "reverse_basic" in after["lift"]["newly_passing"]

    # run history is tracked
    runs = client.get("/api/eval/runs").json()["runs"]
    assert len(runs) >= 2


# --- autonomous synthesis + HITL gate ------------------------------------


def test_dispatch_autonomously_synthesizes_a_skill():
    data = client.post("/api/task", json={"directive": "build a function that reverses a string"}).json()
    assert data["synthesized"]  # reflector recommended a skill, swarm synthesized it
    assert any(s["ok"] for s in data["synthesized"])
    # in auto mode the non-sensitive skill is usable (quarantined), in the library
    skills = client.get("/api/skills").json()["skills"]
    assert any(s["name"] == "reverse_string" for s in skills)


def test_gated_mode_requires_approval_then_approve():
    client.post("/api/approval", json={"mode": "gated"})
    assert client.get("/api/approval").json()["mode"] == "gated"

    client.post("/api/task", json={"directive": "build a function that reverses a string"})
    pending = [s for s in client.get("/api/skills").json()["skills"] if s["status"] == "pending_approval"]
    assert pending  # held for approval

    approved = client.post(f"/api/skills/{pending[0]['id']}/approve").json()
    assert approved["status"] == "quarantined"


def test_invalid_approval_mode_rejected():
    assert client.post("/api/approval", json={"mode": "bogus"}).status_code == 400


def test_approve_nonexistent_skill_404():
    assert client.post("/api/skills/nope/approve").status_code == 404


# --- observability -------------------------------------------------------


def test_metrics_update_after_dispatch_and_eval():
    client.post("/api/task", json={"directive": "build a function that reverses a string"})
    client.post("/api/eval/run")
    m = client.get("/api/metrics").json()
    assert m["tasks_total"] >= 1
    assert m["tasks_success"] >= 1
    assert m["llm_calls"] > 0
    assert m["tokens_total"] > 0
    assert m["eval_runs"] == 1
    assert m["skills_synthesized"] >= 1  # autonomous synthesis happened


def test_prometheus_endpoint():
    client.post("/api/task", json={"directive": "do something"})
    text = client.get("/metrics").text
    assert "swarm_tasks_total" in text
    assert "llm_tokens_total" in text


# --- MCP tools -----------------------------------------------------------


def test_mcp_list_and_call():
    tools = client.get("/api/mcp/tools").json()["tools"]
    names = {t["name"] for t in tools}
    assert {"calc", "word_count", "uppercase"} <= names

    res = client.post("/api/mcp/call", json={"tool": "calc", "args": {"expression": "10 / 2"}}).json()
    assert res["ok"] is True and res["result"] == 5.0

    bad = client.post("/api/mcp/call", json={"tool": "nope", "args": {}}).json()
    assert bad["ok"] is False


def test_mcp_server_add_list_call_remove(tmp_path):
    import pathlib
    import sys

    fake = pathlib.Path(__file__).parent / "fixtures" / "fake_mcp_server.py"
    # keep persistence off the user's real ~/.athena during the test
    original = STATE.mcp.config_path
    STATE.mcp.config_path = tmp_path / "mcp.json"
    try:
        r = client.post(
            "/api/mcp/servers",
            json={"name": "fake", "transport": "stdio", "command": sys.executable, "args": [str(fake)]},
        )
        assert r.status_code == 200
        server = r.json()["server"]
        assert server["status"] == "connected" and server["tool_count"] >= 2

        # the server's tools now show up in the aggregated tool list...
        names = {t["name"] for t in client.get("/api/mcp/tools").json()["tools"]}
        assert {"calc", "echo", "add"} <= names  # builtin + connected server

        # ...and are callable through the same endpoint
        res = client.post("/api/mcp/call", json={"tool": "add", "args": {"a": 4, "b": 5}}).json()
        assert res["ok"] is True and res["result"] == "9"

        assert "fake" in {s["name"] for s in client.get("/api/mcp/servers").json()["servers"]}

        client.delete("/api/mcp/servers/fake")
        assert client.get("/api/mcp/servers").json()["servers"] == []
        assert "echo" not in {t["name"] for t in client.get("/api/mcp/tools").json()["tools"]}
    finally:
        STATE.mcp.remove_server("fake", persist=False)
        STATE.mcp.config_path = original


# --- LLM backend selection -----------------------------------------------


def test_llm_status_defaults_to_demo():
    data = client.get("/api/llm").json()
    assert data["backend"] == "demo"  # no key in tests
    assert "ollama" in data and "reachable" in data["ollama"]
    assert set(data["native"]) == {"demo", "ollama", "anthropic"}
    # the full OpenAI-compatible provider catalog is surfaced to the UI
    ids = {p["id"] for p in data["providers"]}
    assert {"openai", "openrouter", "deepseek", "sarvam", "groq", "gemini"} <= ids
    # key values are never exposed — only presence
    assert all("key_present" in p and "api_key" not in p for p in data["providers"])


def test_switch_to_demo_ok():
    assert client.post("/api/llm", json={"backend": "demo"}).json()["backend"] == "demo"


def test_provider_requires_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    r = client.post("/api/llm", json={"backend": "deepseek"})
    assert r.status_code == 400 and "DEEPSEEK_API_KEY" in r.json()["detail"]


def test_provider_with_explicit_key_switches():
    r = client.post("/api/llm", json={"backend": "openai", "model": "gpt-4o", "api_key": "sk-test"})
    assert r.status_code == 200
    assert r.json()["model_id"] == "openai:gpt-4o"
    # the key is held in memory but never echoed back anywhere
    assert "api_key" not in r.json()
    assert client.get("/api/llm").json()["backend"] == "openai"


def test_custom_provider_requires_base_url():
    assert client.post("/api/llm", json={"backend": "custom", "model": "m"}).status_code == 400
    r = client.post(
        "/api/llm",
        json={"backend": "custom", "model": "m", "base_url": "https://my.host/v1", "api_key": "k"},
    )
    assert r.status_code == 200 and r.json()["model_id"] == "custom:m"


def test_local_provider_needs_no_key():
    r = client.post("/api/llm", json={"backend": "lmstudio", "model": "local-model"})
    assert r.status_code == 200 and r.json()["backend"] == "lmstudio"


# --- local model files ---------------------------------------------------


def test_local_model_plan_detects_gguf(tmp_path):
    gguf = tmp_path / "tiny.gguf"
    gguf.write_bytes(b"\x00")
    plan = client.post("/api/llm/local/plan", json={"path": str(gguf)}).json()
    assert plan["format"] == "gguf" and plan["path"] == str(gguf)


def test_local_model_missing_path_400():
    r = client.post("/api/llm/local", json={"path": "/no/such/model.gguf"})
    assert r.status_code == 400 and "not found" in r.json()["detail"]


def test_local_model_load_serves_and_unloads(tmp_path, monkeypatch):
    import pathlib
    import sys

    fixture = pathlib.Path(__file__).parent / "fixtures" / "fake_openai_server.py"

    def fake_plan(path):
        return {
            "format": "gguf", "runtime": "stub", "available": True, "model": path.stem,
            "cmd": lambda port: [sys.executable, str(fixture), "--port", str(port)],
        }

    monkeypatch.setattr("llm.localmodel.plan_runtime", fake_plan)
    gguf = tmp_path / "mymodel.gguf"
    gguf.write_bytes(b"\x00")
    try:
        r = client.post("/api/llm/local", json={"path": str(gguf)})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["backend"] == "localmodel"
        assert body["model_id"] == "local:mymodel"
        assert body["local_model"]["running"] is True
        # health + status reflect the running local model
        assert client.get("/api/health").json()["backend"] == "localmodel"
        assert client.get("/api/llm").json()["local_model"]["running"] is True
        # unload switches back to demo and stops the server
        assert client.delete("/api/llm/local").json()["backend"] == "demo"
        assert client.get("/api/llm").json()["local_model"]["running"] is False
    finally:
        STATE.local_model.stop()


# --- scheduled jobs ------------------------------------------------------


def test_schedule_add_list_run_remove(tmp_path):
    # keep persistence off the user's real ~/.athena during the test
    original = STATE.scheduler.store_path
    STATE.scheduler.store_path = tmp_path / "sched.json"
    STATE.scheduler.jobs.clear()
    try:
        r = client.post("/api/schedules", json={"directive": "summarize the day", "schedule": "@daily"})
        assert r.status_code == 200
        job = r.json()["job"]
        assert job["next_run"] and job["schedule"] == "@daily"

        listed = client.get("/api/schedules").json()["jobs"]
        assert any(j["id"] == job["id"] for j in listed)

        # run it now → goes through the demo swarm and signs blocks onto the ledger
        before = client.get("/api/health").json()["blocks"]
        run = client.post(f"/api/schedules/{job['id']}/run").json()["job"]
        assert run["last_status"] == "ok" and run["run_count"] == 1
        assert client.get("/api/health").json()["blocks"] > before

        client.post(f"/api/schedules/{job['id']}/enable", json={"enabled": False})
        assert client.get("/api/schedules").json()["jobs"][0]["enabled"] is False

        assert client.delete(f"/api/schedules/{job['id']}").status_code == 200
        assert client.get("/api/schedules").json()["jobs"] == []
    finally:
        STATE.scheduler.jobs.clear()
        STATE.scheduler.store_path = original


def test_schedule_rejects_bad_cron():
    assert client.post("/api/schedules", json={"directive": "x", "schedule": "not a cron"}).status_code == 400


def test_schedule_run_unknown_404():
    assert client.post("/api/schedules/nope/run").status_code == 404


# --- workspace: projects + sessions --------------------------------------


def test_workspace_has_an_active_session():
    w = client.get("/api/workspace").json()
    assert w["active_id"] and any(s["id"] == w["active_id"] for s in w["sessions"])


def test_task_records_into_active_session():
    active = client.get("/api/workspace").json()["active_id"]
    r = client.post("/api/task", json={"directive": "Compute the sum of 2 and 3"}).json()
    assert r["session_id"] == active
    sess = client.get(f"/api/sessions/{active}").json()["session"]
    assert sess["run_count"] == 1
    run = sess["runs"][0]
    assert run["directive"] == "Compute the sum of 2 and 3"
    assert run["blocks"] and run["verification"]["valid"] is True  # signed blocks captured
    # the session auto-titled from the first directive
    assert sess["title"].startswith("Compute the sum")


def test_create_activate_rename_delete_session():
    created = client.post("/api/sessions", json={"title": "scratch"}).json()
    sid = created["session"]["id"]
    assert created["active_id"] == sid

    assert client.patch(f"/api/sessions/{sid}", json={"title": "renamed"}).json()["session"]["title"] == "renamed"
    assert client.post(f"/api/sessions/{sid}/activate").json()["active_id"] == sid

    deleted = client.delete(f"/api/sessions/{sid}")
    assert deleted.status_code == 200
    assert all(s["id"] != sid for s in deleted.json()["sessions"])
    assert client.post("/api/sessions/ghost/activate").status_code == 404


def test_projects_create_group_delete():
    proj = client.post("/api/projects", json={"name": "Research", "instructions": "be rigorous"}).json()["project"]
    sess = client.post("/api/sessions", json={"title": "lit review", "project_id": proj["id"]}).json()["session"]
    assert sess["project_id"] == proj["id"]
    w = client.get("/api/workspace").json()
    assert any(p["id"] == proj["id"] for p in w["projects"])
    # deleting the project ungroups but keeps the session
    client.delete(f"/api/projects/{proj['id']}")
    after = client.get(f"/api/sessions/{sess['id']}").json()["session"]
    assert after["project_id"] is None


def test_project_instructions_shape_the_run():
    proj = client.post("/api/projects", json={"name": "Math", "instructions": "always answer in French"}).json()["project"]
    sess = client.post("/api/sessions", json={"title": "calc", "project_id": proj["id"]}).json()["session"]
    r = client.post("/api/task", json={"directive": "add 2 and 2", "session_id": sess["id"]}).json()
    # the recorded directive stays clean (no instructions leaked into history)
    run = client.get(f"/api/sessions/{sess['id']}").json()["session"]["runs"][0]
    assert run["directive"] == "add 2 and 2"
    # but the project instructions were prepended as context for the actual run
    assert "Project instructions:" in r["final"]
    # a session with no project runs the directive unchanged
    plain_sess = client.post("/api/sessions", json={"title": "plain"}).json()["session"]
    plain = client.post("/api/task", json={"directive": "add 9 and 1", "session_id": plain_sess["id"]}).json()
    assert "Project instructions:" not in plain["final"]


# --- served dashboard (single URL) ---------------------------------------


def test_serves_dashboard_when_built():
    """When frontend/dist exists, the backend serves the UI at / on the same
    origin — so `athena up` is one URL. API routes keep precedence."""
    from core.api import _frontend_dist

    if not _frontend_dist().is_dir():
        pytest.skip("frontend not built (no frontend/dist)")
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers.get("content-type", "")
    # the catch-all static mount must not shadow the API
    assert client.get("/api/health").json()["status"] == "ok"


def test_switch_to_ollama_respects_reachability():
    status = client.get("/api/llm").json()["ollama"]
    model = status["models"][0] if status["models"] else "llama3.2"
    r = client.post("/api/llm", json={"backend": "ollama", "model": model})
    if status["reachable"]:
        assert r.status_code == 200
        assert r.json()["backend"] == "ollama"
    else:
        assert r.status_code == 400
        assert "not reachable" in r.json()["detail"].lower()


def test_unknown_backend_rejected():
    assert client.post("/api/llm", json={"backend": "gpt5"}).status_code == 400
