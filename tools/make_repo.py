#!/usr/bin/env python3
"""
Builds the files Kodi reads (the Now/ folder) from add-on ZIPs in Later/.

For each add-on ID, the ZIP with the highest version is published as
Now/<id>/<id>-<version>.zip, with its icon and fanart, and listed in
Now/addons.xml with Now/addons.xml.md5.

The repository add-on ZIP is built as well.

Background audio:
    Later/27_aquatic-ambiance.opus
    Later/28_rain-and-waves.mp3
    Later/29_forest-at-night.m4a

The highest-numbered supported audio file is copied to:
    Now/io.page.background.track/<original-filename>

A current.json manifest identifies the selected audio file.

After a successful build:
- Superseded add-on ZIP files are deleted from Later/.
- Older numbered background audio files are deleted from Later/.
- The newest selected background audio file remains in Later/.

The io.page.background.track index page includes a looping audio player.

    --base  Address files are served from
    --out   Output directory (default: Now/)
    --now   Source directory (default: Later/)
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

OUT_NAME = 'Now'
SOURCE_NAME = 'Later'

DEFAULT_BASE = (
    'https://raw.githubusercontent.com/'
    'FookYuuRai/LongTime/OnTheSide/Now/'
)

TOO_BIG = 90 * 1024 * 1024

REPOSITORY_SOURCE = os.path.join(
    HERE,
    '_source',
    'repository.longtime',
)

STAMP = (2026, 1, 1, 0, 0, 0)

JUNK_DIRECTORIES = {
    '__macosx',
    '__pycache__',
    '.git',
    '.svn',
}
JUNK_FILES = {
    '.ds_store',
    'thumbs.db',
    'desktop.ini',
    'ehthumbs.db',
}
JUNK_SUFFIXES = ('.pyc', '.pyo')


def is_junk_path(name):
    """Return True for hidden path components and common packaging debris."""
    normalized = name.replace('\\', '/')
    parts = [part for part in normalized.split('/') if part not in ('', '.')]
    if not parts:
        return True
    if any(part.startswith('.') or part.casefold() in JUNK_DIRECTORIES for part in parts):
        return True
    basename = parts[-1].casefold()
    return basename in JUNK_FILES or basename.endswith(JUNK_SUFFIXES)

# Directories under Now/ maintained outside the add-on ZIP build.
PRESERVED_OUTPUT_DIRS = {
    'repository.longtime',
    'io.page.background.track',
}

# Background audio configuration.
AUDIO_FOLDER = 'io.page.background.track'

AUDIO_TYPES = {
    '.mp3': 'audio/mpeg',
    '.opus': 'audio/ogg; codecs=opus',
    '.m4a': 'audio/mp4',
}

# Accepted filenames:
#   27_aquatic-ambiance.opus
#   28_rain-and-waves.mp3
#   29_forest-at-night.m4a
AUDIO_FILENAME_RE = re.compile(
    r'^(?P<number>\d+)_.+\.(?P<extension>mp3|opus|m4a)$',
    re.IGNORECASE,
)


class RepoError(Exception):
    pass


def addon_info(xml_text):
    """Return (id, version) from the <addon ...> tag."""
    tag = re.search(r'<addon\b[^>]*>', xml_text, re.S)

    if not tag:
        raise RepoError('no <addon> tag in addon.xml')

    ident = re.search(r'\bid="([^"]+)"', tag.group(0))
    version = re.search(r'\bversion="([^"]+)"', tag.group(0))

    if not ident or not version:
        raise RepoError(
            'the <addon> tag has no id or version'
        )

    return ident.group(1), version.group(1)


def _order(char):
    if char == '~':
        return -1

    if char.isalpha():
        return ord(char)

    return ord(char) + 256


def compare(a, b):
    """
    Compare add-on versions using Kodi-style, Debian-like ordering.

    Return:
        -1 if a is older than b
         0 if a and b are equivalent
         1 if a is newer than b
    """
    while a or b:
        text_a = re.match(r'\D*', a).group(0)
        text_b = re.match(r'\D*', b).group(0)

        a = a[len(text_a):]
        b = b[len(text_b):]

        for i in range(max(len(text_a), len(text_b))):
            order_a = (
                _order(text_a[i])
                if i < len(text_a)
                else 0
            )

            order_b = (
                _order(text_b[i])
                if i < len(text_b)
                else 0
            )

            if order_a != order_b:
                return -1 if order_a < order_b else 1

        num_a = re.match(r'\d*', a).group(0)
        num_b = re.match(r'\d*', b).group(0)

        a = a[len(num_a):]
        b = b[len(num_b):]

        if int(num_a or 0) != int(num_b or 0):
            return (
                -1
                if int(num_a or 0) < int(num_b or 0)
                else 1
            )

    return 0


def body(xml_text):
    """Remove the XML declaration for inclusion in addons.xml."""
    return re.sub(
        r'^\s*<\?xml[^>]*\?>\s*',
        '',
        xml_text,
    ).strip()


def open_zip(path):
    """
    Return (zipfile, id, version, addon.xml text) after validation.
    """
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise RepoError(
            '{0}: not a zip file'.format(
                os.path.basename(path)
            )
        )

    names = [
        name
        for name in z.namelist()
        if not name.endswith('/')
    ]

    folders = {name.split('/')[0] for name in names}

    if (
        len(folders) != 1
        or any('/' not in name for name in names)
    ):
        raise RepoError(
            '{0}: the zip must hold one top level folder '
            'and nothing outside it'.format(
                os.path.basename(path)
            )
        )

    folder = folders.pop()
    addon_xml_path = '{0}/addon.xml'.format(folder)

    if addon_xml_path not in names:
        raise RepoError(
            '{0}: no addon.xml in {1}/'.format(
                os.path.basename(path),
                folder,
            )
        )

    xml_text = z.read(addon_xml_path).decode('utf-8')
    ident, version = addon_info(xml_text)

    if folder != ident:
        raise RepoError(
            '{0}: the folder inside is "{1}" but the add-on '
            'id is "{2}"'.format(
                os.path.basename(path),
                folder,
                ident,
            )
        )

    for name in names:
        if is_junk_path(name):
            raise RepoError(
                '{0}: contains hidden or packaging-junk entry {1}'.format(
                    os.path.basename(path),
                    name,
                )
            )

    return z, ident, version, xml_text


def read_zip(path):
    """Return (id, version, addon.xml text, {name: bytes})."""
    z, ident, version, xml_text = open_zip(path)

    files = {
        name: z.read(name)
        for name in z.namelist()
        if not name.endswith('/')
    }

    return ident, version, xml_text, files


def assets_of(xml_text):
    """Find icon and fanart paths declared in addon.xml."""
    return re.findall(
        r'<(?:icon|fanart)>([^<]+)</',
        xml_text,
    )


def write_zip(path, folder, files):
    """Write a reproducible ZIP."""
    if os.path.exists(path):
        os.remove(path)

    with zipfile.ZipFile(
        path,
        'w',
        zipfile.ZIP_DEFLATED,
    ) as z:
        for name, data in files:
            info = zipfile.ZipInfo(
                '{0}/{1}'.format(folder, name),
                STAMP,
            )

            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16

            z.writestr(info, data)


def clear_folder(folder):
    """Remove and recreate a generated add-on folder."""
    if os.path.isdir(folder):
        shutil.rmtree(folder)

    os.makedirs(folder)


def publish_background_audio(source, out):
    """
    Publish the highest-numbered supported audio file from source/.

    Supported:
        .mp3
        .opus
        .m4a

    Expected filename format:
        NUMBER_name.extension

    The selected file keeps its original filename and extension.

    Writes:
        Now/io.page.background.track/<filename>
        Now/io.page.background.track/current.json

    Returns the selected filename.

    If no matching audio file exists, the existing published track
    is left unchanged and None is returned.
    """
    if not os.path.isdir(source):
        print(
            'background audio: source directory not found; '
            'leaving published audio unchanged'
        )
        return None

    candidates = []

    for name in os.listdir(source):
        path = os.path.join(source, name)

        if not os.path.isfile(path):
            continue

        match = AUDIO_FILENAME_RE.fullmatch(name)

        if not match:
            continue

        number = int(match.group('number'))
        extension = os.path.splitext(name)[1].lower()

        candidates.append(
            (
                number,
                name.lower(),
                name,
                path,
                extension,
            )
        )

    if not candidates:
        print(
            'background audio: no numbered MP3, OPUS, or M4A '
            'files found; leaving published audio unchanged'
        )
        return None

    # Highest integer wins.
    # Filename order breaks ties.
    candidates.sort(
        key=lambda item: (item[0], item[1], item[2])
    )

    number, _, filename, source_path, extension = candidates[-1]

    audio_dir = os.path.join(out, AUDIO_FOLDER)
    os.makedirs(audio_dir, exist_ok=True)

    # Remove old numbered published tracks.
    for name in os.listdir(audio_dir):
        path = os.path.join(audio_dir, name)

        if (
            os.path.isfile(path)
            and AUDIO_FILENAME_RE.fullmatch(name)
        ):
            os.remove(path)

    destination = os.path.join(audio_dir, filename)

    shutil.copy2(
        source_path,
        destination,
    )

    manifest = {
        'number': number,
        'file': filename,
        'type': AUDIO_TYPES[extension],
    }

    manifest_path = os.path.join(
        audio_dir,
        'current.json',
    )

    with open(
        manifest_path,
        'w',
        encoding='utf-8',
        newline='\n',
    ) as f:
        json.dump(manifest, f, indent=2)
        f.write('\n')

    print(
        'published background audio {0}'.format(filename)
    )

    return filename


def prune_source_audio(source, keep_filename):
    """
    Delete older numbered background audio files from Later/.

    Retain the currently selected track so it remains the source
    for subsequent builds.

    Only numbered MP3, OPUS, and M4A files are affected.
    """
    if not keep_filename or not os.path.isdir(source):
        return []

    removed = []

    for name in sorted(os.listdir(source)):
        path = os.path.join(source, name)

        if not os.path.isfile(path):
            continue

        if not AUDIO_FILENAME_RE.fullmatch(name):
            continue

        if name == keep_filename:
            continue

        os.remove(path)
        removed.append(name)

        print(
            'removed older background audio from Later: {0}'.format(
                name
            )
        )

    return removed


# The NightShift skin's colors for the listing pages.
_CSS = """
:root{--bg:#03050c;--panel:#071426;--header:#123b66;--text:#f0f6ff;--grey:#9cb0c9;--blue:#49c9ff;--focus:#35bfff;--pink:#ff5cbf;--line:rgba(53,191,255,.5)}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;min-height:100vh;color:var(--text);text-shadow:0 1px 4px rgba(0,0,0,.95);font:16px/1.45 "Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background:linear-gradient(rgba(3,5,12,.28),rgba(3,5,12,.42))__FANART__,var(--bg);background-size:cover;background-attachment:fixed;background-position:center}
.wrap{max-width:920px;margin:0 auto;padding:28px 16px 150px}
.panel{background:rgba(7,20,38,.3);-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px);border:1px solid var(--line);border-radius:6px;box-shadow:0 0 28px rgba(53,191,255,.14);overflow:hidden}
.head{display:flex;align-items:center;gap:14px;padding:14px 18px;background:rgba(18,59,102,.3);border-bottom:1px solid var(--line)}
.head img{width:44px;height:44px;border-radius:8px}
.head h1{margin:0;font-size:1.25rem;font-weight:600;letter-spacing:.02em}
.crumbs{margin:0;color:var(--grey);font-size:.9rem;word-break:break-all}
ul{list-style:none;margin:0;padding:6px}
li{margin:0}
li a{display:block;padding:11px 14px;margin:3px 0;border-radius:4px;border:1px solid rgba(53,191,255,.12);background:rgba(3,5,12,.3);color:var(--text);text-decoration:none;word-break:break-all;transition:box-shadow .12s,border-color .12s,background .12s}
li a:hover,li a:focus{background:rgba(53,191,255,.1);color:#fff;border-color:var(--focus);box-shadow:0 0 5px var(--focus),0 0 16px rgba(53,191,255,.55),inset 0 0 10px rgba(53,191,255,.25);text-shadow:0 0 6px rgba(73,201,255,.75);outline:none}
li a.file:hover,li a.file:focus{border-color:var(--pink);background:rgba(255,92,191,.1);box-shadow:0 0 5px var(--pink),0 0 16px rgba(255,92,191,.5),inset 0 0 10px rgba(255,92,191,.22);text-shadow:0 0 6px rgba(255,92,191,.75)}
li a::before{content:"\\25B8";display:inline-block;width:1.4em;color:var(--blue)}
li a.file::before{content:"\\2193";color:var(--pink)}
.foot{padding:10px 18px;color:var(--grey);font-size:.8rem;border-top:1px solid var(--line)}
@media (max-width:520px){.wrap{padding:12px 8px 24px}.head h1{font-size:1.05rem}}
.audio-player{position:fixed;z-index:10000;left:max(12px,env(safe-area-inset-left,0px));right:max(12px,env(safe-area-inset-right,0px));bottom:calc(8px + env(safe-area-inset-bottom,0px));width:auto;max-width:920px;margin:0 auto;padding:10px 12px;border:1px solid rgba(53,191,255,.5);border-radius:6px;background:rgba(3,5,12,.96);box-shadow:0 0 20px rgba(53,191,255,.2);display:grid;grid-template-columns:minmax(0,1fr);align-items:stretch;gap:8px;box-sizing:border-box}
.audio-player strong{color:var(--blue);display:block;min-width:0;overflow-wrap:anywhere}
.audio-player p{grid-column:1/-1;margin:0;color:var(--grey);font-size:.85rem;line-height:1.35;overflow-wrap:anywhere}
.audio-player audio{grid-column:1/-1;display:block;width:100%;max-width:100%;min-width:0;height:54px;margin:0;box-sizing:border-box}
.audio-player button{grid-column:1/-1;display:block;width:100%;min-width:0;min-height:42px;padding:10px 12px;border:1px solid #35bfff;border-radius:4px;background:#123b66;color:#fff;font-size:15px;cursor:pointer;white-space:normal;overflow-wrap:anywhere;box-sizing:border-box}
.audio-player button:disabled{opacity:.55;cursor:wait}
.audio-player button[hidden]{display:none}
@media (max-width:520px){.wrap{padding:12px 8px 230px}.audio-player{gap:7px;padding:9px 10px}.audio-player audio{height:52px}.audio-player p{font-size:.8rem}}
"""


def _relative(target, folder):
    return os.path.relpath(
        target,
        folder,
    ).replace(os.sep, '/')


def _listing(folder, entries, title, out):
    """
    Write a themed index page with one site-wide background audio player.

    The player is present on the root page, Now/, and every folder below
    Now/. Directory navigation is handled in-page so the audio element
    is not destroyed when the visitor browses between folders.

    File links remain ordinary links for Kodi's file manager.
    """
    icon = os.path.join(
        out,
        'skin.nightshift',
        'resources',
        'icon.png',
    )

    fanart = os.path.join(
        out,
        'skin.nightshift',
        'resources',
        'fanart.jpg',
    )

    fanart_background = (
        ',url("{0}")'.format(_relative(fanart, folder))
        if os.path.isfile(fanart)
        else ''
    )

    # Use literal placeholder replacement instead of %-formatting.
    # This preserves CSS percentages such as width:100%.
    css = _CSS.replace(
        '__FANART__',
        fanart_background,
    )

    audio_dir = os.path.join(out, AUDIO_FOLDER)
    audio_folder_url = _relative(audio_dir, folder).replace(os.sep, '/')
    if not audio_folder_url.endswith('/'):
        audio_folder_url += '/'

    lines = [
        '<!DOCTYPE html>',
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>{0}</title>'.format(title),
        '<style>{0}</style></head><body>'.format(css),
        '<section class="audio-player" aria-label="Site background audio">',
        '  <strong>LongTime background audio</strong>',
        '  <p id="audio-status" role="status">Loading selected track...</p>',
        '  <audio id="background-audio" controls loop preload="none"></audio>',
        '  <button id="audio-start" type="button" disabled>Preparing audio...</button>',
        '</section>',
        '<div class="wrap"><div class="panel">',
        '<div class="head">',
    ]

    if os.path.isfile(icon):
        lines.append(
            '<img src="{0}" alt="">'.format(
                _relative(icon, folder)
            )
        )

    lines += [
        '<div><h1>LongTime</h1><p class="crumbs">{0}</p>'
        '</div></div>'.format(title),
        '<ul>',
    ]

    for name, is_dir in entries:
        suffix = '/' if is_dir else ''
        css_class = '' if is_dir else ' class="file"'

        lines.append(
            '<li><a href="{0}{1}"{2}>{0}{1}</a></li>'.format(
                name,
                suffix,
                css_class,
            )
        )

    lines += [
        '</ul>',
        '<div class="foot">Add-on repository for Kodi</div>',
        '</div></div>',
        '<script>',
        '(function () {',
        '    "use strict";',
        '',
        '    const audio = document.getElementById("background-audio");',
        '    const button = document.getElementById("audio-start");',
        '    const status = document.getElementById("audio-status");',
        '    const audioFolder = {0};'.format(json.dumps(audio_folder_url)),
        '    let trackReady = false;',
        '    let audioConfigured = false;',
        '    let playbackStarted = false;',
        '    let playRequestPending = false;',
        '    let playRequestNumber = 0;',
        '    let navigationNumber = 0;',
        '',
        '    function showStartButton(message) {',
        '        status.textContent = message;',
        '        button.hidden = false;',
        '        button.disabled = false;',
        '        button.textContent = "Start background audio";',
        '    }',
        '',
        '    function startPlayback(userInitiated) {',
        '        // Call audio.play() immediately in the click event when possible.',
        '        // Do not wait for canplay: browsers can queue play() while loading.',
        '        if (!audioConfigured) {',
        '            if (userInitiated) {',
        '                status.textContent = "Audio is still loading. Tap Start once the track is ready.";',
        '            }',
        '            return;',
        '        }',
        '        if (playbackStarted && (!userInitiated || !audio.paused)) return;',
        '        if (playRequestPending && !userInitiated) return;',
        '        const requestNumber = ++playRequestNumber;',
        '        playRequestPending = true;',
        '        let playPromise;',
        '        try {',
        '            playPromise = audio.play();',
        '        } catch (error) {',
        '            if (requestNumber === playRequestNumber) playRequestPending = false;',
        '            if (requestNumber === playRequestNumber) handlePlaybackError(error);',
        '            return;',
        '        }',
        '        Promise.resolve(playPromise).catch(function (error) {',
        '            if (requestNumber === playRequestNumber) handlePlaybackError(error);',
        '        }).finally(function () {',
        '            if (requestNumber === playRequestNumber) playRequestPending = false;',
        '        });',
        '    }',
        '',
        '    function handlePlaybackError(error) {',
        '        console.warn("Background audio playback was blocked or failed:", error);',
        '        if (error.name === "NotAllowedError") {',
        '            showStartButton("Tap Start, or tap the Now folder, to start background audio.");',
        '        } else {',
        '            showStartButton("Playback failed: " + error.message);',
        '        }',
        '    }',
        '',
        '    function requestPlaybackFromGesture() {',
        '        // Shared by the visible Start/Resume button and the Now/ folder tap.',
        '        // The play() call stays synchronous with the user\'s gesture.',
        '        startPlayback(true);',
        '    }',
        '',
        '    button.addEventListener("click", function () {',
        '        requestPlaybackFromGesture();',
        '    });',
        '',
        '    audio.addEventListener("playing", function () {',
        '        playbackStarted = true;',
        '        status.textContent = "Background audio is playing while you browse folders.";',
        '        button.hidden = true;',
        '    });',
        '',
        '    audio.addEventListener("pause", function () {',
        '        if (!trackReady || audio.ended) return;',
        '        button.hidden = false;',
        '        button.disabled = false;',
        '        if (playbackStarted) {',
        '            button.textContent = "Resume background audio";',
        '            status.textContent = "Background audio is paused.";',
        '        } else {',
        '            // Safari can emit pause while rejecting the initial autoplay attempt.',
        '            // Do not label a track as Resume until it has actually played once.',
        '            button.textContent = "Start background audio";',
        '            status.textContent = "Tap Start, or tap the Now folder, to begin playback.";',
        '        }',
        '    });',
        '',
        '    audio.addEventListener("error", function () {',
        '        const code = audio.error ? audio.error.code : "unknown";',
        '        showStartButton("The audio file could not be loaded or decoded (media error " + code + ").");',
        '    });',
        '',
        '    async function loadBackgroundAudio() {',
        '        const audioBase = new URL(audioFolder, document.baseURI);',
        '        const manifestUrl = new URL("current.json?v=" + Date.now(), audioBase);',
        '        const response = await fetch(manifestUrl.href, { cache: "no-store" });',
        '        if (!response.ok) {',
        '            throw new Error("Could not load current.json: HTTP " + response.status);',
        '        }',
        '',
        '        const track = await response.json();',
        '        if (',
        '            typeof track.file !== "string" ||',
        '            track.file.includes("/") ||',
        '            track.file.includes(String.fromCharCode(92)) ||',
        '            !/^\\d+_.+\\.(mp3|opus|m4a)$/i.test(track.file)',
        '        ) {',
        '            throw new Error("Invalid audio filename in current.json");',
        '        }',
        '',
        '        const fileUrl = new URL(encodeURIComponent(track.file), audioBase);',
        '        fileUrl.searchParams.set("v", String(track.number || "current"));',
        '        audio.src = fileUrl.href;',
        '        audioConfigured = true;',
        '        // Enable the gesture button as soon as the source is assigned.',
        '        // A tap can call play() while the browser is still buffering.',
        '        button.disabled = false;',
        '        button.hidden = false;',
        '        button.textContent = "Start background audio";',
        '        audio.preload = "auto";',
        '        audio.load();',
        '',
        '        status.textContent = "Selected track: " + track.file;',
        '        await new Promise(function (resolve, reject) {',
        '            if (audio.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {',
        '                resolve();',
        '                return;',
        '            }',
        '            function cleanup() {',
        '                audio.removeEventListener("canplay", onReady);',
        '                audio.removeEventListener("error", onError);',
        '            }',
        '            function onReady() { cleanup(); resolve(); }',
        '            function onError() { cleanup(); reject(new Error("The browser could not decode the audio file.")); }',
        '            audio.addEventListener("canplay", onReady, { once: true });',
        '            audio.addEventListener("error", onError, { once: true });',
        '        });',
        '',
        '        trackReady = true;',
        '        button.disabled = false;',
        '        button.textContent = "Start background audio";',
        '        status.textContent = "Ready: " + track.file + ". Attempting autoplay...";',
        '        startPlayback(false);',
        '    }',
        '',
        '    async function navigateDirectory(targetUrl, addHistory) {',
        '        const requestNumber = ++navigationNumber;',
        '        const response = await fetch(targetUrl.href, { cache: "no-cache" });',
        '        if (!response.ok) throw new Error("Folder request failed: HTTP " + response.status);',
        '        const html = await response.text();',
        '        const nextDocument = new DOMParser().parseFromString(html, "text/html");',
        '        const nextPanel = nextDocument.querySelector(".panel");',
        '        const currentPanel = document.querySelector(".panel");',
        '        if (!nextPanel || !currentPanel) throw new Error("Folder page did not contain a repository listing.");',
        '        if (requestNumber !== navigationNumber) return;',
        '',
        '        // Keep the audio dock and audio element alive; replace only the folder listing.',
        '        const nextStyle = nextDocument.querySelector("style");',
        '        const currentStyle = document.querySelector("style");',
        '        // Resolve page-relative links and images against the folder being opened.',
        '        nextPanel.querySelectorAll("a[href], img[src]").forEach(function (element) {',
        '            const attribute = element.hasAttribute("href") ? "href" : "src";',
        '            element.setAttribute(attribute, new URL(element.getAttribute(attribute), targetUrl).href);',
        '        });',
        '        if (nextStyle && currentStyle) {',
        '            currentStyle.textContent = nextStyle.textContent.replace(/url[(]"(.*?)"[)]/g, function (match, path) {',
        '                return "url(\\\"" + new URL(path, targetUrl).href + "\\\")";',
        '            });',
        '        }',
        '        currentPanel.innerHTML = nextPanel.innerHTML;',
        '        document.title = nextDocument.title || "LongTime";',
        '        if (addHistory) history.pushState({ folder: targetUrl.href }, "", targetUrl.href);',
        '        window.scrollTo(0, 0);',
        '    }',
        '',
        '    document.addEventListener("click", function (event) {',
        '        const link = event.target.closest ? event.target.closest("a") : null;',
        '        if (!link || event.defaultPrevented || event.button !== 0) return;',
        '        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;',
        '        if (link.hasAttribute("download") || (link.target && link.target !== "_self")) return;',
        '        let targetUrl;',
        '        try { targetUrl = new URL(link.href, document.baseURI); } catch (_) { return; }',
        '        if (targetUrl.origin !== location.origin || !targetUrl.pathname.endsWith("/")) return;',
        '        // The root page links to Now/. Use that tap as the audio permission gesture.',
        '        // This retries only until playback has successfully started; it will not',
        '        // restart or interrupt a track that is already playing.',
        '        if (targetUrl.pathname.toLowerCase().replace(/\\/+$/, "").endsWith("/now")) {',
        '            requestPlaybackFromGesture();',
        '        }',
        '        event.preventDefault();',
        '        navigateDirectory(targetUrl, true).catch(function (error) {',
        '            console.error("Folder navigation failed; loading normally:", error);',
        '            location.assign(targetUrl.href);',
        '        });',
        '    });',
        '',
        '    window.addEventListener("popstate", function () {',
        '        const targetUrl = new URL(location.href);',
        '        navigateDirectory(targetUrl, false).catch(function (error) {',
        '            console.error("Could not restore folder from browser history:", error);',
        '            location.reload();',
        '        });',
        '    });',
        '',
        '    loadBackgroundAudio().catch(function (error) {',
        '        console.error("Background audio setup failed:", error);',
        '        showStartButton("Audio setup failed: " + error.message);',
        '    });',
        '})();',
        '</script>',
        '</body></html>',
    ]

    with open(
        os.path.join(folder, 'index.html'),
        'w',
        encoding='utf-8',
        newline='\n',
    ) as f:
        f.write('\n'.join(lines) + '\n')


def write_indexes(out):
    """
    Write index.html into out/ and every directory below it.
    """
    for folder, dirs, files in os.walk(out):
        dirs.sort()

        entries = (
            [(directory, True) for directory in dirs]
            + [
                (filename, False)
                for filename in sorted(files)
                if filename != 'index.html'
            ]
        )

        title = os.path.relpath(
            folder,
            os.path.dirname(out),
        ).replace(os.sep, '/')

        _listing(
            folder,
            entries,
            title.replace('/', ' / '),
            out,
        )


def write_root_index(root, out):
    """Write the top-level website index."""
    entries = [
        (
            os.path.relpath(out, root).replace(os.sep, '/'),
            True,
        )
    ]

    _listing(
        root,
        entries,
        'Add-ons',
        out,
    )


def prune_source(source, keep):
    """
    Remove superseded ZIP files after a successful build.

    Non-ZIP files, including numbered audio tracks, are untouched here.
    Audio cleanup is handled separately by prune_source_audio().
    """
    removed = []

    for name in sorted(os.listdir(source)):
        path = os.path.join(source, name)

        if (
            name.lower().endswith('.zip')
            and os.path.abspath(path) not in keep
        ):
            os.remove(path)
            removed.append(name)

    return removed


def build(base, out, source):
    """Build the Kodi repository and publish the selected background track."""
    found = {}

    for name in sorted(os.listdir(source)) if os.path.isdir(source) else []:
        if not name.endswith('.zip'):
            continue

        path = os.path.join(source, name)

        if os.path.getsize(path) > TOO_BIG:
            raise RepoError(
                '{0}: too big for a normal GitHub commit '
                '({1} MB; the limit is 100 MB)'.format(
                    name,
                    os.path.getsize(path) // (1024 * 1024),
                )
            )

        ident, version, xml_text, files = read_zip(path)

        if ident == 'repository.longtime':
            raise RepoError(
                '{0}: the id repository.longtime is the '
                'repository add-on itself'.format(name)
            )

        if (
            ident not in found
            or compare(version, found[ident][0]) > 0
        ):
            found[ident] = (
                version,
                path,
                xml_text,
                files,
            )

        elif compare(version, found[ident][0]) == 0:
            raise RepoError(
                '{0}: version {1} of {2} is there twice'.format(
                    name,
                    version,
                    ident,
                )
            )

    os.makedirs(out, exist_ok=True)

    # Preserve manually maintained output directories.
    for entry in os.listdir(out):
        full = os.path.join(out, entry)

        if (
            os.path.isdir(full)
            and entry not in PRESERVED_OUTPUT_DIRS
            and entry not in found
        ):
            shutil.rmtree(full)

    listing = []

    for ident in sorted(found):
        version, path, xml_text, files = found[ident]
        folder = os.path.join(out, ident)

        clear_folder(folder)

        shutil.copyfile(
            path,
            os.path.join(
                folder,
                '{0}-{1}.zip'.format(ident, version),
            ),
        )

        for asset in assets_of(xml_text):
            data = files.get(
                '{0}/{1}'.format(ident, asset)
            )

            if data is not None:
                target = os.path.join(folder, asset)

                os.makedirs(
                    os.path.dirname(target),
                    exist_ok=True,
                )

                with open(target, 'wb') as f:
                    f.write(data)

        listing.append(body(xml_text))

    repository_xml_path = os.path.join(
        REPOSITORY_SOURCE,
        'addon.xml',
    )

    with open(repository_xml_path, 'rb') as f:
        repository_xml = (
            f.read()
            .decode('utf-8')
            .replace('@BASE@', base)
        )

    repository_id, repository_version = addon_info(
        repository_xml
    )

    repository_folder = os.path.join(
        out,
        repository_id,
    )

    clear_folder(repository_folder)

    write_zip(
        os.path.join(
            repository_folder,
            '{0}-{1}.zip'.format(
                repository_id,
                repository_version,
            ),
        ),
        repository_id,
        [
            (
                'addon.xml',
                repository_xml.encode('utf-8'),
            )
        ],
    )

    listing.append(body(repository_xml))

    text = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<addons>\n{0}\n</addons>\n'
    ).format('\n'.join(listing))

    with open(
        os.path.join(out, 'addons.xml'),
        'wb',
    ) as f:
        f.write(text.encode('utf-8'))

    with open(
        os.path.join(out, 'addons.xml.md5'),
        'w',
    ) as f:
        f.write(
            hashlib.md5(text.encode('utf-8')).hexdigest()
        )

    # Publish the newest numbered track before generating indexes.
    audio_filename = publish_background_audio(
        source,
        out,
    )

    # Generate indexes after the selected audio and manifest exist.
    write_indexes(out)

    # Keep selected add-on ZIPs in Later/.
    keep = {
        os.path.abspath(found[ident][1])
        for ident in found
    }

    # Remove superseded add-on ZIPs.
    removed = (
        prune_source(source, keep)
        if os.path.isdir(source)
        else []
    )

    # Remove older numbered audio files from Later/.
    # Keep the selected source file for future builds.
    prune_source_audio(
        source,
        audio_filename,
    )

    return (
        [
            (ident, found[ident][0])
            for ident in sorted(found)
        ],
        (repository_id, repository_version),
        removed,
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '--base',
        default=DEFAULT_BASE,
    )

    parser.add_argument(
        '--out',
        default=os.path.join(ROOT, OUT_NAME),
    )

    parser.add_argument(
        '--now',
        default=os.path.join(ROOT, SOURCE_NAME),
    )

    args = parser.parse_args()

    try:
        published, repository, removed = build(
            args.base if args.base.endswith('/') else args.base + '/',
            args.out,
            args.now,
        )

    except RepoError as error:
        sys.exit('error: {0}'.format(error))

    if os.path.abspath(args.out) == os.path.join(ROOT, OUT_NAME):
        write_root_index(
            ROOT,
            args.out,
        )

    for ident, version in published:
        print(
            'published {0} {1}'.format(
                ident,
                version,
            )
        )

    for name in removed:
        print(
            'removed old zip from {0}: {1}'.format(
                SOURCE_NAME,
                name,
            )
        )

    print(
        'repository add-on {0} {1}'.format(*repository)
    )
