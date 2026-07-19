"""The `athena` CLI — arg parsing, pid/daemon helpers, result formatting."""

from __future__ import annotations

import os

import pytest

import cli


def test_parser_run_collects_directive():
    args = cli.build_parser().parse_args(["run", "summarize", "the", "news"])
    assert args.command == "run" and args.directive == ["summarize", "the", "news"]
    assert args.func is cli.cmd_run


def test_parser_up_flags():
    args = cli.build_parser().parse_args(["--port", "9001", "up", "--foreground", "--open"])
    assert args.command == "up" and args.port == 9001 and args.foreground and args.open
    assert args.func is cli.cmd_up


def test_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_parser_desktop():
    args = cli.build_parser().parse_args(["desktop", "--build"])
    assert args.command == "desktop" and args.build is True and args.func is cli.cmd_desktop
    assert cli.build_parser().parse_args(["desktop"]).build is False


def test_parser_restart_and_rebuild():
    p = cli.build_parser()
    assert p.parse_args(["restart"]).func is cli.cmd_restart
    rb = p.parse_args(["rebuild", "--no-build", "--open"])
    assert rb.func is cli.cmd_rebuild and rb.no_build is True and rb.open is True
    assert p.parse_args(["rebuild"]).no_build is False


def test_restart_waits_for_port_then_starts(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_stop_daemon", lambda: calls.append("stop") or 123)
    monkeypatch.setattr(cli, "_wait_port_free", lambda h, p, **k: calls.append("wait") or True)
    monkeypatch.setattr(cli, "_start_daemon", lambda h, p, **k: calls.append("start") or 0)
    rc = cli.cmd_restart(cli.build_parser().parse_args(["restart"]))
    assert rc == 0 and calls == ["stop", "wait", "start"]


def test_restart_aborts_if_port_stuck(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_stop_daemon", lambda: 1)
    monkeypatch.setattr(cli, "_wait_port_free", lambda h, p, **k: False)
    started = []
    monkeypatch.setattr(cli, "_start_daemon", lambda *a, **k: started.append(1) or 0)
    rc = cli.cmd_restart(cli.build_parser().parse_args(["restart"]))
    assert rc == 1 and not started  # never tries to start onto a busy port
    assert "still in use" in capsys.readouterr().err.lower()


def test_rebuild_skips_start_when_build_fails(monkeypatch):
    monkeypatch.setattr(cli, "_build_frontend", lambda: 1)
    restarted = []
    monkeypatch.setattr(cli, "cmd_restart", lambda a: restarted.append(1) or 0)
    rc = cli.cmd_rebuild(cli.build_parser().parse_args(["rebuild"]))
    assert rc == 1 and not restarted  # a failed build must not bounce the server


def test_parser_new_commands():
    p = cli.build_parser()
    assert p.parse_args(["chat"]).func is cli.cmd_chat
    assert p.parse_args(["login", "--email", "a@b.com"]).email == "a@b.com"
    assert p.parse_args(["logout"]).func is cli.cmd_logout
    assert p.parse_args(["whoami"]).func is cli.cmd_whoami
    m = p.parse_args(["messaging", "enable", "telegram", "--set", "bot_token=x", "--set", "allowed_ids=1"])
    assert m.action == "enable" and m.platform == "telegram" and m.set == ["bot_token=x", "allowed_ids=1"]
    assert p.parse_args(["messaging"]).action == "list"
    assert p.parse_args(["run", "--json", "do", "it"]).json is True


def test_parser_config_commands():
    p = cli.build_parser()
    assert p.parse_args(["safety", "halted"]).func is cli.cmd_safety
    assert p.parse_args(["approval", "gated"]).mode == "gated"
    assert p.parse_args(["workspace", "on"]).action == "on"
    assert p.parse_args(["playbooks"]).action == "list"
    assert p.parse_args(["playbooks", "add", "X", "--body", "b"]).body == "b"
    sa = p.parse_args(["subagents", "add", "Legal", "--prompt", "p", "--iters", "6"])
    assert sa.action == "add" and sa.prompt == "p" and sa.iters == 6
    assert p.parse_args(["evolution", "revert"]).action == "revert"
    assert p.parse_args(["evolve"]).func is not None
    assert p.parse_args(["skills", "synth", "x"]).action == "synth"
    assert p.parse_args(["personas"]).func is cli.cmd_personas


def _record_api(monkeypatch, response=None):
    calls = []

    def fake(base, method, path, payload=None):
        calls.append((method, path, payload))
        return {} if response is None else response

    monkeypatch.setattr(cli, "_api", fake)
    return calls


def test_safety_set_maps_dashes(monkeypatch):
    calls = _record_api(monkeypatch, {"mode": "dry_run"})
    assert cli.cmd_safety(cli.build_parser().parse_args(["safety", "dry-run"])) == 0
    assert calls == [("POST", "/api/safety", {"mode": "dry_run"})]


def test_workspace_toggle(monkeypatch):
    calls = _record_api(monkeypatch, {"enabled": True, "root": "/w"})
    cli.cmd_workspace(cli.build_parser().parse_args(["workspace", "on"]))
    assert calls == [("POST", "/api/fs", {"enabled": True})]


def test_playbook_add_and_rm(monkeypatch):
    calls = _record_api(monkeypatch, {"slug": "deploy"})
    cli.cmd_playbooks(cli.build_parser().parse_args(["playbooks", "add", "Deploy", "--desc", "d", "--body", "steps"]))
    assert calls[0] == ("POST", "/api/playbooks", {"name": "Deploy", "description": "d", "body": "steps"})
    calls2 = _record_api(monkeypatch, {"deleted": True})
    cli.cmd_playbooks(cli.build_parser().parse_args(["playbooks", "rm", "deploy"]))
    assert calls2 == [("DELETE", "/api/playbooks/deploy", None)]


def test_subagent_add(monkeypatch):
    calls = _record_api(monkeypatch, {"slug": "legal"})
    cli.cmd_subagents(cli.build_parser().parse_args(
        ["subagents", "add", "Legal", "--prompt", "you are legal", "--iters", "6"]))
    assert calls == [("POST", "/api/subagents",
                      {"name": "Legal", "description": "", "prompt": "you are legal", "iterations": 6})]


def test_evolution_evolve_summarizes(monkeypatch, capsys):
    _record_api(monkeypatch, {"routing": {"applied": True}, "skills": {"applied": True}, "budgets": {"applied": False}})
    cli.cmd_evolution(cli.build_parser().parse_args(["evolution", "evolve"]))
    out = capsys.readouterr().out
    assert "routing" in out and "skills" in out and "budgets" not in out


def test_evolution_auto_and_alias(monkeypatch):
    calls = _record_api(monkeypatch, {"enabled": True, "every": 20})
    cli.cmd_evolution(cli.build_parser().parse_args(["evolution", "auto", "on", "--every", "20"]))
    assert calls == [("POST", "/api/evolution/auto", {"enabled": True, "every": 20})]
    calls2 = _record_api(monkeypatch, {"routing": {"applied": False}})
    args = cli.build_parser().parse_args(["evolve"])
    args.func(args)
    assert calls2[0][:2] == ("POST", "/api/evolution/evolve")


def test_skills_synth_and_approve(monkeypatch):
    calls = _record_api(monkeypatch, {"ok": True, "stored": {"name": "reverse_string", "status": "quarantined"}})
    cli.cmd_skills(cli.build_parser().parse_args(["skills", "synth", "reverse", "a", "string"]))
    assert calls == [("POST", "/api/skills/synthesize", {"task": "reverse a string"})]
    calls2 = _record_api(monkeypatch, {"name": "x", "status": "quarantined"})
    cli.cmd_skills(cli.build_parser().parse_args(["skills", "approve", "abc"]))
    assert calls2 == [("POST", "/api/skills/abc/approve", None)]


def test_parser_authoring_commands():
    p = cli.build_parser()
    pa = p.parse_args(["personas", "add", "Coach", "--prompt", "x", "--emoji", "🏅"])
    assert pa.action == "add" and pa.name == "Coach" and pa.prompt == "x" and pa.emoji == "🏅"
    rc = p.parse_args(["recipes", "add", "Standup", "--prompt", "x", "--desc", "d"])
    assert rc.action == "add" and rc.desc == "d"
    assert p.parse_args(["personas"]).action == "list"
    assert p.parse_args(["recipes", "rm", "id1"]).name == "id1"


def test_persona_add_and_rm(monkeypatch):
    calls = _record_api(monkeypatch, {"persona": {"id": "p1", "name": "Coach"}})
    cli.cmd_personas(cli.build_parser().parse_args(["personas", "add", "Coach", "--prompt", "be encouraging", "--emoji", "🏅"]))
    assert calls == [("POST", "/api/personas", {"name": "Coach", "instructions": "be encouraging", "emoji": "🏅"})]
    calls2 = _record_api(monkeypatch, {"ok": True})
    cli.cmd_personas(cli.build_parser().parse_args(["personas", "rm", "p1"]))
    assert calls2 == [("DELETE", "/api/personas/p1", None)]


def test_recipe_add_and_rm(monkeypatch):
    calls = _record_api(monkeypatch, {"recipe": {"id": "r1", "name": "Standup"}})
    cli.cmd_recipes(cli.build_parser().parse_args(["recipes", "add", "Standup", "--prompt", "summarize my day", "--desc", "daily"]))
    assert calls == [("POST", "/api/recipes",
                      {"name": "Standup", "prompt": "summarize my day", "description": "daily", "emoji": None})]
    calls2 = _record_api(monkeypatch, {"ok": True})
    cli.cmd_recipes(cli.build_parser().parse_args(["recipes", "rm", "r1"]))
    assert calls2 == [("DELETE", "/api/recipes/r1", None)]


def test_api_delete_routes_through_req_json(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "_req_json", lambda m, u, p=None, **k: seen.update(method=m, url=u, payload=p) or {"ok": True})
    monkeypatch.setattr(cli, "_get_json", lambda u, **k: {"should_not": "be_called"})
    out = cli._api("http://x", "DELETE", "/api/playbooks/foo")
    assert out == {"ok": True}
    assert seen["method"] == "DELETE" and seen["url"].endswith("/api/playbooks/foo") and seen["payload"] is None


def test_token_roundtrip_and_auth_header(tmp_path, monkeypatch):
    monkeypatch.setenv("ATHENA_HOME", str(tmp_path))
    assert cli.read_token() is None and cli._auth_headers() == {}
    cli.write_token("tok123")
    assert cli.read_token() == "tok123"
    assert cli._auth_headers() == {"Authorization": "Bearer tok123"}
    cli.write_token(None)
    assert cli.read_token() is None


def test_pid_roundtrip_and_liveness(tmp_path, monkeypatch):
    monkeypatch.setenv("ATHENA_HOME", str(tmp_path))
    assert cli.read_pid() is None
    cli.write_pid(os.getpid())
    assert cli.read_pid() == os.getpid()
    assert cli.process_alive(os.getpid()) is True
    assert cli.process_alive(2_000_000_000) is False  # almost certainly no such pid
    assert cli.process_alive(None) is False


def test_uvicorn_cmd_targets_the_app():
    cmd = cli._uvicorn_cmd("127.0.0.1", 8000)
    assert "uvicorn" in cmd and "core.api:app" in cmd and "8000" in cmd


def test_env_with_src_has_src_on_pythonpath():
    env = cli._env_with_src()
    assert str(cli.SRC_DIR) in env["PYTHONPATH"]


def test_format_run_result_success():
    out = cli._format_run_result({
        "success": True,
        "final": "the answer is 42",
        "verification": {"valid": True},
        "cost": {"llm_calls": 3, "total_tokens": 120, "usd": 0.0021},
        "new_blocks": [1, 2, 3, 4],
    })
    assert out.startswith("✓ the answer is 42")
    assert "chain verified" in out
    assert "3 model calls" in out and "4 blocks" in out


def test_format_run_result_failure_and_tamper():
    out = cli._format_run_result({"success": False, "final": "gave up", "verification": {"valid": False}})
    assert out.startswith("✗ gave up")
    assert "CHAIN INVALID" in out


def test_status_when_not_running(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ATHENA_HOME", str(tmp_path))
    rc = cli.cmd_status(cli.build_parser().parse_args(["status"]))
    assert rc == 1
    assert "not running" in capsys.readouterr().out.lower()


def test_run_unreachable_server(monkeypatch, capsys):
    import urllib.error

    def boom(*a, **k):
        raise urllib.error.URLError("refused")

    # `run` streams by default: it opens the SSE stream and looks up agents.
    monkeypatch.setattr(cli, "_open_stream", boom)
    monkeypatch.setattr(cli, "_get_json", boom)
    rc = cli.cmd_run(cli.build_parser().parse_args(["run", "do", "something"]))
    assert rc == 1
    assert "couldn't reach" in capsys.readouterr().err.lower()


def test_run_no_stream_uses_blocking_endpoint(monkeypatch, capsys):
    import urllib.error

    def boom(*a, **k):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(cli, "_post_json", boom)
    rc = cli.cmd_run(cli.build_parser().parse_args(["run", "--no-stream", "do", "something"]))
    assert rc == 1
    assert "couldn't reach" in capsys.readouterr().err.lower()
