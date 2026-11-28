import io
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from pwf import guard, launch, project
from pwf import team as team_mod


def make_repo(tmp_path: Path, files) -> Path:
    root = tmp_path / "shop"
    for f in files:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True,
                                    capture_output=True)
    run("init", "-q", "-b", "main")
    run("add", "-A")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return root


@pytest.fixture
def repo(tmp_path):
    files = [f"backend/m{i}.py" for i in range(5)] + ["web/a.ts", "web/b.ts", "README.md"]
    root = make_repo(tmp_path, files)
    project.init(root, None, graph=False, say=lambda *_: None)
    return root


def test_init_generates_valid_team(repo):
    team = team_mod.load(repo)
    assert team.project == "shop" and team.main_branch == "main"
    assert [s.name for s in team.sessions] == ["shop-architect", "shop-builder", "shop-backend"]
    worker = team.session("shop-backend")
    assert worker.scope == ["backend/"] and worker.can_send_to == ["shop-builder"]
    ignore = (repo / ".gitignore").read_text()
    assert ".workflow/run/" in ignore and "graphify-out/" in ignore


def test_init_rerun_keeps_user_edits(repo):
    path = repo / ".workflow" / "team.yaml"
    path.write_text(path.read_text() + "\n# của tôi\n")
    project.init(repo, None, graph=False, say=lambda *_: None)
    assert path.read_text().endswith("# của tôi\n")
    assert (repo / ".gitignore").read_text().count(".workflow/run/") == 1


def test_propose_areas_descends_into_dominant_dir():
    files = [f"src/api/f{i}.py" for i in range(6)] + [f"src/ui/f{i}.ts" for i in range(3)]
    assert project.propose_areas(files) == [("src/api", 6), ("src/ui", 3)]


@pytest.mark.parametrize("change,message", [
    ({"permission_mode": "bypassPermissions"}, "permission_mode"),
    ({"name": "other-builder"}, "bắt đầu bằng"),
    ({"can_send_to": ["shop-nobody"]}, "không tồn tại"),
    ({"inbound": "maybe"}, "inbound"),
    ({"surprise": 1}, "khóa lạ"),
])
def test_team_validation_rejects(repo, change, message):
    data = yaml.safe_load((repo / ".workflow" / "team.yaml").read_text())
    data["sessions"][1].update(change)
    with pytest.raises(team_mod.TeamError, match=message):
        team_mod.parse(data, repo)


def run_guard(repo, sender, tool_input, tool="SendMessage"):
    payload = {"tool_name": tool, "tool_input": tool_input}
    err = io.StringIO()
    code = guard.run(repo, sender, io.StringIO(json.dumps(payload)), err)
    return code, err.getvalue()


def test_guard_allows_listed_and_blocks_others(repo):
    assert run_guard(repo, "shop-backend", {"to": "shop-builder"})[0] == 0
    assert run_guard(repo, "shop-backend", {"to": "shop-builder [46ed9e]"})[0] == 0
    code, err = run_guard(repo, "shop-backend", {"to": "shop-architect"})
    assert code == 2 and "shop-builder" in err
    assert run_guard(repo, "shop-backend", {"to": "other-builder"})[0] == 2
    assert run_guard(repo, "shop-backend", {})[0] == 2
    assert run_guard(repo, "shop-backend", {"file_path": "x"}, tool="Read")[0] == 0


def test_guard_fails_closed(repo, tmp_path):
    assert guard.run(repo, "shop-backend", io.StringIO("not json"), io.StringIO()) == 2
    assert run_guard(tmp_path, "shop-backend", {"to": "shop-builder"})[0] == 2
    assert run_guard(repo, "shop-unknown", {"to": "shop-builder"})[0] == 2


def test_prepare_writes_settings_and_prompt(repo):
    team = team_mod.load(repo)
    (repo / ".workflow" / "roles" / "shop-backend.md").write_text("Dùng pytest.")
    argv = launch.prepare(team, team.session("shop-backend"))
    opt = lambda flag: argv[argv.index(flag) + 1]
    assert opt("--name") == "shop-backend" and opt("--model") == "haiku"
    assert opt("--permission-mode") == "acceptEdits"
    settings = json.loads(Path(opt("--settings")).read_text())
    assert settings["crossSessionInbound"] == "accept"
    hook = settings["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "SendMessage"
    assert "--session shop-backend" in hook["hooks"][0]["command"]
    prompt = Path(opt("--append-system-prompt-file")).read_text()
    assert "backend/" in prompt and "shop-builder" in prompt and "Dùng pytest." in prompt
    assert "{{" not in prompt
    assert "--mcp-config" not in argv  # chưa có đồ thị


def test_up_print_creates_worktrees_and_is_repeatable(repo):
    team = team_mod.load(repo)
    lines = []
    assert launch.up(team, "print", say=lines.append) == 0
    assert len(lines) == 3 and all("--name shop-" in l for l in lines)
    tree = team.cwd(team.session("shop-builder"))
    assert (tree / ".git").exists() and tree.parent.name == "shop.worktrees"
    head = subprocess.run(["git", "-C", str(tree), "rev-parse", "--abbrev-ref", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert head == "pwf/shop-builder"
    assert launch.up(team, "print", say=lines.append) == 0
    out = []
    launch.status(team, "print", say=out.append)
    assert any("pwf/shop-builder, 0 file" in l for l in out)
