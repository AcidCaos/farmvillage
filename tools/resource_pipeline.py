"""Public resource pack assembly; all generated files stay in one explicitly owned pack."""
from __future__ import annotations
import gzip, hashlib, importlib.util, io, json, os
from pathlib import Path
import shutil, signal, sqlite3, subprocess, sys, time
from urllib.parse import unquote, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parent))
from public_downloads import child, download, identity, ordinary
ROOT = Path(__file__).resolve().parents[1]
MARKER = '.farmvillage-public-resources.json'
GIB = 1024 ** 3

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

def write_json(path, value):
    path = ordinary(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ordinary(path.with_name(path.name + '.new'))
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)

def target_path(value, source=ROOT):
    target, source = ordinary(value), ordinary(source)
    forbidden = {Path('/'), Path.home(), Path('/Users'), Path('/home'), Path('/tmp'), Path('/private/tmp')}
    if target in forbidden or len(target.parts) < 4 or target == source or source in target.parents or target in source.parents:
        raise ValueError('Choose a dedicated NEW resource folder outside the source checkout and system folders')
    if target.parts[1] in ('System', 'bin', 'sbin', 'usr', 'etc', 'dev', 'proc', 'var'):
        raise ValueError('System resource targets are refused')
    if target.exists():
        if not target.is_dir():
            raise ValueError('The selected target is not a directory')
        marker = child(target, MARKER)
        if not marker.is_file():
            if any(target.iterdir()):
                raise ValueError('Existing unrelated folder refused; choose a new folder')
        else:
            record = json.loads(marker.read_text())
            if record != {'schema': 1, 'product': 'farmvillage-public-resources', 'target': str(target)}:
                raise ValueError('Resource folder ownership marker does not match its path')
    return target

def own_target(target, source=ROOT):
    target = target_path(target, source)
    target.mkdir(parents=True, exist_ok=True)
    write_json(child(target, MARKER), {'schema': 1, 'product': 'farmvillage-public-resources', 'target': str(target)})
    return target

def plan(audience, manifest=None):
    manifest = manifest or json.loads((ROOT / 'tools/public-resources.json').read_text())
    return {'schema': 1, 'audience': audience, 'archive_bytes': sum(x['bytes'] for x in manifest['archives']),
        'original_file_bytes': sum(x['bytes'] for x in manifest['upstream']['files']),
        'archive_count': len(manifest['archives']), 'minimum_free_gib': 110 if audience == 'mac' else 80,
        'reserve_gib': 5, 'max_pack_gib': 100 if audience == 'mac' else 70,
        'sources': ['raw.githubusercontent.com/AcidCaos/farmvillage at ' + manifest['upstream']['revision'], manifest['archiveBase'],
                    'pypi.org and files.pythonhosted.org (pinned Python packages)',
                    'github.com/ruffle-rs and public submodules, static.rust-lang.org, nodejs.org, registry.npmjs.org, crates.io and Eclipse Adoptium Java (pinned build inputs)',
                    'github.com/jindrapetrik FFDec (Mac UI/font extraction tools only)'],
        'builds': 'Pinned reviewed Ruffle from source; Mac additionally builds the native app with installed full Xcode.',
        'retention': 'One WARC at a time; verified WARC removed after extraction. Partial downloads and stages survive retry. Tools remain in the chosen folder until explicit cleanup.',
        'qualification': 'Exact fresh-install peak and native/Ubuntu gameplay have not been measured for this public pipeline.'}

def environment(pack):
    home, temp = child(pack, 'work/home'), child(pack, 'work/tmp')
    home.mkdir(parents=True, exist_ok=True)
    temp.mkdir(parents=True, exist_ok=True)
    env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ', 'DEVELOPER_DIR') if k in os.environ}
    env.update(HOME=str(home), TMPDIR=str(temp), TEMP=str(temp), TMP=str(temp), XDG_CACHE_HOME=str(home / '.cache'), NETRC=os.devnull,
        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0', PIP_CONFIG_FILE=os.devnull,
        PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PIP_CACHE_DIR=str(home / '.cache/pip'))
    return env

def tree_bytes(root):
    return sum((Path(base) / name).stat().st_size for base, dirs, files in os.walk(root, followlinks=False) for name in files if not (Path(base) / name).is_symlink())

