"""Explicitly isolated Session A browser fixture; synthetic saves only.

Prepare a fresh /private/tmp root using --prepare --source CHECKOUT --assets ART.
Then run this helper with --root ROOT using the checkout's Python environment.
The browser uses 1280x800 landscape; one live client per synthetic profile.
"""
import argparse
import base64
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sys
import threading
import time

PORT = 8101
ORIGIN = f'http://127.0.0.1:{PORT}'
MARKER = '.disposable-session-a-farming-fixture'
PROFILES = ('bushels', 'rename', 'crafting', 'rush')


def prepare(root, source, artwork):
    if source is None or artwork is None:
        raise ValueError('Preparation requires explicit source and artwork paths.')
    source, artwork = source.resolve(strict=True), artwork.resolve(strict=True)
    if not (source / 'villages/initial.json').is_file():
        raise ValueError('The source must be a FarmVillage checkout.')
    if not all((artwork / name).is_dir() for name in ('Environment', 'xpromoSupport')):
        raise ValueError('The artwork path is incomplete.')
    root.mkdir()  # Existing progress is never overwritten.
    (root / MARKER).touch()
    for name in ('Runtime', 'data', 'tmp', 'baseline', 'evidence'):
        (root / name).mkdir()
    runtime = root / 'Runtime'
    for path in source.glob('*.py'):
        shutil.copy2(path, runtime / path.name)
    for name in ('templates', 'villages', 'warc_extractor', 'patched', 'ruffle_runtime'):
        shutil.copytree(source / name, runtime / name,
                        ignore=shutil.ignore_patterns('__pycache__', '.DS_Store'))
    for name in ('xml', 'embeds', 'assethash'):
        (runtime / name).symlink_to(source / name, target_is_directory=True)
    (root / 'data/assets').symlink_to(artwork, target_is_directory=True)
    metadata = dict(root=str(root), runtime=str(runtime), data=str(root / 'data'),
                    port=PORT, origin=ORIGIN, cookieName='fv_session_a_8101',
                    synthetic=True, credentials=False, source=str(source), landscape=[1280, 800])
    (root / 'fixture.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (root / 'source-hashes.json').write_text(json.dumps({
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.glob('*.py')}, indent=2) + '\n')


def protect(root):
    original = socket.socket.connect
    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in ('127.0.0.1', 'localhost', '::1'):
            raise RuntimeError('External networking is disabled in synthetic QA.')
        return original(sock, address)
    socket.socket.connect = connect
    def inside(path):
        if isinstance(path, (str, bytes, os.PathLike)) and not Path(os.fsdecode(path)).resolve().is_relative_to(root):
            raise RuntimeError('Write outside the synthetic fixture denied: ' + str(path))
    def audit(event, args):
        if event == 'open' and len(args) > 2 and isinstance(args[2], int):
            if args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                inside(args[0])
        elif event in ('os.remove', 'os.rmdir', 'os.mkdir'):
            inside(args[0])
        elif event in ('os.rename', 'os.link', 'os.symlink'):
            inside(args[0]); inside(args[1])
    sys.addaudithook(audit)


def seed_profile(save, key):
    import breeding, bushels, items, peaceful
    now = int(time.time())
    person = save['userInfo']['player']
    person.update(gold=2_500_000, cash=1000, xp=100010, mastery={}, masteryCounters={})
    person.setdefault('seenFlags', {}).update(ftue_complete=True, UnlockedCottage=True,
        placeCottage=True, craftingTutorialComplete=True, FirstMarketStall=False)
    save['userInfo'].update(is_new=False, firstDay=False, firstDayTimestamp=0)
    save['questState'] = {'active': {}, 'completed': [], 'retired': [], 'replayed': {}}
    save['craftingState'].update(craftingItems=[], maxCapacity=400, currentMarketStallCount=0)
    if key in ('bushels', 'rename'):
        save['world']['objectsArray'] = [o for o in save['world']['objectsArray'] if o['className'] != 'Plot']
    if key == 'bushels':
        # Earned progress is an explicit precondition. All award actions remain UI actions.
        save[bushels.COUNTERS_KEY] = {}
        for index, name in enumerate(('strawberry', 'wheat', 'soybeans', 'sunflowers', 'cotton')):
            seed = items.get_item_by_name(name)
            save[bushels.COUNTERS_KEY][seed['code']] = 49
            save['world']['objectsArray'].append(dict(id=10 + index, itemName=name,
                className='Plot', state='grown', plantTime=int((now-peaceful.grow_seconds(seed)-60)*1000),
                position=dict(x=14+4*index, y=13, z=0), isJumbo=False, isBigPlot=False,
                isProduceItem=False, direction=0, deleted=False))
    if key == 'rename':
        dna = copy.deepcopy(breeding._config()['variants']['ewePlain']); dna['N'] = 'Hazel'
        packed = json.dumps(dna, separators=(',', ':')); identity = breeding.dna_hash(dna)
        save['world']['objectsArray'].extend([
            dict(id=10, itemName='sheeppen_lamb', className='MutableAnimalBaby',
                 state='construction', isFullyBuilt=False, contents=[], expansionParts={},
                 position=dict(x=20,y=16,z=0), direction=0, mutableAnimalState=dict(dna=copy.deepcopy(dna))),
            dict(id=11, itemName=breeding.FEATURE, className='FeatureBuilding',
                 state='built', isFullyBuilt=True, expansionLevel=1, capacity=40,
                 position=dict(x=14,y=25,z=0), direction=0, expansionParts={},
                 contents=[dict(itemCode='cw',numItem=1)], storageMetadata={'cw:'+identity:[packed]},
                 extraDataState=dict(breedHistory={},breedingQueue=[]))])
        person['storageData'].update({'-1':{'cy':[1,[],[packed]]},'11':{'cw':[1,[],[packed]]}})
    if key == 'crafting':
        # One paid skill upgrade's XP is an explicit precondition; production
        # queues, completion clocks and crafted goods start empty.
        person['seenFlags'].update(craftTutDone=True)
        save['world']['objectsArray'].append(dict(id=80, itemName='craftingbakery',
            className='CraftingCottageBuilding', state='built', isFullyBuilt=True,
            craftLevel=1, position=dict(x=12,y=25,z=0), direction=0,
            contents=[], expansionParts={}, recipeQueue=[], finishedRecipes={}))
        save['world']['objectsArray'].append(dict(id=81, itemName='tractor',
            className='Tractor', state='built', isFullyBuilt=True,
            position=dict(x=32,y=20,z=0), direction=0))
        save['craftingState']['craftingSkillState'] = dict(recipeStates=[],
            craftTypes=[dict(type='bakery',level=1,xp=6,exp=6)])


