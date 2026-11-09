# LongTime

LongTime builds and publishes a Kodi add-on repository and its GitHub Pages website. Add-on ZIPs are submitted through `Later/`; validated, generated repository files are published under `Now/`. Previous releases are retained in `Oldies/` and can be browsed from inside Kodi with the **LongTime Oldies Browser**.

## Repository layout

- `Later/`: incoming add-on ZIPs awaiting publication.
- `Now/`: generated Kodi repository, current published add-on ZIPs, and website assets.
- `Oldies/`: automatically maintained archive of up to five superseded versions per add-on, plus the catalog used by the Kodi browser.
- `tools/make_repo.py`: builds the Kodi repository and prepares a descriptive commit message from add-on changelog changes.
- `tools/archive_releases.py`: archives only published versions that are being superseded, retains five distinct releases, and generates the Oldies indexes and SHA-256 catalog.
- `tools/package_oldies_browser.py`: creates the LongTime Oldies Browser ZIP from its maintained source folder.
- `tools/_source/plugin.program.longtime.oldies/`: source code for the in-Kodi archive browser.
- `tools/validate_repo_files.py`: read-only validation of repository payloads, including Oldies archives.
- `.github/workflows/`: automation for repository builds, Pages deployment, and supported add-on update tasks.
- `index.html`: GitHub Pages homepage.

Generated files in `Now/` and `Oldies/` should be produced by the repository build rather than edited manually. The Oldies Browser package is built automatically during the repository build; you do not need to manually place its ZIP in `Later/`.

## Add or update an add-on

1. Place the add-on ZIP in `Later/`.
2. The ZIP must contain one top-level directory named exactly after the add-on ID, with `addon.xml` inside it. Do not include unrelated files outside that directory.
3. The build validates the incoming payloads and currently published files.
4. The build packages the LongTime Oldies Browser from `tools/_source/plugin.program.longtime.oldies/` into `Later/` so that it is published through the same Kodi repository feed.
5. Before generating the replacement repository, the build archives a currently published ZIP only when a higher version of that same add-on is queued in `Later/`. Scheduled no-change runs do not copy the active release into Oldies.
6. Each copied ZIP is integrity-checked and its add-on ID/version are verified. The build then runs `tools/make_repo.py`, updates repository metadata, and validates `Now/`, `Later/`, and `Oldies/`.
7. The build commits and pushes generated changes to `OnTheSide`.
8. The separate Pages stage publishes the homepage, `Now/`, and `Oldies/` after the repository build succeeds.

A new release should have a higher version in `addon.xml` than the currently published release. The build stops rather than replacing a current add-on with a lower version from `Later/`; use the in-Kodi Oldies Browser for a deliberate rollback. Version ordering follows Kodi-compatible comparison rules. For example, `1.1.1~beta2` is older than `1.1.1`, which is older than `1.1.2`.

## Browse and install previous releases inside Kodi

The Oldies archive is not just a web download folder. The **LongTime Oldies Browser** is a Program add-on published through the existing LongTime Kodi repository.

After the workflow has completed successfully:

1. In Kodi, open the LongTime repository and allow it to refresh. If the browser does not appear, use **Check for updates** or restart Kodi and refresh the repository.
2. Open **Add-ons → Install from repository → LongTime → Program add-ons**.
3. Install **LongTime Oldies Browser**.
4. Open **Programs → Program add-ons → LongTime Oldies Browser**.
5. Select an add-on ID, then select the exact archived version you want.
6. Confirm the selection. The browser downloads the original ZIP and checks the published size, SHA-256, ZIP integrity, add-on ID, and version.
7. On first use only, the browser asks you to restart Kodi once after the verified ZIP is staged. Kodi loads File Manager sources at startup, so this activates the new `LongTime Oldies Archive` source. After restarting, reopen the Oldies Browser and accept its prompt to open Kodi's native **Install from ZIP** window. Select `LongTime Oldies Archive`, then select the staged ZIP. Kodi handles installation and dependency checks.
8. On later installs the source is already loaded, so the browser opens the native installer immediately after staging the selected ZIP. No restart is required.

**Why is there one extra selection in Kodi?** Kodi's documented `InstallFromZip` built-in opens the native ZIP picker but does not accept a ZIP file path as an argument. The browser therefore maintains one dedicated File Manager source pointing at its package folder and opens Kodi's own installer. It does not directly overwrite Kodi's add-on folder or bypass Kodi's installer.

