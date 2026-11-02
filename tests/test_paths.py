"""paths: the state directory, and the ATHENA_* names from before the rename."""

import paths


def test_legacy_env_names_still_work():
    env = {"ATHENA_HOME": "/old", "ATHENA_MODEL": "m", "GLAUX_MODEL": "explicit"}
    paths.adopt_legacy_env(env)
    assert env["GLAUX_HOME"] == "/old"
    assert env["GLAUX_MODEL"] == "explicit"  # an explicit new name wins


def test_home_prefers_glaux_home(monkeypatch, tmp_path):
    monkeypatch.setenv("GLAUX_HOME", str(tmp_path / "state"))
    assert paths.home() == tmp_path / "state"


def test_home_keeps_an_install_from_before_the_rename(monkeypatch, tmp_path):
    monkeypatch.delenv("GLAUX_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.home() == tmp_path / ".glaux"  # fresh machine
    (tmp_path / ".athena").mkdir()
    assert paths.home() == tmp_path / ".athena"  # existing install keeps its data
    (tmp_path / ".glaux").mkdir()
    assert paths.home() == tmp_path / ".glaux"  # once ~/.glaux exists, it wins
