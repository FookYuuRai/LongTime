# -*- coding: utf-8 -*-
"""LongTime Oldies Browser - browse archived add-on versions in Kodi."""

import hashlib
import hmac
import json
import os
import re
import stat
import shutil
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import xbmc
import xbmcgui
import xbmcplugin
import xbmcvfs

ADDON_ID = "plugin.program.longtime.oldies"
OLDIES_BASE = "https://fookyuurai.github.io/LongTime/Oldies/"
CATALOG_URL = OLDIES_BASE + "catalog.json"
SOURCE_NAME = "LongTime Oldies Archive"
SOURCE_PREFIX = "LongTime Oldies - "
MAX_CATALOG_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 90 * 1024 * 1024
ADDON_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,160}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9._+~-]{1,100}$")
FILENAME_RE = re.compile(r"^[A-Za-z0-9._+-]{1,220}\.zip$")
SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")

HANDLE = int(sys.argv[1])
PLUGIN_URL = sys.argv[0]
QUERY = dict(urllib.parse.parse_qsl(sys.argv[2].lstrip("?"), keep_blank_values=True))


def _addon_profile_path():
    return xbmcvfs.translatePath("special://profile/addon_data/{}/".format(ADDON_ID))


def _ensure_dir(path):
    if not xbmcvfs.exists(path):
        if not xbmcvfs.mkdirs(path):
            raise RuntimeError("Kodi could not create the Oldies download folder.")


def _catalog_cache_path():
    return os.path.join(_addon_profile_path(), "catalog-cache.json")


def _pending_install_path():
    return os.path.join(_addon_profile_path(), "pending-install.json")


def _source_restart_marker_path():
    return os.path.join(_addon_profile_path(), "source-restart-required.json")


def _write_json_atomically(path, payload):
    _ensure_dir(_addon_profile_path())
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")
    os.replace(temporary, path)


