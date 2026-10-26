#!/usr/bin/env python3
"""Deploy the reviewed Barn overlay without replacing game code or farm data.

Run on Bifrost through the existing portable release's Python environment.
Close game tabs first. Rollback restores only the previous Barn loader/checksums.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path('/home/farmvillage/farmville-test')
RELEASE = 'farmvillage-portable-preparation-1acf91b47487'
EXPECTED_SHA256 = '7ff2f6a639f08f656343f5d6b465effdecdcfb3bfc4534c5545ebc4a39067f96'
SERVICE = 'farmvillage.service'
ORIGIN = 'http://192.168.50.80:5501'
PROTECTED = ('saves', 'god-barn', 'neighborhood')
MODULES = {'__init__.py', 'engine.py', 'integration.py', 'seasonal.py',
           'encyclopedia.py', 'progression_tools.py', 'catalog_tools.py', 'helper_tools.py'}
ARTWORK_LIMIT = 2 * 1024 * 1024 * 1024
ARTWORK_FILE_LIMIT = 64 * 1024 * 1024
ARTWORK_NAME = re.compile(r'static/assets/items/[0-9a-fA-F]{32,64}\.(?:png|jpe?g|gif|webp)\Z', re.IGNORECASE)
DATA = {'archive-provenance.json', 'asset-map.json', 'catalog-audit.json',
        'catalog.json.gz', 'encyclopedia.json.gz', 'historical-prizes.json',
        'progression.json', 'rules.json', 'helpers.json'}
# The pinned recovery archive predates this index. Accept both that archive and
# new bundles without excluding the Not in Market classifications on install.
OPTIONAL_DATA = {'untabbed.json'}


def progress(message):
    print('[God Barn] ' + message, file=sys.stderr, flush=True)


def digest(contents):
    return hashlib.sha256(contents).hexdigest()


def file_digest(path):
    """Hash archive artwork without loading a potentially large pack in memory."""
    result = hashlib.sha256()
    with ordinary(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def ordinary(path, *, directory=False):
    """Reject links in every existing component, including parent directories."""
    path = Path(path).absolute()
    for component in (path, *path.parents):
        if component.is_symlink():
            raise RuntimeError('Refusing symbolic link: ' + str(component))
    if not (path.is_dir() if directory else path.is_file()):
        raise RuntimeError('Expected ordinary ' + ('directory: ' if directory else 'file: ') + str(path))
    return path


def relative_path(name, *, allow_hidden=False):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or str(path) != name or
            any(part in ('', '.', '..') or (part.startswith('.') and not allow_hidden) for part in path.parts) or
            '\\' in name or '\n' in name or '\r' in name):
        raise ValueError('Unsafe relative path: ' + repr(name))
    return path


def checksum_entries(contents):
    entries = {}
    for line in contents.decode('ascii').splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64}) [ *](.+)', line)
        if not match:
            raise ValueError('Malformed SHA256SUMS.')
        value, name = match.groups()
        relative_path(name, allow_hidden=True)
        if name in entries:
            raise ValueError('Duplicate checksum path: ' + name)
        entries[name] = value.lower()
    if not entries:
        raise ValueError('Empty SHA256SUMS.')
    return entries


def verify_checksums(directory):
    entries = checksum_entries(ordinary(directory / 'SHA256SUMS').read_bytes())
    for name, expected in entries.items():
        if digest(ordinary(directory / name).read_bytes()) != expected:
            raise ValueError('Installed checksum mismatch: ' + str(directory / name))
    return entries


def archive_files(archive, expected):
    if not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('Expected archive SHA256 must have 64 lowercase hex digits.')
    ordinary(archive)
    if archive.stat().st_size > 64 * 1024 * 1024 or digest(archive.read_bytes()) != expected:
        raise ValueError('The Barn archive does not match its expected SHA256.')
    files, seen, total = {}, set(), 0
    with tarfile.open(archive, 'r:gz') as source:
        for member in source:
            name = member.name.rstrip('/')
            path = relative_path(name)
            if name in seen or path.parts[0] != 'GodBarn':
                raise ValueError('Duplicate or non-Barn archive member: ' + name)
            seen.add(name)
            tail = path.parts[1:]
            allowed = (not tail or (len(tail) == 1 and tail[0] in MODULES) or
                       (tail[0] == 'data' and (len(tail) == 1 or len(tail) == 2 and tail[1] in DATA | OPTIONAL_DATA)) or
                       (tail[0] == 'static' and 'items' not in tail and
                        not any(part in ('workspace', 'saves', '__pycache__') or
                                'bootstrap' in part.lower() for part in tail)))
            if not allowed or not (member.isdir() or member.isfile()):
                raise ValueError('Unexpected Barn archive member: ' + name)
            if member.isdir():
                continue
            total += member.size
            if member.size < 0 or member.size > 64 * 1024 * 1024 or total > 160 * 1024 * 1024:
                raise ValueError('Barn payload exceeds size limits.')
            contents = source.extractfile(member).read(member.size + 1)
            if len(contents) != member.size:
                raise ValueError('Incomplete Barn archive member: ' + name)
            files[name] = contents
    required = {'GodBarn/' + name for name in MODULES}
    required.update('GodBarn/data/' + name for name in DATA)
    required.update('GodBarn/static/' + name for name in ('index.html', 'app.js', 'style.css', 'farmville.css'))
    if not required.issubset(files):
        raise ValueError('The Barn runtime is incomplete.')
    return files


def artwork_requirements(files):
    """Recover exactly the first-name catalog art the live Barn will display."""
    mapping = json.loads(files['GodBarn/data/asset-map.json'])
    if not isinstance(mapping, dict):
        raise ValueError('The Barn asset map must be an object.')
    for path, asset in mapping.items():
        if not isinstance(path, str) or not isinstance(asset, str):
            raise ValueError('The Barn asset map must contain relative path strings.')
        relative_path(path)
        relative_path(asset)
    catalog = json.loads(gzip.decompress(files['GodBarn/data/catalog.json.gz']))
    if not isinstance(catalog, list):
        raise ValueError('The Barn catalog must be an array.')
    requirements, names = {}, set()
    for item in catalog:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            continue
        if item['name'] in names:
            continue
        names.add(item['name'])
        artwork = item.get('artwork') or {}
        if not isinstance(artwork, dict):
            raise ValueError('The catalog artwork declaration must be an object.')
        if not (artwork.get('status') == 'exact' or
                'status' not in artwork and item.get('hasOriginalThumbnail')):
            continue
        image = item.get('image')
        if not isinstance(image, str) or not image.startswith('/'):
            raise ValueError('An exact catalog image must declare its Barn static path.')
        path = image[1:]
        relative_path(path)
        if not ARTWORK_NAME.fullmatch(path) or path not in mapping:
            raise ValueError('An exact catalog image has no safe original asset mapping: ' + path)
        sha, size = artwork.get('sha256'), artwork.get('bytes')
        if (not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha) or
                type(size) is not int or not 0 < size <= ARTWORK_FILE_LIMIT):
            raise ValueError('An exact catalog image has invalid SHA256 or byte metadata: ' + path)
        requirement = {'path': path, 'sha256': sha, 'bytes': size, 'assetPath': mapping[path]}
        if path in requirements and requirements[path] != requirement:
            raise ValueError('Catalog declarations disagree about exact artwork: ' + path)
        requirements[path] = requirement
    return requirements


def artwork_matches(path, requirement):
    """Missing or corrupt archive bytes can be supplemented; unsafe paths cannot."""
    path = Path(path).absolute()
    for component in (path, *path.parents):
        if component.is_symlink():
            raise RuntimeError('Refusing symbolic link: ' + str(component))
    if not path.exists():
        return False
    ordinary(path)
    return path.stat().st_size == requirement['bytes'] and file_digest(path) == requirement['sha256']


def audit_artwork(archive, expected=EXPECTED_SHA256, *, root=ROOT):
    ordinary(root, directory=True)
    ordinary(root / 'data/assets', directory=True)
    files = archive_files(archive, expected)
    requirements = artwork_requirements(files)
    progress('Checking ' + str(len(requirements)) + ' selected original images; no service changes are made.')
    missing = []
    for index, (path, requirement) in enumerate(sorted(requirements.items()), 1):
        if not artwork_matches(root / 'data/assets' / requirement['assetPath'], requirement):
            missing.append(requirement)
        if index % 10000 == 0:
            progress('Checked ' + str(index) + '/' + str(len(requirements)) + ' original images.')
    progress('Artwork audit complete: ' + str(len(missing)) + ' exact images need a Barn-only copy.')
    return {'schema': 1, 'bundleSha256': expected, 'items': missing}


def supplement_files(archive, expected, requirements, stage):
    """Stream a bounded, separately authenticated art pack into Barn-only staging."""
    if not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('Expected artwork SHA256 must have 64 lowercase hex digits.')
    ordinary(archive)
    progress('Verifying the supplemental artwork archive SHA256.')
    if archive.stat().st_size > ARTWORK_LIMIT or file_digest(archive) != expected:
        raise ValueError('The artwork archive does not match its expected SHA256.')
    result, total = {}, 0
    with tarfile.open(archive, 'r|gz') as source:
        for member in source:
            name = member.name
            relative_path(name)
            if not name.startswith('GodBarn/'):
                raise ValueError('Unexpected supplemental artwork member: ' + name)
            path = name[len('GodBarn/'):]
            requirement = requirements.get(path)
            if (not member.isfile() or member.issparse() or not ARTWORK_NAME.fullmatch(path) or
                    requirement is None or path in result):
                raise ValueError('Unexpected or duplicate supplemental artwork member: ' + name)
            total += member.size
            if member.size != requirement['bytes'] or total > ARTWORK_LIMIT:
                raise ValueError('Supplemental artwork exceeds declared byte or size limits: ' + name)
            target = stage / path
            target.parent.mkdir(parents=True, exist_ok=True)
            result_hash = hashlib.sha256()
            remaining = member.size
            with source.extractfile(member) as incoming, target.open('xb') as output:
                while remaining:
                    chunk = incoming.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError('Incomplete supplemental artwork: ' + name)
                    remaining -= len(chunk)
                    result_hash.update(chunk)
                    output.write(chunk)
                if incoming.read(1):
                    raise ValueError('Oversized supplemental artwork: ' + name)
            if result_hash.hexdigest() != requirement['sha256']:
                raise ValueError('Supplemental artwork SHA256 mismatch: ' + name)
            result[path] = target
            if len(result) % 1000 == 0:
                progress('Verified and staged ' + str(len(result)) + ' supplemental images.')
    progress('Verified ' + str(len(result)) + ' supplemental images in Barn-only staging.')
    return result


def stage_payload(releases, files, expected, requirements, artwork_archive, artwork_sha256):
    """Publish immutable base resources plus optional original artwork in Barn space."""
    version = expected[:12] + ('-' + artwork_sha256[:12] if artwork_sha256 else '')
    destination = releases / version
    progress('Preparing the immutable Barn payload and any supplemental artwork.')
    with tempfile.TemporaryDirectory(prefix='.artwork-', dir=releases) as temporary:
        extras = supplement_files(artwork_archive, artwork_sha256, requirements, Path(temporary)) if artwork_archive else {}
        manifest = {name: digest(contents) for name, contents in files.items()}
        manifest.update({'GodBarn/' + path: requirements[path]['sha256'] for path in extras})
        if destination.exists() or destination.is_symlink():
            ordinary(destination, directory=True)
            if any(path.is_symlink() for path in destination.rglob('*')):
                raise RuntimeError('Existing Barn version contains a symbolic link.')
            actual = {path.relative_to(destination).as_posix(): file_digest(path)
                      for path in destination.rglob('*') if not path.is_dir()}
            if actual != manifest:
                raise RuntimeError('An existing Barn version directory differs from this package.')
        else:
            stage = Path(tempfile.mkdtemp(prefix='.staging-', dir=releases))
            try:
                for name, contents in files.items():
                    target = stage / name
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    target.write_bytes(contents)
                    if file_digest(target) != manifest[name]:
                        raise RuntimeError('Staged payload verification failed.')
                for path, source in extras.items():
                    target = stage / 'GodBarn' / path
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    if not artwork_matches(target, requirements[path]):
                        raise RuntimeError('Staged artwork verification failed.')
                stage.rename(destination)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
    return version, destination, manifest


def inventory(data):
    """Read hashes and metadata only; no farm content is copied into the report."""
    result = {}
    for name in PROTECTED:
        directory = ordinary(data / name, directory=True)
        for path in sorted(directory.rglob('*')):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise RuntimeError('Unexpected protected data entry: ' + str(path))
            if path.is_file():
                info = path.stat()
                result[path.relative_to(data).as_posix()] = {
                    'sha256': digest(path.read_bytes()), 'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns}
    return result


def atomic_write(path, contents):
    ordinary(path.parent, directory=True)
    if path.exists() or path.is_symlink():
        ordinary(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.barn-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def loader_source(payload, version):
    return ("\"\"\"Versioned God Barn overlay; the accepted game Runtime stays sealed.\"\"\"\n"
            'import importlib\nimport importlib.util\nfrom pathlib import Path\nimport sys\n'
            f'_root = Path({str(payload)!r})\n_name = "_god_barn_{version}"\n'
            '_spec = importlib.util.spec_from_file_location(_name, _root / "__init__.py", '
            'submodule_search_locations=[str(_root)])\n'
            '_package = importlib.util.module_from_spec(_spec)\nsys.modules[_name] = _package\n'
            '_spec.loader.exec_module(_package)\n'
            '_bridge = importlib.import_module(_name + ".integration")\n'
            'def register_god_barn(app, **arguments):\n'
            '    arguments["root"] = _root\n'
            '    return _bridge.register_god_barn(app, **arguments)\n').encode()


class Service:
    def __init__(self, root):
        self.root = root

    def command(self, *arguments):
        return subprocess.run(['systemctl', '--user', *arguments, SERVICE], check=True,
                              capture_output=True, text=True, timeout=75).stdout.strip()

    def preflight(self):
        if self.command('show', '--property=ActiveState', '--value') != 'active':
            raise RuntimeError('The existing managed service must be active before deploying.')
        unit = ordinary(Path(self.command('show', '--property=FragmentPath', '--value')))
        if unit.stat().st_uid != os.getuid():
            raise RuntimeError('The managed service belongs to a different user.')
        lines = unit.read_text().splitlines()
        expected = ['/bin/bash', str(self.root / 'hosting/start-server.sh'), '192.168.50.80', '5501']
        starts = [shlex.split(line.split('=', 1)[1]) for line in lines if line.startswith('ExecStart=')]
        if '# Managed by FarmVillage LAN hosting (install-service.sh)' not in lines or starts != [expected]:
            raise RuntimeError('The service is not the expected Bifrost LAN service.')
        pid = int(self.command('show', '--property=MainPID', '--value'))
        process = Path('/proc') / str(pid)
        tokens = process.joinpath('cmdline').read_bytes().decode().rstrip('\0').split('\0')
        if (pid <= 1 or process.stat().st_uid != os.getuid() or
                str(self.root / 'hosting/server_runner.py') not in tokens or
                '--data-dir' not in tokens or tokens[tokens.index('--data-dir') + 1] != str(self.root / 'data')):
            raise RuntimeError('The live service does not own the expected runner and data folder.')

    def stop(self):
        self.command('stop')
        if self.command('show', '--property=ActiveState', '--value') != 'inactive' or self.command('show', '--property=MainPID', '--value') != '0':
            raise RuntimeError('The server has not finished stopping; nothing will be replaced.')

    def start(self):
        self.command('start')


@contextmanager
def exclusive(path, *, create=False):
    if not create:
        ordinary(path)
    ordinary(path.parent, directory=True)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW if not create else
                         os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RuntimeError('Lock is not an ordinary file.')
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def http_health(root, files):
    """Authenticate read-only checks in memory; never expose the secret or cookie."""
    from flask import Flask
    app = Flask('barn-deployment-health')
    app.secret_key = ordinary(root / 'data/.lan-server/session.secret').read_bytes()
    if len(app.secret_key) != 32:
        raise RuntimeError('The existing server session secret is invalid.')
    cookie = app.session_interface.get_signing_serializer(app).dumps({'_farmvillage_lan_authenticated': True})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(path, authenticated=False):
        headers = {'Cookie': 'farmvillage_lan=' + cookie} if authenticated else {}
        with opener.open(urllib.request.Request(ORIGIN + path, headers=headers), timeout=5) as response:
            if response.status != 200 or response.url != ORIGIN + path:
                raise RuntimeError('Unexpected deployment health response.')
            return response.read(8 * 1024 * 1024)

    deadline = time.monotonic() + 60
    while True:
        try:
            if b'FarmVillage' not in get('/server-login'):
                raise RuntimeError('The login page is unavailable.')
            break
        except (OSError, RuntimeError):
            if time.monotonic() >= deadline:
                raise RuntimeError('The service did not become healthy within 60 seconds.') from None
            time.sleep(1)
    audit = json.loads(files['GodBarn/data/catalog-audit.json'])
    catalog = json.loads(get('/god-barn/api/catalog?limit=1', True))
    coverage = catalog.get('coverage', {})
    if (coverage.get('total') != audit['catalogUniqueItems'] or
            coverage.get('exactArt') != audit['exactUniqueItems'] or
            coverage.get('missingArt') != audit['missingUniqueItems'] or len(catalog.get('types', [])) != 27):
        raise RuntimeError('The running Barn catalog does not match the deployed recovery.')
    for path in ('static/app.js', 'static/assets/ui/missing-art.svg'):
        if get('/god-barn/' + path, True) != files['GodBarn/' + path]:
            raise RuntimeError('The running Barn static resource does not match the deployment.')


def deploy(archive, expected=EXPECTED_SHA256, *, root=ROOT, service=None, health=http_health,
           artwork_archive=None, artwork_sha256=None):
    if bool(artwork_archive) != bool(artwork_sha256):
        raise ValueError('Provide both the artwork archive and its SHA256.')
    ordinary(root, directory=True)
    hosting, data = root / 'hosting', root / 'data'
    ordinary(hosting, directory=True)
    ordinary(data, directory=True)
    with exclusive(root / '.god-barn-deploy.lock', create=True):
        progress('Verifying the package, existing hosting checksums, and sealed game release.')
        files = archive_files(archive, expected)
        requirements = artwork_requirements(files)
        hosting_entries = verify_checksums(hosting)
        release = root / 'release' / RELEASE
        verify_checksums(release)
        service = service or Service(root)
        service.preflight()
        original_loader = ordinary(hosting / 'GodBarn/integration.py').read_bytes()
        original_sums = ordinary(hosting / 'SHA256SUMS').read_bytes()
        before = inventory(data)
        releases = hosting / 'god-barn-releases'
        if not releases.exists():
            releases.mkdir(mode=0o700)
        ordinary(releases, directory=True)
        version, destination, payload_manifest = stage_payload(
            releases, files, expected, requirements, artwork_archive, artwork_sha256)
        payload = destination / 'GodBarn'
        progress('Checking every selected image before stopping the service.')
        for index, (path, requirement) in enumerate(requirements.items(), 1):
            local = payload / path
            if local.exists() or local.is_symlink():
                available = artwork_matches(local, requirement)
            else:
                available = artwork_matches(data / 'assets' / requirement['assetPath'], requirement)
            if not available:
                raise RuntimeError('Missing or corrupt selected artwork: ' + requirement['assetPath'] +
                                   '. Re-run the Mac deployment script to prepare the Barn artwork supplement.')
            if index % 10000 == 0:
                progress('Confirmed ' + str(index) + '/' + str(len(requirements)) + ' selected images.')
        loader = loader_source(payload, version)
        entries = dict(hosting_entries)
        entries['GodBarn/integration.py'] = digest(loader)
        for name, sha in payload_manifest.items():
            entries[(destination / name).relative_to(hosting).as_posix()] = sha
        sums = ''.join(f'{value}  {name}\n' for name, value in sorted(entries.items())).encode()
        backups = root / 'backups'
        if not backups.exists():
            backups.mkdir(mode=0o700)
        ordinary(backups, directory=True)
        backup = Path(tempfile.mkdtemp(prefix='pre-god-barn-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'), dir=backups))
        (backup / 'integration.py').write_bytes(original_loader)
        (backup / 'SHA256SUMS').write_bytes(original_sums)
        (backup / 'inventory-before-stop.json').write_text(json.dumps(before, indent=2) + '\n')
        progress('Payload staged. Gracefully stopping the existing service and checking farm files.')
        stopped = None
        did_stop = False
        published = False
        try:
            service.stop()
            did_stop = True
            with exclusive(data / '.lan-server/owner.lock'):
                stopped = inventory(data)
                (backup / 'inventory-stopped.json').write_text(json.dumps(stopped, indent=2) + '\n')
                atomic_write(hosting / 'GodBarn/integration.py', loader)
                published = True
                atomic_write(hosting / 'SHA256SUMS', sums)
                verify_checksums(hosting)
                if inventory(data) != stopped:
                    raise RuntimeError('Protected farm data changed while the server was stopped.')
            progress('Starting the existing service and checking the recovered catalog without opening a farm.')
            service.start()
            health(root, files)
            after = inventory(data)
            (backup / 'inventory-after-start.json').write_text(json.dumps(after, indent=2) + '\n')
            if after != stopped:
                raise RuntimeError('Protected farm data changed after restart. Close all game tabs before retrying.')
            verify_checksums(release)
            progress('Deployed successfully. Game release checksums pass; protected farm files are unchanged.')
            progress('Barn-only rollback files and hash inventories: ' + str(backup))
            return backup
        except Exception:
            if published:
                progress('Verification failed. Restoring the previous Barn loader and checksums only.')
                service.stop()
                with exclusive(data / '.lan-server/owner.lock'):
                    atomic_write(hosting / 'GodBarn/integration.py', original_loader)
                    atomic_write(hosting / 'SHA256SUMS', original_sums)
                service.start()
            elif did_stop:
                service.start()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--expected-sha256', default=EXPECTED_SHA256)
    parser.add_argument('--audit-artwork', action='store_true',
                        help='Print missing exact artwork JSON without stopping or changing the service.')
    parser.add_argument('--artwork-archive', type=Path)
    parser.add_argument('--artwork-sha256')
    arguments = parser.parse_args()
    try:
        if arguments.audit_artwork:
            if arguments.artwork_archive or arguments.artwork_sha256:
                raise ValueError('Artwork audit does not accept a supplemental archive.')
            print(json.dumps(audit_artwork(arguments.archive, arguments.expected_sha256),
                             separators=(',', ':')))
        else:
            deploy(arguments.archive, arguments.expected_sha256,
                   artwork_archive=arguments.artwork_archive, artwork_sha256=arguments.artwork_sha256)
    except (OSError, RuntimeError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        print('[God Barn] Deployment stopped: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