def run(command, pack, *, audience='server', runner=None):
    print('\nRunning ' + ' '.join(str(x) for x in command), flush=True)
    if runner is not None:
        return runner([str(x) for x in command], env=environment(pack), check=True)
    process = subprocess.Popen([str(x) for x in command], env=environment(pack), start_new_session=True)
    last_size = 0.0
    try:
        while process.poll() is None:
            if shutil.disk_usage(pack).free < 5 * GIB:
                raise OSError('Five GiB storage reserve reached; setup paused for retry')
            if time.monotonic() - last_size > 20:
                if tree_bytes(pack) > (100 if audience == 'mac' else 70) * GIB:
                    raise OSError('Chosen folder storage budget reached; setup paused')
                last_size = time.monotonic()
            time.sleep(.25)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        raise

def headers(stream):
    result, size = {}, 0
    while True:
        line = stream.readline(65537)
        size += len(line)
        if size > 65536:
            raise ValueError('Archive header exceeds bounds')
        if line in (b'\r\n', b'\n', b''):
            return result
        key, separator, value = line.partition(b':')
        if not separator:
            raise ValueError('Malformed archive header')
        result[key.decode('ascii').lower()] = value.strip().decode('utf-8')

def art_name(url):
    parsed = urlsplit(url)
    prefix = '/farmville/assets/hashed/assets/'
    if parsed.hostname != 'zynga1-a.akamaihd.net' or not parsed.path.startswith(prefix):
        return None
    name = unquote(parsed.path[len(prefix):])
    child(Path('/safe/assets'), name)
    if ':' in name or '\x00' in name:
        raise ValueError('Unsafe artwork name')
    return name

def extract_archive(archive, pack, *, reserve=5 * GIB):
    assets = child(pack, 'assets')
    assets.mkdir(exist_ok=True)
    count = 0
    with sqlite3.connect(child(pack, 'artwork.sqlite3')) as db, gzip.open(archive, 'rb') as stream:
        db.execute('CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, bytes INTEGER, sha256 TEXT)')
        while True:
            line = stream.readline(65537)
            if not line:
                break
            if line in (b'\n', b'\r\n'):
                continue
            if not line.startswith(b'WARC/1.'):
                raise ValueError('Malformed WARC version')
            meta = headers(stream)
            length = int(meta.get('content-length', '-1'))
            if not 0 <= length <= 128 * 1024**2:
                raise ValueError('WARC record exceeds the 128 MiB safety bound')
            name = art_name(meta.get('warc-target-uri', '')) if meta.get('warc-type') == 'response' else None
            if name is None:
                remaining = length
                while remaining:
                    block = stream.read(min(1 << 20, remaining))
                    if not block:
                        raise ValueError('Truncated WARC')
                    remaining -= len(block)
                continue
            raw = stream.read(length)
            if len(raw) != length:
                raise ValueError('Truncated WARC record')
            content = io.BytesIO(raw)
            status = content.readline(65537).split()
            http = headers(content)
            if len(status) < 2 or status[1] != b'200':
                continue
            body = content.read()
            if http.get('transfer-encoding', '').lower() == 'chunked':
                decoded, chunks = bytearray(), io.BytesIO(body)
                while True:
                    size = int(chunks.readline(256).split(b';')[0].strip(), 16)
                    if not size:
                        break
                    if size > 128 * 1024**2 or len(decoded) + size > 128 * 1024**2:
                        raise ValueError('Oversized HTTP chunk body')
                    block = chunks.read(size)
                    if len(block) != size or chunks.read(2) != b'\r\n':
                        raise ValueError('Truncated HTTP chunk')
                    decoded.extend(block)
                body = bytes(decoded)
            if http.get('content-encoding') == 'gzip':
                with gzip.GzipFile(fileobj=io.BytesIO(body)) as decoded:
                    body = decoded.read(128 * 1024**2 + 1)
                if len(body) > 128 * 1024**2:
                    raise ValueError('Expanded HTTP body exceeds bounds')
            output = child(assets, name)
            output.parent.mkdir(parents=True, exist_ok=True)
            if shutil.disk_usage(pack).free < reserve + len(body):
                raise OSError('Storage reserve reached during artwork extraction')
            sha = hashlib.sha256(body).hexdigest()
            if not identity(output, {'bytes': len(body), 'sha256': sha}):
                temporary = child(assets, name + '.extracting')
                temporary.write_bytes(body)
                temporary.replace(output)
            db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)', (name, len(body), sha))
            count += 1
            if count % 1000 == 0:
                db.commit()
                print('Artwork: %d records extracted from %s' % (count, archive.name), flush=True)
        db.commit()
    return count

