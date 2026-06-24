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
