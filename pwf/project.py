"""Khảo sát dự án và sinh cấu hình `.workflow/` (lệnh `pwf init`)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__
from .team import TEAM_FILE, WORKFLOW_DIR

GRAPH_MIN_FILES = 500  # dưới mức này công dựng đồ thị không được bù lại
GRAPH_DIR = "graphify-out"
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "target", ".next", ".idea", ".vscode", GRAPH_DIR, WORKFLOW_DIR,
}
LANGUAGES = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rs": "Rust",
    ".cs": "C#", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".c": "C",
    ".cpp": "C++", ".h": "C/C++", ".sql": "SQL", ".vue": "Vue", ".dart": "Dart",
}
GITIGNORE_LINES = [f"{WORKFLOW_DIR}/run/", f"{WORKFLOW_DIR}/log/", f"{GRAPH_DIR}/"]


@dataclass
class Survey:
    root: Path
    is_git: bool
    main_branch: str
    files: List[str]
    languages: Dict[str, int]

    @property
    def code_files(self) -> List[str]:
        return [f for f in self.files if Path(f).suffix.lower() in LANGUAGES]


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def survey(root: Path) -> Survey:
    is_git = _git(root, "rev-parse", "--is-inside-work-tree") == "true"
    listed = _git(root, "ls-files", "-z") if is_git else None
    if listed is not None:
        files = [f for f in listed.split("\0") if f]
    else:
        files = []
        for base, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            rel = Path(base).relative_to(root)
            files += [(rel / n).as_posix() for n in names]
    langs = Counter(
        LANGUAGES[Path(f).suffix.lower()] for f in files if Path(f).suffix.lower() in LANGUAGES
    )
    branch = (_git(root, "symbolic-ref", "--short", "HEAD") if is_git else None) or "main"
    return Survey(root, is_git, branch, files, dict(langs.most_common()))


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "project"


def propose_areas(files: List[str], limit: int = 3) -> List[tuple]:
    """Đề xuất phạm vi worker theo thư mục: [(thư mục, số file)], lớn trước.

    Nếu một thư mục cấp một chiếm hơn 70% (ví dụ `src/`), chia theo cấp hai.
    """
    def group(depth: int) -> Counter:
        c: Counter = Counter()
        for f in files:
            parts = f.split("/")
            if len(parts) > depth:
                c["/".join(parts[:depth])] += 1
        return c

    top = group(1)
    if top and files and top.most_common(1)[0][1] > 0.7 * len(files):
        deeper = group(2)
        if len(deeper) > 1:
            top = deeper
    return top.most_common(limit)


def render_team(prefix: str, main_branch: str, dirname: str, areas: List[tuple]) -> str:
    def worker(area: str, commented: bool) -> str:
        short = slug(area.split("/")[-1])
        text = (
            f"  - name: {prefix}-{short}\n"
            f"    role: worker\n"
            f"    model: haiku\n"
            f"    permission_mode: acceptEdits\n"
            f"    inbound: accept\n"
            f"    worktree: ../{dirname}.worktrees/{short}\n"
            f"    can_send_to: [{prefix}-builder]\n"
            f"    scope: [{area}/]\n"
        )
        if commented:
            text = "".join(f"  # {line[2:]}" if line.strip() else line
                           for line in text.splitlines(keepends=True))
        return text

    first = areas[0][0] if areas else None
    worker_name = f"{prefix}-{slug(first.split('/')[-1])}" if first else f"{prefix}-worker"
    out = [
        "# Cấu hình đội hình cho dự án này. Sửa rồi chạy `pwf up`.\n"
        "# `pwf init` chạy lại sẽ không ghi đè file này.\n"
        f"toolkit_version: {__version__}\n"
        f"project: {prefix}        # tiền tố của mọi tên phiên\n"
        f"main_branch: {main_branch}\n"
        "\n"
        "# permission_mode: default | acceptEdits | plan | auto | dontAsk\n"
        "# inbound (crossSessionInbound): accept | hold | refuse\n"
        "# can_send_to: hook của pwf chặn mọi SendMessage tới phiên ngoài danh sách\n"
        "sessions:\n"
        f"  - name: {prefix}-architect\n"
        "    role: architect\n"
        "    model: opus\n"
        "    permission_mode: default\n"
        "    inbound: hold            # tin đến được giữ lại chờ bạn thả\n"
        f"    can_send_to: [{prefix}-builder]\n"
        "\n"
        f"  - name: {prefix}-builder\n"
        "    role: builder\n"
        "    model: sonnet\n"
        "    permission_mode: acceptEdits\n"
        "    inbound: accept\n"
        f"    worktree: ../{dirname}.worktrees/builder\n"
        f"    can_send_to: [{prefix}-architect, {worker_name}]\n"
        "\n"
    ]
    if first:
        out.append(worker(first, commented=False))
    else:
        out.append(
            f"  - name: {worker_name}\n    role: worker\n    model: haiku\n"
            "    permission_mode: acceptEdits\n    inbound: accept\n"
            f"    worktree: ../{dirname}.worktrees/worker\n"
            f"    can_send_to: [{prefix}-builder]\n    scope: []\n"
        )
    if len(areas) > 1:
        out.append(
            "\n  # Worker đề xuất thêm theo thư mục. Bỏ dấu # để bật, và thêm tên\n"
            f"  # vào can_send_to của {prefix}-builder.\n"
        )
        out += [worker(a, commented=True) for a, _ in areas[1:]]
    return "".join(out)


ROLES_README = """\
# Ghi đè prompt vai trò cho dự án này

