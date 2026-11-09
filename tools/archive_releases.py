#!/usr/bin/env python3
"""Archive superseded Kodi add-on ZIPs and build the Oldies catalog for Kodi."""

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import urllib.parse
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
NOW = ROOT / "Now"
LATER = ROOT / "Later"
OLDIES = ROOT / "Oldies"
KEEP_PER_ADDON = 5
REPO_ADDON_ID = "repository.longtime"
TIMESTAMP_RE = re.compile(r"^(\d{8}T\d{6}Z)_")
JUNK_PARTS = {"__macosx", "__pycache__", ".git", ".svn"}
JUNK_FILES = {".ds_store", "thumbs.db", "desktop.ini", "ehthumbs.db"}
JUNK_SUFFIXES = (".pyc", ".pyo")
PAGES_BASE = "https://fookyuurai.github.io/LongTime/Oldies/"


def package_details(zip_path):
    """Return validated package identity and display metadata."""
    with zipfile.ZipFile(zip_path, "r") as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise ValueError("corrupt ZIP member: " + bad_member)

        candidates = [
            name for name in archive.namelist()
            if name.count("/") == 1
            and name.lower().endswith("/addon.xml")
            and not name.startswith("/")
        ]
        if len(candidates) != 1:
            raise ValueError("expected exactly one top-level addon.xml")

        xml_data = archive.read(candidates[0])
        addon = ElementTree.fromstring(xml_data)
        addon_id = addon.attrib.get("id", "")
        version = addon.attrib.get("version", "")
        name = addon.attrib.get("name", addon_id)
        folder_id = candidates[0].split("/", 1)[0]

        if not addon_id or not version or addon_id != folder_id:
            raise ValueError("addon.xml ID/version or top-level folder is invalid")
        return addon_id, version, name


def _order(char):
    if char == "~":
        return -1
    if char.isalpha():
        return ord(char)
    return ord(char) + 256


def compare_versions(a, b):
    """Kodi-compatible Debian-style version comparison; return -1, 0, or 1."""
    while a or b:
        text_a = re.match(r"\D*", a).group(0)
        text_b = re.match(r"\D*", b).group(0)
        a = a[len(text_a):]
        b = b[len(text_b):]
        for i in range(max(len(text_a), len(text_b))):
            order_a = _order(text_a[i]) if i < len(text_a) else 0
            order_b = _order(text_b[i]) if i < len(text_b) else 0
            if order_a != order_b:
                return -1 if order_a < order_b else 1

        num_a = re.match(r"\d*", a).group(0)
        num_b = re.match(r"\d*", b).group(0)
        a = a[len(num_a):]
        b = b[len(num_b):]
        if int(num_a or 0) != int(num_b or 0):
            return -1 if int(num_a or 0) < int(num_b or 0) else 1
    return 0


def _highest_packages(folder):
    """Map add-on IDs to their highest valid ZIP package in one folder."""
    found = {}
    if not folder.is_dir():
        return found
    for zip_path in sorted(folder.glob("*.zip")):
        if not zip_path.is_file():
            continue
        try:
            addon_id, version, name = package_details(zip_path)
        except (OSError, zipfile.BadZipFile, ElementTree.ParseError, ValueError) as error:
            print("warning: skipping {}: {}".format(zip_path, error))
            continue
        if addon_id == REPO_ADDON_ID:
            continue
        existing = found.get(addon_id)
        if existing is None or compare_versions(version, existing["version"]) > 0:
            found[addon_id] = {"path": zip_path, "version": version, "name": name}
    return found


