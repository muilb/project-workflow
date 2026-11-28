"""pwf: bộ lệnh điều phối nhiều phiên Claude Code cho một dự án."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, checks, guard, launch, messages, project
from . import router as router_mod
from . import team as team_mod


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pwf", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="khảo sát dự án và sinh .workflow/")
    i.add_argument("path", nargs="?", default=".")
    i.add_argument("--prefix", help="tiền tố tên phiên (mặc định: tên thư mục)")
    g = i.add_mutually_exclusive_group()
    g.add_argument("--graph", dest="graph", action="store_true", default=None,
                   help="luôn dựng đồ thị graphify")
    g.add_argument("--no-graph", dest="graph", action="store_false",
                   help="không dựng đồ thị")

    for name, text in (("up", "bật các phiên"), ("down", "tắt các phiên"),
                       ("status", "xem trạng thái")):
        c = sub.add_parser(name, help=text)
        c.add_argument("--backend", choices=launch.BACKENDS, default=None,
                       help="tmux, wt (Windows Terminal) hoặc print (chỉ in lệnh)")
        if name != "status":
            c.add_argument("sessions", nargs="*", help="chỉ các phiên này")

    sub.add_parser("tasks", help="trạng thái các task theo sổ tin")

    o = sub.add_parser("reopen", help="đặt lại bộ đếm tin của một task đã chạm giới hạn")
    o.add_argument("task")
    sub.add_parser("check", help="rà cấu hình và rào chắn của dự án")

    r = sub.add_parser("route", help="hỏi router một tin sẽ được xử lý thế nào, không gửi")
    r.add_argument("--from", dest="sender", required=True, help="tên phiên gửi")
    r.add_argument("--to", required=True, help="tên phiên định gửi")
    r.add_argument("text", help="nội dung tin; '-' để đọc từ stdin")

    h = sub.add_parser("guard", help="hook PreToolUse cho SendMessage (Claude Code gọi)")
    h.add_argument("--root", required=True)
    h.add_argument("--session", required=True)
    return p


def route(team, sender: str, to: str, text: str) -> int:
    """Chạy đúng bước router của hook nhưng không gửi và không ghi sổ."""
    r = router_mod.JevRouter(router_mod.load_config(team.root))
    me, target = team.session(sender), team.session(to)
    routed = text.lstrip().startswith("[pwf:assign]") and target.role == "worker"
    d = r.decide(text, to, router_mod.candidates_for(team, me) if routed else {})
    print(json.dumps({"action": d.action, "to": d.to or to, "reason": d.reason,
                      "model": d.model, "error": d.error, "answers": d.answers},
                     ensure_ascii=False, indent=2))
    return 0 if d.action != "block" else 2


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        # Console Windows mặc định không in được tiếng Việt.
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "init":
            project.init(Path(args.path), args.prefix, args.graph)
            return 0
        if args.cmd == "guard":
            return guard.main(args.root, args.session)
        team = team_mod.load(team_mod.find_root(Path.cwd()))
        backend = getattr(args, "backend", None) or launch.default_backend()
        if args.cmd == "route":
            return route(team, args.sender, args.to,
                         sys.stdin.read() if args.text == "-" else args.text)
        if args.cmd == "reopen":
            if not messages.reopen(team.root, args.task):
                raise team_mod.TeamError(f"Không có task '{args.task}' trong sổ tin")
            print(f"{args.task}: đã mở lại")
            return 0
        if args.cmd == "check":
            return 1 if checks.report(checks.run(team)) else 0
        if args.cmd == "tasks":
            return launch.tasks(team)
        if args.cmd == "status":
            return launch.status(team, backend)
        unknown = set(args.sessions) - {s.name for s in team.sessions}
        if unknown:
            raise team_mod.TeamError(f"Không có phiên: {', '.join(sorted(unknown))}")
        if args.cmd == "up" and checks.report(checks.run(team)):
            print("pwf: sửa các lỗi trên rồi chạy lại `pwf up`.", file=sys.stderr)
            return 1
        fn = launch.up if args.cmd == "up" else launch.down
        return fn(team, backend, args.sessions or None)
    except (team_mod.TeamError, router_mod.RouterError) as e:
        print(f"pwf: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
