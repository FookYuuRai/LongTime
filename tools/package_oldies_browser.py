#!/usr/bin/env python3
"""Build the LongTime Oldies Kodi browser ZIP from its maintained source tree."""

import argparse
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DEFAULT = ROOT / "tools" / "_source" / "plugin.program.longtime.oldies"
OUTPUT_DEFAULT = ROOT / "Later"
ZIP_STAMP = (2026, 1, 1, 0, 0, 0)
JUNK_NAMES = {"__pycache__", "__macosx", ".git", ".svn", ".ds_store", "thumbs.db", "desktop.ini"}


def safe_member(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    parts = PurePosixPath(rel).parts
    if not parts or any(part.startswith(".") or part.casefold() in JUNK_NAMES for part in parts):
        raise ValueError("Hidden or packaging-junk path is not allowed: {}".format(rel))
    if path.is_symlink() or not path.is_file():
        raise ValueError("Only regular files are allowed in the browser source: {}".format(rel))
    return rel


def build(source: Path, output: Path) -> Path:
    source = source.resolve()
    if not source.is_dir():
        raise ValueError("Browser source folder does not exist: {}".format(source))
    addon_xml = source / "addon.xml"
    if not addon_xml.is_file():
        raise ValueError("Browser source must contain addon.xml.")

    root = ElementTree.parse(str(addon_xml)).getroot()
    if root.tag != "addon":
        raise ValueError("addon.xml root must be <addon>.")
    addon_id = root.attrib.get("id", "")
    version = root.attrib.get("version", "")
    if addon_id != "plugin.program.longtime.oldies":
        raise ValueError("Unexpected Oldies browser add-on ID: {}".format(addon_id))
    if not re.fullmatch(r"[0-9A-Za-z._+-]{1,100}", version):
        raise ValueError("Invalid add-on version in addon.xml.")

    files = sorted(path for path in source.rglob("*") if path.is_file())
    if not files:
        raise ValueError("Browser source contains no files.")
    members = [(safe_member(path, source), path) for path in files]
    if "addon.xml" not in {member for member, _ in members}:
        raise ValueError("addon.xml was not included in the package.")

    output.mkdir(parents=True, exist_ok=True)
    destination = output / "{}-{}.zip".format(addon_id, version)
    fd, temporary_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=str(output))
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, path in members:
                info = zipfile.ZipInfo("{}/{}".format(addon_id, relative), date_time=ZIP_STAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.create_system = 3
                archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        with zipfile.ZipFile(temporary, "r") as check:
            bad = check.testzip()
            if bad:
                raise ValueError("Generated ZIP failed CRC check at {}".format(bad))
            names = check.namelist()
            if not names or any(not name.startswith(addon_id + "/") for name in names):
                raise ValueError("Generated ZIP has an invalid top-level layout.")
            if addon_id + "/addon.xml" not in names:
                raise ValueError("Generated ZIP does not contain the add-on manifest.")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    print("Generated {} ({} files)".format(destination, len(members)))
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    args = parser.parse_args()
    try:
        build(args.source, args.output)
    except (OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as error:
        parser.exit(1, "error: {}\n".format(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