def _current_packages():
    """Read currently published packages from Now/<addon-id>/*.zip."""
    found = {}
    if not NOW.is_dir():
        return found
    for addon_dir in sorted(p for p in NOW.iterdir() if p.is_dir()):
        addon_id = addon_dir.name
        if addon_id.startswith(".") or addon_id == REPO_ADDON_ID:
            continue
        for zip_path in sorted(addon_dir.glob("*.zip")):
            try:
                package_id, version, name = package_details(zip_path)
            except (OSError, zipfile.BadZipFile, ElementTree.ParseError, ValueError) as error:
                print("warning: skipping current package {}: {}".format(zip_path, error))
                continue
            if package_id != addon_id:
                continue
            current = found.get(addon_id)
            if current is None or compare_versions(version, current["version"]) > 0:
                found[addon_id] = {"path": zip_path, "version": version, "name": name}
    return found


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _archived_at(filename):
    match = TIMESTAMP_RE.match(filename)
    if not match:
        return ""
    try:
        value = dt.datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
        return value.replace(tzinfo=dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return ""


def _release_records(addon_id, addon_dir):
    records = []
    if not addon_dir.is_dir():
        return records
    for archive_path in sorted(addon_dir.glob("*.zip"), key=lambda p: p.name, reverse=True):
        try:
            package_id, version, name = package_details(archive_path)
            if package_id != addon_id:
                continue
            records.append({
                "version": version,
                "filename": archive_path.name,
                "archived_at": _archived_at(archive_path.name),
                "bytes": archive_path.stat().st_size,
                "sha256": _sha256(archive_path),
                "name": name,
            })
        except (OSError, zipfile.BadZipFile, ElementTree.ParseError, ValueError) as error:
            print("warning: excluding invalid archive {}: {}".format(archive_path, error))
    return records


def _effective_published_versions(current, staged):
    """Use the queued higher version when deciding which archive is historical."""
    effective = {addon_id: item["version"] for addon_id, item in current.items()}
    for addon_id, item in staged.items():
        live = current.get(addon_id)
        if live is None or compare_versions(item["version"], live["version"]) > 0:
            effective[addon_id] = item["version"]
    return effective


def write_oldies_indexes(current=None, staged=None):
    """Write HTML indexes and the signed-by-hash machine-readable catalog."""
    OLDIES.mkdir(parents=True, exist_ok=True)
    current = current if current is not None else _current_packages()
    staged = staged if staged is not None else _highest_packages(LATER)
    effective_versions = _effective_published_versions(current, staged)
    addon_dirs = sorted(
        p for p in OLDIES.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )

    catalog_addons = []
    root_rows = []
    for addon_dir in addon_dirs:
        addon_id = addon_dir.name
        releases = _release_records(addon_id, addon_dir)
        live_version = effective_versions.get(addon_id)

        # Do not show the active release as an Oldies entry. If a newer version
        # is queued in Later, the current Now version is correctly listed as
        # historical because the queued version is treated as the target.
        releases = [
            release for release in releases
            if live_version is None or compare_versions(release["version"], live_version) != 0
        ]
        display_name = (
            (releases[0].get("name") if releases else None)
            or (current.get(addon_id, {}).get("name"))
            or (staged.get(addon_id, {}).get("name"))
            or addon_id
        )

        rows = []
        for release in releases:
            href = urllib.parse.quote(release["filename"], safe="")
            label = "Version {} — archived {}".format(
                release["version"], release["archived_at"] or "date unknown"
            )
            rows.append('<li><a href="{}">{}</a></li>'.format(
                html.escape(href, quote=True), html.escape(label)
            ))

        if releases:
            catalog_addons.append({
                "id": addon_id,
                "name": display_name,
                "releases": releases,
            })
            root_rows.append('<li><a href="{}/">{}</a> ({} archived versions)</li>'.format(
                html.escape(urllib.parse.quote(addon_id, safe=""), quote=True),
                html.escape(display_name),
                len(releases),
            ))
            body_message = "Choose an archived ZIP to download, or install the <strong>LongTime Oldies Browser</strong> in Kodi to browse versions and stage an install from within Kodi."
        else:
            body_message = 'There are no previous releases for this add-on at the moment. The active version is published in <a href="../../Now/">Now/</a>.'

        page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oldies — {title}</title></head>
<body><h1>Previous releases: {title}</h1>
<p>{message}</p>
<ul>{items}</ul><p><a href="../">Back to Oldies</a> · <a href="../../Now/">Current releases</a></p></body></html>
""".format(title=html.escape(display_name), message=body_message, items="".join(rows))
        (addon_dir / "index.html").write_text(page, encoding="utf-8", newline="\n")

    catalog = {
        "schema_version": 1,
        "retention_per_addon": KEEP_PER_ADDON,
        "addons": catalog_addons,
    }
    catalog_path = OLDIES / "catalog.json"
    catalog_bytes = (json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    # The catalog contains archive identities and SHA-256 hashes. It remains
    # stable between no-change runs, avoiding unnecessary Git commits.
    if not catalog_path.exists() or catalog_path.read_bytes() != catalog_bytes:
        catalog_path.write_bytes(catalog_bytes)

    page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oldies — LongTime</title></head>
<body><h1>Oldies — previous releases</h1>
<p>Up to five previous releases are retained per add-on. The current release is in <a href="../Now/">Now/</a>.</p>
<p>Kodi: install <strong>LongTime Oldies Browser</strong> from the LongTime repository, then open it under Programs to browse archived add-ons and versions.</p>
<ul>{items}</ul><p><a href="../">Back to LongTime</a></p></body></html>
""".format(items="".join(root_rows))
    (OLDIES / "index.html").write_text(page, encoding="utf-8", newline="\n")

    readme = """# Oldies — previous LongTime releases

This folder is created and maintained automatically by the LongTime build.

- Only releases superseded by a higher version queued in `Later/` are added to the archive.
- Up to five previous distinct releases are retained per add-on.
- The current release remains in `Now/` and is not shown as an Oldies version.
- Original ZIP contents and the internal top-level add-on folder are preserved unchanged.
- `catalog.json` is the version list used by the Kodi LongTime Oldies Browser. It includes each original filename, size, archived date, and SHA-256 checksum.

On the first build with this logic, any Oldies ZIP whose version matches the active ZIP in `Now/` is removed because it is not a previous release. The uploaded repository snapshot does not contain Git history, so genuine older ZIPs must already be present as separate files to appear immediately. Otherwise, this archive fills as future releases supersede the active versions. Do not rename a current ZIP to make it appear historical.

## Browse and install from Kodi

1. Update the LongTime repository and install **LongTime Oldies Browser** from the Programs category.
2. Open the browser from Kodi's Programs add-ons.
3. Select an add-on, then select the exact archived version.
4. The browser downloads the original ZIP and checks its size, SHA-256, archive integrity, add-on ID, and version.
5. The first time only, Kodi asks you to restart once after the verified ZIP is staged. This is needed because Kodi loads File Manager sources at startup. After restarting, reopen the browser and accept the prompt to open the native **Install from ZIP** window. Select `LongTime Oldies Archive`, then the staged ZIP. On later installs, the existing source is already loaded and no restart is needed.

Kodi's native ZIP dialog does not accept a file path as a command argument. The browser therefore maintains one dedicated File Manager source pointing at its private package folder; it stages only the version you selected. This keeps installation inside Kodi's supported installer instead of copying files directly into Kodi's add-on directory.

Kodi 22 automatically pins a ZIP-installed add-on version when it is older than the latest compatible version available from installed repositories. That prevents the newer version in `Now/` from automatically replacing the rollback version. To return to the current release, install the current version from the LongTime repository.
"""
    (OLDIES / "README.md").write_text(readme, encoding="utf-8", newline="\n")


def archive_current():
    """Archive only published versions that are about to be superseded."""
    OLDIES.mkdir(parents=True, exist_ok=True)
    run_id = re.sub(r"[^A-Za-z0-9_-]", "", os.environ.get("ARCHIVE_RUN_ID", "manual"))
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    current = _current_packages()
    staged = _highest_packages(LATER)
    archived_count = 0

    for addon_id, live in sorted(current.items()):
        incoming = staged.get(addon_id)
        comparison = compare_versions(incoming["version"], live["version"]) if incoming else 0
        if incoming and comparison < 0:
            raise RuntimeError(
                "Refusing to publish a downgrade for {}: Now has {}, but Later selects {}. "
                "Keep the current ZIP in Later or use the in-Kodi Oldies Browser to install a historical release.".format(
                    addon_id, live["version"], incoming["version"]
                )
            )
        will_be_replaced = incoming is not None and comparison > 0
        target_dir = OLDIES / addon_id

        if not will_be_replaced:
            # Clean false-current archives created by earlier archive logic.
            # Do not create empty per-add-on folders during no-change runs.
            if target_dir.is_dir():
                for archive_path in target_dir.glob("*.zip"):
                    try:
                        archived_id, archived_version, _ = package_details(archive_path)
                    except (OSError, zipfile.BadZipFile, ElementTree.ParseError, ValueError):
                        continue
                    if archived_id == addon_id and compare_versions(archived_version, live["version"]) == 0:
                        archive_path.unlink()
                        print("removed active version from Oldies: {} {}".format(addon_id, live["version"]))
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        source_zip = live["path"]
        duplicate = False
        for existing in target_dir.glob("*.zip"):
            try:
                existing_id, existing_version, _ = package_details(existing)
                if existing_id == addon_id and compare_versions(existing_version, live["version"]) == 0:
                    duplicate = True
                    break
            except (OSError, zipfile.BadZipFile, ElementTree.ParseError, ValueError):
                continue

        if duplicate:
            print("already archived: {} {}".format(addon_id, live["version"]))
        else:
            safe_version = re.sub(r"[^A-Za-z0-9._+-]", "_", live["version"])
            filename = "{}_{}_{}-{}.zip".format(timestamp, run_id, addon_id, safe_version)
            destination = target_dir / filename
            shutil.copyfile(source_zip, destination)
            copied_id, copied_version, _ = package_details(destination)
            if copied_id != addon_id or copied_version != live["version"]:
                destination.unlink(missing_ok=True)
                raise RuntimeError("archive verification failed: " + str(destination))
            archived_count += 1
            print("archived superseded release: {} {}".format(addon_id, live["version"]))

    # Prune every add-on archive, including folders for add-ons no longer live.
    for target_dir in sorted(p for p in OLDIES.iterdir() if p.is_dir()):
        addon_id = target_dir.name
        unique_releases = []
        for archive_path in sorted(target_dir.glob("*.zip"), key=lambda p: p.name, reverse=True):
            try:
                archive_id, archive_version, _ = package_details(archive_path)
                if archive_id != addon_id:
                    continue
            except (OSError, zipfile.BadZipFile, ElementTree.ParseError, ValueError):
                continue
            equivalent = next(
                (index for index, (version, _) in enumerate(unique_releases)
                 if compare_versions(archive_version, version) == 0),
                None,
            )
            if equivalent is None:
                unique_releases.append((archive_version, archive_path))
            else:
                # Newest timestamp wins when duplicate version copies exist.
                if archive_path.name > unique_releases[equivalent][1].name:
                    unique_releases[equivalent] = (archive_version, archive_path)

        keep_paths = {path for _, path in unique_releases[:KEEP_PER_ADDON]}
        for obsolete in target_dir.glob("*.zip"):
            if obsolete not in keep_paths:
                obsolete.unlink()
                print("pruned old archive: {}".format(obsolete))

        # Remove generated empty archive pages/folders left by earlier builds.
        if not list(target_dir.glob("*.zip")):
            generated_index = target_dir / "index.html"
            if generated_index.is_file():
                generated_index.unlink()
            try:
                target_dir.rmdir()
            except OSError:
                pass

    write_oldies_indexes(current=current, staged=staged)
    print("Oldies archive complete; newly archived ZIPs: {}".format(archived_count))


def add_root_link():
    """Add an Oldies/ link to the root index generated by make_repo.py."""
    root_index = ROOT / "index.html"
    if not root_index.is_file():
        raise SystemExit("index.html was not generated; refusing to create a partial root page")

    content = root_index.read_text(encoding="utf-8")
    marker = '<li><a href="Oldies/">Oldies/</a></li>'
    if marker in content:
        print("Oldies link already present in root index.")
        return
    if "<ul>" not in content:
        raise SystemExit("root index has no expected <ul> listing; refusing unsafe edit")
    content = content.replace("<ul>", "<ul>\n" + marker, 1)
    root_index.write_text(content, encoding="utf-8", newline="\n")
    print("Added Oldies/ link to root index.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--add-root-link", action="store_true")
    args = parser.parse_args()
    if args.archive == args.add_root_link:
        parser.error("choose exactly one of --archive or --add-root-link")
    if args.archive:
        archive_current()
    else:
        add_root_link()


if __name__ == "__main__":
    main()
