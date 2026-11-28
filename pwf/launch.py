"""Bật, tắt và xem trạng thái các phiên Claude Code của một dự án."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import List, Optional

from . import messages
from .project import GRAPH_DIR
from .team import WORKFLOW_DIR, Session, Team

BACKENDS = ("tmux", "wt", "print")


def default_backend() -> str:
    if os.name == "nt":
        return "wt" if shutil.which("wt") else "print"
    return "tmux" if shutil.which("tmux") else "print"


def tmux_session(team: Team) -> str:
    return f"pwf-{team.project}"


def branch_of(s: Session) -> str:
    return s.branch or f"pwf/{s.name}"


# ---------- file sinh ra cho từng phiên ----------

def role_prompt(team: Team, s: Session) -> str:
    base = resources.files("pwf").joinpath(f"templates/roles/{s.role}.md").read_text(
        encoding="utf-8"
    )
    peers = ", ".join(s.can_send_to) or "(không có)"
    scope = ", ".join(s.scope) or "toàn bộ dự án"
    text = (
        base.replace("{{name}}", s.name)
        .replace("{{project}}", team.project)
        .replace("{{peers}}", peers)
        .replace("{{scope}}", scope)
        .replace("{{main_branch}}", team.main_branch)
    )
    text += "\n\n" + messages.prompt_section(
        s.role, [team.session(n).role for n in s.can_send_to]
    )
    if s.role != "worker" and graph_mcp_config(team):
        text += "\n\n" + GRAPH_NOTE
    for extra in (f"{s.role}.md", f"{s.name}.md"):
        p = team.root / WORKFLOW_DIR / "roles" / extra
        if p.is_file():
            text += "\n\n" + p.read_text(encoding="utf-8")
    return text


GRAPH_NOTE = """\
## Đồ thị mã nguồn

