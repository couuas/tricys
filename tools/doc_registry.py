#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Document Asset Registry CLI

Purpose:
- Track important project documents and their versions
- Maintain a JSON registry with metadata for search and audit
- Generate a Markdown report for quick review

Usage examples:
  python doc_registry.py init --root "." \
      --registry ".registry/docs.json" --report ".registry/docs_report.md"
  python doc_registry.py scan --root "." --patterns "*.md" "*.docx" "*.tex"
  python doc_registry.py add --file "path/to/file.md" --version "v1.0" --tags "设计" "报告"
  python doc_registry.py report

Registry file structure (JSON):
{
  "project_code": "TRITIUM-CYCLE",
  "updated_at": "2025-10-16T10:20:00Z",
  "documents": [
    {
      "id": "sha1-of-path",
      "path": "relative/path/to/file.md",
      "name": "file.md",
      "ext": ".md",
      "size": 1024,
      "mtime": 1734360000.0,
      "created_at": "2025-10-01T12:00:00Z",
      "tags": ["报告", "设计"],
      "versions": [
        {"version": "v1.0", "date": "2025-10-16", "notes": "初版"}
      ]
    }
  ]
}
"""

from __future__ import annotations
import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

DEFAULT_REGISTRY = ".registry/docs.json"
DEFAULT_REPORT = ".registry/docs_report.md"
SUPPORTED_EXTS = [
    ".md", ".docx", ".doc", ".pdf", ".tex", ".txt", ".pptx", ".xlsx", ".csv"
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def sha1_of(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def load_registry(path: Path) -> Dict[str, Any]:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"project_code": None, "updated_at": utc_now_iso(), "documents": []}


def save_registry(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = utc_now_iso()
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def relpath(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root))
    except Exception:
        return str(p)


def guess_project_code(root: Path) -> str | None:
    cfg = root / ".pm-project.json"
    if cfg.exists():
        try:
            with cfg.open("r", encoding="utf-8") as f:
                j = json.load(f)
                return j.get("project_code")
        except Exception:
            return None
    return None


def ensure_doc_entry(reg: Dict[str, Any], rel: str, fs_stat: os.stat_result) -> Dict[str, Any]:
    doc_id = sha1_of(rel)
    for d in reg["documents"]:
        if d["id"] == doc_id:
            # Update basic fields
            d["size"], d["mtime"] = fs_stat.st_size, fs_stat.st_mtime
            return d
    entry = {
        "id": doc_id,
        "path": rel,
        "name": os.path.basename(rel),
        "ext": os.path.splitext(rel)[1].lower(),
        "size": fs_stat.st_size,
        "mtime": fs_stat.st_mtime,
        "created_at": utc_now_iso(),
        "tags": [],
        "versions": []
    }
    reg["documents"].append(entry)
    return entry


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    registry = Path(args.registry)
    report = Path(args.report)

    data = load_registry(registry)
    if not data.get("project_code"):
        data["project_code"] = guess_project_code(root)
    save_registry(registry, data)

    print(f"Initialized registry at {registry}")
    print(f"Project code: {data.get('project_code')}")
    # Create empty report placeholder
    report.parent.mkdir(parents=True, exist_ok=True)
    if not report.exists():
        report.write_text("# 文档资产报告\n\n(初始化，尚未扫描)\n", encoding="utf-8")
    return 0


def iter_files(root: Path, include_patterns: List[str]) -> List[Path]:
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip hidden and registry dirs
        if any(seg.startswith(".") for seg in Path(dirpath).parts):
            # still include the root if it is the starting point
            pass
        for fn in filenames:
            p = Path(dirpath) / fn
            rel = relpath(root, p)
            # skip our own outputs
            if rel.startswith(".registry/"):
                continue
            if include_patterns:
                if any(fnmatch.fnmatch(fn, pat) for pat in include_patterns):
                    files.append(p)
            else:
                if p.suffix.lower() in SUPPORTED_EXTS:
                    files.append(p)
    return files


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    registry = Path(args.registry)
    data = load_registry(registry)
    if not data.get("project_code"):
        data["project_code"] = guess_project_code(root)

    patterns = args.patterns or []
    files = iter_files(root, patterns)

    count = 0
    for p in files:
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        rel = relpath(root, p)
        ensure_doc_entry(data, rel, st)
        count += 1

    save_registry(registry, data)
    print(f"Scanned {count} files. Registry: {registry}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    registry = Path(args.registry)
    data = load_registry(registry)
    fp = Path(args.file)
    if not fp.is_absolute():
        fp = (root / fp).resolve()
    if not fp.exists():
        print(f"File not found: {fp}")
        return 1
    st = fp.stat()
    rel = relpath(root, fp)
    entry = ensure_doc_entry(data, rel, st)

    # add version
    version = args.version or f"v{datetime.now().strftime('%Y.%m.%d')}"
    notes = args.notes or ""
    entry["versions"].append({
        "version": version,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "notes": notes
    })

    # tags
    if args.tags:
        for t in args.tags:
            if t not in entry["tags"]:
                entry["tags"].append(t)

    save_registry(registry, data)
    print(f"Added version {version} for {rel}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    registry = Path(args.registry)
    report = Path(args.report)
    data = load_registry(registry)

    docs = sorted(data.get("documents", []), key=lambda d: (d.get("ext", ""), d.get("path", "")))

    lines: List[str] = []
    lines.append(f"# 文档资产报告\n")
    lines.append(f"- 生成时间: {utc_now_iso()}\n")
    lines.append(f"- 项目代码: {data.get('project_code')}\n")
    lines.append("")
    if not docs:
        lines.append("(暂无文档记录)\n")
    else:
        by_ext: Dict[str, List[Dict[str, Any]]] = {}
        for d in docs:
            by_ext.setdefault(d.get("ext", ""), []).append(d)
        for ext, items in sorted(by_ext.items()):
            lines.append(f"## {ext or '其他'} ({len(items)})\n")
            for d in items:
                size_kb = max(1, d.get("size", 0) // 1024)
                tags = ",".join(d.get("tags", [])) if d.get("tags") else "-"
                last = d.get("versions", [])[-1] if d.get("versions") else None
                last_str = f"{last['version']}@{last['date']}" if last else "-"
                lines.append(f"- {d['path']} ({size_kb} KB) | 标签: {tags} | 最近版本: {last_str}")
            lines.append("")

    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report generated: {report}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Document Asset Registry CLI")
    p.add_argument("--root", default=".", help="Project root directory")
    p.add_argument("--registry", default=DEFAULT_REGISTRY, help="Registry JSON path")
    p.add_argument("--report", default=DEFAULT_REPORT, help="Report Markdown path")

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="Initialize registry and report placeholders")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("scan", help="Scan workspace and update registry entries")
    sp.add_argument("--patterns", nargs="*", default=None, help="Glob patterns, e.g. *.md *.docx")
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("add", help="Add a version entry for a file with optional tags")
    sp.add_argument("--file", required=True, help="File path (relative to root or absolute)")
    sp.add_argument("--version", default=None, help="Version label, e.g. v1.0")
    sp.add_argument("--notes", default=None, help="Notes for this version")
    sp.add_argument("--tags", nargs="*", default=None, help="Tags to attach to the document")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("report", help="Generate Markdown report")
    sp.set_defaults(func=cmd_report)

    return p


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
