#!/usr/bin/env python3
# coding: utf-8
"""Verify a Phaser conversion project against its conversion contract (inventory).

Checks (static; real playability is verified separately by serving and playing):
  1. Asset coverage   - every image/audio/font in the inventory contract exists
                        in the web project (by original basename, or via the
                        optional conversion/asset-map.json rename/convert map).
  2. Shell integrity  - index.html exists and uses a LOCAL phaser.min.js.
  3. Reference scan   - literal references in HTML/CSS/JS (script src, ES
                        imports, Phaser loader calls, fetch) resolve to files
                        inside the project. External URLs are warnings.
  4. JS syntax        - runs `node --check` on each .js file when node exists.

Exit code 1 if any error; warnings do not fail the build but must be reviewed.

Usage:
  python verify_output.py --project <web-project-dir> --inventory <inventory.json>
                          [--asset-map <asset-map.json>]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

REQUIRED_KINDS = ("images", "audio", "fonts")

BASE = None
present = set()
report = None
scanned = set()
_seen_items = set()
shared_basenames = set()
claimed = {}


def rel(p: Path) -> str:
    return p.relative_to(BASE).as_posix()


def resolve_ref(value: str, base_dir: Path):
    """Resolve a literal URL-ish reference. Returns (project_rel|None, problem|None)."""
    value = value.strip()
    if not value or value.startswith(("#", "data:", "blob:", "about:")):
        return None, None
    parsed = urlsplit(value)
    if parsed.scheme in ("http", "https") or value.startswith("//"):
        return None, "external"
    if parsed.scheme or value.startswith("/"):
        return None, "nonportable"
    target = (base_dir / unquote(parsed.path))
    if BASE not in target.resolve().parents and target.resolve() != BASE:
        return None, "outside"
    name = rel(target)
    if not target.is_file():
        # 引用无扩展名（如 'data/levels/Level'）多半是动态拼接的路径片段，
        # 归为 dynamic 提示而非缺失错误（对应 unity_intake 对计算路径的处理思路）
        if not Path(name).suffix:
            return name, "dynamic"
        return name, "missing"
    return name, None


class HtmlRefs(HTMLParser):
    def __init__(self, name: str, base_dir: Path):
        super().__init__()
        self.name, self.base_dir = name, base_dir

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        attr = ("src" if tag in ("script", "img", "audio", "video", "source", "iframe", "track")
                else "href" if tag == "link" else "data" if tag == "object" else None)
        if attr and a.get(attr):
            add_ref(a[attr], self.base_dir, self.name, "html-" + tag)
        if a.get("style"):
            add_css(a["style"], self.base_dir, self.name)


def add_css(text: str, base_dir: Path, source: str):
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    for m in re.finditer(r"url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)|@import\s+['\"]([^'\"]+)['\"]", text):
        add_ref(m.group(1) or m.group(2), base_dir, source, "css")


JS_PATTERNS = [
    (re.compile(r"\b(?:import|export)\s+[^;\n]*?\bfrom\s*['\"]([^'\"]+)['\"]"), "module"),
    (re.compile(r"\bimport\s*['\"]([^'\"]+)['\"]"), "module"),
    (re.compile(r"\bimport\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"), "module"),
    (re.compile(r"\bfetch\s*\(\s*['\"]([^'\"]+)['\"]"), "fetch"),
    (re.compile(r"\.load\s*\.\s*(?:image|audio|svg|json|text|binary|spritesheet|atlas|tilemapTiledJSON)"
                r"\s*\(\s*['\"][^'\"]*['\"]\s*,\s*['\"]([^'\"]+)['\"]"), "phaser-loader"),
    (re.compile(r"\bthis\s*\.\s*load\s*\.\s*(?:image|audio|spritesheet|atlas)\s*\(\s*['\"][^'\"]*['\"]\s*,\s*['\"]([^'\"]+)['\"]"), "phaser-loader"),
]


def add_js(text: str, name: str, document_base: Path):
    base_dir = (BASE / name).parent
    for pattern, kind in JS_PATTERNS:
        for m in pattern.finditer(text):
            add_ref(m.group(1), document_base if kind in ("fetch", "phaser-loader") else base_dir,
                    name, kind)


def add_ref(value: str, base_dir: Path, source: str, kind: str):
    if not value or not value.strip():
        return
    name, problem = resolve_ref(value, base_dir)
    if problem == "external":
        add_unique("warnings", {"kind": "external-url", "source": source, "ref": value.strip()[:200],
                                "note": "外部网络依赖；离线环境不可用，如属字体/CDN需评估"})
    elif problem == "nonportable":
        add_unique("errors", {"kind": "nonportable-ref", "source": source, "ref": value.strip()[:200]})
    elif problem == "outside":
        add_unique("errors", {"kind": "outside-project-ref", "source": source, "ref": value.strip()[:200]})
    elif problem == "missing":
        add_unique("errors", {"kind": "missing-ref", "source": source, "ref": name,
                              "note": "引用的文件不存在"})
    elif problem == "dynamic":
        add_unique("warnings", {"kind": "dynamic-ref", "source": source, "ref": name,
                                "note": "疑似动态拼接路径（无扩展名）；请人工确认目标文件存在"})
    elif name:
        add_unique("references", {"source": source, "kind": kind, "target": name})


def add_unique(bucket: str, item: dict):
    key = json.dumps(item, ensure_ascii=False, sort_keys=True)
    if key not in _seen_items:
        _seen_items.add(key)
        report[bucket].append(item)


def find_asset_match(src: str, basename: str):
    """Locate the migrated copy of a contract asset in the web project.

    Match priority: full preserved path > parent-dir disambiguation (when the
    basename is shared within the contract) > 2-segment suffix > unique
    basename. Returns (path|None, ambiguous_count).
    """
    exact = "assets/" + PurePosixPath(src).as_posix()
    if exact in present:
        return exact, 0
    hits = [n for n in present if PurePosixPath(n).name == basename]
    if len(hits) > 1 or basename in shared_basenames:
        parent = PurePosixPath(src).parent.name
        if parent:
            by_parent = [h for h in hits if f"/{parent}/" in "/" + h]
            if len(by_parent) == 1:
                return by_parent[0], 0
        tail = "/".join(PurePosixPath(src).parts[-2:])
        by_tail = [h for h in present if h.replace("\\", "/").endswith(tail)]
        if len(by_tail) == 1:
            return by_tail[0], 0
        if len(hits) > 1:
            return None, len(hits)
        return None, -1  # basename shared in contract but only one candidate: must be mapped
    if len(hits) == 1:
        return hits[0], 0
    return None, 0


def scan_file(name: str, document_base=None):
    key = (name, str(document_base))
    if key in scanned:
        return
    scanned.add(key)
    p = BASE / name
    if not p.is_file() or p.suffix.lower() not in (".html", ".htm", ".js", ".mjs", ".css"):
        return
    if p.stat().st_size > 4_000_000 or "phaser" in name.lower():
        return  # vendored engine lib: skip internal scanning
    try:
        text = p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return
    if p.suffix.lower() in (".html", ".htm"):
        parser = HtmlRefs(name, p.parent)
        try:
            parser.feed(text)
        except Exception:
            report["warnings"].append({"kind": "html-parse", "source": name})
    elif p.suffix.lower() == ".css":
        add_css(text, p.parent, name)
    else:
        add_js(text, name, document_base or p.parent)


def main() -> int:
    global BASE, present, report, scanned, _seen_items, shared_basenames, claimed
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", required=True, help="Phaser 输出项目目录")
    ap.add_argument("--inventory", required=True, help="inventory.json 路径")
    ap.add_argument("--asset-map", default=None, help="conversion/asset-map.json（改名/转换映射）")
    args = ap.parse_args()

    BASE = Path(args.project).resolve()
    if not BASE.is_dir():
        raise SystemExit("Project dir not found: " + str(BASE))
    inv = json.loads(Path(args.inventory).read_text(encoding="utf-8-sig"))

    report = {"format": "unity2phaser-verify/1", "errors": [], "warnings": [],
              "references": [], "coverage": [], "content": []}
    scanned = set()
    _seen_items = set()
    claimed = {}

    # ---- 1. asset coverage ----
    asset_map = {}
    if args.asset_map and Path(args.asset_map).is_file():
        asset_map = json.loads(Path(args.asset_map).read_text(encoding="utf-8-sig"))
    present = {rel(p) for p in BASE.rglob("*") if p.is_file()}

    required = []
    for kind in REQUIRED_KINDS:
        required += [(n, kind) for n in inv["assets"].get(kind, [])]

    name_counts = {}
    for n, _ in required:
        name_counts[PurePosixPath(n).name] = name_counts.get(PurePosixPath(n).name, 0) + 1
    shared_basenames = {n for n, c in name_counts.items() if c > 1}

    for src, entry in sorted(asset_map.items()):
        target = PurePosixPath(entry.get("target", "")).as_posix() if isinstance(entry, dict) else None
        if not target or target not in present:
            report["errors"].append({"kind": "asset-map-missing-target", "source": src, "target": target,
                                     "note": "asset-map 声明的输出文件不存在"})
    for src, entry in asset_map.items():
        if isinstance(entry, dict) and not (entry.get("operation") or "").strip():
            report["warnings"].append({"kind": "asset-map-no-operation", "source": src,
                                       "note": "改名/转换必须写明 operation 说明"})

    for src, kind in required:
        if src in asset_map:
            target = PurePosixPath(asset_map[src].get("target", "")).as_posix()
            report["coverage"].append({"source": src, "kind": kind, "status": "mapped", "target": target})
            claimed[target] = src
            continue
        match, ambiguous = find_asset_match(src, PurePosixPath(src).name)
        if match is None:
            if ambiguous == -1:
                report["errors"].append({"kind": "asset-shared-basename-unmapped", "source": src,
                                         "note": "契约内存在同名文件；必须用 asset-map 指明对应关系"})
            elif ambiguous:
                report["errors"].append({"kind": "asset-ambiguous", "source": src,
                                         "note": f"{ambiguous} 个同名候选，无法确定对应关系；保留目录结构复制或用 asset-map 消歧"})
            else:
                report["errors"].append({"kind": "asset-missing", "source": src, "kind_required": kind,
                                         "note": "契约要求的原素材未出现在输出项目中（禁止静默缺失；确属源缺失需登记 progress.md）"})
        elif match in claimed and claimed[match] != src:
            report["errors"].append({"kind": "asset-target-conflict", "source": src, "target": match,
                                     "note": f"该输出文件已被 {claimed[match]} 占用；保留目录结构复制或用 asset-map 消歧"})
        else:
            report["coverage"].append({"source": src, "kind": kind, "status": "covered", "target": match})
            claimed[match] = src

    # ---- 2. shell integrity ----
    index = BASE / "index.html"
    if not index.is_file():
        report["errors"].append({"kind": "no-index", "note": "缺少 index.html"})
    else:
        html = index.read_text(encoding="utf-8-sig", errors="replace")
        has_local_phaser = bool(re.search(r"<script[^>]+src=['\"][^'\"]*phaser[^'\"]*\.min\.js['\"]", html))
        if not has_local_phaser:
            report["warnings"].append({"kind": "phaser-not-local",
                                       "note": "index.html 未引用本地 phaser.min.js；CDN 会造成离线不可用"})

    # ---- 3. static reference scan ----
    if index.is_file():
        scan_file("index.html", BASE)
    for p in sorted(BASE.rglob("*.js")):
        name = rel(p)
        if name.startswith("lib/") or name.startswith("conversion/"):
            continue
        scan_file(name, BASE)

    # ---- 4. JS syntax via node --check (optional) ----
    node = shutil.which("node")
    if node:
        for p in sorted(BASE.rglob("*.js")):
            name = rel(p)
            if name.startswith(("lib/", "conversion/")):
                continue
            try:
                r = subprocess.run([node, "--check", str(p)], capture_output=True, timeout=30)
                if r.returncode != 0:
                    report["errors"].append({"kind": "js-syntax", "source": name,
                                             "detail": r.stderr.decode("utf-8", "replace")[:500]})
            except (OSError, subprocess.TimeoutExpired) as e:
                report["warnings"].append({"kind": "js-check-skipped", "source": name, "detail": str(e)})
    else:
        report["warnings"].append({"kind": "node-absent", "note": "本机无 node，跳过 JS 语法检查"})

    # ---- content checklist (data parity is an AI duty; verify only lists) ----
    for n in inv["assets"].get("data", []):
        report["content"].append({"source": n, "status": "check-manually",
                                  "note": "关卡/文案数据的迁移与数量一致性需人工核对 progress.md"})

    out_dir = BASE / "conversion"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "verify-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # markdown summary
    md = ["# 核销报告", "",
          f"- 项目：`{BASE}`",
          f"- 结果：{'✅ 通过' if not report['errors'] else '❌ 存在错误'}；"
          f"错误 {len(report['errors'])}，警告 {len(report['warnings'])}",
          f"- 契约资源覆盖：{sum(1 for c in report['coverage'])}/{len(required)}", ""]
    if report["errors"]:
        md += ["## 错误（必须修复）", ""]
        for e in report["errors"]:
            md.append(f"- **{e['kind']}** `{e.get('source', '')}` {e.get('ref', '')} {e.get('note', '')} {e.get('detail', '')}")
        md.append("")
    if report["warnings"]:
        md += ["## 警告（逐条确认后写明结论）", ""]
        for w in report["warnings"]:
            md.append(f"- **{w['kind']}** `{w.get('source', '')}` {w.get('ref', '')} {w.get('note', '')}")
        md.append("")
    missing = [c for c in report["content"]]
    if missing:
        md += ["## 内容核对清单（人工/进度文件确认）", ""]
        for c in missing:
            md.append(f"- `{c['source']}`")
    (out_dir / "verify-report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"verify: {'PASS' if not report['errors'] else 'FAIL'} | "
          f"errors {len(report['errors'])} | warnings {len(report['warnings'])} | "
          f"coverage {len(report['coverage'])}/{len(required)}")
    print(f"report: {out_dir / 'verify-report.md'}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