Phiên này có MCP server `graphify` đọc đồ thị của dự án, dựng từ nhánh chính.
Dùng nó khi chia việc và khi xem một thay đổi lan tới đâu. Đồ thị có thể cũ:
đọc file thật trước khi kết luận. Khi giao việc, chép phần liên quan vào trường
`Ngữ cảnh` để phiên nhận không phải tự tra."""


def tasks(team: Team, say=print) -> int:
    rows = messages.tasks(team.root)
    if not rows:
        say("Chưa có task nào trong sổ tin.")
    for e in rows:
        say(f"  {e['task']:<14} {e['state']:<9} {e['from']} → {e['to']} "
            f"({e['type']}, {e['time']}, {e['count']} tin)")
    return 0


def session_settings(team: Team, s: Session) -> dict:
    guard = subprocess.list2cmdline if os.name == "nt" else shlex.join
    command = guard(
        [sys.executable, "-m", "pwf", "guard", "--root", str(team.root), "--session", s.name]
    )
    return {
        "crossSessionInbound": s.inbound,
        "hooks": {
            "PreToolUse": [
                {"matcher": "SendMessage", "hooks": [{"type": "command", "command": command}]}
            ]
        },
    }


def graph_mcp_config(team: Team) -> Optional[dict]:
    """Mọi phiên đọc chung đồ thị ở thư mục gốc, kể cả phiên chạy trong worktree."""
    graph = team.root / GRAPH_DIR / "graph.json"
    exe = shutil.which("graphify-mcp")
    if not graph.is_file() or not exe:
        return None
    return {
        "mcpServers": {
            "graphify": {
                "command": exe,
                "args": [str(graph)],
                "env": {"GRAPHIFY_QUERY_LOG_DISABLE": "1"},
            }
        }
    }


def prepare(team: Team, s: Session) -> List[str]:
    """Ghi các file của phiên vào `.workflow/run/` và trả về argv để chạy."""
    run = team.run_dir
    run.mkdir(parents=True, exist_ok=True)
    prompt = run / f"{s.name}.prompt.md"
    settings = run / f"{s.name}.settings.json"
    prompt.write_text(role_prompt(team, s), encoding="utf-8")
    settings.write_text(json.dumps(session_settings(team, s), indent=2), encoding="utf-8")
    argv = [
        shutil.which("claude") or "claude",
        "--name", s.name,
        "--model", s.model,
        "--permission-mode", s.permission_mode,
        "--settings", str(settings),
        "--append-system-prompt-file", str(prompt),
    ]
    mcp = graph_mcp_config(team)
    if mcp:
        path = run / "graphify.mcp.json"
        path.write_text(json.dumps(mcp, indent=2), encoding="utf-8")
        argv += ["--mcp-config", str(path)]
    return argv


# ---------- worktree ----------

def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def ensure_worktree(team: Team, s: Session) -> Optional[str]:
    """Tạo worktree nếu chưa có. Trả về lỗi, hoặc None."""
    if not s.worktree:
        return None
    path = team.cwd(s)
    if (path / ".git").exists():
        return None
    branch = branch_of(s)
    exists = _git(team.root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    args = ["worktree", "add", str(path)]
    args += [branch] if exists.returncode == 0 else ["-b", branch, team.main_branch]
    r = _git(team.root, *args)
    return None if r.returncode == 0 else r.stderr.strip()


# ---------- backend ----------

def tmux_windows(team: Team) -> List[str]:
    r = subprocess.run(
        ["tmux", "list-windows", "-t", tmux_session(team), "-F", "#{window_name}"],
        capture_output=True, text=True,
    )
    return r.stdout.split() if r.returncode == 0 else []


def start(team: Team, s: Session, argv: List[str], backend: str, say=print) -> None:
    cwd = str(team.cwd(s))
    if backend == "tmux":
        name, cmd = tmux_session(team), shlex.join(argv)
        has = subprocess.run(["tmux", "has-session", "-t", name], capture_output=True)
        head = (["new-window", "-d", "-t", name] if has.returncode == 0
                else ["new-session", "-d", "-s", name])
        subprocess.run(["tmux", *head, "-n", s.name, "-c", cwd, cmd], check=True)
        # Không cho tmux đổi tên cửa sổ, vì `status` và `down` tìm theo tên.
        subprocess.run(["tmux", "set-window-option", "-t", f"{name}:{s.name}",
                        "automatic-rename", "off"], capture_output=True)
    elif backend == "wt":
        subprocess.Popen(["wt", "-w", tmux_session(team), "new-tab", "--title", s.name,
                          "-d", cwd, "--", *argv])
    else:
        join = subprocess.list2cmdline if os.name == "nt" else shlex.join
        say(f"cd {join([cwd])} && {join(argv)}")


def up(team: Team, backend: str, only: Optional[List[str]] = None, say=print) -> int:
    running = tmux_windows(team) if backend == "tmux" else []
    failed = 0
    for s in team.sessions:
        if only and s.name not in only:
            continue
        if s.name in running:
            say(f"{s.name}: đang chạy, bỏ qua")
            continue
        err = ensure_worktree(team, s)
        if err:
            say(f"{s.name}: không tạo được worktree: {err}")
            failed += 1
            continue
        start(team, s, prepare(team, s), backend, say)
        if backend != "print":
            say(f"{s.name}: đã bật ({s.model}) tại {team.cwd(s)}")
    if backend == "tmux" and not failed:
        say(f"Xem các phiên: tmux attach -t {tmux_session(team)}")
    return 1 if failed else 0


def down(team: Team, backend: str, only: Optional[List[str]] = None, say=print) -> int:
    if backend != "tmux":
        say("Backend này không tắt phiên tự động được; hãy đóng các tab của phiên.")
        return 0
    running = tmux_windows(team)
    for s in team.sessions:
        if (only and s.name not in only) or s.name not in running:
            continue
        subprocess.run(["tmux", "kill-window", "-t", f"{tmux_session(team)}:{s.name}"])
        say(f"{s.name}: đã tắt")
    say("Worktree và nhánh được giữ nguyên.")
    return 0


def status(team: Team, backend: str, say=print) -> int:
    running = tmux_windows(team) if backend == "tmux" else None
    say(f"Dự án {team.project} · {team.root}")
    for s in team.sessions:
        state = "?" if running is None else ("chạy" if s.name in running else "tắt")
        path = team.cwd(s)
        if not s.worktree:
            tree = "thư mục gốc"
        elif not (path / ".git").exists():
            tree = "worktree chưa tạo"
        else:
            dirty = len(_git(path, "status", "--porcelain").stdout.splitlines())
            head = _git(path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            tree = f"{head}, {dirty} file chưa commit"
        say(f"  {s.name:<28} {s.role:<10} {s.model:<8} {state:<5} {tree}")
    return 0
