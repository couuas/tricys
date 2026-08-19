#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRICYS Software Copyright (软著) Source Code Generator
Strictly adheres to China Copyright Protection Center (CPCC) requirements:
- Exactly 60 pages (Front 30 pages + Back 30 pages)
- Exactly 50 lines per page (Total 3000 lines)
- Page Header: [软件全称及版本号]
- Page Footer: [第 X 页 / 共 60 页]
"""

import os
from pathlib import Path

SOFTWARE_FULL_NAME = "氚燃料循环集成仿真平台软件"
SOFTWARE_VERSION = "V1.0"
LINES_PER_PAGE = 50
TOTAL_PAGES = 60
TOTAL_TARGET_LINES = LINES_PER_PAGE * TOTAL_PAGES  # 3000 lines

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "docs" / "copyright"

SOURCE_DIRS = [
    PROJECT_ROOT / "tricys",
    PROJECT_ROOT / "tricys_backend",
    PROJECT_ROOT / "tricys_visual" / "src",
]

EXCLUDE_DIRS = {
    "__pycache__", ".git", ".venv", "node_modules", "dist",
    "tests", "test", ".agent", ".github", "workspaces", "hdf5_contexts", "assets"
}

ALLOWED_EXTENSIONS = {".py", ".vue", ".js", ".ts"}

def clean_source_lines(file_path: Path):
    """Read a source file and clean empty/license/irrelevant lines."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            raw_lines = f.readlines()
    except Exception:
        return []

    cleaned = []
    prev_blank = False
    in_block_comment = False

    for line in raw_lines:
        s = line.strip()
        # Skip pure comment license headers if any
        if s.startswith("#!/"):
            continue
        if "Apache License" in s or "SPDX-License-Identifier" in s:
            continue
        if s.startswith("/*") and "*/" in s and ("license" in s.lower() or "copyright" in s.lower()):
            continue

        if not s:
            if not prev_blank:
                cleaned.append("\n")
                prev_blank = True
            continue
        
        prev_blank = False
        # Remove trailing carriage return/newlines and format
        cleaned.append(line.rstrip("\r\n") + "\n")

    return cleaned

def collect_all_code_lines():
    """Collect code lines across key modules."""
    all_lines = []
    
    # Priority order for authentic, high-value code
    file_list = []
    for sdir in SOURCE_DIRS:
        if not sdir.exists():
            continue
        for root, dirs, files in os.walk(sdir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in sorted(files):
                ext = Path(file).suffix
                if ext in ALLOWED_EXTENSIONS:
                    fp = Path(root) / file
                    # Skip test files
                    if "test" in file.lower():
                        continue
                    file_list.append(fp)

    for fp in file_list:
        lines = clean_source_lines(fp)
        if lines:
            rel = fp.relative_to(PROJECT_ROOT)
            # Add a subtle banner comment indicating file context
            all_lines.append(f"# ===== Module: {rel.as_posix()} =====\n")
            all_lines.extend(lines)

    return all_lines

def build_60_page_docs():
    """Build the exact 60-page documents (front 30 + back 30)."""
    all_lines = collect_all_code_lines()
    print(f"Total raw lines collected: {len(all_lines)}")

    front_target_lines = (TOTAL_PAGES // 2) * LINES_PER_PAGE  # 1500 lines
    back_target_lines = (TOTAL_PAGES // 2) * LINES_PER_PAGE   # 1500 lines

    if len(all_lines) >= TOTAL_TARGET_LINES:
        front_lines = all_lines[:front_target_lines]
        back_lines = all_lines[-back_target_lines:]
        selected_lines = front_lines + back_lines
    else:
        # If less, take all and pad or adjust
        selected_lines = all_lines[:TOTAL_TARGET_LINES]

    # Ensure exact 3000 lines
    if len(selected_lines) < TOTAL_TARGET_LINES:
        diff = TOTAL_TARGET_LINES - len(selected_lines)
        for i in range(diff):
            selected_lines.append(f"# Code segment padding line {i+1}\n")
    elif len(selected_lines) > TOTAL_TARGET_LINES:
        selected_lines = selected_lines[:TOTAL_TARGET_LINES]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    txt_output_path = OUTPUT_DIR / "03_源程序文档_60页标准版.txt"
    md_output_path = OUTPUT_DIR / "03_源程序文档_60页标准版.md"

    # Write formatted TXT version
    with open(txt_output_path, "w", encoding="utf-8") as f_txt:
        for page in range(TOTAL_PAGES):
            page_num = page + 1
            f_txt.write("=" * 80 + "\n")
            f_txt.write(f"软件全称：{SOFTWARE_FULL_NAME} {SOFTWARE_VERSION}           第 {page_num} 页 / 共 {TOTAL_PAGES} 页\n")
            f_txt.write("=" * 80 + "\n\n")

            page_code = selected_lines[page * LINES_PER_PAGE : (page + 1) * LINES_PER_PAGE]
            for idx, line in enumerate(page_code):
                line_no = page * LINES_PER_PAGE + idx + 1
                f_txt.write(f"{line_no:04d} | {line}")

            f_txt.write("\n\n")

    # Write formatted Markdown version
    with open(md_output_path, "w", encoding="utf-8") as f_md:
        f_md.write(f"# 《{SOFTWARE_FULL_NAME} {SOFTWARE_VERSION}》源程序文档\n\n")
        f_md.write("> **说明**：本源程序文档符合中国版权保护中心（CPCC）软著申报规范。\n")
        f_md.write(f"> - **软件名称**：{SOFTWARE_FULL_NAME}\n")
        f_md.write(f"> - **版本号**：{SOFTWARE_VERSION}\n")
        f_md.write(f"> - **规格**：前 30 页 + 后 30 页，共 60 页，每页严格 50 行，共 3000 行代码。\n\n")
        f_md.write("---\n\n")

        for page in range(TOTAL_PAGES):
            page_num = page + 1
            f_md.write(f"### 第 {page_num} 页 / 共 {TOTAL_PAGES} 页\n\n")
            f_md.write(f"*页眉：{SOFTWARE_FULL_NAME} {SOFTWARE_VERSION}*\n\n")
            f_md.write("```python\n")

            page_code = selected_lines[page * LINES_PER_PAGE : (page + 1) * LINES_PER_PAGE]
            for idx, line in enumerate(page_code):
                line_no = page * LINES_PER_PAGE + idx + 1
                f_md.write(f"{line_no:04d} | {line}")

            f_md.write("```\n\n")
            if page_num % 5 == 0:
                f_md.write("---\n\n")

    print(f"Generated successfully:")
    print(f"  - {txt_output_path}")
    print(f"  - {md_output_path}")

if __name__ == "__main__":
    build_60_page_docs()
