"""pwf: bộ lệnh điều phối nhiều phiên Claude Code cho một dự án."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, guard, launch, project
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

    h = sub.add_parser("guard", help="hook PreToolUse cho SendMessage (Claude Code gọi)")
    h.add_argument("--root", required=True)
    h.add_argument("--session", required=True)
    return p


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
        backend = args.backend or launch.default_backend()
        if args.cmd == "status":
            return launch.status(team, backend)
        unknown = set(args.sessions) - {s.name for s in team.sessions}
        if unknown:
            raise team_mod.TeamError(f"Không có phiên: {', '.join(sorted(unknown))}")
        fn = launch.up if args.cmd == "up" else launch.down
        return fn(team, backend, args.sessions or None)
    except team_mod.TeamError as e:
        print(f"pwf: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
