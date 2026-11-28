"""Hook PreToolUse cho SendMessage.

Chặn tin gửi tới phiên ngoài `can_send_to`, và tin không theo một trong bốn mẫu
của `pwf.messages`. Khi team.yaml bật `router: jev`, hỏi thêm router: nó có thể
chặn tin hoặc đổi người nhận. Tin được cho qua thì ghi vào sổ tin của dự án.

Claude Code đưa lời gọi công cụ vào stdin dưới dạng JSON. Thoát với mã 2 thì lời
gọi bị chặn và nội dung stderr được trả về cho Claude (đã kiểm chứng trên
v2.1.332, xem docs/phase0-results.md).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TextIO

from . import messages
from . import router as router_mod
from . import team as team_mod

BLOCK = 2


def recipient_of(tool_input: dict) -> Optional[str]:
    value = tool_input.get("to") or tool_input.get("recipient")
    if not isinstance(value, str) or not value.strip():
        return None
    # Khi trùng tên, Claude Code thêm định danh ngắn: "tên [abc123]".
    return value.strip().split()[0]


@dataclass
class Outcome:
    block: Optional[str] = None      # lý do chặn
    new_input: Optional[dict] = None  # tool_input đã đổi người nhận


def check(payload: dict, team: team_mod.Team, sender: str,
          router: Optional[router_mod.JevRouter] = None) -> Outcome:
    if payload.get("tool_name") != "SendMessage":
        return Outcome()
    tool_input = payload.get("tool_input") or {}
    me = team.session(sender)
    target = recipient_of(tool_input)
    if target not in me.can_send_to:
        listing = ", ".join(me.can_send_to) if me.can_send_to else "(không có phiên nào)"
        return Outcome(block=(
            f"Phiên {sender} không được gửi tin tới '{target}'. "
            f"Chỉ được gửi tới: {listing}. Không thử lại với tên khác ngoài danh sách này."
        ))
    text = tool_input.get("message") or tool_input.get("content") or ""
    text = text if isinstance(text, str) else ""
    msg, err = messages.validate(text, me.role, team.session(target).role)
    if err:
        return Outcome(block=err)
    # Chặn hai phiên nhắn qua lại vô hạn về cùng một task. Tin ký duyệt vẫn đi
    # được, vì nó khép task lại.
    if msg.type != "signoff" and messages.count(team.root, msg.task) >= team.messages_per_task:
        return Outcome(block=(
            f"Task {msg.task} đã có {team.messages_per_task} tin, chạm giới hạn. Dừng trao "
            f"đổi về task này và báo người dùng tình trạng hiện tại. Người dùng mở lại "
            f"bằng `pwf reopen {msg.task}`. Không đổi mã task để gửi tiếp."
        ))

    new_input = None
    if router:
        # Chỉ tin giao việc cho worker mới cần chọn người nhận và ước lượng độ lớn;
        # các tin khác chỉ kiểm tra rò rỉ.
        routed = msg.type == "assign" and team.session(target).role == "worker"
        candidates = router_mod.candidates_for(team, me) if routed else {}
        d = router.decide(text, target, candidates)
        router_mod.log_decision(team.root, sender, target, text, d, msg.task, msg.type)
        if d.action == "block":
            return Outcome(block=d.reason)
        if d.action == "redirect":
            new_input = dict(tool_input)
            for key in ("to", "recipient"):
                if key in new_input:
                    new_input[key] = d.to
            target = d.to
    messages.record(team.root, sender, target, msg)
    return Outcome(new_input=new_input)


def run(root: Path, sender: str, stdin: TextIO, stderr: TextIO,
        stdout: Optional[TextIO] = None, router=None) -> int:
    # Lỗi nào cũng chặn: hook hỏng không được biến thành cho gửi tự do.
    try:
        payload = json.load(stdin)
        team = team_mod.load(root)
        outcome = check(payload, team, sender, router or router_mod.for_team(team))
    except Exception as e:  # noqa: BLE001
        print(f"pwf guard lỗi, chặn lời gọi: {e}", file=stderr)
        return BLOCK
    if outcome.block:
        print(outcome.block, file=stderr)
        return BLOCK
    if outcome.new_input is not None:
        json.dump({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "allow",
            "updatedInput": outcome.new_input}}, stdout or sys.stdout)
    return 0


def main(root: str, sender: str) -> int:
    return run(Path(root), sender, sys.stdin, sys.stderr)
