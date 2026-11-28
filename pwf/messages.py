"""Bốn mẫu tin cố định giữa các phiên, và luồng ai được gửi loại nào cho ai.

Một tin hợp lệ có dạng:

    [pwf:assign] T-12
    Mục tiêu: ...
    File: ...
    Xong khi: ...

Dòng đầu là loại tin và mã task; các dòng sau là các trường bắt buộc của loại
đó. Giá trị của một trường có thể kéo dài nhiều dòng.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .team import WORKFLOW_DIR


@dataclass(frozen=True)
class MessageType:
    key: str
    title: str
    fields: Tuple[Tuple[str, str], ...]  # (nhãn, gợi ý nội dung)
    optional: Tuple[Tuple[str, str], ...] = ()


TYPES: Dict[str, MessageType] = {
    t.key: t
    for t in (
        MessageType(
            "assign", "Giao việc",
            (("Mục tiêu", "việc cần làm, trong một hai câu"),
             ("File", "các file hoặc thư mục liên quan"),
             ("Xong khi", "điều kiện kiểm tra được, ví dụ test nào phải qua")),
            (("Ngữ cảnh", "phần trích từ đồ thị hoặc ghi chú thiết kế, nếu có"),),
        ),
        MessageType(
            "result", "Kết quả",
            (("Đã làm", "tóm tắt thay đổi"),
             ("Commit", "nhánh và mã commit"),
             ("Test", "lệnh đã chạy và kết quả; ghi rõ nếu chưa chạy")),
        ),
        MessageType(
            "blocked", "Bị chặn",
            (("Vướng ở", "điều gì cản, kèm lỗi nguyên văn nếu có"),
             ("Cần", "quyết định hoặc thông tin cần từ phiên nhận")),
        ),
        MessageType(
            "signoff", "Ký duyệt",
            (("Quyết định", "`duyệt` hoặc `trả lại`"),
             ("Lý do", "đã kiểm tra gì; nếu trả lại thì cần sửa gì")),
        ),
    )
}

# Luồng chuẩn: (vai trò gửi, vai trò nhận) -> các loại tin được phép.
FLOW: Dict[Tuple[str, str], Tuple[str, ...]] = {
    ("architect", "builder"): ("assign", "signoff"),
    ("builder", "worker"): ("assign",),
    ("builder", "architect"): ("result", "blocked"),
    ("worker", "builder"): ("result", "blocked"),
}

HEADER_RE = re.compile(r"^\[pwf:([a-z]+)\][ \t]+([A-Za-z0-9][A-Za-z0-9._-]*)[ \t]*$")
DECISIONS = ("duyệt", "trả lại")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().casefold()


@dataclass
class Message:
    type: str
    task: str
    fields: Dict[str, str]


def template(key: str) -> str:
    t = TYPES[key]
    lines = [f"[pwf:{t.key}] <mã-task>"]
    lines += [f"{label}: <{hint}>" for label, hint in t.fields]
    lines += [f"{label}: <{hint}> (không bắt buộc)" for label, hint in t.optional]
    return "\n".join(lines)


def parse(text: str) -> Tuple[Optional[Message], Optional[str]]:
    """Trả về (tin, None) nếu hợp lệ, hoặc (None, lý do) nếu không."""
    lines = unicodedata.normalize("NFC", text or "").strip().splitlines()
    m = HEADER_RE.match(lines[0].strip()) if lines else None
    if not m:
        return None, "Dòng đầu phải có dạng `[pwf:<loại>] <mã-task>`, ví dụ `[pwf:assign] T-12`."
    key, task = m.groups()
    if key not in TYPES:
        return None, f"Loại tin '{key}' không tồn tại. Các loại: {', '.join(TYPES)}."
    t = TYPES[key]
    labels = {_norm(label): label for label, _ in t.fields + t.optional}
    fields: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in lines[1:]:
        head, sep, rest = line.partition(":")
        if sep and _norm(head) in labels:
            current = labels[_norm(head)]
            fields[current] = [rest.strip()]
        elif current:
            fields[current].append(line.strip())
    values = {k: "\n".join(v).strip() for k, v in fields.items()}
    missing = [label for label, _ in t.fields if not values.get(label)]
    if missing:
        return None, f"Tin `{key}` thiếu trường: {', '.join(missing)}."
    if key == "signoff" and not _norm(values["Quyết định"]).startswith(DECISIONS):
        return None, "Trường `Quyết định` phải bắt đầu bằng `duyệt` hoặc `trả lại`."
    return Message(key, task, values), None


def validate(text: str, sender_role: str, recipient_role: str) -> Tuple[Optional[Message], Optional[str]]:
    allowed = FLOW.get((sender_role, recipient_role), ())
    msg, err = parse(text)
    if msg and msg.type not in allowed:
        err = f"Phiên {sender_role} không gửi tin `{msg.type}` cho phiên {recipient_role}."
    if err is None:
        return msg, None
    if not allowed:
        return None, f"{err} Không có loại tin nào được phép giữa hai vai trò này."
    shapes = "\n\n".join(template(k) for k in allowed)
    return None, f"{err} Gửi lại theo đúng một trong các mẫu sau:\n\n{shapes}"


def prompt_section(role: str, peer_roles: List[str]) -> str:
    """Phần mô tả mẫu tin để nối vào prompt vai trò."""
    sends = sorted({k for r in peer_roles for k in FLOW.get((role, r), ())},
                   key=list(TYPES).index)
    receives = sorted({k for r in peer_roles for k in FLOW.get((r, role), ())},
                      key=list(TYPES).index)
    out = ["## Mẫu tin", "",
           "Mọi tin gửi cho phiên khác phải theo đúng một mẫu dưới đây; tin sai mẫu "
           "bị chặn trước khi gửi. Dòng đầu giữ nguyên dạng `[pwf:<loại>] <mã-task>`. "
           "Mã task do phiên giao việc đặt (ví dụ `T-12`); mọi tin về sau của task đó "
           "dùng lại đúng mã ấy. Cần hỏi lại điều gì thì dùng mẫu `blocked`."]
    for k in sends:
        out += ["", f"**{TYPES[k].title}** (`{k}`):", "", "```", template(k), "```"]
    if receives:
        names = ", ".join(f"`{k}` ({TYPES[k].title.lower()})" for k in receives)
        out += ["", f"Bạn sẽ nhận các loại tin: {names}."]
    return "\n".join(out)


# ---------- sổ tin ----------

def log_path(root: Path) -> Path:
    return root / WORKFLOW_DIR / "log" / "messages.jsonl"


def record(root: Path, sender: str, recipient: str, msg: Message) -> None:
    path = log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "from": sender, "to": recipient,
             "type": msg.type, "task": msg.task}
    if msg.type == "signoff":
        entry["decision"] = "approved" if _norm(msg.fields["Quyết định"]).startswith("duyệt") else "returned"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


STATE = {"assign": "đang làm", "result": "chờ xem", "blocked": "bị chặn"}


def _entries(root: Path) -> List[dict]:
    path = log_path(root)
    out = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("task"):
                out.append(e)
    return out


def tasks(root: Path) -> List[dict]:
    """Trạng thái mới nhất của từng task, theo thứ tự xuất hiện.

    `count` là số tin kể từ lần mở lại gần nhất; hook so nó với giới hạn.
    """
    latest: Dict[str, dict] = {}
    for e in _entries(root):
        prev = latest.get(e["task"], {})
        if e.get("type") == "reopen":
            if prev:
                prev["count"] = 0
            continue
        e["count"] = prev.get("count", 0) + 1
        latest[e["task"]] = e
    for e in latest.values():
        if e["type"] == "signoff":
            e["state"] = "xong" if e.get("decision") == "approved" else "trả lại"
        else:
            e["state"] = STATE.get(e["type"], e["type"])
    return list(latest.values())


def count(root: Path, task: str) -> int:
    return next((e["count"] for e in tasks(root) if e["task"] == task), 0)


def reopen(root: Path, task: str) -> bool:
    """Đặt lại bộ đếm tin của một task. Trả về False nếu task chưa có trong sổ."""
    if not any(e["task"] == task for e in tasks(root)):
        return False
    with log_path(root).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "type": "reopen", "task": task}) + "\n")
    return True
