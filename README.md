# LongTime

LongTime builds and publishes a Kodi add-on repository and its GitHub Pages website. Add-on ZIPs are submitted through `Later/`; validated, generated repository files are published under `Now/`.

## Repository layout

- `Later/`: incoming add-on ZIPs awaiting publication.
- `Now/`: generated Kodi repository, published add-on ZIPs, and website assets.
- `tools/make_repo.py`: builds the Kodi repository and prepares a descriptive commit message from add-on changelog changes.
- `tools/validate_repo_files.py`: read-only validation of repository payloads.
- `.github/workflows/`: automation for repository builds, Pages deployment, and supported add-on update tasks.
- `index.html`: GitHub Pages homepage.

Generated files in `Now/` should be produced by the repository build rather than edited manually.

## Add or update an add-on

1. Place the add-on ZIP in `Later/`.
2. The ZIP must contain one top-level directory named exactly after the add-on ID, with `addon.xml` inside it. Do not include unrelated files outside that directory.
3. The build validates the incoming payloads, runs `tools/make_repo.py`, and validates the generated repository and remaining payloads.
4. The build publishes the highest eligible version of each add-on, updates repository metadata and checksums, and removes older ZIPs from `Later/` when appropriate.
5. Generated changes are committed and pushed to `OnTheSide`.

A new release must have a higher version in `addon.xml` than the currently published release. Version ordering follows Kodi-compatible comparison rules. For example, `1.1.1~beta2` is older than `1.1.1`, which is older than `1.1.2`.

### Generated commit messages

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

The Pages workflow validates repository payloads, prepares the website from `index.html` and the published `Now/` directory, checks the configured background-audio asset, validates the staged website, and deploys the Pages artifact.

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
