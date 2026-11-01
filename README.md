# LongTime

Add-on ZIPs and the files Kodi needs to install and update them.

Folders:
- `Later/`: upload folder. Put new add-on ZIPs here.
- `Now/`: published folder. The build writes it. Kodi reads it.

## Add or update an add-on

1. Put the add-on ZIP in `Later/`. The ZIP must hold one top-level folder named exactly like the add-on ID, with `addon.xml` inside, and nothing else outside that folder.
2. The `build repo` workflow validates the payloads, runs `tools/make_repo.py`, validates the generated repository again, and commits the generated files.
3. The build publishes the highest version of each add-on in `Now/`, updates `Now/addons.xml` and its checksum, and deletes older ZIPs from `Later/`. Deleted copies remain in Git history.

A new version needs a higher `version` in its `addon.xml` than the one published. Versions are compared like Kodi does: `1.1.1~beta2` is older than `1.1.1`, which is older than `1.1.2`.

## Payload cleanliness checks

`tools/validate_repo_files.py` is the shared, read-only validator used by both `build-repo.yml` and `pages.yml` (and by the Nightshift ambience pack updater). It recursively checks loose files and every ZIP under `Now/` and `Later/`. It fails the workflow rather than silently publishing a dirty archive.

The validator rejects hidden files or directories, `__pycache__`, `__MACOSX`, `.pyc`, `.pyo`, `.DS_Store`, `Thumbs.db`, `desktop.ini`, `ehthumbs.db`, symbolic links, unsafe ZIP paths, duplicate ZIP entries, and corrupt ZIP archives. It also validates the staged `Now/` copy before GitHub Pages uploads it.

Run it locally from the repository root with:

```bash
python3 tools/validate_repo_files.py --areas Now Later
```

The validator does not delete or repair files. Remove or replace the reported item, then rerun the build.

## Nightshift ambience pack

The ambience pack updater discovers the actual supported audio filenames in each release ZIP. It regenerates `tracks.py`, the per-track Kodi settings, and English labels from that list; there is no fixed track count. The add-on stores the installed pack SHA-256 and refreshes audio even when a track is replaced under the same filename. Obsolete pack-managed tracks are removed only after the replacement pack is verified and installed.

## Install in Kodi (once)

Kodi needs the repository add-on, `repository.longtime-1.0.0.zip`, once. Add `https://FookYuuRai.github.io/LongTime/` as a source in Kodi's File Manager, then install the repository ZIP from `Now/repository.longtime/`.

Kodi checks the repository for updates on its own schedule (and at start-up). Restarting Kodi forces a check.

## Already installed before the folder rename

Devices that installed the repository before the rename still point at the old `repo/` address, which no longer exists, so they will not see updates. Reinstall the repository add-on once from the `Now/` paths above. After that, updates arrive through the normal check.
