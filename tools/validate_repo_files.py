#!/usr/bin/env python3
"""Validate Now/ and Later/ for hidden files and packaging junk.

Checks loose files and directories recursively, then inspects every ZIP archive
found under the selected areas. The validator is intentionally read-only: it
fails with a complete report rather than deleting or silently rewriting files.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

JUNK_DIRECTORY_NAMES = {
    "__pycache__",
    "__macosx",
    ".git",
    ".svn",
}
JUNK_FILE_NAMES = {
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
    "ehthumbs.db",
}
JUNK_SUFFIXES = (".pyc", ".pyo")


def path_problem(parts: tuple[str, ...] | list[str]) -> str | None:
    """Return a reason when a path component is hidden or known packaging junk."""
    clean_parts = [part for part in parts if part not in ("", ".")]
    if not clean_parts:
        return "empty path"

    for part in clean_parts:
        lowered = part.casefold()
        if part.startswith("."):
            return f"hidden path component: {part}"
        if lowered in JUNK_DIRECTORY_NAMES:
            return f"packaging directory: {part}"

    basename = clean_parts[-1]
    lowered_basename = basename.casefold()
    if lowered_basename in JUNK_FILE_NAMES:
        return f"operating-system metadata file: {basename}"
    if lowered_basename.endswith(JUNK_SUFFIXES):
        return f"Python bytecode file: {basename}"
    return None


def validate_loose_tree(area: Path) -> list[str]:
    issues: list[str] = []
    if not area.exists():
        return [f"{area}: required directory does not exist"]
    if not area.is_dir():
        return [f"{area}: expected a directory"]

    for current, directories, filenames in os.walk(area, topdown=True, followlinks=False):
        current_path = Path(current)
        relative_directory = current_path.relative_to(area)

        kept_directories: list[str] = []
        for name in directories:
            rel = relative_directory / name
            reason = path_problem(rel.parts)
            full_path = current_path / name
            if reason:
                issues.append(f"{full_path}: {reason}")
            elif full_path.is_symlink():
                issues.append(f"{full_path}: symbolic links are not allowed in repository payload folders")
            else:
                kept_directories.append(name)
        directories[:] = kept_directories

        for name in filenames:
            full_path = current_path / name
            rel = relative_directory / name
            reason = path_problem(rel.parts)
            if reason:
                issues.append(f"{full_path}: {reason}")
            elif full_path.is_symlink():
                issues.append(f"{full_path}: symbolic links are not allowed in repository payload folders")

    return issues


def validate_zip(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names_seen: set[str] = set()
            for info in archive.infolist():
                raw_name = info.filename
                normalized = raw_name.replace("\\", "/")
                parts = PurePosixPath(normalized).parts

                if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
                    issues.append(f"{path}!/{raw_name}: absolute ZIP path is not allowed")
                    continue
                if ".." in parts:
                    issues.append(f"{path}!/{raw_name}: path traversal component '..' is not allowed")
                    continue

                reason = path_problem(parts)
                if reason:
                    issues.append(f"{path}!/{raw_name}: {reason}")

                # Duplicate ZIP entries can make extraction behavior ambiguous.
                folded = normalized.casefold()
                if folded in names_seen:
                    issues.append(f"{path}!/{raw_name}: duplicate ZIP entry (case-insensitive)")
                names_seen.add(folded)

                # Reject symlink entries rather than trusting extraction behavior.
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    issues.append(f"{path}!/{raw_name}: symbolic-link ZIP entry is not allowed")

            bad_member = archive.testzip()
            if bad_member is not None:
                issues.append(f"{path}: ZIP CRC/read check failed at {bad_member}")
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        issues.append(f"{path}: cannot read ZIP archive: {exc}")

    return issues


def validate_area(area: Path) -> list[str]:
    issues = validate_loose_tree(area)
    if area.exists() and area.is_dir():
        for archive_path in sorted(area.rglob("*.zip")):
            if archive_path.is_file():
                issues.extend(validate_zip(archive_path))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root (default: current directory)")
    parser.add_argument(
        "--areas",
        nargs="+",
        default=["Now", "Later"],
        choices=["Now", "Later", "Oldies"],
        help="payload directories to validate (default: Now Later)",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    all_issues: list[str] = []
    for area_name in args.areas:
        area = root / area_name
        print(f"Validating {area} ...")
        all_issues.extend(validate_area(area))

    if all_issues:
        print("\nRepository payload validation FAILED:", file=sys.stderr)
        for issue in all_issues:
            print(f"- {issue}", file=sys.stderr)
        print(f"\nFound {len(all_issues)} issue(s). No files were changed.", file=sys.stderr)
        return 1

    print("Repository payload validation PASSED. No hidden files, cache files, OS metadata, unsafe ZIP paths, duplicate ZIP entries, symlinks, or corrupt ZIPs were found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
