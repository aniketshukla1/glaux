"""Phase 0.4: secrets broker injection, isolation, and redaction."""

from __future__ import annotations

import pytest

import safety
from sandbox import Capabilities, DictSecretsBackend, EnvSecretsBackend, SecretsBroker, run
from sandbox.secrets import SecretsBroker as Broker


@pytest.fixture(autouse=True)
def _live_mode():
    safety.set_mode("live")
    yield
    safety.set_mode(None)


def _broker():
    return SecretsBroker(
        DictSecretsBackend(
            {"API_TOKEN": "tok-12345-secret", "OTHER_SECRET": "do-not-leak"}
        )
    )


def test_declared_secret_is_available():
    code = (
        "import os\n"
        "def main():\n"
        "    return os.environ.get('API_TOKEN') is not None\n"
    )
    res = run(
        code,
        caps=Capabilities(time_limit_s=5, secrets=["API_TOKEN"]),
        entrypoint="main",
        broker=_broker(),
    )
    assert res.ok
    assert res.return_value is True


def test_undeclared_secret_absent():
    code = (
        "import os\n"
        "def main():\n"
        "    return os.environ.get('OTHER_SECRET')\n"
    )
    res = run(
        code,
        caps=Capabilities(time_limit_s=5, secrets=["API_TOKEN"]),
        entrypoint="main",
        broker=_broker(),
    )
    assert res.ok
    assert res.return_value is None


def test_secret_value_redacted_from_stdout():
    code = "import os\nprint(os.environ['API_TOKEN'])\n"
    res = run(
        code,
        caps=Capabilities(time_limit_s=5, secrets=["API_TOKEN"]),
        broker=_broker(),
    )
    assert res.ok
    assert "tok-12345-secret" not in res.stdout
    assert "***REDACTED***" in res.stdout


def test_secrets_requested_without_broker_fails():
    res = run(
        "x = 1",
        caps=Capabilities(time_limit_s=5, secrets=["API_TOKEN"]),
    )
    assert not res.ok
    assert "broker" in res.error.lower()


def test_unknown_secret_fails():
    res = run(
        "x = 1",
        caps=Capabilities(time_limit_s=5, secrets=["NONEXISTENT"]),
        broker=_broker(),
    )
    assert not res.ok
    assert "unknown secret" in res.error.lower()


def test_env_backend(monkeypatch):
    monkeypatch.setenv("ATHENA_SECRET_DB_PASSWORD", "hunter2")
    broker = Broker(EnvSecretsBackend())
    assert broker.resolve("DB_PASSWORD") == "hunter2"
