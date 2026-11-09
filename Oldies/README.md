# Oldies — previous LongTime releases

This folder is created and maintained automatically by the LongTime build.

- Only a published release that is being replaced by a higher version staged in `Later/` is added to the archive.
- Up to five previous, distinct releases are retained for each add-on.
- The current release remains in `Now/` and is not listed as an Oldies version.
- Original ZIP files are preserved unchanged, including their internal top-level add-on folder names.
- `catalog.json` is the machine-readable list used by the Kodi LongTime Oldies Browser. It records each archived ZIP's filename, version, size, archive date, and SHA-256 checksum.

The build removes an archived ZIP when it is the same version as the active release in `Now/`; the current release is not a rollback version. On the first build with this archive logic, older releases appear only when genuine older ZIPs already exist as separate files. Otherwise, Oldies fills as future releases supersede current versions. Do not rename a current ZIP to make it appear older.

## Browse and install previous releases in Kodi

1. Update the LongTime repository and install **LongTime Oldies Browser** from its **Program add-ons** category.
2. Open **LongTime Oldies Browser** from Kodi's Programs add-ons.
3. Select an add-on, then select the exact archived version you want.
4. The browser downloads the original ZIP and verifies its published size, SHA-256 checksum, ZIP integrity, add-on ID, and version.
5. On the first install only, the browser creates the `LongTime Oldies Archive` File Manager source and asks you to restart Kodi once. Kodi loads File Manager sources at startup.
6. After restarting Kodi, open **LongTime Oldies Browser** again and accept its prompt to open Kodi's native **Install from ZIP** window. Choose **LongTime Oldies Archive**, then select the staged ZIP.
7. For later installs, the source is already loaded, so no restart is needed; the browser opens Kodi's native ZIP installer after staging the selected version.

The browser uses Kodi's native ZIP installer. It does not directly overwrite the installed add-on folder or bypass Kodi's dependency and compatibility checks. Kodi's native `InstallFromZip` command opens the ZIP picker; it does not accept a package file path as an argument. The browser therefore stages only the selected ZIP in its private package folder and registers one dedicated File Manager source for that folder.

Kodi may require **Unknown sources** to be enabled before installing ZIP packages. Only install archived add-ons you trust.

## Keeping and restoring a previous version

Kodi 22 automatically pins a ZIP-installed add-on version when it is older than the latest compatible version available from installed repositories. This prevents the newer release in `Now/` from automatically replacing the rollback version. To return to the current release, install the current version from the LongTime repository.

Do not copy an older ZIP into `Later/` and expect the normal build to publish it as a downgrade. The build deliberately rejects lower-version submissions. Use **LongTime Oldies Browser** inside Kodi to install a historical version.

## Public archive

The public web archive remains available for browsing and direct ZIP downloads:

- Oldies index: https://fookyuurai.github.io/LongTime/Oldies/
- Version catalog: https://fookyuurai.github.io/LongTime/Oldies/catalog.json
- Current releases: https://fookyuurai.github.io/LongTime/Now/

The Kodi browser reads `catalog.json`; the HTML pages are provided for ordinary web browsing.