def export_art_manifest(pack):
    with sqlite3.connect(child(pack, 'artwork.sqlite3')) as db, child(pack, 'assets-manifest.jsonl').open('w') as output:
        for name, size, sha in db.execute('SELECT path,bytes,sha256 FROM files ORDER BY path'):
            output.write(json.dumps({'path': name, 'bytes': size, 'sha256': sha}, separators=(',', ':')) + '\n')
    for name in ('Environment', 'xpromoSupport'):
        if not child(pack, 'assets/' + name).is_dir():
            raise ValueError('Original artwork is incomplete: missing ' + name)

def assemble_runtime(source, pack, python):
    game, runtime = source / 'FarmVillage', child(pack, 'Runtime')
    runtime.mkdir(exist_ok=True)
    for item in sorted(game.glob('*.py')):
        shutil.copyfile(ordinary(item), child(runtime, item.name))
    for name in ('requirements.txt', 'LICENSE', 'README.md', 'FLASH.md'):
        shutil.copyfile(ordinary(game / name), child(runtime, name))
    for name in ('assethash', 'embeds', 'patched', 'templates', 'villages', 'xml', 'warc_extractor'):
        for base in (game, child(pack, 'original')):
            directory = ordinary(base / name)
            if directory.is_dir():
                for item in directory.rglob('*'):
                    ordinary(item)
                    if item.is_file() and '__pycache__' not in item.parts and item.name != '.DS_Store':
                        out = child(runtime, item.relative_to(base).as_posix())
                        out.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(item, out)
    run([python, '-I', '-B', source / 'FarmVillage/macOS/Scripts/patch-game-client.py',
         pack / 'original/embeds/Flash/v855097-855094/FarmGame.swf', runtime / 'embeds/Flash/v855097-855094/FarmGame.swf'], pack)
    companion = runtime / 'GodBarn'
    if companion.exists():
        shutil.rmtree(child(pack, 'Runtime/GodBarn'))
    run([python, '-I', '-B', source / 'GodBarn/scripts/bundle_companion.py', source / 'GodBarn', companion, '--resources', pack / 'godbarn'], pack)
    return runtime

def seal(pack, audience):
    files = {}
    for group in ('Runtime', 'native'):
        folder = child(pack, group)
        if folder.is_dir():
            for item in sorted(folder.rglob('*')):
                ordinary(item)
                if item.is_file():
                    files[item.relative_to(pack).as_posix()] = {'bytes': item.stat().st_size, 'sha256': digest(item)}
    manifest = child(pack, 'assets-manifest.jsonl')
    files['assets-manifest.jsonl'] = {'bytes': manifest.stat().st_size, 'sha256': digest(manifest)}
    state = {'schema': 1, 'status': 'complete', 'audience': audience, 'files': files,
             'active_worlds': 16, 'retired_worlds': ['glen', 'hlights'], 'source_manifest_sha256': digest(ROOT / 'SOURCE_MANIFEST.json')}
    write_json(child(pack, 'resource-state.json'), state)
    return state

def check_pack(pack, *, verify_art=True):
    pack = target_path(pack)
    state = json.loads(child(pack, 'resource-state.json').read_text())
    if state.get('schema') != 1 or state.get('status') != 'complete' or not state.get('files'):
        raise ValueError('Resource pack has no complete seal')
    if state.get('source_manifest_sha256') != digest(ROOT / 'SOURCE_MANIFEST.json'):
        raise ValueError('Resource pack was prepared from a different source release; use its matching source checkout')
    actual = {item.relative_to(pack).as_posix() for group in ('Runtime', 'native') for item in child(pack, group).rglob('*') if item.is_file() or item.is_symlink()}
    expected = {name for name in state['files'] if name.startswith(('Runtime/', 'native/'))}
    if actual != expected:
        raise ValueError('Resource runtime contains missing or unlisted files')
    for name, entry in state['files'].items():
        if not identity(child(pack, name), entry):
            raise ValueError('Resource pack differs: ' + name)
    if verify_art:
        with child(pack, 'assets-manifest.jsonl').open() as stream:
            for line in stream:
                entry = json.loads(line)
                if not identity(child(pack, 'assets/' + entry['path']), entry):
                    raise ValueError('Artwork differs: ' + entry['path'])
    return state

