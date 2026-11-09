# Oldies — previous LongTime releases

This folder is created and maintained automatically by the LongTime build.

- Only releases superseded by a higher version queued in `Later/` are added to the archive.
- Up to five previous distinct releases are retained per add-on.
- The current release remains in `Now/` and is not shown as an Oldies version.
- Original ZIP contents and the internal top-level add-on folder are preserved unchanged.
- `catalog.json` is the version list used by the Kodi LongTime Oldies Browser. It includes each original filename, size, archived date, and SHA-256 checksum.

On the first build with this logic, any Oldies ZIP whose version matches the active ZIP in `Now/` is removed because it is not a previous release. The uploaded repository snapshot does not contain Git history, so genuine older ZIPs must already be present as separate files to appear immediately. Otherwise, this archive fills as future releases supersede the active versions. Do not rename a current ZIP to make it appear historical.

## Browse and install from Kodi

1. Update the LongTime repository and install **LongTime Oldies Browser** from the Programs category.
2. Open the browser from Kodi's Programs add-ons.
3. Select an add-on, then select the exact archived version.
4. The browser downloads the original ZIP and checks its size, SHA-256, archive integrity, add-on ID, and version.
5. The first time only, Kodi asks you to restart once after the verified ZIP is staged. This is needed because Kodi loads File Manager sources at startup. After restarting, reopen the browser and accept the prompt to open the native **Install from ZIP** window. Select `LongTime Oldies Archive`, then the staged ZIP. On later installs, the existing source is already loaded and no restart is needed.

Kodi's native ZIP dialog does not accept a file path as a command argument. The browser therefore maintains one dedicated File Manager source pointing at its private package folder; it stages only the version you selected. This keeps installation inside Kodi's supported installer instead of copying files directly into Kodi's add-on directory.

Kodi 22 automatically pins a ZIP-installed add-on version when it is older than the latest compatible version available from installed repositories. That prevents the newer version in `Now/` from automatically replacing the rollback version. To return to the current release, install the current version from the LongTime repository.
