"""Đọc và kiểm tra `.workflow/team.yaml`."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

WORKFLOW_DIR = ".workflow"
TEAM_FILE = "team.yaml"
ROLES = ("architect", "builder", "worker")
INBOUND = ("accept", "hold", "refuse")
ROUTERS = ("none", "jev")
# Không phiên nào được chạy ở chế độ bỏ qua quyền (PLAN.md, giai đoạn 4).
PERMISSION_MODES = ("default", "acceptEdits", "plan", "auto", "dontAsk")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class TeamError(Exception):
    pass


@dataclass
class Session:
    name: str
    role: str
    model: str
    permission_mode: str = "default"
    inbound: str = "accept"
    worktree: Optional[str] = None
    branch: Optional[str] = None
    can_send_to: List[str] = field(default_factory=list)
    scope: List[str] = field(default_factory=list)
    description: Optional[str] = None  # router dùng để mô tả phiên cho Jev


@dataclass
class Team:
    root: Path
    project: str
    main_branch: str
    toolkit_version: str
    sessions: List[Session]
    router: str = "none"
    messages_per_task: int = 12

    def session(self, name: str) -> Session:
        for s in self.sessions:
            if s.name == name:
                return s
        raise TeamError(f"Không có phiên '{name}' trong team.yaml")

    def cwd(self, s: Session) -> Path:
        if not s.worktree:
            return self.root
        return (self.root / s.worktree).resolve()

    @property
    def run_dir(self) -> Path:
        return self.root / WORKFLOW_DIR / "run"


def find_root(start: Path) -> Path:
    """Tìm thư mục chứa `.workflow/team.yaml`, đi ngược lên từ `start`."""
    start = start.resolve()
    for d in (start, *start.parents):
        if (d / WORKFLOW_DIR / TEAM_FILE).is_file():
            return d
    raise TeamError(
        f"Không thấy {WORKFLOW_DIR}/{TEAM_FILE} từ {start} trở lên. Chạy `pwf init` trước."
    )


def load(root: Path) -> Team:
    path = root / WORKFLOW_DIR / TEAM_FILE
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise TeamError(f"Không đọc được {path}: {e}") from e
    return parse(data, root)


def parse(data: dict, root: Path) -> Team:
    if not isinstance(data, dict):
        raise TeamError("team.yaml phải là một map")
    project = str(data.get("project") or "")
    if not NAME_RE.match(project):
        raise TeamError("`project` phải gồm chữ thường, số và dấu gạch ngang")
    raw = data.get("sessions")
    if not isinstance(raw, list) or not raw:
        raise TeamError("`sessions` phải là danh sách có ít nhất một phiên")

    sessions: List[Session] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise TeamError(f"sessions[{i}] phải là một map")
        unknown = set(item) - set(Session.__dataclass_fields__)
        if unknown:
            raise TeamError(f"sessions[{i}] có khóa lạ: {', '.join(sorted(unknown))}")
        for key in ("name", "role", "model"):
            if not item.get(key):
                raise TeamError(f"sessions[{i}] thiếu `{key}`")
        s = Session(**item)
        s.can_send_to = list(s.can_send_to or [])
        s.scope = list(s.scope or [])
        where = f"Phiên '{s.name}'"
        # Mọi phiên cùng người dùng trên máy đều thấy nhau, nên tên phải mang
        # tiền tố dự án để không lẫn với dự án khác.
        if not NAME_RE.match(s.name) or not s.name.startswith(project + "-"):
            raise TeamError(f"{where}: tên phải bắt đầu bằng '{project}-'")
        if s.role not in ROLES:
            raise TeamError(f"{where}: role phải là một trong {ROLES}")
        if s.permission_mode not in PERMISSION_MODES:
            raise TeamError(
                f"{where}: permission_mode phải là một trong {PERMISSION_MODES}"
            )
        if s.inbound not in INBOUND:
            raise TeamError(f"{where}: inbound phải là một trong {INBOUND}")
        sessions.append(s)

    names = [s.name for s in sessions]
    if len(set(names)) != len(names):
        raise TeamError("Tên phiên bị trùng")
    for s in sessions:
        for target in s.can_send_to:
            if target not in names:
                raise TeamError(f"Phiên '{s.name}': can_send_to có '{target}' không tồn tại")
            if target == s.name:
                raise TeamError(f"Phiên '{s.name}': can_send_to không được chứa chính nó")
    trees = [s.worktree for s in sessions if s.worktree]
    if len(set(trees)) != len(trees):
        raise TeamError("Hai phiên dùng chung một worktree")

    router = str(data.get("router") or "none")
    if router not in ROUTERS:
        raise TeamError(f"`router` phải là một trong {ROUTERS}")

    limits = data.get("limits") or {}
    if not isinstance(limits, dict) or set(limits) - {"messages_per_task"}:
        raise TeamError("`limits` chỉ nhận khóa `messages_per_task`")
    per_task = limits.get("messages_per_task", 12)
    if not isinstance(per_task, int) or isinstance(per_task, bool) or per_task < 2:
        raise TeamError("`limits.messages_per_task` phải là số nguyên từ 2 trở lên")

    return Team(
        messages_per_task=per_task,
        router=router,
        root=root,
        project=project,
        main_branch=str(data.get("main_branch") or "main"),
        toolkit_version=str(data.get("toolkit_version") or ""),
        sessions=sessions,
    )
