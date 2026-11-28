"""Router: quyết định một tin giao việc nên đi đâu, và có được gửi không.

`Router` là giao diện chung; `JevRouter` gọi Jev của TypeSafe. Lời gọi Jev thật
chưa được chạy thử (chưa có khóa); dạng request và response theo
docs/reference/jev-api.md.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Callable, Dict, List, Optional

import yaml

from .team import WORKFLOW_DIR, Session, Team

KEY_ENV = "TYPESAFE_API_KEY"
OVERRIDE_FILE = "thresholds.yaml"
STATE_LOG_CHARS = 200


class RouterError(Exception):
    pass


@dataclass
class Decision:
    action: str                      # allow | redirect | block
    reason: str = ""
    to: Optional[str] = None         # người nhận mới khi action là redirect
    answers: dict = field(default_factory=dict)
    model: str = ""
    error: str = ""


def _merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(root: Path) -> dict:
    text = resources.files("pwf").joinpath("templates/router.yaml").read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    override = root / WORKFLOW_DIR / OVERRIDE_FILE
    if override.is_file():
        try:
            cfg = _merge(cfg, yaml.safe_load(override.read_text(encoding="utf-8")) or {})
        except yaml.YAMLError as e:
            raise RouterError(f"Không đọc được {override}: {e}") from e
    return cfg


def http_post(cfg: dict, body: dict) -> dict:
    key = os.environ.get(KEY_ENV)
    if not key:
        raise RouterError(f"Chưa đặt biến môi trường {KEY_ENV}")
    req = urllib.request.Request(
        cfg["endpoint"], data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    attempts = int(cfg.get("retries", 1)) + 1
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=float(cfg.get("timeout_seconds", 10))) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 529) and attempt + 1 < attempts:
                time.sleep(1 + attempt)
                continue
            raise RouterError(f"Jev trả mã {e.code}") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise RouterError(f"Không gọi được Jev: {e}") from e
    raise RouterError("Jev không trả lời")


def candidates_for(team: Team, sender: Session) -> Dict[str, str]:
    """Các worker mà phiên gửi được phép giao việc, kèm mô tả phạm vi."""
    out = {}
    for name in sender.can_send_to:
        s = team.session(name)
        if s.role == "worker":
            out[name] = s.description or ("Phạm vi: " + (", ".join(s.scope) or "toàn bộ dự án"))
    return out


class JevRouter:
    def __init__(self, cfg: dict, post: Optional[Callable[[dict, dict], dict]] = None):
        self.cfg = cfg
        self.post = post or http_post

    def questions(self, candidates: Dict[str, str]) -> dict:
        q = self.cfg["questions"]
        out = {"leaks": q["leaks"]}
        if candidates:
            listing = "\n".join(f"- {n}: {d}" for n, d in candidates.items())
            fits = dict(q["fits_any"])
            fits["instructions"] = f"{fits['instructions']}\nDanh sách phiên:\n{listing}"
            out["fits_any"] = fits
            out["task_size"] = q["task_size"]
        if len(candidates) > 1:  # choice cần ít nhất hai lựa chọn
            out["recipient"] = dict(q["recipient"], criteria=candidates)
        return out

    def decide(self, text: str, target: str, candidates: Dict[str, str]) -> Decision:
        """`candidates` rỗng nghĩa là tin không cần chọn người nhận, chỉ kiểm tra rò rỉ."""
        try:
            resp = self.post(self.cfg, {"model": self.cfg["model"], "state": text,
                                        "questions": self.questions(candidates)})
            answers = resp["answers"]
            return self._apply(answers, target, candidates, str(resp.get("model", "")))
        except (RouterError, KeyError, TypeError, ValueError) as e:
            return self._on_error(f"{type(e).__name__}: {e}", bool(candidates))

    def _on_error(self, error: str, routed: bool) -> Decision:
        if routed and self.cfg.get("on_error", "escalate") == "escalate":
            return Decision("block", error=error, reason=(
                "Router không trả lời được nên chưa xác nhận được người nhận và độ lớn "
                "task. Tự làm task này, hoặc gửi architect một tin `blocked` để xin quyết định."))
        return Decision("allow", error=error, reason="router lỗi, cho qua")

    def _apply(self, a: dict, target: str, candidates: Dict[str, str], model: str) -> Decision:
        th = self.cfg["thresholds"]
        d = lambda action, reason, to=None: Decision(action, reason, to, a, model)
        if float(a["leaks"]["noul"]) > th["leaks_block"]:
            return d("block", "Tin có vẻ chứa bí mật hoặc chép nguyên một khối ngữ cảnh "
                              "dài. Bỏ phần đó, nêu đường dẫn file thay vào, rồi gửi lại.")
        if not candidates:
            return d("allow", "không rò rỉ")
        if float(a["fits_any"]["noul"]) < th["fits_any_min"]:
            return d("block", "Task này không thuộc phạm vi của worker nào. Tự làm, hoặc "
                              "gửi architect một tin `blocked` để xin chia lại việc.")
        size = a["task_size"]
        if float(size["confidence"]) < th["size_confidence_min"]:
            return d("block", "Không rõ task lớn cỡ nào. Mô tả lại cụ thể hơn, hoặc gửi "
                              "architect một tin `blocked` để xin chia nhỏ.")
        if float(size["score"]) > th["builder_max_size"]:
            return d("block", "Task cần thiết kế hoặc phải chia nhỏ. Gửi architect một "
                              "tin `blocked` để xin chia việc, không giao nguyên cho worker.")
        if float(size["score"]) > th["worker_max_size"]:
            return d("block", "Task chạm nhiều module, quá lớn cho một worker. Tự làm, "
                              "hoặc tách thành các task nằm gọn trong phạm vi từng worker.")
        if "recipient" in a:
            choice = a["recipient"]["choice"]
            p = float(a["recipient"]["probabilities"][choice])
            if choice != target and choice in candidates and p >= th["recipient_min"]:
                return d("redirect", f"router chọn {choice} (xác suất {p:.2f})", choice)
        return d("allow", "giữ người nhận do phiên gửi chọn")


def for_team(team: Team) -> Optional[JevRouter]:
    if team.router == "none":
        return None
    return JevRouter(load_config(team.root))


def log_decision(root: Path, sender: str, target: str, text: str, d: Decision) -> None:
    path = root / WORKFLOW_DIR / "log" / "router.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "from": sender, "to": target,
             "action": d.action, "final_to": d.to or target, "reason": d.reason,
             "model": d.model, "answers": d.answers,
             "state": " ".join(text.split())[:STATE_LOG_CHARS]}
    if d.error:
        entry["error"] = d.error
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
