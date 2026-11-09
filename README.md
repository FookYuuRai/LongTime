# LongTime

LongTime builds and publishes a Kodi add-on repository and its GitHub Pages website. Add-on ZIPs are submitted through `Later/`; validated, generated repository files are published under `Now/`. Previous published releases are retained in `Oldies/` so users can recover or roll back an update.

## Repository layout

- `Later/`: incoming add-on ZIPs awaiting publication.
- `Now/`: generated Kodi repository, current published add-on ZIPs, and website assets.
- `Oldies/`: automatically maintained archive of the five newest previous releases per add-on.
- `tools/make_repo.py`: builds the Kodi repository and prepares a descriptive commit message from add-on changelog changes.
- `tools/archive_releases.py`: archives and verifies previous published ZIPs, applies the five-release retention limit, and generates the Oldies browsing pages.
- `tools/validate_repo_files.py`: read-only validation of repository payloads.
- `.github/workflows/`: automation for repository builds, Pages deployment, and supported add-on update tasks.
- `index.html`: GitHub Pages homepage.

Generated files in `Now/` and `Oldies/` should be produced by the repository build rather than edited manually.

## Add or update an add-on

1. Place the add-on ZIP in `Later/`.
2. The ZIP must contain one top-level directory named exactly after the add-on ID, with `addon.xml` inside it. Do not include unrelated files outside that directory.
3. The build validates the incoming payloads and currently published files.
4. Before generating the replacement repository, the build copies valid currently published add-on ZIPs from `Now/` into `Oldies/`. Each copied ZIP is checked for integrity and its add-on ID/version are verified.
5. The build runs `tools/make_repo.py`, updates the repository metadata, and validates the generated repository and remaining payloads.
6. The build commits and pushes generated changes to `OnTheSide`.
7. The separate Pages stage publishes the homepage, `Now/`, and `Oldies/` after the repository build succeeds.

A new release must have a higher version in `addon.xml` than the currently published release. Version ordering follows Kodi-compatible comparison rules. For example, `1.1.1~beta2` is older than `1.1.1`, which is older than `1.1.2`.

## Previous releases and rollback

GitHub Actions creates `Oldies/` automatically when the archive step runs; you do not need to create the folder yourself.

- Archived ZIPs are stored under `Oldies/<addon-id>/`.
- The five newest distinct archived versions are retained for each add-on.
- The current release remains in `Now/`; `Oldies/` contains previous releases only.
- The same version is not archived repeatedly on every pipeline run.
- A copied ZIP is integrity-checked and its `addon.xml` identity/version are verified before it is retained.
- The original ZIP contents and internal top-level add-on folder are preserved; the archive process does not repackage the add-on.

The public archive is browsable from the GitHub Pages homepage through the **Oldies** link:

https://FookYuuRai.github.io/LongTime/Oldies/

### Roll back an add-on

1. Open the Oldies page and select the add-on ID.
2. Download the version you want to restore.
3. Upload that ZIP into `Later/` using the normal add-on ZIP structure.
4. A rollback is still processed by the normal version-validation rules. If the selected archived version is older than the currently published version, the normal build may reject it as a downgrade. In that case, a maintainer must deliberately perform the rollback by restoring the archived ZIP to `Now/` and regenerating the repository metadata, or use a controlled rollback procedure that explicitly permits the downgrade. Do not simply rename an old ZIP to a newer version; that would misrepresent its actual add-on version.

## Generated commit messages

The repository build compares uploaded add-on changelogs with the previously published ZIPs and uses newly added or changed release notes to prepare the Git commit message.

This keeps repository history more descriptive than a generic message such as `rebuild repo`. If a useful changelog delta cannot be determined, the build uses a fallback message rather than inventing release notes.

The automation uses the `github-actions[bot]` Git author identity for generated commits.

## Payload validation

`tools/validate_repo_files.py` is a read-only validator used by the build and Pages workflows. It checks loose files and ZIP archives under `Now/` and `Later/`, including the staged website payload.

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
