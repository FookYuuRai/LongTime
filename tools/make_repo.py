#!/usr/bin/env python3
"""
Builds the files Kodi reads (the repo/ folder) from the add-on zips in now/.

Put any number of add-on zips in now/ (each zip: one top level folder named exactly like the add-on id, with
addon.xml inside), run `python3 tools/make_repo.py`, commit, push. For every add-on id the zip with the highest
version is published as repo/<id>/<id>-<version>.zip, with its icon and fanart, and listed in repo/addons.xml with
repo/addons.xml.md5. The zip of the small repository add-on (the one Kodi installs once) is built as well.

Also written: index.html pages for browsing on the site (the root, repo/ and each folder below it, and now/, which
lists the zips waiting to be published). Those pages only link to files on this same site.

  --base  the address the files are served from (default: this repository's raw files)
  --out   where the files are written (default: repo/)
  --now   the folder with the source zips (default: now/)
"""
import argparse
import hashlib
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_BASE = 'https://raw.githubusercontent.com/FookYuuRai/LongTime/OnTheSide/repo/'
TOO_BIG = 90 * 1024 * 1024                          # GitHub refuses files over 100 MB; stay well under
REPOSITORY_SOURCE = os.path.join(HERE, '_source', 'repository.longtime')
STAMP = (2026, 1, 1, 0, 0, 0)                        # a fixed date: the same files give the same zip
JUNK = ('__MACOSX', '.DS_Store', '__pycache__', '.git', '.svn', 'Thumbs.db', '.pyc')


class RepoError(Exception):
    pass


def addon_info(xml_text):
    """(id, version) from the <addon ...> tag of an addon.xml."""
    tag = re.search(r'<addon\b[^>]*>', xml_text, re.S)
    if not tag:
        raise RepoError('no <addon> tag in addon.xml')
    ident = re.search(r'\bid="([^"]+)"', tag.group(0))
    version = re.search(r'\bversion="([^"]+)"', tag.group(0))
    if not ident or not version:
        raise RepoError('the <addon> tag has no id or version')
    return ident.group(1), version.group(1)


def _order(char):
    if char == '~':
        return -1                                   # before everything, even the end of the version
    if char.isalpha():
        return ord(char)
    return ord(char) + 256


def compare(a, b):
    """-1, 0, 1: a is older than, the same as, newer than b. Like Kodi's own comparison (Debian style): numbers by
    value, '~' before everything (1.1.1~beta2 is older than 1.1.1), letters after the end of the version
    (1.1.1Beta2 is newer than 1.1.1)."""
    while a or b:
        text_a, text_b = re.match(r'\D*', a).group(0), re.match(r'\D*', b).group(0)
        a, b = a[len(text_a):], b[len(text_b):]
        for i in range(max(len(text_a), len(text_b))):
            order_a = _order(text_a[i]) if i < len(text_a) else 0
            order_b = _order(text_b[i]) if i < len(text_b) else 0
            if order_a != order_b:
                return -1 if order_a < order_b else 1
        num_a, num_b = re.match(r'\d*', a).group(0), re.match(r'\d*', b).group(0)
        a, b = a[len(num_a):], b[len(num_b):]
        if int(num_a or 0) != int(num_b or 0):
            return -1 if int(num_a or 0) < int(num_b or 0) else 1
    return 0


def body(xml_text):
    """An addon.xml without its XML declaration, to go inside addons.xml."""
    return re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', xml_text).strip()


