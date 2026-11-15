#!/usr/bin/env python3
# coding: utf-8
"""Local static server for playing the converted game in a browser (127.0.0.1 only).

Usage:
  python serve.py --project <web-project-dir> [--port 8768]
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description="在浏览器试玩转换后的游戏（仅本机）")
    ap.add_argument("--project", default=".", help="web 项目目录（含 index.html）")
    ap.add_argument("--port", type=int, default=8768)
    args = ap.parse_args()
    root = Path(args.project).resolve()
    if not (root / "index.html").is_file():
        ap.exit(1, "项目目录缺少 index.html：%s\n" % root)
    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    try:
        with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
            print("打开 http://127.0.0.1:%d/ 试玩（调试静音加 ?muted=1）；按 Ctrl+C 结束。" % args.port,
                  flush=True)
            server.serve_forever()
    except OSError as e:
        ap.exit(1, "无法启动：%s。端口占用时换端口：--port %d\n" % (e, args.port + 1))


if __name__ == "__main__":
    raise SystemExit(main())
