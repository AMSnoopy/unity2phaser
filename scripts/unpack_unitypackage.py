#!/usr/bin/env python3
# coding: utf-8
"""Unpack a Unity .unitypackage into a readable project tree.

A .unitypackage is a gzipped tar. Each asset lives in its own <GUID>/ folder:
  pathname   -> text file holding the original project path (e.g. Assets/Scripts/Game.cs)
  asset      -> the raw file bytes (absent for folder entries)
  asset.meta -> Unity .meta YAML (absent in rare legacy packages)

This script reconstructs the original Assets/ tree under <output-dir>.

Usage:
  python unpack_unitypackage.py <input.unitypackage> <output-dir>

Stdlib only. Read-only on the input; never opens Unity or executes project code.
"""
import sys
import tarfile
from pathlib import Path, PurePosixPath


def safe_rel(name: str) -> PurePosixPath:
    """Reject paths that could escape the output directory."""
    if not name or name.startswith("/") or "\\" in name or ":" in name:
        raise SystemExit("Unsafe source path: " + name)
    p = PurePosixPath(name)
    if ".." in p.parts or any(part in {"", "."} for part in name.split("/")):
        raise SystemExit("Unsafe source path: " + name)
    return p


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    src, dest = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_file():
        raise SystemExit("Input not found: %s" % src)

    with tarfile.open(src, "r:*") as tar:
        members = {}
        for m in tar.getmembers():
            if not m.isfile():
                continue
            name = m.name.rstrip("/")
            if name in members:
                raise SystemExit("Duplicate archive member: " + name)
            members[name] = m

        pathnames = sorted(n for n in members if n.endswith("/pathname"))
        if not pathnames:
            raise SystemExit("No pathname records found; not a valid .unitypackage?")

        counts, errors, written = {}, [], 0
        for entry in pathnames:
            guid_dir = entry.rsplit("/", 1)[0]
            name = (
                tar.extractfile(members[entry])
                .read()
                .decode("utf-8-sig")
                .rstrip("\r\n\x00")
            )
            rel = safe_rel(name)
            meta_member = members.get(guid_dir + "/asset.meta")
            meta_data = (
                tar.extractfile(meta_member).read() if meta_member is not None else None
            )
            is_folder = bool(
                meta_data is not None
                and b"folderAsset: yes" in meta_data
            )
            asset_member = members.get(guid_dir + "/asset")
            if is_folder:
                (dest / rel).mkdir(parents=True, exist_ok=True)
            elif asset_member is not None:
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                data = tar.extractfile(asset_member).read()
                out.write_bytes(data)
                written += 1
                counts[rel.suffix.lower() or "(none)"] = (
                    counts.get(rel.suffix.lower() or "(none)", 0) + 1
                )
            else:
                errors.append("missing asset bytes: " + name)
            if meta_data is not None:
                meta_out = dest / (rel.as_posix() + ".meta")
                meta_out.parent.mkdir(parents=True, exist_ok=True)
                meta_out.write_bytes(meta_data)

    print("unpacked files:", written)
    for suffix, n in sorted(counts.items(), key=lambda kv: -kv[1])[:25]:
        print("  %-10s %d" % (suffix, n))
    if errors:
        print("warnings (%d):" % len(errors))
        for e in errors[:20]:
            print("  " + e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
