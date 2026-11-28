import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import yaml

from pwf import cli, guard, messages, router
from pwf import team as team_mod
from test_pwf import ASSIGN, RESULT, repo, run_guard  # noqa: F401


@pytest.fixture
def team2(repo):
    """Đội có hai worker (backend, web) và bật router."""
    path = repo / ".workflow" / "team.yaml"
    data = yaml.safe_load(path.read_text())
    data["router"] = "jev"
    data["sessions"][1]["can_send_to"].append("shop-web")
    data["sessions"].append({"name": "shop-web", "role": "worker", "model": "haiku",
                             "worktree": "../shop.worktrees/web", "scope": ["web/"],
                             "description": "Giao diện web", "can_send_to": ["shop-builder"]})
    path.write_text(yaml.safe_dump(data, allow_unicode=True))
    return repo


def answers(leaks=0.02, fits=0.95, size=0.4, conf=0.9, choice="shop-backend", p=0.9):
    other = "shop-web" if choice == "shop-backend" else "shop-backend"
    return {"leaks": {"type": "noul", "noul": leaks},
            "fits_any": {"type": "noul", "noul": fits},
            "task_size": {"type": "score", "score": size, "confidence": conf},
            "recipient": {"type": "choice", "choice": choice,
                          "probabilities": {choice: p, other: round(1 - p, 2)}}}


class FakeJev:
    def __init__(self, ans=None, error=None):
        self.ans, self.error, self.bodies = ans, error, []

    def __call__(self, cfg, body):
        self.bodies.append(body)
        if self.error:
            raise self.error
        return {"model": "jev-1.14.0", "answers": self.ans}


def make(repo, **kw):
    fake = FakeJev(**kw)
    return router.JevRouter(router.load_config(repo), post=fake), fake


def send(repo, r, sender="shop-builder", to="shop-backend", text=ASSIGN):
    out = io.StringIO()
    code, err = run_guard(repo, sender, {"to": to, "recipient": to, "message": text},
                          router=r, out=out)
    return code, err, out.getvalue()


def decisions(repo):
    path = repo / ".workflow" / "log" / "router.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()]


def test_request_carries_candidates_and_all_questions(team2):
    r, fake = make(team2, ans=answers())
    assert send(team2, r) == (0, "", "")
    (body,) = fake.bodies
    assert body["model"] == "jev-latest" and body["state"] == ASSIGN
    q = body["questions"]
    assert set(q) == {"leaks", "fits_any", "task_size", "recipient"}
    assert q["recipient"]["criteria"] == {"shop-backend": "Phạm vi: backend/",
                                          "shop-web": "Giao diện web"}
    assert "shop-web: Giao diện web" in q["fits_any"]["instructions"]
    assert len(q["task_size"]["criteria"]) == 4
    (d,) = decisions(team2)
    assert d["action"] == "allow" and d["model"] == "jev-1.14.0" and d["answers"]["leaks"]


def test_redirects_when_router_is_confident(team2):
    r, _ = make(team2, ans=answers(choice="shop-web", p=0.92))
    code, err, out = send(team2, r)
    assert code == 0 and err == ""
    new = json.loads(out)["hookSpecificOutput"]
    assert new["permissionDecision"] == "allow"
    assert new["updatedInput"]["to"] == new["updatedInput"]["recipient"] == "shop-web"
    assert new["updatedInput"]["message"] == ASSIGN
    assert messages.tasks(team2)[0]["to"] == "shop-web"
    assert decisions(team2)[0]["final_to"] == "shop-web"


def test_keeps_sender_choice_below_threshold(team2):
    r, _ = make(team2, ans=answers(choice="shop-web", p=0.6))
    assert send(team2, r) == (0, "", "")


@pytest.mark.parametrize("kw,needle", [
    (dict(leaks=0.9), "bí mật"),
    (dict(fits=0.1), "không thuộc phạm vi"),
    (dict(conf=0.3), "Không rõ task lớn cỡ nào"),
    (dict(size=2.8), "cần thiết kế"),
    (dict(size=2.0), "quá lớn cho một worker"),
])
def test_blocks(team2, kw, needle):
    r, _ = make(team2, ans=answers(**kw))
    code, err, out = send(team2, r)
    assert code == 2 and needle in err and out == ""
    assert messages.tasks(team2) == []
    assert decisions(team2)[0]["action"] == "block"