Prompt mặc định nằm trong bộ công cụ (`pwf/templates/roles/`). Để bổ sung riêng
cho dự án, tạo file ở đây; nội dung được nối vào sau prompt mặc định:

- `architect.md`, `builder.md`, `worker.md`: áp dụng cho mọi phiên của vai trò.
- `<tên-phiên>.md` (ví dụ `shop-backend.md`): áp dụng cho đúng một phiên.
"""


def update_gitignore(root: Path) -> List[str]:
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    have = {line.strip() for line in existing.splitlines()}
    missing = [line for line in GITIGNORE_LINES if line not in have]
    if missing:
        sep = "" if not existing or existing.endswith("\n") else "\n"
        path.write_text(existing + sep + "\n".join(missing) + "\n", encoding="utf-8")
    return missing


def build_graph(root: Path) -> Optional[str]:
    """Dựng đồ thị chỉ từ code (không gọi LLM). Trả về lỗi, hoặc None nếu xong."""
    exe = shutil.which("graphify")
    if not exe:
        return "chưa cài graphify (pip install graphifyy)"
    env = dict(os.environ, GRAPHIFY_BACKEND="none", GRAPHIFY_QUERY_LOG_DISABLE="1")
    try:
        subprocess.run([exe, "update", "."], cwd=root, env=env, check=True,
                       capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        return f"graphify lỗi: {(e.stderr or e.stdout or '').strip()[-300:]}"
    return None


def init(root: Path, prefix: Optional[str], graph: Optional[bool], say=print) -> None:
    root = root.resolve()
    sv = survey(root)
    prefix = slug(prefix or root.name)
    code = sv.code_files
    langs = ", ".join(f"{k} ({v})" for k, v in list(sv.languages.items())[:4]) or "không rõ"
    say(f"Dự án: {root}")
    say(f"  git: {'có' if sv.is_git else 'KHÔNG'} · {len(sv.files)} file · ngôn ngữ: {langs}")
    if not sv.is_git:
        say("  Cảnh báo: không phải repo git, `pwf up` sẽ không tạo được worktree.")

    wf = root / WORKFLOW_DIR
    (wf / "roles").mkdir(parents=True, exist_ok=True)
    team_path = wf / TEAM_FILE
    if team_path.exists():
        say(f"  Giữ nguyên {team_path.relative_to(root)} (đã có).")
    else:
        areas = propose_areas(code or sv.files)
        team_path.write_text(
            render_team(prefix, sv.main_branch, root.name, areas), encoding="utf-8"
        )
        say(f"  Đã ghi {team_path.relative_to(root)}; worker đề xuất: "
            + (", ".join(f"{a} ({n} file)" for a, n in areas) or "không có"))
    readme = wf / "roles" / "README.md"
    if not readme.exists():
        readme.write_text(ROLES_README, encoding="utf-8")

    added = update_gitignore(root)
    if added:
        say(f"  Đã thêm vào .gitignore: {', '.join(added)}")

    want_graph = graph if graph is not None else len(sv.files) >= GRAPH_MIN_FILES
    if not want_graph:
        say(f"  Bỏ qua đồ thị (dưới {GRAPH_MIN_FILES} file; ép bằng --graph).")
    else:
        err = build_graph(root)
        say(f"  Đồ thị: {'đã dựng trong ' + GRAPH_DIR + '/' if err is None else 'bỏ qua, ' + err}")
    say(f"Tiếp theo: xem lại {WORKFLOW_DIR}/{TEAM_FILE} rồi chạy `pwf up`.")
