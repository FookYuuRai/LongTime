# LongTime

LongTime builds and publishes a Kodi add-on repository and its GitHub Pages website. Add-on ZIPs are submitted through `Later/`; validated, generated repository files are published under `Now/`. Previous published releases are retained in `Oldies/` so users can browse and restore older versions.

## Repository layout

- `Later/`: incoming add-on ZIPs awaiting publication.
- `Now/`: generated Kodi repository, current published add-on ZIPs, and website assets.
- `Oldies/`: automatically maintained archive of the five newest previous releases per add-on. Original ZIPs are preserved.
- `tools/make_repo.py`: builds the current Kodi repository and prepares a descriptive commit message from add-on changelog changes.
- `tools/archive_releases.py`: archives and verifies previous published ZIPs, applies the five-release retention limit, and generates Oldies website pages.
- `tools/validate_repo_files.py`: read-only validation of repository payloads.
- `.github/workflows/`: automation for repository builds, Pages deployment, and supported add-on update tasks.
- `index.html`: GitHub Pages homepage.

Generated files in `Now/` and `Oldies/` should be produced by the repository build rather than edited manually.

## Add or update an add-on

1. Place the add-on ZIP in `Later/`.
2. The ZIP must contain one top-level directory named exactly after the add-on ID, with `addon.xml` inside it. Do not include unrelated files outside that directory.
3. The build validates the incoming payloads and currently published files.
4. Before generating the replacement repository, the build copies valid currently published add-on ZIPs from `Now/` into `Oldies/`. Each copied ZIP is checked for integrity and its add-on ID/version are verified.
5. The build runs `tools/make_repo.py`, updates the current repository metadata, and validates the generated repository and remaining payloads.
6. The build commits and pushes generated changes to `OnTheSide`.
7. The separate Pages stage publishes the homepage, `Now/`, and `Oldies/` after the repository build succeeds.

A new release must have a higher version in `addon.xml` than the currently published release. Version ordering follows Kodi-compatible comparison rules. For example, `1.1.1~beta2` is older than `1.1.1`, which is older than `1.1.2`.

## Previous releases: Oldies

GitHub Actions creates `Oldies/` automatically when the archive step runs; you do not need to create the folder yourself.

- Archived ZIPs are stored under `Oldies/<addon-id>/`.
- The five newest distinct archived versions are retained for each add-on.
- The current release remains in `Now/`; `Oldies/` contains previous releases only.
- The same add-on version is not archived repeatedly on every pipeline run.
- Each copied ZIP is integrity-checked and its `addon.xml` identity/version are verified.
- The original ZIP is copied byte-for-byte; its internal top-level add-on folder and contents are not renamed or repackaged.

Public web archive:

https://FookYuuRai.github.io/LongTime/Oldies/

### Browsing and installing a specific archived version in Kodi

**The intended Oldies experience is a Kodi ZIP browser:** choose an add-on, see its retained archived versions, select the exact version, and install that original ZIP. This is different from a standard Kodi repository feed.

A standard Kodi repository index is designed to advertise one selected version of an add-on ID at a time. Listing several historical ZIPs with the same add-on ID in an ordinary `addons.xml` feed does not reliably create a version picker in Kodi. Therefore, Oldies must not be presented as though the existing repository metadata already provides this feature.

**Implementation status: the archive and website listing are present; the in-Kodi Oldies ZIP-browser add-on is not yet included in this repository.** Until that companion add-on is added, users can browse the Oldies website and manually install a selected archive ZIP through Kodi's **Install from zip file** interface. The direct in-Kodi browse/select/install workflow is not available yet.

When the companion browser is implemented, the intended Kodi workflow will be:

1. Open the LongTime Oldies browser from Kodi's Add-ons area.
2. Choose an add-on ID.
3. Browse its available archived versions (up to five).
4. Select the exact version to install.
5. Review Kodi's install confirmation and allow Kodi to install the selected ZIP.

