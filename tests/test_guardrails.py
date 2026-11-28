import json

import pytest
import yaml

from pwf import checks, cli, launch, messages
from pwf import team as team_mod
from test_pwf import ASSIGN, RESULT, SIGNOFF, repo, run_guard  # noqa: F401

OK_VERSION = (2, 1, 332)


def edit(repo, fn):
    path = repo / ".workflow" / "team.yaml"
    data = yaml.safe_load(path.read_text())
    fn(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True))


def ping_pong(repo, n):
    """Builder và worker nhắn qua lại n tin về T-1; trả về mã thoát của từng tin."""
    turns = [("shop-builder", "shop-backend", ASSIGN), ("shop-backend", "shop-builder", RESULT)]
    return [run_guard(repo, s, {"to": t, "message": m})[0] for s, t, m in (turns * n)[:n]]


def test_message_limit_stops_ping_pong_until_reopened(repo):
    edit(repo, lambda d: d.update(limits={"messages_per_task": 4}))
    assert ping_pong(repo, 5) == [0, 0, 0, 0, 2]
    code, err = run_guard(repo, "shop-backend", {"to": "shop-builder", "message": RESULT})
    assert code == 2 and "pwf reopen T-1" in err
    assert messages.count(repo, "T-1") == 4  # tin bị chặn không được đếm
    other = ASSIGN.replace("T-1", "T-2")
    assert run_guard(repo, "shop-builder", {"to": "shop-backend", "message": other})[0] == 0

    assert messages.reopen(repo, "T-1") and not messages.reopen(repo, "T-404")
    assert messages.count(repo, "T-1") == 0
    assert ping_pong(repo, 5) == [0, 0, 0, 0, 2]


def test_signoff_still_passes_at_the_limit(repo):
    edit(repo, lambda d: d.update(limits={"messages_per_task": 2}))
    assert ping_pong(repo, 3) == [0, 0, 2]
    assert run_guard(repo, "shop-architect", {"to": "shop-builder", "message": SIGNOFF})[0] == 0
    assert messages.tasks(repo)[0]["state"] == "xong"


@pytest.mark.parametrize("limits", [{"messages_per_task": 1}, {"messages_per_task": "many"},
                                    {"hops": 3}, {"messages_per_task": True}])
def test_limits_validation(repo, limits):
    data = yaml.safe_load((repo / ".workflow" / "team.yaml").read_text())
    data["limits"] = limits
    with pytest.raises(team_mod.TeamError, match="limits"):
        team_mod.parse(data, repo)


def test_generated_team_has_default_limit_and_passes_checks(repo):
    team = team_mod.load(repo)
    assert team.messages_per_task == 12
    assert checks.run(team, version=OK_VERSION, env={}) == []


def test_session_settings_disable_bypass_mode(repo):
    team = team_mod.load(repo)
    for s in team.sessions:
        settings = launch.session_settings(team, s)
        assert settings["permissions"] == {"disableBypassPermissionsMode": "disable"}


def findings(repo, version=OK_VERSION, env=None):
    return checks.run(team_mod.load(repo), version=version, env=env or {})


def test_check_flags_weak_guardrails(repo):
    def weaken(d):
        d["router"] = "jev"
        d["sessions"][0]["inbound"] = "accept"
        d["sessions"][2].update(inbound="hold", scope=[], permission_mode="auto")
    edit(repo, weaken)
    (repo / ".gitignore").write_text("")
    text = "\n".join(t for _, t in findings(repo))
    for needle in ("architect nên để inbound là hold", "sẽ không tự nhận việc", "chưa có scope",
                   "permission_mode auto", ".gitignore thiếu", "TYPESAFE_API_KEY"):
        assert needle in text
    assert all(level == checks.WARN for level, _ in findings(repo))
    assert "TYPESAFE_API_KEY" not in "\n".join(
        t for _, t in findings(repo, env={"TYPESAFE_API_KEY": "x"}))


def test_check_errors_on_secrets_and_old_claude(repo):
    (repo / ".workflow" / "thresholds.yaml").write_text(
        "model: jev-1.14.0\n# api_key: trong chú thích thì bỏ qua\napi_key: abc123\n")
    found = findings(repo, version=(2, 1, 100))
    errors = [t for level, t in found if level == checks.ERROR]
    assert len(errors) == 2
    assert any("thresholds.yaml dòng 3" in t for t in errors)
    assert any("quá cũ" in t for t in errors)
    assert "abc123" not in "\n".join(errors)  # không in lại giá trị khóa


def test_up_refuses_when_check_has_errors(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    monkeypatch.setattr(checks, "claude_version", lambda: None)
    assert cli.main(["up", "--backend", "print"]) == 1
    assert "LỖI" in capsys.readouterr().out
    assert not (repo / ".workflow" / "run").exists()
    monkeypatch.setattr(checks, "claude_version", lambda: OK_VERSION)
    assert cli.main(["check"]) == 0
    assert cli.main(["up", "--backend", "print"]) == 0


def test_reopen_and_tasks_commands(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    ping_pong(repo, 2)
    assert cli.main(["reopen", "T-1"]) == 0 and cli.main(["reopen", "T-404"]) == 1
    capsys.readouterr()
    cli.main(["tasks"])
    assert "0/12 tin" in capsys.readouterr().out
