"""Workspace model: projects, sessions, runs, persistence."""

from __future__ import annotations

from core.sessions import NEW_SESSION_TITLE, Run, SessionStore


def _run(directive="do a thing", final="done", success=True):
    return Run(id="", directive=directive, final=final, success=success, blocks=[{"index": 0}])


def test_ensure_active_creates_a_session(tmp_path):
    s = SessionStore(store_path=tmp_path / "ws.json")
    active = s.ensure_active()
    assert active.id == s.active_id
    assert active.title == NEW_SESSION_TITLE
    assert len(s.sessions) == 1


def test_record_run_titles_from_first_directive(tmp_path):
    s = SessionStore(store_path=tmp_path / "ws.json")
    s.ensure_active()
    s.record_run(_run("Summarize the quarterly report"))
    sess = s.active()
    assert sess.title == "Summarize the quarterly report"  # derived from first run
    assert len(sess.runs) == 1 and sess.runs[0].id  # id stamped
    # a second run keeps the title
    s.record_run(_run("and now translate it"))
    assert s.active().title == "Summarize the quarterly report"
    assert len(s.active().runs) == 2


def test_new_session_becomes_active(tmp_path):
    s = SessionStore(store_path=tmp_path / "ws.json")
    first = s.ensure_active()
    second = s.create_session()
    assert s.active_id == second.id != first.id
    assert s.activate(first.id).id == first.id
    assert s.active_id == first.id
    assert s.activate("nope") is None


def test_projects_group_and_ungroup(tmp_path):
    s = SessionStore(store_path=tmp_path / "ws.json")
    proj = s.create_project("Research", "be rigorous")
    sess = s.create_session(title="lit review", project_id=proj["id"])
    assert sess.project_id == proj["id"]
    tree = s.tree()
    assert any(p["id"] == proj["id"] and p["instructions"] == "be rigorous" for p in tree["projects"])
    # deleting the project ungroups its sessions but keeps them
    assert s.delete_project(proj["id"]) is True
    assert s.sessions[sess.id].project_id is None


def test_update_session_rename_and_move(tmp_path):
    s = SessionStore(store_path=tmp_path / "ws.json")
    proj = s.create_project("P")
    sess = s.ensure_active()
    assert s.update_session(sess.id, title="renamed")["title"] == "renamed"
    # project_id default "_keep" leaves it unchanged
    assert s.update_session(sess.id, title="again")["project_id"] is None
    # explicitly move into the project
    assert s.update_session(sess.id, project_id=proj["id"])["project_id"] == proj["id"]
    # and back out (null)
    assert s.update_session(sess.id, project_id=None)["project_id"] is None


def test_delete_active_session_keeps_one_active(tmp_path):
    s = SessionStore(store_path=tmp_path / "ws.json")
    a = s.ensure_active()
    b = s.create_session()
    assert s.delete_session(b.id) is True
    assert s.active_id == a.id
    # deleting the last one re-creates a fresh active session
    assert s.delete_session(a.id) is True
    assert s.active_id and s.active_id in s.sessions


def test_tree_sorted_by_recency(tmp_path):
    s = SessionStore(store_path=tmp_path / "ws.json")
    s.ensure_active()
    s.create_session(title="older")
    newest = s.create_session(title="newest")
    s.record_run(_run("touch newest"), session_id=newest.id)
    assert s.tree()["sessions"][0]["id"] == newest.id  # most recently updated first


def test_persistence_roundtrip(tmp_path):
    path = tmp_path / "ws.json"
    s = SessionStore(store_path=path)
    proj = s.create_project("Finance", "use GAAP")
    sess = s.create_session(title="close the books", project_id=proj["id"])
    s.record_run(_run("book the accruals", final="booked"))
    active_before = s.active_id

    s2 = SessionStore(store_path=path)
    s2.load()
    assert s2.active_id == active_before
    assert proj["id"] in s2.projects and s2.projects[proj["id"]].instructions == "use GAAP"
    reloaded = s2.session_full(sess.id)
    assert reloaded["title"] == "close the books"  # explicit title is preserved
    assert reloaded["runs"][0]["final"] == "booked"
    assert reloaded["runs"][0]["blocks"] == [{"index": 0}]  # signed blocks preserved