def setup(pack, audience, source=ROOT):
    specification = json.loads((source / 'tools/public-resources.json').read_text())
    proposal = plan(audience, specification)
    pack = own_target(pack, source)
    with child(pack, '.setup.lock').open('a+') as lock:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (pack / 'resource-state.json').is_file():
            state = check_pack(pack)
            if audience == 'server' or state['audience'] == 'mac':
                print('Complete resource pack verified. No downloads needed.')
                return pack
        if shutil.disk_usage(pack).free < proposal['minimum_free_gib'] * GIB:
            raise OSError('Keep at least %d GiB free before starting; no downloads were made.' % proposal['minimum_free_gib'])
        originals = child(pack, 'original')
        print('\n1/6 — Download the pinned original client and configuration', flush=True)
        for entry in specification['upstream']['files']:
            download('https://raw.githubusercontent.com/AcidCaos/farmvillage/' + specification['upstream']['revision'] + '/' + entry['path'], child(originals, entry['path']), entry)
        print('\n2/6 — Download and extract the four original artwork archives, one at a time', flush=True)
        receipts = child(pack, 'archive-receipts.json')
        done = json.loads(receipts.read_text()) if receipts.is_file() else {}
        for entry in specification['archives']:
            if done.get(entry['name']) == entry:
                print('Extraction already complete: ' + entry['name'], flush=True)
                continue
            archive = download(specification['archiveBase'] + entry['name'], child(pack, 'downloads/' + entry['name']), entry)
            extract_archive(archive, pack)
            done[entry['name']] = entry
            write_json(receipts, done)
            archive.unlink()
            print('Verified archive extracted; WARC removed to save space.', flush=True)
        export_art_manifest(pack)
        print('\n3/6 — Prepare a private Python engine and generate companion metadata', flush=True)
        venv = child(pack, 'python')
        if not (venv / 'bin/python').is_file():
            run([sys.executable, '-I', '-B', '-m', 'venv', '--copies', venv], pack, audience=audience)
        python = venv / 'bin/python'
        run([python, '-I', '-B', '-m', 'pip', '--isolated', 'install', '--disable-pip-version-check', '--no-input', '--require-virtualenv', '--index-url', 'https://pypi.org/simple', '-r', source / 'tools/preparation-requirements.txt'], pack, audience=audience)
        if not (pack / 'godbarn').is_dir():
            run([python, '-I', '-B', source / 'GodBarn/scripts/bootstrap_resources.py', '--game-root', originals, '--assets-root', pack / 'assets', '--policy-root', source / 'FarmVillage', '--output', pack / 'godbarn'], pack, audience=audience)
        run([python, '-I', '-B', source / 'GodBarn/scripts/verify_resources.py', '--resources', pack / 'godbarn', '--game-root', originals, '--expected-records', '111206'], pack, audience=audience)
        runtime = assemble_runtime(source, pack, python)
        print('\n4/6 — Build the reviewed local Ruffle player from pinned public source', flush=True)
        runtime_out = runtime / 'ruffle_runtime/0.7.1-farmvillage-gc1'
        run([python, '-I', '-B', source / 'tools/build-public-ruffle.py', '--work', pack / 'work/ruffle', '--output', runtime_out], pack, audience=audience)
        spec = importlib.util.spec_from_file_location('public_runtime_compatibility', source / 'FarmVillage/runtime_compatibility.py')
        compat = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = compat
        spec.loader.exec_module(compat)
        receipt = runtime_out.parent / (runtime_out.name + '.build-receipt.json')
        pin = compat.prepare_public_runtime(runtime, receipt, receipt_sha256=digest(receipt))
        write_json(runtime / 'PREPARED_RUNTIME.json', {'schema': 1, 'runtime_manifest_sha256': pin})
        shutil.copyfile(receipt, runtime / 'PUBLIC_RUNTIME_BUILD.json')
        print('\n5/6 — Prepare the native interface' if audience == 'mac' else '\n5/6 — Browser runtime assembled', flush=True)
        if audience == 'mac':
            run([python, '-I', '-B', source / 'tools/native_resources.py', '--resources', pack, '--original', originals, '--assets', pack / 'assets', '--python', python], pack, audience=audience)
        print('\n6/6 — Seal resources and verify every generated file', flush=True)
        if audience == 'mac':
            write_json(runtime / 'PUBLIC_INSTALL.json', {'schema': 1, 'assets_root': str(pack / 'assets')})
        seal(pack, audience)
        check_pack(pack)
        return pack
