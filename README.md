# LongTime

Add-on zips and the files Kodi needs to install and update them.

## Add or update an add-on

1. Put the add-on zip in `now/`. The zip must hold one top level folder named exactly like the add-on id, with
   `addon.xml` inside, and nothing else outside the folder (no hidden files, no `__MACOSX`, no `__pycache__`).
2. `python3 tools/make_repo.py`
3. Commit and push.

Any number of add-ons can be there. For each id the highest version is published; older zips of it can stay in
`now/` or be removed. A new version needs a higher `version` in its `addon.xml` than the one published.
Versions are compared like Kodi does: `1.1.1~beta2` is older than `1.1.1`, which is older than `1.1.2`.

## Install in Kodi (once)

Kodi needs the repository add-on, `repository.longtime-1.0.0.zip`, once. Get it onto the device in one of these ways:

**A. A web source in Kodi's file manager.** Settings, File manager, Add source, enter
`https://FookYuuRai.github.io/LongTime/` and give it a name (LongTime). Then Add-ons, Install from zip file, LongTime,
`repo`, `repository.longtime`, the zip.

**B. Download on the device.** In a browser on the device open
`https://raw.githubusercontent.com/FookYuuRai/LongTime/OnTheSide/repo/repository.longtime/repository.longtime-1.0.0.zip`
The file goes to the device's Downloads folder. In Kodi: Add-ons, Install from zip file, choose the Downloads folder
(or External storage / Downloads), choose the zip.

**C. From a PC.** Copy `repo/repository.longtime/repository.longtime-1.0.0.zip` to the device and choose it with
Install from zip file.
