#!/usr/bin/env python3
# coding: utf-8
"""Scan an unpacked Unity project and produce the conversion contract (inventory).

The inventory tells the converting agent WHAT exists and WHAT MUST be migrated:
scoped scenes, active scripts (with feature flags and Resources.Load candidates),
images / audio / fonts / data assets, prefabs, and risk flags (3D, shaders,
native plugins, Spine, ...).

Usage:
  python inventory.py --source <unpacked-unity-project> [--entry <Assets/.../Scene.unity>]
                      [--folder Assets/... ]... [--extra Assets/...]...
                      [--out <output-dir>]

--entry/--folder/--extra restrict the contract to the game's own scope via a
GUID reference closure (same mechanism Unity itself uses for serialized
references). Without scope flags the contract covers every non-plugin file and
marks itself "unscoped" - verify_output.py will then require everything, so
declare a scope in real conversions.

Stdlib only. Read-only on the source; never opens Unity or executes game code.
"""
import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

GUID = re.compile(r"\bguid:\s*([a-fA-F0-9]{32})\b")

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".bmp"}
AUDIO_EXT = {".wav", ".mp3", ".ogg", ".aiff", ".aif", ".flac", ".m4a", ".aac"}
FONT_EXT = {".ttf", ".otf", ".ttc"}
DATA_EXT = {".json", ".txt", ".csv", ".xml", ".yaml", ".yml", ".bytes"}
SCENE_EXT = {".unity"}
PREFAB_EXT = {".prefab"}
ANIM_EXT = {".anim", ".controller", ".overridecontroller", ".playable"}
MAT_EXT = {".mat", ".shader", ".shadergraph", ".cginc"}
MODEL_EXT = {".fbx", ".obj", ".blend"}
NATIVE_EXT = {".dll", ".so", ".aar", ".mm", ".m", ".dylib", ".bundle", ".plugin"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".avi"}
SPINE_HINT = re.compile(r"(spine|\.skel$)", re.IGNORECASE)

# Feature detection on C# sources (patterns distilled from real conversions).
FEATURES = {
    "dotween": r"\b(?:DOTween|DOFade|DOMove|DOLocalMove|DOScale|DORotate|DOPunchScale|DOJump|DOAnchor(?:Pos|Size)?|SetDelay|SetEase|OnComplete|Sequence)\b",
    "coroutines": r"\b(?:IEnumerator|StartCoroutine|StopCoroutine|WaitForSeconds|WaitUntil|WaitWhile)\b",
    "audio": r"\b(?:AudioSource|AudioClip|PlayOneShot|PlayClipAtPoint|AudioMixer)\b",
    "tmp_text": r"\b(?:TMP_Text|TextMeshPro|TextMeshProUGUI|TMP_FontAsset|TMP_InputField)\b",
    "legacy_ui_text": r"\busing\s+UnityEngine\.UI\b|\b(?:Text|Image|Button|Slider|Toggle|ScrollRect)\b",
    "physics": r"\b(?:Rigidbody2?D?|Collider2?D?|OnTriggerEnter2?D?|OnCollisionEnter2?D?|CharacterController)\b",
    "ui_events": r"\b(?:IPointer(?:Click|Down|Up|Drag|BeginDrag|EndDrag)Handler|IBeginDragHandler|IEndDragHandler|IDragHandler|EventTrigger|OnMouse(?:Down|Up|Drag|Over))\b",
    "touch_plugin": r"\b(?:TouchScript|ITouchable|Gesture)\b",
    "spine": r"\b(?:SkeletonAnimation|SkeletonGraphic|Spine\.Unity)\b",
    "video": r"\b(?:VideoPlayer|VideoClip)\b",
    "scene_manager": r"\bSceneManager\s*\.\s*(?:LoadScene(?:Async)?|UnloadScene)\b",
    "timers": r"\b(?:Invoke\s*\(|InvokeRepeating|CancelInvoke)\b",
    "dynamic_ui": r"\b(?:AddComponent<|new\s+GameObject\s*\()",
    "singletons": r"\b(?:static\s+\w+\s+Instance|Singleton)\b",
    "playerprefs": r"\bPlayerPrefs\s*\.\s*(?:Get|Set|Delete)",
    "network": r"\b(?:UnityWebRequest|HttpClient|WebSocket|WWW\s*\()",
}

