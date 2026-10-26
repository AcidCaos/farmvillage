"""Interactive player installation; imported only after showing the public plan."""
import json, os, platform, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from resource_pipeline import check_pack, plan, run, setup, target_path
from public_downloads import child

def preflight(audience):
    if sys.version_info < (3, 10):
        raise ValueError('Install Python 3.10 or newer, then reopen this installer.')
    if audience == 'mac':
        if platform.system() != 'Darwin' or tuple(int(x) for x in platform.mac_ver()[0].split('.')[:2]) < (14,):
            raise ValueError('Native Mac installation requires macOS 14 or newer.')
        result = subprocess.run(['/usr/bin/xcode-select', '-p'], check=True, capture_output=True, text=True)
        if not (Path(result.stdout.strip()) / 'usr/bin/xcodebuild').is_file():
            raise ValueError('Install full Xcode, open it once to finish setup, then select it in Xcode Settings → Locations → Command Line Tools.')
    elif platform.system() != 'Linux':
        raise ValueError('Run server setup on the Ubuntu/Linux computer that will host the game.')
    else:
        if not shutil.which('systemctl'):
            raise ValueError('The server installer needs an Ubuntu systemd user session.')
        subprocess.run(['systemctl', '--user', 'show-environment'], check=True, stdout=subprocess.DEVNULL)
    import ensurepip, venv  # Fail before large downloads if this Python lacks venv support.
    if not shutil.which('git') or not shutil.which('clang'):
        raise ValueError('Git and Clang are required. Ubuntu: sudo apt install git clang build-essential pkg-config libssl-dev python3-venv. Mac: finish Xcode setup.')
    targets = subprocess.run(['clang', '--print-targets'], check=True, capture_output=True, text=True).stdout
    if 'wasm32' not in targets:
        raise ValueError('Installed Clang must support wasm32 for the reviewed Ruffle build.')

def install(root, audience, pack, *, consent=False, open_game=True):
    pack = target_path(pack, root)
    if not consent:
        raise ValueError('Download/build consent is required')
    preflight(audience)
    setup(pack, audience, root)
    check_pack(pack, verify_art=False)  # setup already verified every artwork file.
    if audience == 'mac':
        run(['/bin/bash', root / 'FarmVillage/macOS/Scripts/build.sh', 'Release', '--resources', pack,
             '--output', pack / 'macos-build', '--python', pack / 'python/bin/python'], pack, audience=audience)
        app = pack / 'macos-build/DerivedData/Build/Products/Release/FarmVillage.app'
        if not app.is_dir():
            raise ValueError('Xcode did not produce the expected FarmVillage.app')
        print('Preparing the app engine with its bundled runtime and already extracted artwork…')
        run(['/bin/bash', app / 'Contents/Resources/Scripts/runtime.sh', 'prepare', '--runtime', app / 'Contents/Resources/Runtime',
             '--data-dir', pack / 'player-data', '--python', pack / 'python/bin/python', '--token', 'public-installer-prepare'], pack, audience=audience)
        shortcut = pack / 'PLAY_MAC.command'
        if shortcut.is_symlink():
            raise ValueError('Linked launch shortcut refused')
        shortcut.write_text('''#!/bin/bash
set -euo pipefail
FV_GAME_FOLDER="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/open -n "$FV_GAME_FOLDER/macos-build/DerivedData/Build/Products/Release/FarmVillage.app" --args --farmvillage-data-dir "$FV_GAME_FOLDER/player-data"
''')
        shortcut.chmod(0o755)
        print('Native app ready: ' + str(app))
        print('Choose Create Farm in the app. Use PLAY_MAC.command in your chosen folder later. Settings → Setup → Prepare Runtime is available for repairs.')
        if open_game:
            subprocess.run(['/usr/bin/open', '-n', str(app), '--args', '--farmvillage-data-dir', str(pack / 'player-data')], check=True)
    else:
        subprocess.run([sys.executable, '-I', '-B', str(root / 'tools/setup-wizard.py'), '--resources', str(pack)], check=True)
    return 0

def show_plan(audience):
    proposal = plan(audience)
    print('\nFarmVillage — ' + ('Mac player setup' if audience == 'mac' else 'Ubuntu server setup'))
    print('Setup downloads the original client and four original artwork archives, generates God Barn and builds the reviewed local Ruffle player.')
    print('Original artwork download: 19.13 GB (17.81 GiB). Extracted art and build tools need more space.')
    print('Keep at least %d GiB free before starting. Setup pauses at its 5 GiB reserve or %d GiB folder budget.' % (proposal['minimum_free_gib'], proposal['max_pack_gib']))
    print('These are conservative preparation budgets; the exact fresh-install peak is not yet qualified.')
    print('Downloads come from:')
    for source in proposal['sources']:
        print('  ' + source)
    print(proposal['retention'])
    print('No GitHub login, token, original owner’s Mac files or named server is needed.')
    print('Mac: macOS 14+, Python 3.10+ and installed full Xcode. Server: Ubuntu/Linux, Python with venv, Git and Clang/build tools.')
    print('Browser players visit a server address; they do not install the full archive collection.')
    return proposal

def wizard(root, audience, input_fn=input):
    while True:
        print('\n1. Install or resume installation\n2. Read the full guide\n3. Close\n4. Check source files only')
        try:
            choice = input_fn('Choose 1–4: ').strip()
        except (EOFError, KeyboardInterrupt):
            print('Installer closed. No installation was started.')
            return 0
        if choice == '3':
            return 0
        if choice == '2':
            try:
                guide = child(root, 'docs/PLAY_ON_MAC.md' if audience == 'mac' else 'docs/PLAY_ON_SERVER.md')
                if not guide.is_file():
                    raise ValueError('Guide is not an ordinary file')
                print(guide.read_text())
            except (OSError, ValueError):
                print('The guide is missing, linked or unreadable.')
        elif choice == '4':
            checker = child(root, 'tools/check-source.py')
            if not checker.is_file():
                raise ValueError('Source checker is missing')
            subprocess.run([sys.executable, '-I', '-S', '-B', str(checker), '--root', str(root)], check=True)
            print('Source check completed. No installation was started.')
        elif choice == '1':
            suggestion = Path.home() / ('FarmVillage-Mac' if audience == 'mac' else 'FarmVillage-Resources')
            text = input_fn('Dedicated resources/build folder [%s]: ' % suggestion).strip()
            pack = target_path(Path(text).expanduser() if text else suggestion, root)
            print('\nTarget: %s\nDownloads, extracted originals, Python engine and build tools will all live here. Existing unrelated folders are refused.' % pack)
            challenge = 'INSTALL ' + str(pack)
            if input_fn('To allow downloads and builds, type exactly: ' + challenge + '\n> ').strip() != challenge:
                print('Confirmation did not match. Nothing was installed.')
                continue
            return install(root, audience, pack, consent=True)
        else:
            print('Choose a displayed number. No action was taken.')
