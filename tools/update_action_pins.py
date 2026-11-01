#!/usr/bin/env python3
"""Update pinned GitHub Actions to newer stable releases in the same major."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
API_ROOT = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN", "")

VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

PIN_RE = re.compile(
    r"^(?P<prefix>\s*uses:\s*)"
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
    r"@(?P<sha>[0-9a-fA-F]{40})"
    r"(?P<spacing>\s+#\s*)"
    r"(?P<version>v?\d+\.\d+\.\d+)"
    r"(?P<tail>\s*)$"
)


def parse_version(value: str) -> tuple[int, int, int] | None:
    match = VERSION_RE.fullmatch(value)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def api_get(path: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "LongTime-action-pin-updater",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"

    request = urllib.request.Request(API_ROOT + path, headers=headers)

    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)

        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429, 500, 502, 503, 504) and attempt < 2:
                retry_after = exc.headers.get("Retry-After", "")
                delay = (
                    int(retry_after)
                    if retry_after.isdigit()
                    else 2 ** (attempt + 1)
                )
                time.sleep(min(delay, 30))
                continue
            raise

        except urllib.error.URLError:
            if attempt >= 2:
                raise
            time.sleep(2 ** (attempt + 1))

    raise RuntimeError(f"GitHub API request failed: {path}")


def repository_path(repository: str) -> str:
    return "/".join(
        urllib.parse.quote(part, safe="")
        for part in repository.split("/", 1)
    )


def get_releases(repository: str) -> list[dict]:
    path = repository_path(repository)
    return api_get(f"/repos/{path}/releases?per_page=100")


def find_newer_release(
    releases: list[dict],
    current_version: tuple[int, int, int],
) -> tuple[str, tuple[int, int, int]] | None:
    candidates = []

    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue

        tag = release.get("tag_name", "")
        version = parse_version(tag)

        if version is None:
            continue
        if version[0] != current_version[0]:
            continue
        if version <= current_version:
            continue

        candidates.append((version, tag))

    if not candidates:
        return None

    version, tag = max(candidates, key=lambda item: item[0])
    return tag, version


def resolve_commit(repository: str, tag: str) -> str:
    path = repository_path(repository)
    encoded_tag = urllib.parse.quote(tag, safe="")
    result = api_get(f"/repos/{path}/commits/{encoded_tag}")
    sha = result.get("sha", "")

    if not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise RuntimeError(
            f"Invalid commit SHA returned for {repository}@{tag}"
        )

    return sha.lower()


def update_file(
    path: Path,
    releases_cache: dict[str, list[dict] | None],
    commit_cache: dict[tuple[str, str], str | None],
) -> int:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    changes = 0

    for index, line in enumerate(lines):
        content = line.rstrip("\r\n")
        newline = line[len(content):]
        match = PIN_RE.fullmatch(content)

        if not match:
            continue

        repository = match.group("repo")
        current_sha = match.group("sha").lower()
        current_tag = match.group("version")
        current_version = parse_version(current_tag)

        if current_version is None:
            continue

        if repository not in releases_cache:
            try:
                releases_cache[repository] = get_releases(repository)
            except Exception as exc:
                print(
                    f"WARNING: could not read releases for "
                    f"{repository}: {exc}",
                    file=sys.stderr,
                )
                releases_cache[repository] = None

        releases = releases_cache[repository]
        if releases is None:
            continue

        release = find_newer_release(releases, current_version)
        if release is None:
            continue

        new_tag, _new_version = release
        cache_key = (repository, new_tag)

        if cache_key not in commit_cache:
            try:
                commit_cache[cache_key] = resolve_commit(
                    repository, new_tag
                )
            except Exception as exc:
                print(
                    f"WARNING: could not resolve "
                    f"{repository}@{new_tag}: {exc}",
                    file=sys.stderr,
                )
                commit_cache[cache_key] = None

        new_sha = commit_cache[cache_key]

        if not new_sha or new_sha == current_sha:
            continue

        lines[index] = (
            f"{match.group('prefix')}{repository}@{new_sha}"
            f"{match.group('spacing')}{new_tag}"
            f"{match.group('tail')}{newline}"
        )

        changes += 1
        print(
            f"Updated {path.relative_to(ROOT)}: "
            f"{repository} {current_tag} -> {new_tag}"
        )

    updated = "".join(lines)

    if updated != original:
        path.write_text(updated, encoding="utf-8")

    return changes


def main() -> int:
    if not WORKFLOWS_DIR.is_dir():
        print(
            f"ERROR: workflow directory not found: {WORKFLOWS_DIR}",
            file=sys.stderr,
        )
        return 1

    workflow_files = sorted(
        path
        for pattern in ("*.yml", "*.yaml")
        for path in WORKFLOWS_DIR.glob(pattern)
        if path.is_file()
    )

    if not workflow_files:
        print("No workflow YAML files found.")
        return 0

    releases_cache: dict[str, list[dict] | None] = {}
    commit_cache: dict[tuple[str, str], str | None] = {}
    total_changes = 0

    for path in workflow_files:
        total_changes += update_file(
            path, releases_cache, commit_cache
        )

    if total_changes:
        print(f"Updated {total_changes} action pin(s).")
    else:
        print("No newer compatible stable action releases found.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
