import io
import json

import yaml

from pwf import cli, launch, messages, project, router
from pwf import team as team_mod
from test_pwf import ASSIGN, RESULT, SIGNOFF, make_repo, repo, run_guard  # noqa: F401
from test_router import FakeJev, answers, send, team2  # noqa: F401

QUIET = lambda *_: None


def test_init_with_three_workers(tmp_path):
    files = ([f"api/a{i}.py" for i in range(5)] + [f"web/w{i}.ts" for i in range(4)]
             + [f"db/m{i}.sql" for i in range(3)] + ["tools/t.py"])
    root = make_repo(tmp_path, files)
    project.init(root, None, graph=False, say=QUIET, workers=3)
    team = team_mod.load(root)
    workers = [s for s in team.sessions if s.role == "worker"]
    assert [w.name for w in workers] == ["shop-api", "shop-web", "shop-db"]
    assert [w.scope for w in workers] == [["api/"], ["web/"], ["db/"]]
    assert team.session("shop-builder").can_send_to == ["shop-architect", "shop-api",
                                                        "shop-web", "shop-db"]
    assert len({w.worktree for w in workers}) == 3
    lines = []
    assert launch.up(team, "print", say=lines.append) == 0 and len(lines) == 5


def test_init_disambiguates_same_named_dirs(tmp_path):
    files = [f"src/api/a{i}.py" for i in range(4)] + [f"lib/api/b{i}.py" for i in range(3)]
    root = make_repo(tmp_path, files)
    project.init(root, None, graph=False, say=QUIET, workers=2)
    names = [s.name for s in team_mod.load(root).sessions if s.role == "worker"]
    assert names == ["shop-src", "shop-lib"]  # mỗi thư mục cấp một là một worker


def test_two_projects_do_not_cross(tmp_path):
    """Hai dự án trên cùng máy: phiên của dự án này không gửi được sang dự án kia."""
    roots = {}
    for name in ("alpha", "beta"):
        (tmp_path / name).mkdir()
        root = make_repo(tmp_path / name, ["backend/a.py", "backend/b.py"])
        project.init(root, name, graph=False, say=QUIET)
        roots[name] = root
    alpha, beta = (team_mod.load(roots[n]) for n in ("alpha", "beta"))
    assert {s.name for s in alpha.sessions}.isdisjoint(s.name for s in beta.sessions)
    assert launch.tmux_session(alpha) != launch.tmux_session(beta)

    code, err = run_guard(roots["alpha"], "alpha-builder",
                          {"to": "beta-backend", "message": ASSIGN})
    assert code == 2 and "alpha-backend" in err
    # Phiên của beta không có trong team.yaml của alpha nên hook từ chối chạy thay nó.
    assert run_guard(roots["alpha"], "beta-builder",
                     {"to": "alpha-backend", "message": ASSIGN})[0] == 2

    for name in ("alpha", "beta"):
        assert run_guard(roots[name], f"{name}-builder",
                         {"to": f"{name}-backend", "message": ASSIGN})[0] == 0
    # Cùng mã T-1 ở hai dự án, nhưng mỗi dự án một sổ tin riêng.
    for name in ("alpha", "beta"):
        (task,) = messages.tasks(roots[name])
        assert task["to"] == f"{name}-backend" and task["count"] == 1


def test_status_board_shows_sessions_tasks_and_router(team2):
    r = router.JevRouter(router.load_config(team2), post=FakeJev(ans=answers()))
    send(team2, r)
    send(team2, router.JevRouter(router.load_config(team2), post=FakeJev(ans=answers(leaks=0.9))),
         text=ASSIGN.replace("T-1", "T-2"))
    out = []
    launch.status(team_mod.load(team2), "print", say=out.append)
    text = "\n".join(out)
    assert "Task: 1 đang mở, 0 đã xong" in text and "T-1" in text and "T-2" not in text
    assert "Router: jev · allow 1, block 1" in text
    assert "shop-web" in text and "worktree chưa tạo" in text


def test_status_marks_tasks_at_the_limit(repo):
    path = repo / ".workflow" / "team.yaml"
    data = yaml.safe_load(path.read_text())
    data["limits"] = {"messages_per_task": 2}
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    run_guard(repo, "shop-builder", {"to": "shop-backend", "message": ASSIGN})
    run_guard(repo, "shop-backend", {"to": "shop-builder", "message": RESULT})
    out = []
    launch.status(team_mod.load(repo), "print", say=out.append)
    assert any("chạm giới hạn tin" in l for l in out) and "Router: tắt" in out


def test_router_stats_joins_decisions_with_outcomes(team2, monkeypatch, capsys):
    def route(task, **kw):
        r = router.JevRouter(router.load_config(team2), post=FakeJev(ans=answers(**kw)))
        return send(team2, r, text=ASSIGN.replace("T-1", task))

    def reply(sender, text):  # tin trả lời chỉ qua bước kiểm tra rò rỉ
        r = router.JevRouter(router.load_config(team2), post=FakeJev(ans={"leaks": {"noul": 0.0}}))
        assert send(team2, r, sender, "shop-builder", text)[0] == 0

    blocked = "[pwf:blocked] {}\nVướng ở: file nằm ngoài phạm vi\nCần: giao lại"
    route("T-1")                                   # giữ backend, worker làm xong
    reply("shop-backend", RESULT)
    route("T-2", choice="shop-web", p=0.95)        # đổi sang web, web báo bị chặn
    reply("shop-web", blocked.format("T-2"))
    route("T-3", choice="shop-web", p=0.65)        # sát ngưỡng, chưa có hồi âm
    route("T-4", size=2.0)                         # bị chặn vì quá lớn
    r = router.JevRouter(router.load_config(team2), post=FakeJev(error=router.RouterError("x")))
    send(team2, r, text=ASSIGN.replace("T-1", "T-5"))

    st = router.stats(router.read_log(team2), messages.entries(team2),
                      router.load_config(team2)["thresholds"])
    assert st["total"] == 7 and st["errors"] == 1
    assert st["actions"] == {"allow": 4, "redirect": 1, "block": 2}
    assert st["outcomes"] == {"hợp": 1, "nghi sai": 1, "chưa rõ": 1}
    assert st["near_threshold"] == 1
    assert [(x["task"], x["to"]) for x in st["suspects"]] == [("T-2", "shop-web")]

    monkeypatch.chdir(team2)
    assert cli.main(["router-stats"]) == 0
    shown = capsys.readouterr().out
    assert "tỉ lệ hợp 50%" in shown and "nghi sai: T-2 → shop-web" in shown


def test_router_stats_with_empty_log(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert cli.main(["router-stats"]) == 0
    assert "Chưa có quyết định" in capsys.readouterr().out
