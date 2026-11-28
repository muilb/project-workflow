"""Hook PreToolUse cho SendMessage.

Chặn tin gửi tới phiên ngoài `can_send_to`, và tin không theo một trong bốn mẫu
của `pwf.messages`. Tin được cho qua thì ghi vào sổ tin của dự án.

Claude Code đưa lời gọi công cụ vào stdin dưới dạng JSON. Thoát với mã 2 thì lời
gọi bị chặn và nội dung stderr được trả về cho Claude (đã kiểm chứng trên
v2.1.332, xem docs/phase0-results.md).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, TextIO

from . import messages
from . import team as team_mod

BLOCK = 2


def recipient_of(tool_input: dict) -> Optional[str]:
    value = tool_input.get("to") or tool_input.get("recipient")
    if not isinstance(value, str) or not value.strip():
        return None
    # Khi trùng tên, Claude Code thêm định danh ngắn: "tên [abc123]".
    return value.strip().split()[0]


def check(payload: dict, team: team_mod.Team, sender: str) -> Optional[str]:
    """Trả về lý do chặn, hoặc None nếu cho gửi."""
    if payload.get("tool_name") != "SendMessage":
        return None
    allowed = team.session(sender).can_send_to
    tool_input = payload.get("tool_input") or {}
    target = recipient_of(tool_input)
    if target not in allowed:
        listing = ", ".join(allowed) if allowed else "(không có phiên nào)"
        return (
            f"Phiên {sender} không được gửi tin tới '{target}'. "
            f"Chỉ được gửi tới: {listing}. Không thử lại với tên khác ngoài danh sách này."
        )
    text = tool_input.get("message") or tool_input.get("content") or ""
    msg, err = messages.validate(
        text if isinstance(text, str) else "", team.session(sender).role, team.session(target).role
    )
    if err:
        return err
    messages.record(team.root, sender, target, msg)
    return None


def run(root: Path, sender: str, stdin: TextIO, stderr: TextIO) -> int:
    # Lỗi nào cũng chặn: hook hỏng không được biến thành cho gửi tự do.
    try:
        payload = json.load(stdin)
        reason = check(payload, team_mod.load(root), sender)
    except Exception as e:  # noqa: BLE001
        print(f"pwf guard lỗi, chặn lời gọi: {e}", file=stderr)
        return BLOCK
    if reason:
        print(reason, file=stderr)
        return BLOCK
    return 0


def main(root: str, sender: str) -> int:
    return run(Path(root), sender, sys.stdin, sys.stderr)