def _load_catalog():
    request = urllib.request.Request(
        CATALOG_URL,
        headers={"User-Agent": "Kodi-LongTime-Oldies/1.0.0", "Cache-Control": "no-cache"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            final_url = response.geturl()
            parsed_final = urllib.parse.urlparse(final_url)
            if parsed_final.scheme != "https" or parsed_final.hostname != "fookyuurai.github.io":
                raise RuntimeError("The Oldies catalog redirected outside the trusted LongTime host.")
            data = response.read(MAX_CATALOG_BYTES + 1)
            if len(data) > MAX_CATALOG_BYTES:
                raise RuntimeError("The Oldies catalog is unexpectedly large.")
        catalog = json.loads(data.decode("utf-8"))
        _validate_catalog(catalog)
        _ensure_dir(_addon_profile_path())
        cache_path = _catalog_cache_path()
        temporary = cache_path + ".tmp"
        with open(temporary, "wb") as cache_file:
            cache_file.write(data)
        os.replace(temporary, cache_path)
        return catalog, False
    except Exception as network_error:
        try:
            with open(_catalog_cache_path(), "rb") as cache_file:
                catalog = json.load(cache_file)
            _validate_catalog(catalog)
            xbmc.log("LongTime Oldies: using cached catalog after fetch error: {}".format(network_error), xbmc.LOGWARNING)
            return catalog, True
        except Exception:
            raise RuntimeError("Could not load the Oldies catalog: {}".format(network_error))


def _validate_catalog(catalog):
    if not isinstance(catalog, dict) or catalog.get("schema_version") != 1:
        raise ValueError("Unsupported or malformed Oldies catalog.")
    addons = catalog.get("addons")
    if not isinstance(addons, list):
        raise ValueError("The Oldies catalog has no add-on list.")
    for addon in addons:
        if not isinstance(addon, dict):
            raise ValueError("Malformed add-on entry in Oldies catalog.")
        addon_id = addon.get("id", "")
        if not isinstance(addon_id, str) or not ADDON_ID_RE.fullmatch(addon_id):
            raise ValueError("Invalid add-on ID in Oldies catalog.")
        releases = addon.get("releases")
        if not isinstance(releases, list):
            raise ValueError("Malformed release list for {}.".format(addon_id))
        for release in releases:
            if not isinstance(release, dict):
                raise ValueError("Malformed release entry for {}.".format(addon_id))
            if not isinstance(release.get("version"), str) or not VERSION_RE.fullmatch(release["version"]):
                raise ValueError("Invalid version for {}.".format(addon_id))
            if not isinstance(release.get("filename"), str) or not FILENAME_RE.fullmatch(release["filename"]):
                raise ValueError("Invalid archive filename for {}.".format(addon_id))
            if not isinstance(release.get("sha256"), str) or not SHA256_RE.fullmatch(release["sha256"]):
                raise ValueError("Invalid SHA-256 for {}.".format(addon_id))
            size = release.get("bytes")
            if not isinstance(size, int) or size < 1 or size > MAX_ARCHIVE_BYTES:
                raise ValueError("Invalid archive size for {}.".format(addon_id))


def _plugin_url(**params):
    return PLUGIN_URL + "?" + urllib.parse.urlencode(params)


def _directory_item(label, url, is_folder=True, info=None):
    item = xbmcgui.ListItem(label=label)
    if info:
        item.setInfo("video", info)
    item.setProperty("IsPlayable", "false")
    xbmcplugin.addDirectoryItem(HANDLE, url, item, isFolder=is_folder)


def _finish(content="files"):
    xbmcplugin.setContent(HANDLE, content)
    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=True, cacheToDisc=False)


def _root():
    if _resume_pending_install():
        return
    catalog, from_cache = _load_catalog()
    addons = catalog.get("addons", [])
    addons = [addon for addon in addons if addon.get("releases")]
    addons.sort(key=lambda item: (str(item.get("name", item["id"])).casefold(), item["id"].casefold()))

    if from_cache:
        xbmcgui.Dialog().notification("LongTime Oldies", "Offline: showing the last cached archive list", xbmcgui.NOTIFICATION_WARNING, 4500)

    for addon in addons:
        addon_id = addon["id"]
        name = str(addon.get("name") or addon_id)
        count = len(addon["releases"])
        label = "{} ({}) — {} archived version{}".format(
            name, addon_id, count, "" if count == 1 else "s"
        )
        _directory_item(
            label,
            _plugin_url(action="versions", addon_id=addon_id),
            True,
            {"title": name, "plot": "Add-on ID: {}\nArchived versions: {}".format(addon_id, count)},
        )

    if not addons:
        xbmcgui.Dialog().ok("LongTime Oldies", "No previous releases are currently available.")
    _finish()


def _versions(addon_id):
    catalog, from_cache = _load_catalog()
    addon = next((item for item in catalog["addons"] if item["id"] == addon_id), None)
    if addon is None:
        raise RuntimeError("That add-on is no longer present in the Oldies catalog.")

    releases = sorted(
        addon["releases"],
        key=lambda release: str(release.get("archived_at", "")),
        reverse=True,
    )
    for release in releases:
        version = release["version"]
        archived = str(release.get("archived_at", ""))
        label = "Version {} — archived {}".format(version, archived or "date unknown")
        _directory_item(
            label,
            _plugin_url(action="stage", addon_id=addon_id, version=version, filename=release["filename"]),
            True,
            {
                "title": "{} {}".format(addon.get("name") or addon_id, version),
                "plot": "Add-on ID: {}\nVersion: {}\nArchived: {}\nOriginal ZIP: {}".format(
                    addon_id, version, archived or "unknown", release["filename"]
                ),
            },
        )
    if from_cache:
        xbmcgui.Dialog().notification("LongTime Oldies", "Showing cached archive information", xbmcgui.NOTIFICATION_WARNING, 3000)
    _finish()


def _find_release(catalog, addon_id, version, filename):
    for addon in catalog["addons"]:
        if addon["id"] != addon_id:
            continue
        for release in addon["releases"]:
            if release["version"] == version and release["filename"] == filename:
                return addon, release
    raise RuntimeError("That archived version is no longer listed. Refresh the Oldies browser.")


def _validate_archive(path, expected_id, expected_version):
    with zipfile.ZipFile(path, "r") as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise ValueError("The downloaded ZIP failed its CRC check at {}.".format(bad_member))

        infos = archive.infolist()
        if not infos:
            raise ValueError("The downloaded ZIP is empty.")
        if sum(info.file_size for info in infos) > 500 * 1024 * 1024:
            raise ValueError("The downloaded ZIP expands beyond the safety limit.")
        names_seen = set()
        addon_xml_members = []
        for info in infos:
            normalized = info.filename.replace("\\", "/")
            clean_name = normalized.rstrip("/")
            parts = clean_name.split("/")
            if normalized.startswith("/") or ".." in parts or "" in parts or not parts or parts[0] != expected_id:
                raise ValueError("The downloaded ZIP has an unsafe or unexpected path.")
            if any(part.startswith(".") for part in parts):
                raise ValueError("The downloaded ZIP contains a hidden file or folder.")
            folded = clean_name.casefold()
            if folded in names_seen:
                raise ValueError("The downloaded ZIP contains duplicate paths.")
            names_seen.add(folded)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ValueError("The downloaded ZIP contains a symbolic link.")
            if not info.is_dir() and len(parts) == 2 and parts[1].casefold() == "addon.xml":
                addon_xml_members.append(info.filename)
        if len(addon_xml_members) != 1:
            raise ValueError("The ZIP must contain exactly one {}/addon.xml.".format(expected_id))

        root = ET.fromstring(archive.read(addon_xml_members[0]))
        if root.tag != "addon" or root.attrib.get("id") != expected_id:
            raise ValueError("The package add-on ID does not match the selected release.")
        if root.attrib.get("version") != expected_version:
            raise ValueError("The package version does not match the selected release.")


def _download_release(addon_id, version, filename, expected_sha256, expected_bytes):
    if not ADDON_ID_RE.fullmatch(addon_id) or not VERSION_RE.fullmatch(version) or not FILENAME_RE.fullmatch(filename):
        raise ValueError("The selected archive information is invalid.")
    if not SHA256_RE.fullmatch(expected_sha256):
        raise ValueError("The selected archive has no valid SHA-256 checksum.")
    if expected_bytes < 1 or expected_bytes > MAX_ARCHIVE_BYTES:
        raise ValueError("The selected archive exceeds the allowed download size.")

    package_dir = os.path.join(_addon_profile_path(), "packages")
    _ensure_dir(package_dir)
    target = os.path.join(package_dir, filename)
    temporary = target + ".download"
    # Keep the registered Kodi source limited to the single newly selected ZIP.
    for old_name in os.listdir(package_dir):
        if old_name.lower().endswith((".zip", ".download")):
            old_path = os.path.join(package_dir, old_name)
            if os.path.isfile(old_path) or os.path.islink(old_path):
                os.remove(old_path)
    url = OLDIES_BASE + urllib.parse.quote(addon_id, safe="") + "/" + urllib.parse.quote(filename, safe="")
    request = urllib.request.Request(url, headers={"User-Agent": "Kodi-LongTime-Oldies/1.0.0"})

    digest = hashlib.sha256()
    downloaded = 0
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            final_url = response.geturl()
            parsed_final = urllib.parse.urlparse(final_url)
            if parsed_final.scheme != "https" or parsed_final.hostname != "fookyuurai.github.io":
                raise RuntimeError("The archive download redirected outside the trusted LongTime host.")
            with open(temporary, "wb") as output:
                while True:
                    block = response.read(1024 * 256)
                    if not block:
                        break
                    downloaded += len(block)
                    if downloaded > MAX_ARCHIVE_BYTES or downloaded > expected_bytes:
                        raise RuntimeError("The archive download exceeded its published size.")
                    digest.update(block)
                    output.write(block)
        if downloaded != expected_bytes:
            raise RuntimeError("The downloaded archive size does not match the catalog.")
        if not hmac.compare_digest(digest.hexdigest().lower(), expected_sha256.lower()):
            raise RuntimeError("The downloaded archive failed its SHA-256 verification.")
        _validate_archive(temporary, addon_id, version)
        if os.path.exists(target):
            os.remove(target)
        os.replace(temporary, target)
        return target, package_dir
    except Exception:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass
        raise


def _register_install_source(package_dir):
    """Ensure one permanent source exists; first creation requires a Kodi restart."""
    sources_path = xbmcvfs.translatePath("special://profile/sources.xml")
    source_virtual_path = "special://profile/addon_data/{}/packages/".format(ADDON_ID)

    if os.path.isfile(sources_path):
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        try:
            tree = ET.parse(sources_path, parser=parser)
            root = tree.getroot()
            if root.tag != "sources":
                raise ValueError("Kodi's sources.xml has an unexpected root element.")
        except Exception as error:
            raise RuntimeError("Could not safely update Kodi's sources.xml: {}".format(error))
    else:
        root = ET.Element("sources")
        tree = ET.ElementTree(root)

    files_node = root.find("files")
    if files_node is None:
        files_node = ET.SubElement(root, "files")

    for source in list(files_node.findall("source")):
        name_node = source.find("name")
        path_node = source.find("path")
        name = (name_node.text or "").strip() if name_node is not None else ""
        path = (path_node.text or "").strip() if path_node is not None else ""
        if name == SOURCE_NAME and path == source_virtual_path:
            marker_path = _source_restart_marker_path()
            if os.path.isfile(marker_path):
                try:
                    with open(marker_path, "r", encoding="utf-8") as marker_file:
                        marker = json.load(marker_file)
                    if marker.get("pid") == os.getpid():
                        return SOURCE_NAME, True
                except Exception:
                    pass
                try:
                    os.remove(marker_path)
                except OSError:
                    pass
            return SOURCE_NAME, False

    # Remove only the source created by this add-on, including names used by
    # the earlier per-version implementation. All user-defined sources stay.
    for source in list(files_node.findall("source")):
        name_node = source.find("name")
        name = (name_node.text or "").strip() if name_node is not None else ""
        if name == SOURCE_NAME or name.startswith(SOURCE_PREFIX):
            files_node.remove(source)

    source = ET.SubElement(files_node, "source")
    ET.SubElement(source, "name").text = SOURCE_NAME
    path_node = ET.SubElement(source, "path", {"pathversion": "1"})
    path_node.text = source_virtual_path
    ET.SubElement(source, "allowsharing").text = "false"

    directory = os.path.dirname(sources_path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    temporary = sources_path + ".longtime.tmp"
    tree.write(temporary, encoding="utf-8", xml_declaration=True)
    os.replace(temporary, sources_path)

    _write_json_atomically(_source_restart_marker_path(), {"pid": os.getpid()})
    return SOURCE_NAME, True


def _resume_pending_install():
    """After the one-time restart, offer to open Kodi's native ZIP installer."""
    pending_path = _pending_install_path()
    if not os.path.isfile(pending_path):
        return False

    try:
        with open(pending_path, "r", encoding="utf-8") as pending_file:
            pending = json.load(pending_file)
        addon_id = pending.get("addon_id", "")
        version = pending.get("version", "")
        filename = pending.get("filename", "")
        expected_sha256 = pending.get("sha256", "")
        expected_bytes = pending.get("bytes", 0)
        if not ADDON_ID_RE.fullmatch(addon_id) or not VERSION_RE.fullmatch(version) or not FILENAME_RE.fullmatch(filename):
            raise ValueError("The staged Oldies selection is malformed.")
        if not SHA256_RE.fullmatch(expected_sha256) or not isinstance(expected_bytes, int) or expected_bytes < 1:
            raise ValueError("The staged Oldies checksum or file size is invalid.")
        package_path = os.path.join(_addon_profile_path(), "packages", filename)
        if not os.path.isfile(package_path) or os.path.getsize(package_path) != expected_bytes:
            raise ValueError("The staged ZIP is missing or has changed. Select the version again to download it.")
        digest = hashlib.sha256()
        with open(package_path, "rb") as archive_file:
            for block in iter(lambda: archive_file.read(1024 * 256), b""):
                digest.update(block)
        if not hmac.compare_digest(digest.hexdigest().lower(), expected_sha256.lower()):
            raise ValueError("The staged ZIP checksum no longer matches the archive catalog.")
        _validate_archive(package_path, addon_id, version)

        marker_path = _source_restart_marker_path()
        if os.path.isfile(marker_path):
            try:
                with open(marker_path, "r", encoding="utf-8") as marker_file:
                    marker = json.load(marker_file)
                if marker.get("pid") == os.getpid():
                    xbmcgui.Dialog().notification(
                        "LongTime Oldies",
                        "Restart Kodi once to load the Oldies install source, then open this browser again.",
                        xbmcgui.NOTIFICATION_WARNING,
                        7000,
                    )
                    return False
            except Exception:
                pass
            try:
                os.remove(marker_path)
            except OSError:
                pass

        prompt = (
            "A verified archive is ready.\n\n"
            "Add-on: {}\nVersion: {}\n\n"
            "Open Kodi's native Install from ZIP window now?"
        ).format(addon_id, version)
        if not xbmcgui.Dialog().yesno("Install staged Oldies release?", prompt, yeslabel="Open installer", nolabel="Not now"):
            return False
        try:
            os.remove(pending_path)
        except OSError:
            pass
        xbmcgui.Dialog().notification(
            "LongTime Oldies",
            "Choose '{}' and then '{}' in Kodi's ZIP installer.".format(SOURCE_NAME, filename),
            xbmcgui.NOTIFICATION_INFO,
            7000,
        )
        xbmc.executebuiltin("InstallFromZip")
        _finish()
        return True
    except Exception as error:
        xbmc.log("LongTime Oldies pending install error: {}".format(error), xbmc.LOGERROR)
        xbmcgui.Dialog().ok("LongTime Oldies", str(error))
        try:
            os.remove(pending_path)
        except OSError:
            pass
        return False


def _stage(addon_id, version, filename):
    catalog, _ = _load_catalog()
    addon, release = _find_release(catalog, addon_id, version, filename)
    name = str(addon.get("name") or addon_id)
    archived = str(release.get("archived_at", "date unknown"))
    message = (
        "Selected: {}\n"
        "Add-on ID: {}\n"
        "Version: {}\n"
        "Archived: {}\n\n"
        "Kodi will open its native Install from ZIP browser. "
        "Choose the LongTime Oldies source and then select the downloaded ZIP. "
        "Kodi 22 pins ZIP-installed versions when they are older than a compatible repository release."
    ).format(name, addon_id, version, archived)
    if not xbmcgui.Dialog().yesno("Install archived release?", message, yeslabel="Continue", nolabel="Cancel"):
        _finish()
        return

    progress = xbmcgui.DialogProgress()
    progress.create("LongTime Oldies", "Downloading and verifying the selected release...")
    try:
        path, package_dir = _download_release(
            addon_id,
            version,
            filename,
            release["sha256"],
            release["bytes"],
        )
        progress.update(100, "Archive verified. Preparing Kodi's native installer...")
        source_name, restart_required = _register_install_source(package_dir)
        _write_json_atomically(_pending_install_path(), {
            "addon_id": addon_id,
            "version": version,
            "filename": filename,
            "sha256": release["sha256"],
            "bytes": release["bytes"],
        })
    finally:
        progress.close()

    if restart_required:
        xbmcgui.Dialog().ok(
            "Restart Kodi once",
            "The archived ZIP is downloaded and verified.\n\n"
            "Kodi loads File Manager sources when it starts, so restart Kodi once to activate "
            "the new '{}' source. Then open LongTime Oldies Browser again; it will offer to "
            "open the installer for version {}.".format(source_name, version),
        )
        _finish()
        return

    # The fixed source was already loaded by Kodi at startup. Kodi's builtin
    # opens its native ZIP picker; it does not accept a ZIP path argument.
    xbmcgui.Dialog().notification(
        "LongTime Oldies",
        "Choose '{}' and then '{}' in Kodi's ZIP installer.".format(source_name, filename),
        xbmcgui.NOTIFICATION_INFO,
        7000,
    )
    try:
        os.remove(_pending_install_path())
    except OSError:
        pass
    xbmc.executebuiltin("InstallFromZip")
    _finish()


def main():
    action = QUERY.get("action", "root")
    try:
        if action == "root":
            _root()
        elif action == "versions":
            addon_id = QUERY.get("addon_id", "")
            if not ADDON_ID_RE.fullmatch(addon_id):
                raise ValueError("Invalid add-on ID.")
            _versions(addon_id)
        elif action == "stage":
            addon_id = QUERY.get("addon_id", "")
            version = QUERY.get("version", "")
            filename = QUERY.get("filename", "")
            if not ADDON_ID_RE.fullmatch(addon_id) or not VERSION_RE.fullmatch(version) or not FILENAME_RE.fullmatch(filename):
                raise ValueError("Invalid archived release selection.")
            _stage(addon_id, version, filename)
        else:
            raise ValueError("Unknown Oldies browser action.")
    except Exception as error:
        xbmc.log("LongTime Oldies error: {}".format(error), xbmc.LOGERROR)
        xbmcgui.Dialog().ok("LongTime Oldies", str(error))
        try:
            _finish()
        except Exception:
            pass


if __name__ == "__main__":
    main()
