#!/usr/bin/env python3
"""Guided, explicitly scoped clean Ubuntu/Linux install on this host."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
import webbrowser

MARKER = '.farmvillage-clean-install.json'
PRODUCT = 'org.farmvillage.bifrost.clean'
SERVICE_MARKER = '# Managed by FarmVillage clean-start wizard (setup-wizard.py)'
LEGACY_MARKER = '# Managed by FarmVillage LAN hosting (install-service.sh)'
UNIT = 'farmvillage.service'
STATE_NAMES = {'saves', 'god-barn', '.lan-server', 'workspace', 'snapshots', 'history', '.git', '.venv', '__pycache__'}

SYSTEM_TOP_LEVEL = {'bin', 'boot', 'dev', 'etc', 'lib', 'lib64', 'opt', 'proc', 'root', 'run', 'sbin', 'srv', 'sys', 'usr', 'var'}

class SetupError(ValueError):
    pass

def ordinary(path):
    path = Path(path).absolute()
    if '..' in path.parts:
        raise SetupError('Parent-directory traversal is not an installation path. Choose the exact ordinary folder.')
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise SetupError('Please use the ordinary, fully resolved folder path; linked paths are not install targets.')
    return path.resolve(strict=False)

def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def service_path(home):
    return Path(os.environ.get('XDG_CONFIG_HOME', str(home / '.config'))) / 'systemd/user' / UNIT

def service_matches(path, target):
    if path.is_symlink() or not path.is_file():
        return False
    text = path.read_text()
    marker = SERVICE_MARKER in text or LEGACY_MARKER in text
    starts = [line for line in text.splitlines() if line.startswith('ExecStart=')]
    if not marker or len(starts) != 1:
        return False
    try:
        argv = shlex.split(starts[0].split('=', 1)[1])
    except ValueError:
        return False
    legacy = len(argv) in {2, 3, 4} and Path(argv[0]).name == 'bash' and argv[1] == str(target / 'hosting/start-server.sh')
    clean = argv == [str(target / 'release/.venv/bin/python'), str(target / 'setup-wizard.py'), '--start']
    return legacy or clean

def classify_target(target, home, bundle, unit):
    home = ordinary(home)
    # A broken or root HOME (for example HOME=/ under sudo) would turn the
    # "inside your home folder" rule into "anywhere on the disk".
    if len(home.parts) < 3 or home.parts[1] in SYSTEM_TOP_LEVEL:
        raise SetupError('Your home folder (%s) is not an ordinary user home. Run the installer as the normal user who will own the game, not as root or with sudo.' % home)
    target, bundle = ordinary(target), ordinary(bundle)
    if target == home or home not in target.parents:
        raise SetupError('Choose a FarmVillage installation inside your own home folder, such as ~/farmvillage-server.')
    if not re.fullmatch(r'(?i)farm(?:ville|village)[a-z0-9._-]*', target.name):
        raise SetupError('The target folder must be clearly named farmville/farmvillage; unrelated folders are refused.')
    if target == bundle or bundle in target.parents or target in bundle.parents:
        raise SetupError('The installer/source bundle must stay outside the installation being replaced.')
    if any((target / name).exists() for name in ['.git', 'server.py', 'FarmVillage', 'macOS']):
        raise SetupError('That looks like a source checkout. Source folders are never wipe targets.')
    if not target.exists() or (target.is_dir() and not any(target.iterdir())):
        return 'new'
    if not target.is_dir():
        raise SetupError('The installation target must be a directory.')
    marker = target / MARKER
    if marker.is_file() and not marker.is_symlink():
        try:
            d = json.loads(marker.read_text())
        except (ValueError, OSError) as error:
            raise SetupError('The managed-install marker is damaged; nothing was erased.') from error
        if d.get('product') == PRODUCT and d.get('target') == str(target) and d.get('schema') == 1:
            return 'managed'
    runner = target / 'hosting/server_runner.py'
    legacy = runner.is_file() and not runner.is_symlink() and (target / 'data').is_dir()
    if legacy:
        code = runner.read_text(errors='replace')
        legacy = all(token in code for token in ['_farmvillage_lan_authenticated', 'def data_ownership(', 'def register_lan_access('])
    releases = list((target / 'release').glob('farmvillage-portable-preparation-*/Runtime/server.py'))
    if legacy and releases and service_matches(unit, target):
        ordinary(target / 'hosting/server_runner.py')
        ordinary(target / 'data')
        return 'legacy-managed'
    raise SetupError('This is not a positively identified managed FarmVillage install. No files were erased. Choose a new empty ~/farmvillage-server folder or the actual managed installation.')

def verify_payload(bundle):
    manifest_path = bundle / 'PRIVATE_RELEASE_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('schema') != 1 or not manifest.get('files'):
        raise SetupError('The private bundle manifest is missing or unsupported.')
    for name, info in manifest['files'].items():
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or any(x in STATE_NAMES for x in p.parts):
            raise SetupError('Player state or an unsafe path appears in the release bundle: ' + name)
        source = ordinary(bundle / name)
        if not source.is_file() or source.stat().st_size != info['bytes'] or file_hash(source) != info['sha256']:
            raise SetupError('Bundle input failed verification: ' + name)
    for required in ['Runtime/server.py', 'BackendHost/native_paths.py', 'hosting/server_runner.py']:
        if required not in manifest['files']:
            raise SetupError('The release is incomplete: ' + required)
    return manifest

def validate_assets(path):
    path = ordinary(path)
    if not path.is_dir() or not all((path / name).is_dir() for name in ['Environment', 'xpromoSupport']):
        raise SetupError('Choose the extracted assets folder containing Environment/ and xpromoSupport/. A WARC archive or game source folder is not the extracted art.')
    total = 0
    for p in path.rglob('*'):
        if p.is_symlink():
            raise SetupError('Linked artwork inputs are refused. Choose the ordinary extracted assets folder.')
        if any(x in STATE_NAMES for x in p.relative_to(path).parts):
            raise SetupError('The art input contains player state; select only the extracted assets folder.')
        if p.is_file():
            total += p.stat().st_size
    return total

@contextmanager
def unlocked_old_data(target):
    lock = target / 'data/.lan-server/owner.lock'
    if not lock.exists():
        yield
        return
    ordinary(lock)
    descriptor = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SetupError('A game process still owns this installation. Stop that managed game before continuing; no files were erased.') from error
        yield
    finally:
        os.close(descriptor)

def copy_clean_payload(bundle, stage, assets, manifest):
    release = stage / 'release'
    release.mkdir()
    for name in manifest['files']:
        source = ordinary(bundle / name)
        destination = release / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    shutil.copyfile(bundle / 'PRIVATE_RELEASE_MANIFEST.json', release / 'PRIVATE_RELEASE_MANIFEST.json')
    data = stage / 'data'
    data.mkdir()
    total_files = sum(1 for p in assets.rglob('*') if p.is_file())
    copied, copied_bytes, last_report = 0, 0, time.monotonic()
    def copy_art(source, destination):
        nonlocal copied, copied_bytes, last_report
        shutil.copyfile(source, destination)
        copied += 1
        copied_bytes += Path(source).stat().st_size
        now = time.monotonic()
        if copied % 200 == 0 or now - last_report >= 3 or copied == total_files:
            print('Artwork: %d/%d files copied, %.1f MiB staged.' % (copied, total_files, copied_bytes / 1024 ** 2), flush=True)
            last_report = now
        return destination
    shutil.copytree(assets, data / 'assets', copy_function=copy_art)
    if any((data / name).exists() for name in STATE_NAMES):
        raise SetupError('An old state directory entered the clean stage; installation refused.')

def publish_clean_stage(stage, target, home, bundle, unit, configuration, confirmation):
    kind = classify_target(target, home, bundle, unit)
    challenge = 'WIPE ' + str(target)
    if confirmation != challenge:
        raise SetupError('The confirmation did not match the named target. Nothing was erased.')
    if stage.parent != target.parent or stage == target or not stage.name.startswith('.farmvillage-stage-'):
        raise SetupError('The prepared stage is not an owned sibling of this installation.')
    ordinary(stage)
    marker = {'schema': 1, 'product': PRODUCT, 'target': str(target), 'cleanStart': True,
              'activeWorlds': 16, 'retiredWorlds': ['glen', 'hlights'], **configuration}
    (stage / MARKER).write_text(json.dumps(marker, indent=2) + '\n')
    with unlocked_old_data(target):
        # Revalidate immediately before the scoped deletion. No sibling, source,
        # asset-input or system directory is a deletion operand.
        classify_target(target, home, bundle, unit)
        if target.exists():
            shutil.rmtree(target)
        stage.rename(target)
    return kind

def private_python_environment():
    environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'LC_CTYPE', 'HOME') if key in os.environ}
    environment['NETRC'] = os.devnull
    environment['PIP_CONFIG_FILE'] = os.devnull
    return environment

def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)

def command_for(target, marker):
    return [str(target / 'release/.venv/bin/python'), '-B', '-u', str(target / 'release/hosting/server_runner.py'),
            '--runtime', str(target / 'release/Runtime'), '--backend-host', str(target / 'release/BackendHost'),
            '--data-dir', str(target / 'data'), '--bind', marker['bind'], '--port', str(marker['port']),
            '--public-url', marker['origin']]

def start_installed(target):
    target = ordinary(target)
    marker = json.loads((target / MARKER).read_text())
    if marker.get('product') != PRODUCT or marker.get('target') != str(target):
        raise SetupError('This is not a matching managed clean installation.')
    verify_payload(target / 'release')
    command = command_for(target, marker)
    os.execve(command[0], command, private_python_environment())

def check_origin(origin, attempts=90, sleeper=time.sleep):
    for _ in range(attempts):
        try:
            with urlopen(origin + '/server-login', timeout=2) as response:
                text = response.read(32768)
                if response.status == 200 and b'FarmVillage' in text and b'password' in text.lower():
                    return True
        except OSError:
            pass
        sleeper(1)
    raise SetupError('The game has not reached its sign-in page yet. Use the guided retry command printed below; your fresh install remains in place.')

def say(step, title, message):
    print('\nStep %d of 8 — %s\n%s\n' % (step, title, message), flush=True)

def ask(prompt, default=None):
    value = input(prompt + ((' [' + str(default) + ']') if default is not None else '') + ': ').strip()
    return value or (str(default) if default is not None else '')

PUBLIC_RESOURCES = None

def choose_bundle():
    if PUBLIC_RESOURCES is not None:
        root = Path(__file__).resolve().parents[1]
        output = PUBLIC_RESOURCES / 'browser-release'
        if output.exists():
            verify_payload(output)
            return output, None
        run([sys.executable, '-I', '-B', str(root / 'tools/prepare-browser-runtime.py'), '--output', str(output), '--resources', str(PUBLIC_RESOURCES)])
        return output, None
    here = Path(__file__).resolve().parent
    if (here / 'PRIVATE_RELEASE_MANIFEST.json').is_file():
        return here, None
    root = here.parent
    if not (root / 'FarmVillage/server.py').is_file():
        raise SetupError('Run the wizard from a complete prepared release bundle or the source checkout. See docs/PLAY_ON_SERVER.md for server setup requirements.')
    checker = [sys.executable, '-I', '-S', '-B', str(root / 'tools/private-inputs.py')]
    if subprocess.run([*checker, 'check'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        raise SetupError(
            'No prepared resource pack was selected. Run bash START_HERE.sh to download '
            'and prepare public originals, then continue this installer automatically. '
            'See docs/PLAY_ON_SERVER.md. This direct advanced entry stopped before '
            'staging or installation; no files were downloaded.'
        )
    temporary = tempfile.TemporaryDirectory(prefix='farmvillage-bundle-')
    output = Path(temporary.name).resolve() / 'payload'
    run([sys.executable, '-B', str(root / 'tools/prepare-browser-runtime.py'), '--output', str(output)])
    return output, temporary

def preflight():
    if platform.system() != 'Linux':
        raise SetupError('Run this installer on the Ubuntu/Linux game host itself. It does not deploy remotely. macOS uses the native desktop app described in README.md.')
    if os.geteuid() == 0:
        raise SetupError('Please run as your normal Ubuntu user, without sudo. The wizard asks separately if a boot-setting step needs it.')
    if sys.version_info < (3, 10):
        raise SetupError('Python 3.10 or newer is needed. Install python3 and python3-venv, then rerun this same wizard.')
    for command in ['systemctl', 'loginctl']:
        if not shutil.which(command):
            raise SetupError('Ubuntu is missing %s. Use a normal systemd Ubuntu login, install the missing prerequisite, then rerun the wizard.' % command)
    result = subprocess.run(['systemctl', '--user', 'show-environment'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode:
        raise SetupError('The Ubuntu user service session is unavailable. Log in normally as the installation owner (not through sudo), then rerun the wizard.')
    with tempfile.TemporaryDirectory(prefix='farmvillage-python-check-') as temporary:
        run([sys.executable, '-I', '-B', '-m', 'venv', str(Path(temporary) / 'environment')], env=private_python_environment())

def validate_network(bind, port):
    import ipaddress
    try:
        address = ipaddress.IPv4Address(bind)
    except ipaddress.AddressValueError as error:
        raise SetupError('That is not an IPv4 address. Choose a detected number or the private address shown by hostname -I. Nothing was erased.') from error
    networks = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '127.0.0.0/8']
    if not any(address in ipaddress.IPv4Network(n) for n in networks) or not 1 <= port <= 65535:
        raise SetupError('Choose a private/loopback IPv4 address and a port from 1 to 65535. Public/wildcard listening stays disabled.')
    return 'http://%s:%d' % (address, port)

def network_choices():
    addresses = []
    if shutil.which('hostname'):
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        if result.returncode == 0:
            for value in result.stdout.split():
                try:
                    validate_network(value, 5501)
                except (SetupError, ValueError):
                    continue
                if not value.startswith('127.') and value not in addresses:
                    addresses.append(value)
    return addresses + ['127.0.0.1']

def choose_network():
    choices = network_choices()
    print('Where will you open the game?')
    for index, address in enumerate(choices, 1):
        label = 'Only this Ubuntu computer' if address.startswith('127.') else 'Open from another computer on your private network'
        print('  %d. %s — %s' % (index, address, label))
    if len(choices) == 1:
        print('No private network address was detected. Loopback works only on this computer. For another computer, run hostname -I here, then enter its private IPv4 address below.')
    selection = ask('Choose an address number, or enter a private IPv4 address', '1')
    if selection.isdigit():
        if not 1 <= int(selection) <= len(choices):
            raise SetupError('Choose one of the displayed numbers, or rerun and enter your private IPv4 address.')
        bind = choices[int(selection) - 1]
    else:
        bind = selection
    try:
        port = int(ask('Game port', 5501))
    except ValueError as error:
        raise SetupError('Use a numeric game port; nothing was erased.') from error
    origin = validate_network(bind, port)
    print('Browser address preview: ' + origin + '/new.html')
    return bind, port, origin

def unit_contents(target):
    # The target is constrained to the user's managed home folder. Quote the
    # complete executable path, retaining spaces in a legitimate home directory.
    script = str(target / 'setup-wizard.py').replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    return '\n'.join([SERVICE_MARKER, '[Unit]', 'Description=FarmVillage clean-start game', 'After=network.target', '', '[Service]', 'Type=simple', 'ExecStart="' + str(target / 'release/.venv/bin/python').replace('%', '%%') + '" "' + script + '" --start', 'Restart=on-failure', 'RestartSec=3', 'TimeoutStopSec=45', 'UMask=0077', '', '[Install]', 'WantedBy=default.target', ''])

def verify_loaded_service(unit):
    result = subprocess.run(['systemctl', '--user', 'show', UNIT, '--property=FragmentPath', '--value'], capture_output=True, text=True)
    loaded = result.stdout.strip()
    if loaded and ordinary(loaded) != ordinary(unit):
        raise SetupError('A different service is loaded under farmvillage.service from ' + loaded + '. It was not stopped or replaced.')

def install_user_service(target, unit):
    verify_loaded_service(unit)
    if unit.exists() and not service_matches(unit, target):
        raise SetupError('An unrelated service unit appeared. It was left untouched.')
    unit.parent.mkdir(parents=True, exist_ok=True)
    ordinary(unit)
    unit.write_text(unit_contents(target))
    unit.chmod(0o600)
    run(['systemctl', '--user', 'daemon-reload'])
    run(['systemctl', '--user', 'enable', '--now', UNIT])

def wizard():
    os.umask(0o077)
    print('\nFarmVillage — a fresh field for sixteen worlds\n')
    print('We will build a clean home for the game, then create your first farm. Old farms, snapshots, history and sign-in state in the named managed installation will be erased. Enchanted Glen and Holiday Lights are retired. iPad development remains abandoned.')
    say(1, 'Check the tools', 'First, a quick check of this Ubuntu login, Python and user services. No game data is changed.')
    preflight()
    bundle, temporary_bundle = choose_bundle()
    stage = None
    try:
        manifest = verify_payload(bundle)
        home = Path.home().resolve()
        unit = service_path(home)
        say(2, 'Choose the home for the game', 'The recommended managed folder is shown below. Source, system, unrelated and linked folders are never erased. Extract this installer outside that target.')
        target = ordinary(Path(ask('Installation folder', home / 'farmvillage-server')).expanduser())
        kind = classify_target(target, home, bundle, unit)
        if unit.exists() and not service_matches(unit, target):
            raise SetupError('An unrelated farmvillage.service already exists. It was not stopped or replaced. Choose the actual managed target or resolve that service before rerunning.')
        verify_loaded_service(unit)
        print('Installation target: %s\nIdentified as: %s' % (target, kind))
        bind, port, origin = choose_network()
        say(3, 'Bring the artwork', 'Choose only the extracted assets folder. If it is inside the old installation, we will stage the art outside the wipe first. Old saves and passwords are never copied.')
        default_assets = PUBLIC_RESOURCES / 'assets' if PUBLIC_RESOURCES is not None else target / 'data/assets'
        if not default_assets.is_dir():
            default_assets = None
        assets = ordinary(Path(ask('Extracted assets folder (contains Environment and xpromoSupport)', default_assets)).expanduser())
        art_bytes = validate_assets(assets)
        target.parent.mkdir(parents=True, exist_ok=True)
        required = art_bytes + sum(x['bytes'] for x in manifest['files'].values()) + 1024 ** 3
        if shutil.disk_usage(target.parent).free < required:
            raise SetupError('There is not enough free space to stage the fresh game and artwork safely. Free at least %.1f GiB and rerun; nothing was erased.' % (required / 1024 ** 3))
        say(4, 'Name the clean slate', 'Here is the whole wipe target, not just a save file:\n  %s\nEvery old farm, snapshot, history, runtime environment and authentication file inside it will be removed. Only the selected artwork is staged as an input. Nothing outside this target will be erased.' % target)
        challenge = 'WIPE ' + str(target)
        confirmation = ask('To continue, type exactly: ' + challenge)
        if confirmation != challenge:
            raise SetupError('That did not match. The old installation is untouched. Run the wizard again when you are ready.')
        say(5, 'Make room for a new season', 'We are staging the verified release and artwork first. Then we stop only the matching managed service, check its data lock, and publish the clean installation.')
        stage = Path(tempfile.mkdtemp(prefix='.farmvillage-stage-', dir=target.parent))
        copy_clean_payload(bundle, stage, assets, manifest)
        shutil.copyfile(Path(__file__).resolve(), stage / 'setup-wizard.py')
        if unit.exists():
            verify_loaded_service(unit)
            if not service_matches(unit, target):
                raise SetupError('The service identity changed. It was left untouched; no wipe was performed.')
            run(['systemctl', '--user', 'stop', UNIT])
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(1)
            if probe.connect_ex((bind, port)) == 0:
                raise SetupError('Another process is using the chosen address/port. It was left alone. Choose an unused port or stop the matching game, then rerun.')
        config = {'bind': bind, 'port': port, 'origin': origin, 'service': UNIT}
        publish_clean_stage(stage, target, home, bundle, unit, config, confirmation)
        stage = None
        say(6, 'Prepare the fresh engine', 'The old state is now gone. We are creating a new Python environment and installing the five pinned dependencies. This step may use the network; it downloads no game artwork.')
        environment = target / 'release/.venv'
        python_env = private_python_environment()
        package_home = ordinary(target / 'data/cache/package-home')
        package_home.mkdir(parents=True, exist_ok=True)
        python_env['HOME'] = str(package_home)
        python_env['XDG_CACHE_HOME'] = str(package_home / '.cache')
        run([sys.executable, '-I', '-B', '-m', 'venv', str(environment)], env=python_env)
        run([str(environment / 'bin/python'), '-I', '-B', '-m', 'pip', '--isolated', 'install', '--disable-pip-version-check', '--no-input', '--require-virtualenv', '--prefer-binary', '--index-url', 'https://pypi.org/simple', '--cache-dir', str(target / 'data/cache/pip'), '-r', str(target / 'release/Runtime/requirements.txt')], env=python_env)
        say(7, 'Choose a new key to the gate', 'Create a new browser password below. It is entered privately and is never put in command arguments, logs or this package. No old password or session is restored.')
        marker = json.loads((target / MARKER).read_text())
        run([*command_for(target, marker), '--init-only'], env=private_python_environment())
        say(8, 'Open the gate', 'We will start the managed user service, check its sign-in page and show the exact browser address. Sign in there and choose Create a new farm.')
        install_user_service(target, unit)
        check_origin(origin)
        boot = ask('Keep the farm service running after logout and at boot? Y/n', 'Y').lower()
        if boot in {'y', 'yes'}:
            print('Ubuntu may ask for your sudo password for this user boot setting.')
            import pwd
            run(['sudo', 'loginctl', 'enable-linger', pwd.getpwuid(os.getuid()).pw_name])
        print('\nThe clean game is ready: %s/new.html\nSign in with the new password, then create your first farm.\nSixteen supported worlds; no previous farms or sign-ins were carried over.' % origin)
        webbrowser.open(origin + '/new.html')
        print('\nUseful controls (no path editing needed):\n  systemctl --user status farmvillage.service\n  systemctl --user restart farmvillage.service\n  journalctl --user -u farmvillage.service -n 50 --no-pager\nTo perform another explicit clean install, run this same wizard again.')
        return target
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        if temporary_bundle is not None:
            temporary_bundle.cleanup()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', action='store_true', help='Start only this already installed managed game (used by its service)')
    parser.add_argument('--resources', type=Path, help='Verified public pack from the resource wizard')
    arguments = parser.parse_args()
    try:
        if arguments.resources is not None:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from resource_pipeline import check_pack, target_path
            PUBLIC_RESOURCES = target_path(arguments.resources)
            check_pack(PUBLIC_RESOURCES)

        if arguments.start:
            start_installed(Path(__file__).resolve().parent)
        else:
            wizard()
    except (SetupError, OSError, subprocess.CalledProcessError, EOFError, KeyboardInterrupt) as error:
        print('\nSetup paused: %s\nNo unrelated folder or server was changed. If the clean install had already been published, its old player state was intentionally erased. Correct the named issue and run the same wizard again; the installed marker will identify that managed target.\n' % error, file=sys.stderr)
        raise SystemExit(1)