def test_non_assign_messages_only_get_leak_check(team2):
    r, fake = make(team2, ans={"leaks": {"noul": 0.01}})
    assert send(team2, r, "shop-backend", "shop-builder", RESULT) == (0, "", "")
    assert set(fake.bodies[0]["questions"]) == {"leaks"}
    r, _ = make(team2, ans={"leaks": {"noul": 0.95}})
    assert send(team2, r, "shop-backend", "shop-builder", RESULT)[0] == 2


def test_single_worker_skips_recipient_question(repo):
    r, fake = make(repo, ans={k: v for k, v in answers().items() if k != "recipient"})
    assert send(repo, r) == (0, "", "")
    assert set(fake.bodies[0]["questions"]) == {"leaks", "fits_any", "task_size"}


@pytest.mark.parametrize("kw", [dict(error=router.RouterError("Jev trả mã 529")),
                                dict(ans={"leaks": {}})])
def test_errors_escalate_assignments_but_let_other_messages_through(team2, kw):
    r, _ = make(team2, **kw)
    code, err, _ = send(team2, r)
    assert code == 2 and "architect" in err
    assert send(team2, r, "shop-backend", "shop-builder", RESULT)[0] == 0
    assert all(d["error"] for d in decisions(team2))


def test_project_overrides_thresholds_and_error_policy(team2):
    (team2 / ".workflow" / "thresholds.yaml").write_text(
        "model: jev-1.14.0\non_error: allow\nthresholds:\n  worker_max_size: 2.2\n")
    cfg = router.load_config(team2)
    assert cfg["model"] == "jev-1.14.0" and cfg["thresholds"]["leaks_block"] == 0.7
    r, fake = make(team2, ans=answers(size=2.0))
    assert send(team2, r)[0] == 0 and fake.bodies[0]["model"] == "jev-1.14.0"
    r, _ = make(team2, error=router.RouterError("x"))
    assert send(team2, r)[0] == 0


def test_router_off_by_default_makes_no_calls(repo):
    assert team_mod.load(repo).router == "none"
    assert router.for_team(team_mod.load(repo)) is None
    assert run_guard(repo, "shop-builder", {"to": "shop-backend", "message": ASSIGN})[0] == 0
    assert not (repo / ".workflow" / "log" / "router.jsonl").exists()


def test_missing_key_is_reported_without_calling_out(team2, monkeypatch):
    monkeypatch.delenv(router.KEY_ENV, raising=False)
    r = router.JevRouter(router.load_config(team2))
    d = r.decide(ASSIGN, "shop-backend", router.candidates_for(
        team_mod.load(team2), team_mod.load(team2).session("shop-builder")))
    assert d.action == "block" and router.KEY_ENV in d.error


@pytest.fixture
def server():
    state = {"codes": [], "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append((self.headers["Authorization"], body))
            code = state["codes"].pop(0) if state["codes"] else 200
            self.send_response(code)
            self.end_headers()
            if code == 200:
                self.wfile.write(json.dumps({"model": "jev-1.14.0", "answers": answers(
                    choice="shop-web", p=0.95)}).encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{srv.server_port}/v1/systemone"
    yield state
    srv.shutdown()


def test_http_path_auth_retry_and_cli(team2, server, monkeypatch, capsys):
    monkeypatch.setenv(router.KEY_ENV, "test-key")
    monkeypatch.setattr(router.time, "sleep", lambda s: None)
    monkeypatch.chdir(team2)
    (team2 / ".workflow" / "thresholds.yaml").write_text(f"endpoint: {server['url']}\n")
    server["codes"] = [429]
    code = cli.main(["route", "--from", "shop-builder", "--to", "shop-backend", ASSIGN])
    shown = json.loads(capsys.readouterr().out)
    assert code == 0 and shown["action"] == "redirect" and shown["to"] == "shop-web"
    assert len(server["requests"]) == 2 and server["requests"][0][0] == "Bearer test-key"
    assert not (team2 / ".workflow" / "log").exists()  # route không ghi sổ

    server["codes"] = [529, 529]
    code = cli.main(["route", "--from", "shop-builder", "--to", "shop-backend", ASSIGN])
    shown = json.loads(capsys.readouterr().out)
    assert code == 2 and "529" in shown["error"]

    # Hook thật, qua guard.run không tiêm router: đọc cấu hình và gọi HTTP.
    out, err = io.StringIO(), io.StringIO()
    payload = {"tool_name": "SendMessage", "tool_input": {"to": "shop-backend", "message": ASSIGN}}
    assert guard.run(team2, "shop-builder", io.StringIO(json.dumps(payload)), err, stdout=out) == 0
    assert json.loads(out.getvalue())["hookSpecificOutput"]["updatedInput"]["to"] == "shop-web"