def open_zip(path):
    """(zipfile, id, version, addon.xml text) of an add-on zip, after checking it is clean."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise RepoError('{0}: not a zip file'.format(os.path.basename(path)))
    names = [n for n in z.namelist() if not n.endswith('/')]
    folders = {n.split('/')[0] for n in names}
    if len(folders) != 1 or any('/' not in n for n in names):
        raise RepoError('{0}: the zip must hold one top level folder and nothing outside it'.format(os.path.basename(path)))
    folder = folders.pop()
    if '{0}/addon.xml'.format(folder) not in names:
        raise RepoError('{0}: no addon.xml in {1}/'.format(os.path.basename(path), folder))
    xml_text = z.read('{0}/addon.xml'.format(folder)).decode('utf-8')
    ident, version = addon_info(xml_text)
    if folder != ident:
        raise RepoError('{0}: the folder inside is "{1}" but the add-on id is "{2}"'.format(
            os.path.basename(path), folder, ident))
    for name in names:
        if any(j in name.split('/') or name.endswith(j) for j in JUNK):
            raise RepoError('{0}: contains {1}'.format(os.path.basename(path), name))
    return z, ident, version, xml_text


def read_zip(path):
    """(id, version, addon.xml text, {name: bytes}) of an add-on zip, after checking it is clean."""
    z, ident, version, xml_text = open_zip(path)
    return ident, version, xml_text, {n: z.read(n) for n in z.namelist() if not n.endswith('/')}


def assets_of(xml_text):
    return re.findall(r'<(?:icon|fanart)>([^<]+)</', xml_text)


def write_zip(path, folder, files):
    if os.path.exists(path):
        os.remove(path)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            info = zipfile.ZipInfo('{0}/{1}'.format(folder, name), STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)


def clear_folder(folder):
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)


# the NightShift skin's colours (colors/defaults.xml of skin.nightshift) for the listing pages
_CSS = """
:root{--bg:#03050c;--panel:#071426;--header:#123b66;--text:#f0f6ff;--grey:#9cb0c9;--blue:#49c9ff;--focus:#35bfff;--pink:#ff5cbf;--line:rgba(53,191,255,.5)}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;min-height:100vh;color:var(--text);text-shadow:0 1px 4px rgba(0,0,0,.95);font:16px/1.45 "Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background:linear-gradient(rgba(3,5,12,.28),rgba(3,5,12,.42))%(fanart)s,var(--bg);background-size:cover;background-attachment:fixed;background-position:center}
.wrap{max-width:920px;margin:0 auto;padding:28px 16px 40px}
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
"""


def _relative(target, folder):
    return os.path.relpath(target, folder).replace(os.sep, '/')


def _listing(folder, entries, title, out):
    """One themed page. Every entry is a plain <a href="name">name</a> on a line of its own: that is what Kodi's file
    manager reads (href first in the tag, no other link in the page, nothing inside the link)."""
    icon = os.path.join(out, 'skin.nightshift', 'resources', 'icon.png')
    fanart = os.path.join(out, 'skin.nightshift', 'resources', 'fanart.jpg')
    css = _CSS % {'fanart': ',url("{0}")'.format(_relative(fanart, folder)) if os.path.isfile(fanart) else ''}
    lines = ['<!DOCTYPE html>', '<html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">', '<title>{0}</title>'.format(title),
             '<style>{0}</style></head><body><div class="wrap"><div class="panel">'.format(css), '<div class="head">']
    if os.path.isfile(icon):
        lines.append('<img src="{0}" alt="">'.format(_relative(icon, folder)))
    lines += ['<div><h1>LongTime</h1><p class="crumbs">{0}</p></div></div>'.format(title), '<ul>']
    for name, is_dir in entries:
        lines.append('<li><a href="{0}{1}"{2}>{0}{1}</a></li>'.format(name, '/' if is_dir else '',
                                                                       '' if is_dir else ' class="file"'))
    lines += ['</ul>', '<div class="foot">Add-on repository for Kodi</div>', '</div></div></body></html>']
    with open(os.path.join(folder, 'index.html'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


def write_indexes(out):
    """An index.html in out/ and in every folder below it: a list of links, so that a web address of the folder (GitHub
    Pages serves index.html) can be browsed from Kodi's file manager. The raw address has no listing."""
    for folder, dirs, files in os.walk(out):
        dirs.sort()
        entries = [(d, True) for d in dirs] + [(f, False) for f in sorted(files) if f != 'index.html']
        title = os.path.relpath(folder, os.path.dirname(out)).replace(os.sep, '/')
        _listing(folder, entries, title.replace('/', ' / '), out)


def write_root_index(root, out, now_dir):
    """index.html at the top of the site: links to the repository files (repo/) and to the zips waiting in now/.
    Kodi's file manager ignores links that contain a path, so the links are folders of this site."""
    entries = [(os.path.relpath(out, root).replace(os.sep, '/'), True)]
    if os.path.isdir(now_dir):
        entries.append((os.path.relpath(now_dir, root).replace(os.sep, '/'), True))
    _listing(root, entries, 'Add-ons', out)


def write_now_index(now_dir, out):
    """index.html in now/: the add-on zips waiting to be published, as links to the zips on this site. Zips that are
    not the newest version of their add-on stay listed until they are removed from now/."""
    zips = sorted(n for n in os.listdir(now_dir) if n.lower().endswith('.zip'))
    _listing(now_dir, [(n, False) for n in zips], 'now', out)


def build(base, out, source):
    found = {}                                          # id -> (version, zip path, addon.xml text, files)
    for name in sorted(os.listdir(source)) if os.path.isdir(source) else []:
        if not name.endswith('.zip'):
            continue
        path = os.path.join(source, name)
        if os.path.getsize(path) > TOO_BIG:
            raise RepoError('{0}: too big for a normal GitHub commit ({1} MB; the limit is 100 MB)'.format(
                name, os.path.getsize(path) // (1024 * 1024)))
        ident, version, xml_text, files = read_zip(path)
        if ident == 'repository.longtime':
            raise RepoError('{0}: the id repository.longtime is the repository add-on itself'.format(name))
        if ident not in found or compare(version, found[ident][0]) > 0:
            found[ident] = (version, path, xml_text, files)
        elif compare(version, found[ident][0]) == 0:
            raise RepoError('{0}: version {1} of {2} is there twice'.format(name, version, ident))

    os.makedirs(out, exist_ok=True)
    for entry in os.listdir(out):                       # what is not published any more goes
        full = os.path.join(out, entry)
        if os.path.isdir(full) and entry != 'repository.longtime' and entry not in found:
            shutil.rmtree(full)
    listing = []
    for ident in sorted(found):
        version, path, xml_text, files = found[ident]
        folder = os.path.join(out, ident)
        clear_folder(folder)
        shutil.copyfile(path, os.path.join(folder, '{0}-{1}.zip'.format(ident, version)))
        for asset in assets_of(xml_text):                                    # what the add-on list shows
            data = files.get('{0}/{1}'.format(ident, asset))
            if data is not None:
                target = os.path.join(folder, asset)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, 'wb') as f:
                    f.write(data)
        listing.append(body(xml_text))

    with open(os.path.join(REPOSITORY_SOURCE, 'addon.xml'), 'rb') as f:
        repository_xml = f.read().decode('utf-8').replace('@BASE@', base)
    repository_id, repository_version = addon_info(repository_xml)
    repository_folder = os.path.join(out, repository_id)
    clear_folder(repository_folder)
    write_zip(os.path.join(repository_folder, '{0}-{1}.zip'.format(repository_id, repository_version)),
              repository_id, [('addon.xml', repository_xml.encode('utf-8'))])
    listing.append(body(repository_xml))

    text = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n{0}\n</addons>\n'.format('\n'.join(listing))
    with open(os.path.join(out, 'addons.xml'), 'wb') as f:
        f.write(text.encode('utf-8'))
    with open(os.path.join(out, 'addons.xml.md5'), 'w') as f:
        f.write(hashlib.md5(text.encode('utf-8')).hexdigest())
    write_indexes(out)
    return [(i, found[i][0]) for i in sorted(found)], (repository_id, repository_version)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', default=DEFAULT_BASE)
    parser.add_argument('--out', default=os.path.join(ROOT, 'repo'))
    parser.add_argument('--now', default=os.path.join(ROOT, 'now'))
    args = parser.parse_args()
    try:
        published, repository = build(args.base if args.base.endswith('/') else args.base + '/', args.out, args.now)
    except RepoError as e:
        sys.exit('error: {0}'.format(e))
    if os.path.abspath(args.out) == os.path.join(ROOT, 'repo'):
        write_root_index(ROOT, args.out, args.now)
    if os.path.abspath(args.now) == os.path.join(ROOT, 'now') and os.path.isdir(args.now):
        write_now_index(args.now, args.out)
    for ident, version in published:
        print('published {0} {1}'.format(ident, version))
    print('repository add-on {0} {1}'.format(*repository))
