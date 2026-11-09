#!/usr/bin/env python3
"""Archive the previously published Kodi add-on ZIPs and expose Oldies on Pages.

Archives are stored as:
    Oldies/<addon-id>/<UTC-timestamp>_<run-id>_<addon-id>-<version>.zip

The five newest archived revisions are retained separately for each add-on.
The currently published ZIP remains in Now/; Oldies contains previous releases.
"""

import argparse
import datetime as dt
import html
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
NOW = ROOT / "Now"
OLDIES = ROOT / "Oldies"
KEEP_PER_ADDON = 5
REPO_ADDON_ID = "repository.longtime"


def package_identity(zip_path):
    """Read and validate the package add-on ID and version."""
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
        folder_id = candidates[0].split("/", 1)[0]

        if not addon_id or not version or addon_id != folder_id:
            raise ValueError("addon.xml ID/version or top-level folder is invalid")

        return addon_id, version


def write_oldies_indexes():
    """Create simple static HTML indexes for GitHub Pages browsing."""
    OLDIES.mkdir(parents=True, exist_ok=True)
    addon_dirs = sorted(
        p for p in OLDIES.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )

    for addon_dir in addon_dirs:
        archives = sorted(
            (p for p in addon_dir.glob("*.zip") if p.is_file()),
            key=lambda p: p.name,
            reverse=True,
        )
        rows = [
            '<li><a href="{0}">{1}</a></li>'.format(
                html.escape(p.name, quote=True),
                html.escape(p.name),
            )
            for p in archives
        ]
        page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oldies — {title}</title></head>
<body><h1>Previous releases: {title}</h1>
<p>Archived Kodi add-on ZIPs. The current release is in <a href="../../Now/">Now/</a>.</p>
<ul>{items}</ul><p><a href="../">Back to Oldies</a></p></body></html>
""".format(title=html.escape(addon_dir.name), items="".join(rows))
        (addon_dir / "index.html").write_text(page, encoding="utf-8")

    rows = [
        '<li><a href="{0}/">{1}</a> ({2} archived ZIPs)</li>'.format(
            html.escape(p.name, quote=True),
            html.escape(p.name),
            len(list(p.glob("*.zip"))),
        )
        for p in addon_dirs
    ]
    page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oldies — LongTime</title></head>
<body><h1>Oldies — previous releases</h1>
<p>Up to five previous releases are retained per add-on. The current release is in <a href="../Now/">Now/</a>.</p>
<ul>{items}</ul><p><a href="../">Back to LongTime</a></p></body></html>
""".format(items="".join(rows))
    (OLDIES / "index.html").write_text(page, encoding="utf-8")

    readme = """# Oldies

This folder is created and maintained automatically by GitHub Actions.

- Previous published add-on ZIPs are archived under `Oldies/<addon-id>/`.
- The five newest archived revisions are retained for each add-on.
- The current release remains in `Now/`.
- ZIP contents and their internal top-level folder names are preserved unchanged.

To roll back, copy the desired ZIP from `Oldies/<addon-id>/` into `Later/` and run the normal pipeline.
"""
    (OLDIES / "README.md").write_text(readme, encoding="utf-8")


def archive_current():
    """Copy each currently published add-on ZIP into Oldies, then prune."""
    OLDIES.mkdir(parents=True, exist_ok=True)
    run_id = re.sub(r"[^A-Za-z0-9_-]", "", os.environ.get("ARCHIVE_RUN_ID", "manual"))
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archived_count = 0

    if NOW.is_dir():
        for addon_dir in sorted(p for p in NOW.iterdir() if p.is_dir()):
            addon_id = addon_dir.name
            if addon_id == REPO_ADDON_ID or addon_id.startswith("."):
                continue

            target_dir = OLDIES / addon_id
            target_dir.mkdir(parents=True, exist_ok=True)

            for zip_path in sorted(addon_dir.glob("*.zip")):
                if not zip_path.is_file():
                    continue
                try:
                    found_id, version = package_identity(zip_path)
                    if found_id != addon_id:
                        raise ValueError(
                            "ZIP add-on ID does not match its Now/ directory"
                        )
                except (OSError, zipfile.BadZipFile, ElementTree.ParseError, ValueError) as exc:
                    print("warning: not archiving {}: {}".format(zip_path, exc))
                    continue

                # Avoid storing the same exact release repeatedly on scheduled runs.
                duplicate = False
                for existing in target_dir.glob("*.zip"):
                    try:
                        existing_id, existing_version = package_identity(existing)
                        if existing_id == addon_id and existing_version == version:
                            duplicate = True
                            break
                    except (OSError, zipfile.BadZipFile, ElementTree.ParseError, ValueError):
                        continue

                if duplicate:
                    print("already archived: {} {}".format(addon_id, version))
                    continue

                safe_version = re.sub(r"[^A-Za-z0-9._+-]", "_", version)
                filename = "{}_{}_{}-{}.zip".format(
                    timestamp, run_id, addon_id, safe_version
                )
                destination = target_dir / filename
                shutil.copyfile(zip_path, destination)

                # Verify the copied archive before considering it retained.
                copied_id, copied_version = package_identity(destination)
                if copied_id != addon_id or copied_version != version:
                    destination.unlink(missing_ok=True)
                    raise RuntimeError("archive verification failed: " + str(destination))

                archived_count += 1
                print("archived: {} {}".format(addon_id, version))

            # Timestamp-prefixed filenames sort chronologically.
            releases = sorted(
                (p for p in target_dir.glob("*.zip") if p.is_file()),
                key=lambda p: p.name,
                reverse=True,
            )
            for obsolete in releases[KEEP_PER_ADDON:]:
                obsolete.unlink()
                print("pruned old archive: {}".format(obsolete))

    write_oldies_indexes()
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
