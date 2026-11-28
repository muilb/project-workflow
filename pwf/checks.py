"""Rà cấu hình và rào chắn của một dự án (`pwf check`, và trước mỗi `pwf up`)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import List, Optional, Tuple

from .project import GITIGNORE_LINES
from .router import KEY_ENV, OVERRIDE_FILE
from .team import TEAM_FILE, WORKFLOW_DIR, Team

ERROR, WARN = "LỖI", "CẢNH BÁO"
# Cross-session messaging cần v2.1.224; Windows gốc cần v2.1.234.
MIN_VERSION = (2, 1, 234) if os.name == "nt" else (2, 1, 224)
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|authorization)\s*[:=]\s*\S+|bearer\s+\S+|sk-[A-Za-z0-9_-]{16,}"
)

Finding = Tuple[str, str]


def claude_version() -> Optional[Tuple[int, ...]]:
    exe = shutil.which("claude")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(x) for x in m.groups()) if m else None


def run(team: Team, version: Optional[Tuple[int, ...]] = None, env=None) -> List[Finding]:
    env = os.environ if env is None else env
    out: List[Finding] = []
    version = version or claude_version()
    if version is None:
        out.append((ERROR, "Không chạy được `claude --version`; Claude Code chưa cài hoặc không có trong PATH."))
    elif version < MIN_VERSION:
        need, have = (".".join(map(str, v)) for v in (MIN_VERSION, version))
        out.append((ERROR, f"Claude Code {have} quá cũ; nhắn tin giữa các phiên cần từ {need}."))

    # Khóa và mật khẩu không được nằm trong file cấu hình sẽ commit.
    for name in (TEAM_FILE, OVERRIDE_FILE):
        path = team.root / WORKFLOW_DIR / name
        if path.is_file():
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if SECRET_RE.search(line.split("#", 1)[0]):
                    out.append((ERROR, f"{WORKFLOW_DIR}/{name} dòng {n} trông như chứa khóa hoặc "
                                       f"mật khẩu. Khóa Jev chỉ đặt trong biến môi trường {KEY_ENV}."))

    for s in team.sessions:
        if s.role == "architect" and s.inbound != "hold":
            out.append((WARN, f"{s.name}: architect nên để inbound là hold, để tin đến chờ bạn xem."))
        if s.role == "worker" and s.inbound != "accept":
            out.append((WARN, f"{s.name}: worker để inbound là {s.inbound} sẽ không tự nhận việc."))
        if s.role == "worker" and not s.scope:
            out.append((WARN, f"{s.name}: worker chưa có scope, nên được sửa toàn bộ dự án."))
        if s.role != "architect" and s.permission_mode in ("auto", "dontAsk"):
            out.append((WARN, f"{s.name}: permission_mode {s.permission_mode} cho phiên chạy lệnh "
                              "mà không hỏi; tin từ phiên khác có thể kéo nó đi sai."))
        if not s.can_send_to:
            out.append((WARN, f"{s.name}: can_send_to rỗng, phiên này không gửi được tin nào."))
    shared = [s.name for s in team.sessions if not s.worktree]
    if len(shared) > 1:
        out.append((WARN, f"Các phiên {', '.join(shared)} cùng chạy ở thư mục gốc và có thể ghi đè file của nhau."))

    ignore = team.root / ".gitignore"
    have = {l.strip() for l in ignore.read_text(encoding="utf-8").splitlines()} if ignore.is_file() else set()
    missing = [l for l in GITIGNORE_LINES if l not in have]
    if missing:
        out.append((WARN, f".gitignore thiếu: {', '.join(missing)} (chạy lại `pwf init`)."))

    if team.router == "jev" and not env.get(KEY_ENV):
        out.append((WARN, f"router là jev nhưng chưa đặt {KEY_ENV}; mọi tin giao việc cho worker sẽ bị chặn."))
    return out


def report(findings: List[Finding], say=print) -> bool:
    """In kết quả; trả về True nếu có lỗi."""
    for level, text in findings:
        say(f"{level}: {text}")
    return any(level == ERROR for level, _ in findings)