Kodi may require **Unknown sources** to be enabled before installing ZIP packages. Follow Kodi's prompt or enable it under **Settings → System → Add-ons → Unknown sources**. Only install archived add-ons you trust.

### Keep a rollback version installed

Kodi 22 automatically marks a ZIP-installed add-on version as pinned when it is older than the latest compatible version available from installed repositories. That prevents the repository copy in `Now/` from automatically replacing the rollback version. To return to the current release, install the current version from the LongTime repository.

## Previous releases and retention

GitHub Actions creates `Oldies/` automatically; you do not need to create the folder yourself.

- Superseded ZIPs are stored under `Oldies/<addon-id>/`.
- The five newest distinct archived versions are retained per add-on.
- The current release stays in `Now/` and is not listed as an Oldies version.
- A currently published ZIP is archived only when a higher version of that add-on is staged in `Later/`.
- A version is not archived repeatedly on scheduled or no-change runs.
- The original ZIP bytes and internal top-level add-on folder are preserved unchanged.
- `Oldies/catalog.json` lists archived versions and their SHA-256 checksums for the Kodi browser.

### Initial archive contents

On the first build using this archive logic, ZIPs already in `Oldies/` are checked against the versions in `Now/`. Any ZIP that is exactly the currently published version is removed from the archive and is not offered as a rollback. Those files are duplicates, not previous releases. The uploaded project snapshot does not contain Git history, so genuine older ZIPs must already exist as separate files to appear immediately. Otherwise, the Oldies list fills as later releases supersede the current versions. Do not rename a current ZIP to make it look older.

The public archive index is:

https://FookYuuRai.github.io/LongTime/Oldies/

The public machine-readable version catalog is:

https://FookYuuRai.github.io/LongTime/Oldies/catalog.json

## Generated commit messages

The repository build compares uploaded add-on changelogs with the previously published ZIPs and uses newly added or changed release notes to prepare the Git commit message. If a useful changelog delta cannot be determined, it uses a fallback message rather than inventing release notes.

Generated commits use the `github-actions[bot]` Git author identity.

## Payload validation

`tools/validate_repo_files.py` is a read-only validator used by the build and Pages workflows. It checks loose files and ZIP archives under `Now/`, `Later/`, and `Oldies/`, including the staged website payload.

Checks include hidden files and directories, Python cache files, operating-system metadata, symbolic links, unsafe ZIP paths, path traversal, duplicate ZIP entries, and corrupt ZIP archives. The validator reports problems and exits unsuccessfully; it does not delete or repair files automatically.

Run it locally from the repository root:

```bash
python3 tools/validate_repo_files.py --areas Now Later Oldies
```

To validate the staged Pages directory:

```bash
python3 tools/validate_repo_files.py --root _site --areas Now Oldies
```

## GitHub Pages

The Pages workflow validates repository payloads, prepares the website from `index.html`, `Now/`, and `Oldies/`, checks the configured background-audio asset, validates the staged website, and deploys the Pages artifact.

The `Prepare website` step in `.github/workflows/pages.yml` must copy `Oldies/` into `_site/`:

```bash
cp index.html _site/index.html
cp -a Now _site/Now
test -d Oldies
cp -a Oldies _site/Oldies
test -s _site/Oldies/index.html
```

A successful repository build does not by itself prove that Pages deployment succeeded; check the corresponding GitHub Actions run.

Published repository URL:

https://FookYuuRai.github.io/LongTime/

## Nightshift ambience pack

The ambience pack updater discovers supported audio filenames from the release ZIP rather than relying on a fixed track count. It regenerates track definitions, per-track Kodi settings, and English labels from the available tracks.

The add-on records the installed pack's SHA-256 so it can detect changed audio even when a filename remains the same. Pack-managed tracks are removed only after a replacement pack has been verified and installed.

## Install the LongTime repository in Kodi

Install the repository ZIP under `Now/repository.longtime/` once. Add this URL as a source in Kodi's File Manager:

https://FookYuuRai.github.io/LongTime/

Then install the repository ZIP and allow Kodi to check for add-on updates.

Kodi checks for updates on its own schedule and at startup. Restarting Kodi can prompt an earlier check.

## Existing installations using the old URL

Devices configured before the repository URL or folder layout changed may still point to the old `repo/` address. Those installations will not receive updates from the new address until the repository add-on is reinstalled from the current `Now/` paths.