def serve(root):
    if not (root / MARKER).is_file():
        raise ValueError('A marked Session A synthetic fixture is required.')
    metadata = json.loads((root / 'fixture.json').read_text())
    runtime, data = root / 'Runtime', root / 'data'
    if (metadata.get('synthetic') is not True or metadata.get('credentials') is not False
            or metadata.get('root') != str(root) or metadata.get('port') != PORT
            or runtime.is_symlink() or data.is_symlink()):
        raise ValueError('The synthetic fixture metadata does not match this root.')
    os.environ.update(FARMVILLAGE_DATA_DIR=str(data), FARMVILLAGE_NATIVE='0',
                      PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(root/'tmp'))
    sys.dont_write_bytecode = True
    os.chdir(runtime); sys.path.insert(0,str(runtime)); protect(root)
    assets = importlib.import_module('assets')
    def verify_assets():
        if not all((data/'assets'/n).is_dir() for n in ('Environment','xpromoSupport')):
            raise ValueError('Local artwork is missing; no download is allowed.')
    assets.check_assets = verify_assets
    sys.argv = ['server.py','--host','127.0.0.1','--port',str(PORT),'--public-url',ORIGIN]
    server = importlib.import_module('server'); player = importlib.import_module('player')
    server.app.secret_key = secrets.token_bytes(32)
    server.app.config.update(SESSION_COOKIE_NAME=metadata['cookieName'],FARMVILLAGE_TRUSTED_ORIGINS=[ORIGIN])
    server.app.root_path = str(runtime); server.app.template_folder = str(runtime/'templates')
    from flask import request, session, redirect, Response
    from pyamf import remoting
    trace_lock = threading.Lock()
    uids = metadata.get('uids',{})
    for key in PROFILES:
        if key in uids:
            if uids[key] not in player.all_saves_uids():
                raise ValueError('Recorded synthetic profile missing; replacement refused.')
            continue
        uid = player.new_village('Session A Synthetic '+key)
        seed_profile(player.session(uid),key); player.save_session(uid); uids[key]=uid
        (root/'baseline'/(key+'.json')).write_text(json.dumps(player.session(uid),indent=2)+'\n')
    @server.app.before_request
    def local_only():
        if request.remote_addr not in ('127.0.0.1','::1') or request.host != f'127.0.0.1:{PORT}':
            return Response('Synthetic loopback QA only',403)
        if request.path == '/proxy':
            return Response(base64.b64decode(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='),
                mimetype='image/png')
    @server.app.get('/__qa/start')
    def start():
        key = request.args.get('profile','bushels')
        if key not in uids: return Response('Unknown synthetic profile',404)
        session['UID']=uids[key]; return redirect('/ruffle.html')
    @server.app.after_request
    def action_trace(response):
        if request.path == '/flashservices/gateway.php' and response.status_code == 200:
            incoming = remoting.decode(request.get_data()).bodies[0][1].body
            outgoing = remoting.decode(response.get_data()).bodies[0][1].body
            record = dict(time=time.time(), uid=session.get('UID'),
                requests=incoming[1], response=outgoing)
            with trace_lock, (root/'evidence/gateway-trace.jsonl').open('a') as stream:
                stream.write(json.dumps(record, default=str) + '\n')
        return response
    metadata.update(uids=uids,pid=os.getpid())
    (root/'fixture.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('READY '+ORIGIN+'/__qa/start?profile=bushels',flush=True)
    server.app.run(host='127.0.0.1',port=PORT,threaded=True,debug=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--source',type=Path); parser.add_argument('--assets',type=Path)
    args=parser.parse_args(); root=args.root.resolve()
    if Path('/private/tmp') not in root.parents or args.root.is_symlink():
        parser.error('Use a dedicated nonsymlinked /private/tmp root.')
    prepare(root,args.source,args.assets) if args.prepare else serve(root)