The browser must download the selected original ZIP from `Oldies/<addon-id>/` and pass it to Kodi's normal ZIP-install flow. It must not silently rename the add-on, alter the ZIP, change the add-on ID, or replace the current `Now/` repository metadata. Kodi's normal dependency and compatibility checks still apply; an older version may not work with the installed Kodi version or other add-ons.

### Manual rollback before the browser exists

1. Open the Oldies website: https://FookYuuRai.github.io/LongTime/Oldies/
2. Open the required add-on's folder and download the exact archived ZIP.
3. In Kodi, use **Add-ons → Install from zip file** and select the downloaded ZIP. Enable **Unknown sources** if Kodi requests it.
4. Confirm the installation and check the installed version in the add-on information screen.

A rollback submitted through `Later/` is still subject to the normal version-validation rules. If the archived version is older than the currently published version, the normal build may reject it as a downgrade. A maintainer must use a deliberate rollback procedure that explicitly permits the downgrade and regenerates the repository metadata. Do not rename an old ZIP to a newer version; that would misrepresent its actual add-on version.

## Generated commit messages

The repository build compares uploaded add-on changelogs with the previously published ZIPs and uses newly added or changed release notes to prepare the Git commit message.

This keeps repository history more descriptive than a generic message such as `rebuild repo`. If a useful changelog delta cannot be determined, the build uses a fallback message rather than inventing release notes.

The automation uses the `github-actions[bot]` Git author identity for generated commits.

## Payload validation

`tools/validate_repo_files.py` is a read-only validator used by the build and Pages workflows. It checks loose files and ZIP archives under the selected payload areas.

Checks include:

- Hidden files and directories.
- Python cache directories and bytecode.
- Operating-system metadata files such as `.DS_Store` and `Thumbs.db`.
- Symbolic links.
- Unsafe ZIP paths and path traversal.
- Duplicate ZIP entries.
- Corrupt ZIP archives.

The validator reports problems and exits unsuccessfully; it does not delete or repair files automatically.

Run it locally from the repository root:

```bash
python3 tools/validate_repo_files.py --areas Now Later
```

To validate a staged Pages directory:

```bash
python3 tools/validate_repo_files.py --root _site --areas Now
```

Remove or replace any reported files, then rerun validation.

## GitHub Pages

The Pages workflow validates repository payloads, prepares the website from `index.html`, `Now/`, and `Oldies/`, checks the configured background-audio asset, validates the staged website, and deploys the Pages artifact.

**Important Pages workflow requirement:** `.github/workflows/pages.yml` must copy `Oldies/` into `_site/` in its existing `Prepare website` step. The relevant commands are:

```bash
cp index.html _site/index.html
cp -a Now _site/Now
test -d Oldies
cp -a Oldies _site/Oldies
test -s _site/Oldies/index.html
```

If the `Oldies/` copy is omitted, archived files may exist in the repository but will not appear on the public Pages website.

Repository generation and website deployment are separate workflow tasks. A successful repository build does not, by itself, prove that website deployment succeeded; check the corresponding GitHub Actions run.

Published repository URL:

https://FookYuuRai.github.io/LongTime/

## Nightshift ambience pack

The ambience pack updater discovers supported audio filenames from the release ZIP rather than relying on a fixed track count. It regenerates track definitions, per-track Kodi settings, and English labels from the available tracks.

The add-on records the installed pack's SHA-256 so it can detect changed audio even when a filename remains the same. Pack-managed tracks are removed only after a replacement pack has been verified and installed.

## Install the repository in Kodi

Install the repository add-on once using the generated repository ZIP under `Now/repository.longtime/`.

Add the repository URL below as a source in Kodi's File Manager:

https://FookYuuRai.github.io/LongTime/

Then install the repository ZIP and allow Kodi to check for add-on updates.

Kodi checks for updates on its own schedule and at startup. Restarting Kodi can prompt an earlier check.

## Existing installations using the old URL

Devices configured before the repository URL or folder layout changed may still point to the old `repo/` address. Those installations will not receive updates from the new address until the repository add-on is reinstalled from the current `Now/` paths.