RESOURCES_LOAD = re.compile(
    r"\bResources\s*\.\s*(LoadAll|LoadAsync|Load)\s*(?:<\s*([\w.\s]+?)\s*>)?\s*\(\s*\"((?:[^\"\\]|\\.)*)\""
)


def posix(p: Path) -> str:
    return p.relative_to(BASE).as_posix()


def classify(ext: str) -> str:
    if ext in IMAGE_EXT:
        return "images"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in FONT_EXT:
        return "fonts"
    if ext in DATA_EXT:
        return "data"
    if ext in SCENE_EXT:
        return "scenes"
    if ext in PREFAB_EXT:
        return "prefabs"
    if ext in ANIM_EXT:
        return "animations"
    if ext in MAT_EXT:
        return "materials"
    if ext in MODEL_EXT:
        return "models"
    if ext in NATIVE_EXT:
        return "native"
    if ext in VIDEO_EXT:
        return "video"
    if ext == ".cs":
        return "scripts"
    return "other"


def script_features(text: str) -> dict:
    flags = {}
    for name, pattern in FEATURES.items():
        hits = len(re.findall(pattern, text))
        if hits:
            flags[name] = hits
    return flags


def script_resources(text: str) -> list:
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        m = RESOURCES_LOAD.search(line)
        if m:
            out.append({
                "line": i,
                "api": "Resources." + m.group(1),
                "type": (m.group(2) or "").strip(),
                "path": m.group(3),
            })
    return out


def scan_meta_guids(names: list) -> dict:
    """guid -> asset path, from every *.meta under the source."""
    guids = {}
    for n in names:
        if n.endswith(".meta"):
            try:
                text = (BASE / n).read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            m = GUID.search(text)
            if m:
                guids.setdefault(m.group(1).lower(), n[:-5])
    return guids


