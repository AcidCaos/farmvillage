#!/usr/bin/env python3
"""Reproduce native resources from public originals, with isolated pinned tools."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, platform, posixpath, shutil, signal, subprocess, tarfile, tempfile, zipfile
from pathlib import Path, PurePosixPath
ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('fv_public_downloads', ROOT / 'tools/public_downloads.py')
downloads = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(downloads)
FFDEC = {'name': 'ffdec_26.4.0.zip', 'bytes': 21917740, 'sha256': '56ce960aeafc7caf034e2052ba49f878a883f7c7ca690da6eeffca9587b5e4b9', 'url': 'https://github.com/jindrapetrik/jpexs-decompiler/releases/download/version26.4.0/ffdec_26.4.0.zip'}
JAVA = {('Darwin', 'arm64'): ('aarch64_mac', 42646245, 'b37759cce74d3104da243c5a4ca1f8a73d6d8811b4a1711028744ec5559f7eb0'), ('Darwin', 'x86_64'): ('x64_mac', 37560312, '0fe26252c258ec239ea6d39a6a1f42b75025bff0d237e9ab3acb4782cef29439'), ('Linux', 'aarch64'): ('aarch64_linux', 45550153, 'd184e8d5caabe51b7ce9d4e0410f51b447a703eab3cec60ca94b7c59fecdad01'), ('Linux', 'x86_64'): ('x64_linux', 46188250, '1c607fb19f153b23a7d62ff980eb55cff1a7d47ce565bbc44d14947c93bd33c9')}
REQUIRED_ART = set('wood-rail.png friend-frame.png friend-frame-hover.png strawberry.png wheat.png eggplant.png red-barn-icon.png coins.png xp-star.png home-normal.png click.mp3 optional-barnyard.mp3 farmville-logo.png parchment.png play-normal.png play-hover.png play-pressed.png heading.ttf red-barn.png strawberry-grown.png wheat-grown.png eggplant-grown.png cow.png chicken.png sunflowers-grown.png cherry-blossom.png hills.png river.png tree.png grass.png'.split()) | {f'{a}-idle-{i:02}.png' for a in ['cow', 'chicken'] for i in range(1, 5)}

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda : stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

def _safe_members(names):
    seen = set()
    for name in names:
        p = PurePosixPath(name)
        if not p.parts or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe archive member: ' + name)
        key = p.as_posix().casefold()
        if key in seen:
            raise ValueError('Duplicate archive member: ' + name)
        seen.add(key)

def extract_tool(archive, destination):
    if destination.exists() or destination.is_symlink():
        raise ValueError('Tool destination must be new')
    destination.mkdir(parents=True)
    if archive.suffix == '.zip':
        with zipfile.ZipFile(archive) as source:
            _safe_members(source.namelist())
            if len(source.infolist()) > 20000 or sum(x.file_size for x in source.infolist()) > (1 << 30):
                raise ValueError('Native tool archive exceeds extraction bounds')
            if any((x.external_attr >> 16 & 61440 == 40960 for x in source.infolist())):
                raise ValueError('Archive links refused')
            source.extractall(destination)
    else:
        with tarfile.open(archive) as source:
            members = source.getmembers()
            _safe_members((x.name for x in members))
            if len(members) > 20000 or sum(x.size for x in members) > (1 << 30):
                raise ValueError('Native tool archive exceeds extraction bounds')
            links = {PurePosixPath(x.name) for x in members if x.issym() or x.islnk()}
            for item in members:
                name = PurePosixPath(item.name)
                if any((p in links for p in name.parents)):
                    raise ValueError('Member below archive link')
                if not (item.isfile() or item.isdir() or item.issym() or item.islnk()):
                    raise ValueError('Special archive file refused')
                if item.issym() or item.islnk():
                    target = PurePosixPath(item.linkname)
                    parent = name.parent if item.issym() else PurePosixPath()
                    normalized = PurePosixPath(posixpath.normpath(str(parent / target)))
                    if target.is_absolute() or '\\' in item.linkname or '..' in normalized.parts:
                        raise ValueError('Archive link escapes extraction')
            # Write ordinary files before links. This also supports Python 3.10,
            # which predates tarfile's extraction-filter argument.
            for item in members:
                out = destination / item.name
                if item.isdir():
                    out.mkdir(parents=True, exist_ok=True)
                elif item.isfile():
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with source.extractfile(item) as stream, out.open('xb') as target:
                        shutil.copyfileobj(stream, target)
                    out.chmod(item.mode & 0o777)
            for item in members:
                out = destination / item.name
                out.parent.mkdir(parents=True, exist_ok=True)
                if item.issym():
                    out.symlink_to(item.linkname)
                elif item.islnk():
                    target = destination / item.linkname
                    if target.is_symlink() or not target.is_file():
                        raise ValueError('Archive hard link target is not an ordinary file')
                    os.link(target, out)

def tool_inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.name == '.farmvillage-tool.json':
            continue
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[name] = {'link': os.readlink(path)}
        elif path.is_file():
            result[name] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
        elif not path.is_dir():
            raise ValueError('Special native tool file refused')
    return result

def _install_tool(resources, name, entry, filename):
    archive = downloads.download(entry['url'], resources / 'downloads' / entry['name'], entry)
    target = downloads.ordinary(resources / 'tools/native' / name)
    identity = {'schema': 1, 'archiveSHA256': entry['sha256'], 'url': entry['url']}
    marker = target / '.farmvillage-tool.json'
    if target.exists():
        stored = json.loads(marker.read_text()) if marker.is_file() and not marker.is_symlink() else {}
        if any(stored.get(k) != v for k, v in identity.items()) or stored.get('files') != tool_inventory(target):
            raise ValueError('Unrecognized native tool directory preserved')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.native-tool-', dir=target.parent))
        try:
            out = stage / 'unpacked'
            extract_tool(archive, out)
            identity['files'] = tool_inventory(out)
            (out / marker.name).write_text(json.dumps(identity, indent=2) + '\n')
            out.rename(target)
        finally:
            shutil.rmtree(stage)
    found = [p for p in target.rglob(filename) if p.is_file() and (filename != 'java' or p.parent.name == 'bin')]
    if len(found) != 1:
        raise ValueError('Incomplete or ambiguous native tool')
    return found[0]

def prepare_tools(resources):
    resources = downloads.ordinary(Path(resources))
    if resources == ROOT or ROOT in resources.parents:
        raise ValueError('Choose an external resource folder outside the source checkout')
    host = (platform.system(), platform.machine())
    if host not in JAVA:
        raise ValueError('Native tools support macOS/Linux ARM64 and x86_64')
    (label, size, sha) = JAVA[host]
    name = f'OpenJDK17U-jre_{label}_hotspot_17.0.17_10.tar.gz'
    entry = {'name': name, 'bytes': size, 'sha256': sha, 'url': 'https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.17%2B10/' + name}
    return (_install_tool(resources, 'temurin-17.0.17-' + label, entry, 'java'), _install_tool(resources, 'ffdec-26.4.0', FFDEC, 'ffdec.jar'))

def render_icons(source, output):
    from PIL import Image, ImageDraw, ImageOps
    source = downloads.ordinary(source)
    output = downloads.ordinary(output)
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Choose an external native icon output outside the source checkout')
    output.mkdir(parents=True)
    metadata = ROOT / 'FarmVillage/macOS/Resources/Assets.xcassets'
    shutil.copyfile(metadata / 'Contents.json', output / 'Contents.json')
    appicon = output / 'AppIcon.appiconset'
    appicon.mkdir()
    description = json.loads((metadata / 'AppIcon.appiconset/Contents.json').read_text())
    canvas = Image.new('RGBA', (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((30, 30, 994, 994), radius=210, fill='#fff7d6', outline='#6b401f', width=28)
    draw.rounded_rectangle((75, 610, 949, 949), radius=140, fill='#6a9138')
    with Image.open(source) as original:
        barn = ImageOps.contain(original.convert('RGBA'), (750, 750), Image.Resampling.LANCZOS)
        canvas.alpha_composite(barn, ((1024 - barn.width) // 2, (1024 - barn.height) // 2))
    for item in description['images']:
        size = int(item['size'].split('x')[0]) * int(item['scale'][:-1])
        canvas.resize((size, size), Image.Resampling.LANCZOS).save(appicon / item['filename'], optimize=True)
    (appicon / 'Contents.json').write_text(json.dumps(description, indent=2) + '\n')

def required_files():
    names = {'Heritage/' + n for n in REQUIRED_ART}
    names.update({'Heritage/manifest.json', 'Heritage/NOTICES.md', 'Assets.xcassets/Contents.json', 'Assets.xcassets/AppIcon.appiconset/Contents.json'})
    icons = json.loads((ROOT / 'FarmVillage/macOS/Resources/Assets.xcassets/AppIcon.appiconset/Contents.json').read_text())
    names.update(('Assets.xcassets/AppIcon.appiconset/' + x['filename'] for x in icons['images']))
    return names

def check_native(root):
    root = downloads.ordinary(root)
    manifest = json.loads(downloads.child(root, 'native-manifest.json').read_text())
    if manifest.get('schema') != 1 or manifest.get('kind') != 'public-native-resources':
        raise ValueError('Unrecognized native resource manifest')
    if not required_files().issubset(manifest.get('files', {})):
        raise ValueError('Native preparation omitted required original launcher artwork or app icons')
    if set(manifest['files']) != required_files():
        raise ValueError('Native resources contain unreviewed additional files')
    actual = set()
    for p in root.rglob('*'):
        if p.is_symlink():
            raise ValueError('Linked native resource refused')
        if p.is_file() and p.name != '.DS_Store':
            actual.add(p.relative_to(root).as_posix())
    if actual != set(manifest['files']) | {'native-manifest.json'}:
        raise ValueError('Native resources contain missing or unreviewed additional files')
    for (name, expected) in manifest['files'].items():
        p = downloads.child(root, name)
        if not p.is_file() or p.stat().st_size != expected['bytes'] or digest(p) != expected['sha256']:
            raise ValueError('Native resource differs or is missing: ' + name)
    return {'schema': 1, 'status': 'ready', 'native': str(root), 'files': len(manifest['files'])}

def check(resources):
    return check_native(Path(resources) / 'native')

def prepare(resources, original, assets, envpython):
    (resources, original, assets) = [downloads.ordinary(Path(p)) for p in (resources, original, assets)]
    if resources == ROOT or ROOT in resources.parents:
        raise ValueError('Choose an external resource folder outside the source checkout')
    envpython = Path(envpython).absolute()
    if not envpython.is_file() or not os.access(envpython, os.X_OK):
        raise ValueError('Select the installed resource Python executable')
    if not original.is_dir() or not assets.is_dir():
        raise ValueError('Original and extracted public resources must be prepared first')
    resources.mkdir(parents=True, exist_ok=True)
    if (resources / 'native').exists():
        return check(resources)
    (java, ffdec) = prepare_tools(resources)
    stage = Path(tempfile.mkdtemp(prefix='.native-stage-', dir=resources))

    def run_owned(arguments):
        process = subprocess.Popen(arguments, start_new_session=True)
        print(f'Owned native resource subprocess PID: {process.pid}', flush=True)
        try:
            code = process.wait()
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
        if code:
            raise subprocess.CalledProcessError(code, arguments)
    try:
        exporter = ROOT / 'FarmVillage/macOS/Scripts/prepare-heritage-assets.py'
        run_owned([str(envpython), '-I', '-B', str(exporter), '--game-root', str(original), '--assets-root', str(assets), '--output', str(stage / 'Heritage'), '--java', str(java), '--ffdec', str(ffdec), '--tool-home', str(resources / 'tools/native/export-home')])
        run_owned([str(envpython), '-I', '-B', str(Path(__file__).resolve()), '--icon-source', str(stage / 'Heritage/red-barn-icon.png'), '--icon-output', str(stage / 'Assets.xcassets')])
        files = {p.relative_to(stage).as_posix(): {'bytes': p.stat().st_size, 'sha256': digest(p)} for p in sorted(stage.rglob('*')) if p.is_file()}
        manifest = {'schema': 1, 'kind': 'public-native-resources', 'files': files, 'exporterSHA256': digest(exporter), 'iconRecipe': 'Authored farm-colored canvas with recovered red-barn artwork; cosmetic difference from former private geometric icon', 'fontPolicy': 'Original Merkin; absent optional BadaBoom BB uses existing system-rounded fallback; no private font', 'toolSources': {'FFDec': FFDEC['url'], 'Java': 'https://github.com/adoptium/temurin17-binaries/releases/tag/jdk-17.0.17%2B10'}}
        (stage / 'native-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        check_native(stage)
        stage.rename(resources / 'native')
        return check(resources)
    finally:
        if stage.exists():
            shutil.rmtree(stage)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['resources', 'original', 'assets']:
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--python', type=Path, dest='envpython')
    parser.add_argument('--tools-only', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--icon-source', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--icon-output', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.icon_source and args.icon_output:
        render_icons(args.icon_source, args.icon_output)
        return
    if not args.resources:
        parser.error('--resources is required')
    if args.tools_only:
        (java, ffdec) = prepare_tools(args.resources)
        result = {'java': str(java), 'ffdec': str(ffdec)}
    elif args.check:
        result = check(args.resources)
    else:
        if not all((args.original, args.assets, args.envpython)):
            parser.error('Preparation requires --original, --assets and --python')
        result = prepare(args.resources, args.original, args.assets, args.envpython)
    print(json.dumps(result, indent=2))
if __name__ == '__main__':
    main()
