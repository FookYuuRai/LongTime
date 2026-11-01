# LongTime

Add-on zips and the files Kodi needs to install and update them.

Folders:
- `Later/`: upload folder. Put new add-on zips here.
- `Now/`: published folder. The build writes it. Kodi reads it.

## Add or update an add-on

1. Put the add-on zip in `Later/`. The zip must hold one top level folder named exactly like the add-on id, with
   `addon.xml` inside, and nothing else outside the folder (no hidden files, no `__MACOSX`, no `__pycache__`).
2. The build runs by itself when zips are pushed to `Later/` (GitHub Actions, workflow "build repo"). To run it
   by hand: Actions tab, "build repo", Run workflow. Or in a Codespace: `python3 tools/make_repo.py`, then commit and push.
3. The build publishes the highest version of each add-on in `Now/`, updates `Now/addons.xml` and its checksum, and
   deletes the older zips from `Later/`. The deleted copies stay in the git history.

A new version needs a higher `version` in its `addon.xml` than the one published. Versions are compared like Kodi does:
`1.1.1~beta2` is older than `1.1.1`, which is older than `1.1.2`.

Kodi checks the repository for updates on its own schedule (and at start-up). Restarting Kodi forces a check.

## Install in Kodi (once)

Kodi needs the repository add-on, `repository.longtime-1.0.0.zip`, once. Get it onto the device in one of these ways:

**A. A web source in Kodi's file manager.** Settings, File manager, Add source, enter
`https://FookYuuRai.github.io/LongTime/` and give it a name (LongTime). Then Add-ons, Install from zip file, LongTime,
`Now`, `repository.longtime`, the zip.

**B. Download on the device.** In a browser on the device open
`https://raw.githubusercontent.com/FookYuuRai/LongTime/OnTheSide/Now/repository.longtime/repository.longtime-1.0.0.zip`
The file goes to the device's Downloads folder. In Kodi: Add-ons, Install from zip file, choose the Downloads folder
(or External storage / Downloads), choose the zip.

**C. From a PC.** Copy `Now/repository.longtime/repository.longtime-1.0.0.zip` to the device and choose it with
Install from zip file.

## Already installed before the folder rename

Devices that installed the repository before the rename still point at the old `repo/` address, which no longer exists,
so they won't see updates. Reinstall the repository add-on once from one of the install methods above, using the `Now`
paths. After that, updates arrive through the normal check.