def yaml_script_refs(path: Path) -> list:
    """m_Script GUIDs referenced by a scene/prefab, resolved to script paths."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    refs = []
    for m in re.finditer(r"(?m)^\s*m_Script:\s*\{[^}]*guid:\s*([0-9a-fA-F]{32})", text):
        target = GUID_MAP.get(m.group(1).lower())
        if target:
            refs.append(target)
    return sorted(set(refs))


def yaml_scene_facts(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    objects = len(re.findall(r"(?m)^--- !u!", text))
    canvas = "m_ReferenceResolution" in text
    camera = "orthographic size" in text or "m_orthographic" in text
    ref_res = None
    m = re.search(r"(?m)^\s*m_ReferenceResolution:\s*\{x:\s*([\d.]+),\s*y:\s*([\d.]+)\}", text)
    if m:
        ref_res = [float(m.group(1)), float(m.group(2))]
    ortho = None
    m = re.search(r"(?m)^\s*orthographic size:\s*([\d.]+)", text)
    if m:
        ortho = float(m.group(1))
    return {
        "objects": objects,
        "usesUICanvas": canvas,
        "usesOrthoCamera": camera,
        "uiReferenceResolution": ref_res,
        "orthoSize": ortho,
        "scripts": yaml_script_refs(path),
    }


def guid_closure(seed_files: set) -> set:
    """Expand seed files through serialized GUID references (text files only)."""
    TEXT_SCAN = {
        ".unity", ".prefab", ".mat", ".asset", ".anim", ".controller",
        ".overridecontroller", ".spriteatlas", ".spriteatlasv2", ".playable",
        ".mixer", ".asset", ".json", ".txt", ".csv", ".xml",
    }
    selected = set(seed_files)
    todo = list(selected)
    while todo:
        n = todo.pop()
        ext = PurePosixPath(n).suffix.lower()
        if ext not in TEXT_SCAN:
            continue
        p = BASE / n
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for g in GUID.findall(text):
            target = GUID_MAP.get(g.lower())
            if target and target in ALL_NAMES and target not in selected:
                selected.add(target)
                todo.append(target)
    return selected


def main() -> int:
    global BASE, ALL_NAMES, GUID_MAP
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", required=True, help="unpacked Unity project dir (contains Assets/)")
    ap.add_argument("--entry", default=None, help="entry scene/prefab, e.g. Assets/Scenes/Game.unity")
    ap.add_argument("--folder", action="append", default=[], help="game-specific folder (repeatable)")
    ap.add_argument("--extra", action="append", default=[], help="extra dynamic dependency file (repeatable)")
    ap.add_argument("--out", default="conversion", help="output dir for inventory.json (default ./conversion)")
    args = ap.parse_args()

    BASE = Path(args.source).resolve()
    if not (BASE / "Assets").is_dir():
        raise SystemExit("Source must be a Unity project root containing Assets/")

    # ---- index everything ----
    all_files = []
    for base in ("Assets", "ProjectSettings", "Packages"):
        root = BASE / base
        if root.is_dir():
            all_files += [posix(p) for p in sorted(root.rglob("*"))
                          if p.is_file() and not p.name.startswith(".")]
    ALL_NAMES = set(all_files)

    by_kind = {}
    for n in all_files:
        by_kind.setdefault(classify(PurePosixPath(n).suffix.lower()), []).append(n)

    GUID_MAP = scan_meta_guids(all_files)

    version = ""
    vp = BASE / "ProjectSettings" / "ProjectVersion.txt"
    if vp.is_file():
        m = re.search(r"m_EditorVersion:\s*(.+)", vp.read_text(errors="replace"))
        if m:
            version = m.group(1).strip()

    orientation = None
    ps = BASE / "ProjectSettings" / "ProjectSettings.asset"
    if ps.is_file():
        m = re.search(r"defaultOrientation:\s*(\d+)", ps.read_text(errors="replace"))
        if m:
            orientation = {
                "0": "Auto", "1": "Portrait", "2": "PortraitUpsideDown",
                "3": "LandscapeRight", "4": "LandscapeLeft",
            }.get(m.group(1), m.group(1))

    # ---- scope: explicit flags or heuristic suggestions ----
    plugin_prefixes = ("Assets/Plugins/",)
    scope_declared = bool(args.entry or args.folder)
    if scope_declared:
        seed = set()
        if args.entry:
            seed.add(args.entry)
        for f in args.folder:
            seed.update(n for n in all_files if n == f or n.startswith(f.rstrip("/") + "/"))
        for e in args.extra:
            seed.add(e)
        missing = [s for s in seed if s not in ALL_NAMES]
        if missing:
            raise SystemExit("Scoped paths not found in source: " + ", ".join(missing))
        scoped = guid_closure(seed)
    else:
        scoped = {n for n in all_files if not n.startswith(plugin_prefixes)
                  and "/Plugins/" not in n}

    scoped = {n for n in scoped
              if not n.endswith(".meta")
              and PurePosixPath(n).parts[-1] != ".DS_Store"}

    # ---- scripts report, tiered: engine packages / platform & shared / game ----
    def tier(n: str) -> str:
        if n.startswith("Packages/"):
            return "engine"      # Unity registry packages: never ported, semantic reference only
        game_folders = tuple(f.rstrip("/") + "/" for f in args.folder)
        if game_folders and n.startswith(game_folders):
            return "game"        # the code being converted
        return "platform"        # own shared/platform code: read for call graph, port selectively

    scripts = []
    for n in sorted(n for n in scoped if n.endswith(".cs")):
        text = (BASE / n).read_text(encoding="utf-8-sig", errors="replace")
        classes = re.findall(r"(?m)^\s*(?:public|private|internal)?\s*(?:sealed |abstract |partial |static )*class\s+(\w+)\s*:\s*([\w<>,\s]+)", text)
        is_mono = any("MonoBehaviour" in base for _, base in classes)
        scripts.append({
            "path": n,
            "tier": tier(n),
            "lines": text.count("\n") + 1,
            "classes": [c for c, _ in classes],
            "isMonoBehaviour": is_mono,
            "features": script_features(text),
            "resources": script_resources(text) if tier(n) != "engine" else [],
        })

    # ---- scenes / prefabs (scoped only) ----
    scenes = []
    for n in sorted(n for n in scoped if n.endswith(".unity")):
        scenes.append({"path": n, **yaml_scene_facts(BASE / n)})
    prefabs = []
    for n in sorted(n for n in scoped if n.endswith(".prefab")):
        prefabs.append({"path": n, "scripts": yaml_script_refs(BASE / n)})

    # ---- assets ----
    assets = {}
    for group in ("images", "audio", "fonts", "data", "models", "video", "native", "materials", "animations", "other"):
        assets[group] = sorted(n for n in scoped
                               if classify(PurePosixPath(n).suffix.lower()) == group
                               and not n.endswith(".cs"))

    def total_bytes(group):
        return sum((BASE / n).stat().st_size for n in assets[group] if (BASE / n).is_file())

    resources_dirs = sorted({str(PurePosixPath(n).parent) for n in scoped
                             if "Resources" in PurePosixPath(n).parts})

    dynamic_loads = []
    for s in scripts:
        if s["tier"] == "engine":
            continue  # engine internals are not conversion targets
        for r in s["resources"]:
            dynamic_loads.append({"source": s["path"], **r})

    # ---- risks ----
    risks = []
    if assets["models"]:
        risks.append({"kind": "3d-models", "detail": f"{len(assets['models'])} model files; Phaser is 2D - these need flat rendering or are out of scope"})
    if any(SPINE_HINT.search(n) for n in scoped):
        risks.append({"kind": "spine", "detail": "Spine skeletal animation detected - needs spine-webgl runtime or re-animation"})
    if assets["video"]:
        risks.append({"kind": "video", "detail": "video files - use HTML5 <video>"})
    if assets["native"]:
        risks.append({"kind": "native-plugins", "detail": f"{len(assets['native'])} native binaries (platform-only; usually excluded from web conversion, but check game code for their APIs)"})
    custom_shaders = [n for n in assets["materials"] if n.endswith((".shader", ".shadergraph"))]
    if custom_shaders:
        risks.append({"kind": "custom-shaders", "detail": f"{len(custom_shaders)} shader files - approximate with tint/blendMode/mask where possible"})

    contract = {
        "format": "unity2phaser-inventory/1",
        "sourceRoot": str(BASE),
        "unityVersion": version,
        "defaultOrientation": orientation,
        "scope": {
            "declared": scope_declared,
            "entry": args.entry,
            "folders": args.folder,
            "extras": args.extra,
        },
        "summary": {
            "files": len(scoped),
            "scenes": len(scenes),
            "prefabs": len(prefabs),
            "scripts": len(scripts),
            "scriptTiers": {t: sum(1 for s in scripts if s["tier"] == t) for t in ("game", "platform", "engine")},
            "monoBehaviours": sum(1 for s in scripts if s["isMonoBehaviour"]),
            "scriptLines": sum(s["lines"] for s in scripts),
            "images": len(assets["images"]),
            "audio": len(assets["audio"]),
            "fonts": len(assets["fonts"]),
            "data": len(assets["data"]),
            "bytes": {g: total_bytes(g) for g in ("images", "audio", "fonts")},
        },
        "scenes": scenes,
        "prefabs": prefabs,
        "scripts": scripts,
        "assets": assets,
        "resourcesDirs": resources_dirs,
        "dynamicLoads": dynamic_loads,
        "risks": risks,
        "limits": [
            "Static serialized evidence only: prefab overrides at runtime, layout groups, and computed paths still require reading the sources.",
            "Resources.Load candidates are literal strings found in code; computed paths must be expanded manually.",
            "Feature flags count source occurrences; they do not prove runtime behavior.",
        ],
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "inventory.json"
    out_json.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- human-readable report ----
    lines = []
    A = lines.append
    A("# Unity 项目盘点报告")
    A("")
    A(f"- 源目录：`{BASE}`")
    A(f"- Unity 版本：{version or '未知'}")
    A(f"- 默认朝向：{orientation or '未知（查场景 Canvas 设置）'}")
    A(f"- Scope：{'显式声明' if scope_declared else '未声明（全量非插件文件）'}"
      + (f"；entry={args.entry}" if args.entry else ""))
    A("")
    A("## 规模概览（转换契约范围）")
    A("")
    s = contract["summary"]
    A(f"| 项 | 数量 |")
    A(f"|---|---|")
    A(f"| 场景 | {s['scenes']} |")
    A(f"| Prefab | {s['prefabs']} |")
    A(f"| C# 脚本 | {s['scripts']}（其中 MonoBehaviour {s['monoBehaviours']} 个，共 {s['scriptLines']} 行） |")
    A(f"| 图片 | {s['images']} |")
    A(f"| 音频 | {s['audio']} |")
    A(f"| 字体 | {s['fonts']} |")
    A(f"| 数据文件 | {s['data']} |")
    A("")
    A("## 场景")
    A("")
    for sc in scenes:
        A(f"- `{sc['path']}`：{sc['objects']} 个序列化对象"
          + (f"；UI Canvas 参考分辨率 {sc['uiReferenceResolution']}" if sc["uiReferenceResolution"] else "")
          + (f"；正交摄像机 orthoSize={sc['orthoSize']}" if sc["orthoSize"] else ""))
        for sp in sc["scripts"]:
            A(f"  - 挂载脚本：`{sp}`")
    A("")
    A("## 脚本清单（按层级分组，行数降序）")
    A("")
    TIER_TITLES = {
        "game": "### 游戏本体（转换目标——逐个移植，见 workflow 阶段4）",
        "platform": "### 平台/共享代码（读调用关系，按需选择性移植）",
        "engine": "### 引擎包源码（不转换，仅作语义参考）",
    }
    for t in ("game", "platform", "engine"):
        group = [sp for sp in scripts if sp["tier"] == t]
        if not group:
            continue
        A(TIER_TITLES[t])
        A("")
        A("| 脚本 | 行数 | MonoBehaviour | 特征 |")
        A("|---|---|---|---|")
        for sp in sorted(group, key=lambda x: -x["lines"]):
            feats = ", ".join(f"{k}×{v}" for k, v in sp["features"].items()) or "-"
            A(f"| `{sp['path']}` | {sp['lines']} | {'是' if sp['isMonoBehaviour'] else '否'} | {feats} |")
        A("")

    ASSET_TITLES = [
        ("images", "图片（全部复制原文件到 assets/，禁止重绘）"),
        ("audio", "音频（全部复制，注意浏览器格式兼容）"),
        ("fonts", "字体（复制 + @font-face，检查中文字形覆盖）"),
        ("data", "数据/关卡文件（迁入 data/，数量必须一致）"),
    ]
    for group, title in ASSET_TITLES:
        if not assets[group]:
            continue
        A(f"## {title}")
        A("")
        for n in assets[group]:
            size = (BASE / n).stat().st_size
            A(f"- `{n}`（{size // 1024} KB）")
        A("")
    if assets["models"] or assets["native"] or assets["video"]:
        A("## 未纳入网页转换的文件（存在但通常不迁移）")
        A("")
        for group in ("models", "video", "native"):
            for n in assets[group]:
                A(f"- `{n}`")
        A("")
    if dynamic_loads:
        A("")
        A("## 动态资源加载（Resources.Load）")
        A("")
        for r in dynamic_loads:
            A(f"- `{r['source']}:{r['line']}` `{r['api']}(\"{r['path']}\")`"
              + (f" 类型 {r['type']}" if r["type"] else ""))
    A("")
    if risks:
        A("## 风险标记")
        A("")
        for r in risks:
            A(f"- **{r['kind']}**：{r['detail']}")
        A("")
    A("## 范围建议（未声明 scope 时）")
    A("")
    top = {}
    for n in scoped:
        parts = PurePosixPath(n).parts
        if len(parts) > 1 and parts[0] == "Assets":
            top[parts[1]] = top.get(parts[1], 0) + 1
    A("| Assets 顶层目录 | 文件数 | 建议 |")
    A("|---|---|---|")
    for d, c in sorted(top.items(), key=lambda kv: -kv[1]):
        A(f"| `Assets/{d}` | {c} | {'插件/第三方，勿纳入转换' if d == 'Plugins' else '候选游戏目录'} |")
    A("")
    A("→ 用 `--entry <场景> --folder <游戏目录>` 重新运行，把契约收窄到游戏本体。")
    (out_dir / "inventory-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"inventory written: {out_json}")
    print(f"report:            {out_dir / 'inventory-report.md'}")
    print(f"scoped files: {len(scoped)} | scripts {len(scripts)} | scenes {len(scenes)} | "
          f"images {s['images']} | audio {s['audio']} | fonts {s['fonts']} | data {s['data']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
