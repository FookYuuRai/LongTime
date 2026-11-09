# Oldies

This folder is created and maintained automatically by GitHub Actions.

- Previous published add-on ZIPs are archived under `Oldies/<addon-id>/`.
- The five newest distinct archived revisions are retained for each add-on.
- The current release remains in `Now/`.
- Original ZIPs are copied unchanged, including their internal add-on folder names.

## Kodi browsing and installation

The intended Oldies experience is a Kodi ZIP browser: select an add-on, browse up to five archived versions, and install the exact version selected.

This is not an ordinary Kodi repository feed. A normal repository index does not provide a reliable picker for several versions of the same add-on ID. The in-Kodi ZIP-browser companion add-on has not yet been added, so the workflow described above is not available inside Kodi yet.

Until that companion add-on is implemented, use the public archive website to browse and download a version, then select the ZIP through Kodi's **Add-ons → Install from zip file** interface:

https://FookYuuRai.github.io/LongTime/Oldies/

Do not rename or repackage an archived ZIP. Kodi's normal dependency and compatibility checks still apply when installing it.
