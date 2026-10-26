print (" [+] Loading basics...")
import os
import sys
import json
import copy
import argparse

# Parsed before anything heavy loads, so --help/bad args answer immediately
_argparser = argparse.ArgumentParser(description="FarmVille Server")
_argparser.add_argument("--host", "--ip", dest="host", default="127.0.0.1", help="Host/IP address to bind to (default: 127.0.0.1)")
_argparser.add_argument("--port", dest="port", type=int, default=5500, help="Port to listen on (default: 5500)")
_argparser.add_argument("--public-url", dest="public_url", default=None, help="URL the client reaches the server at, e.g. when behind a reverse proxy (default: http://<host>:<port>)")
_args = _argparser.parse_args()

if os.name == 'nt':
    os.system("color")
    os.system("title FarmVille Server")
else:
    import sys
    sys.stdout.write("\x1b]2;FarmVille Server\x07")

from assets import check_assets
print(" [+] Loading assets...")
check_assets()

print (" [+] Loading game settings...")
from game_settings import load_game_settings
load_game_settings()

print(" [+] Loading items...")
from items import load_items
load_items()

print(" [+] Loading quests...")
import quests
from quests import load_quests
load_quests()

print(" [+] Loading avatar config...")
from avatar import load_avatar
load_avatar()

print (" [+] Loading players...")
from player import load_saves, load_static_villages, all_saves_info, all_saves_uids, save_info, new_village, social_network_friends
load_saves()
print (" [+] Loading static villages...")
load_static_villages()

print (" [+] Loading server...")
import requests
from flask import Flask, render_template, send_from_directory, request, Response, redirect, session, jsonify
from flask.debughelpers import attach_enctype_error_multidict
from werkzeug.utils import safe_join
from pyamf import remoting
import pyamf
from defusedxml import ElementTree as SafeElementTree

# Select the supported, entity-safe XML interface before threaded requests encode AMF. PyAMF's lazy
# backend discovery probes optional defusedxml.lxml on the first encode, which can fail during startup.
pyamf.set_default_etree(SafeElementTree)

import commands
import ugc
import feature_options
import feature_availability
import themed_client_presentation
import themed_market_presentation
import crafting
import bushels
import paid_buildings
import breeding
import england_animals
import minigames
import pets
import world_travel
import creative_worlds
import maple_frontier
import october_village
import october_presentation
import construction
import gifting
from engine import timestamp_now
from version import version_name
from bundle import BASE_DIR, TMP_BUNDLED_DIR, ASSETS_DIR, EMBEDS_DIR, ASSETHASH_DIR, PATCHED_ASSETS_DIR, TEMPLATES_DIR, XML_DIR, UNHANDLED_LOG
from player import save_session, village_transaction, village_savepoint, session as player_session
from persistence import save_transaction
import peaceful
import market
import client_compatibility
import client_graphics
import runtime_compatibility
from pathlib import Path

BIND_HOST = _args.host
BIND_PORT = _args.port
PUBLIC_URL = (_args.public_url or f"http://{BIND_HOST}:{BIND_PORT}").rstrip("/")
NATIVE_WRAPPER = os.environ.get("FARMVILLAGE_NATIVE") == "1"
RUFFLE_DIR = os.environ.get("FARMVILLAGE_RUFFLE_DIR")
# Source and bundled launches use the same hard-pinned self-hosted package.
_runtime_release = runtime_compatibility.select_runtime_release(
    Path(TMP_BUNDLED_DIR), prepared_pin_sha256=os.environ.get("FARMVILLAGE_PREPARED_RUNTIME_PIN_SHA256"))
_runtime_directory = Path(RUFFLE_DIR) if RUFFLE_DIR else runtime_compatibility.bundled_runtime(Path(TMP_BUNDLED_DIR), _runtime_release)
VERIFIED_RUFFLE = runtime_compatibility.verify_runtime(_runtime_directory, _runtime_release)
RUFFLE_PUBLIC_PATH = runtime_compatibility.public_path(_runtime_release)

app: Flask = Flask(__name__)

print (" [+] Configuring server routes...")

# Templates

@app.route("/", methods=['GET', 'POST'])
@save_transaction
def login():
    # Log out previous session
    session.pop('UID', default=None)
    # Reload saves (not static villages nor quests). Allows saves modification without server reset
    load_saves()
    # If logging in, set session UID, and go to play
    if request.method == 'POST':
        uid = request.form.get('UID', '')
        if uid not in all_saves_uids():
            return redirect("/")
        session['UID'] = uid
        print("[LOGIN] UID:", uid)
        if request.form.get("destination") == "farms":
            session['farm_player_url'] = "/ruffle.html" if NATIVE_WRAPPER or 'RUFFLE' in request.form else "/play.html"
            return redirect("/farms")
        # Ruffle checkbox: only sent when checked
        if NATIVE_WRAPPER or 'RUFFLE' in request.form:
            return redirect("/ruffle.html")
        return redirect("/play.html")
    # Login page
    if request.method == 'GET':
        saves_info = all_saves_info()
        return render_template("login.html",
            saves_info=saves_info,
            version=version_name,
            native_wrapper=NATIVE_WRAPPER,
            # Set by /sn_app_url/index.php after the game reports an error. A fixed flag, never the query text.
            game_error=request.args.get("error") == "1"
        )

@app.route("/farms", methods=['GET', 'POST'])
@save_transaction
def additional_farms():
    import hmac
    import secrets
    uid = session.get("UID")
    if uid not in all_saves_uids():
        return redirect("/")
    session.setdefault("farms_token", secrets.token_urlsafe(24))
    error = None
    if request.method == 'POST':
        if not hmac.compare_digest(session['farms_token'].encode(), request.form.get('token', '').encode()):
            return Response("Reopen your farms and try again.", status=400)
        try:
            with village_transaction(uid):
                action = request.form.get('action')
                destination = request.form.get('world', '')
                if action == 'purchase':
                    creative_worlds.create(player_session(uid), destination,
                                          request.form.get('option', ''), now=timestamp_now())
                elif action == 'visit':
                    if destination not in world_travel.supported_worlds():
                        raise ValueError("That farm is not available yet.")
                    commands.load_own_world(uid, destination)
                else:
                    raise ValueError("Choose a farm to visit or add.")
                save_session(uid)
            if action == 'visit':
                return redirect(session.get('farm_player_url', '/ruffle.html'))
            return redirect('/farms')
        except ValueError as failure:
            error = str(failure)
    saved = player_session(uid)
    current = saved['userInfo'].get('currentWorldType') or 'farm'
    available = {current, *saved.get(world_travel.STATE_KEY, {}).get('inactive', {})}
    import themed_worlds
    names = {'farm': 'Home Farm', 'england': 'English Countryside',
             'meadows': 'Sunflower Meadows', 'fisherman': 'Lighthouse Cove',
             **{key: themed_worlds.SPECS[key]['name'] for key in themed_worlds.active_worlds()}}
    owned = [{'worldType': key, 'name': names[key], 'current': key == current}
             for key in names if key in available]
    return render_template('farms.html', farms=owned,
        candidates=creative_worlds.candidates(saved), error=error,
        cash=saved['userInfo']['player']['cash'], token=session['farms_token'],
        version=version_name)


@app.route("/play.html", methods=['GET'])
@save_transaction
def play():
    if NATIVE_WRAPPER:
        return redirect("/ruffle.html")
    if 'UID' not in session:
        return redirect("/")
    
    if session['UID'] not in all_saves_uids():
        return redirect("/")
    
    UID = session['UID']
    print("[PLAY] UID:", UID)
    return render_template("play.html", 
        version=version_name,
        base_url=PUBLIC_URL,
        server_time=timestamp_now(),
        peaceful_mode=peaceful.enabled(commands.session(UID)),
        feature_icon_blacklist=feature_availability.hud_icon_blacklist(),
        quest_bubble_suppression=feature_availability.QUEST_BUBBLE_SUPPRESSION_VARIANT,
        suppress_world_switch_quests=feature_availability.SUPPRESS_WORLD_SWITCH_QUESTS_VARIANT,
        debug="true",
        user={
            "uid": UID,
            "name": save_info(UID)["name"],
            # Served to getUserInfo()'s pic_square/pic_big - see player.profile_pic()
            "profilePic": save_info(UID)["profilePic"]
        },
        save_info=save_info(UID),
        # Served to the client's getFriendData()/getAppFriendIds() JS hooks - see player.social_network_friends()
        friends=social_network_friends(UID)
    )

@app.route("/ruffle.html", methods=['GET'])
@save_transaction
def play_ruffle():
    if 'UID' not in session:
        return redirect("/")

    if session['UID'] not in all_saves_uids():
        return redirect("/")

    UID = session['UID']
    print("[PLAY_RUFFLE] UID:", UID)
    return render_template("ruffle.html",
        ruffle_public_path=RUFFLE_PUBLIC_PATH,
        native_wrapper=NATIVE_WRAPPER,
        version=version_name,
        base_url=PUBLIC_URL,
        server_time=timestamp_now(),
        peaceful_mode=peaceful.enabled(commands.session(UID)),
        feature_icon_blacklist=feature_availability.hud_icon_blacklist(),
        quest_bubble_suppression=feature_availability.QUEST_BUBBLE_SUPPRESSION_VARIANT,
        suppress_world_switch_quests=feature_availability.SUPPRESS_WORLD_SWITCH_QUESTS_VARIANT,
        debug="true",
        user={
            "uid": UID,
            "name": save_info(UID)["name"],
            # Served to getUserInfo()'s pic_square/pic_big - see player.profile_pic()
            "profilePic": save_info(UID)["profilePic"]
        },
        save_info=save_info(UID),
        # Served to the client's getFriendData()/getAppFriendIds() JS hooks - see player.social_network_friends()
        friends=social_network_friends(UID)
    )

@app.route("/health", methods=['GET'])
def health():
    result = {"status": "ok", "version": version_name}
    if NATIVE_WRAPPER:
        result["wrapper_token"] = os.environ.get("FARMVILLAGE_INSTANCE_TOKEN", "")
    return jsonify(result)

@app.route("/ruffle/<path:path>", methods=['GET'])
def ruffle_runtime(path):
    try:
        name = runtime_compatibility.resource_name(path)
    except runtime_compatibility.RuntimeIntegrityError:
        return Response("Unsupported Ruffle resource.", status=404)
    if name not in VERIFIED_RUFFLE.files:
        return Response("Unknown Ruffle resource.", status=404)
    try:
        contents = runtime_compatibility.read_resource(VERIFIED_RUFFLE, name)
    except runtime_compatibility.RuntimeIntegrityError:
        return Response("The local Ruffle resource failed verification.", status=503)
    response = Response(contents, mimetype="application/octet-stream")
    response.headers["Cache-Control"] = "no-store"
    if path.endswith(".wasm"):
        response.mimetype = "application/wasm"
    elif path.endswith(".js"):
        response.mimetype = "text/javascript"
    return response

@app.route("/new.html", methods=['GET', 'POST'])
@save_transaction
def new():
    # GET only shows the form: a reload must not create another farm. POST creates the farm.
    error = None
    name = ""
    preset = "classic"
    if request.method == 'POST':
        name = request.form.get("name", "")
        preset = request.form.get("preset", "classic")
        try:
            session['UID'] = (new_village(name) if preset == "classic"
                              else new_village(name, preset=preset))
        except ValueError as exception:
            error = str(exception)
        else:
            return redirect("/ruffle.html" if NATIVE_WRAPPER else "/play.html")
    return render_template("new.html",
        version=version_name,
        name=name,
        preset=preset,
        october_available=october_village.AVAILABLE,
        october_description=october_village.DESCRIPTION,
        error=error
    ), (400 if error else 200)

@app.route("/img/<path:path>", methods=['GET'])
def img(path):
    return send_from_directory(TEMPLATES_DIR + "/img", path)

# client ref.: src/Engine/Classes/ResourceLoader.as (m_context.checkPolicyFile = true)
# Every LoadingManager.loadFromUrl() request demands a crossdomain.xml from the url's host, which no modern
# CDN serves - so Flash fails a remote image with a SecurityError before it even requests it. This re-serves
# an arbitrary url from our own origin (which does serve a policy file). Normal
# profile pictures now use player.profile_pic()'s existing no-picture fallback
# for remote URLs, so offline/disabled proxy access cannot interrupt gameplay.
# The separately authenticated LAN host keeps this legacy endpoint disabled.
_proxy_cache = {}
PROXY_CACHE_MAX_ENTRIES = 64

@app.route("/proxy", methods=['GET'])
def proxy():
    url = request.args.get("url", "")
    if not url.startswith(("http://", "https://")):
        return Response("Only http(s) urls can be proxied.", status=400)
    if url not in _proxy_cache:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[!] Proxy could not fetch {url}: {e}")
            return Response("Could not fetch the requested url.", status=502)
        if len(_proxy_cache) >= PROXY_CACHE_MAX_ENTRIES:
            _proxy_cache.clear()
        _proxy_cache[url] = (response.headers.get("Content-Type", "application/octet-stream"), response.content)
    content_type, content = _proxy_cache[url]
    return Response(content, mimetype=content_type)

@app.route("/css/<path:path>")
def css(path):
    return send_from_directory(TEMPLATES_DIR + "/css", path)

@app.route("/crossdomain.xml", methods=['GET'])
def crossdomain():
    return send_from_directory(TEMPLATES_DIR, "crossdomain.xml")

# Static endpoints

@app.route("/embeds/Flash/v855097-855094/FV_Preloader.swf", methods=['GET'])
def patched_preloader():
    return send_from_directory(PATCHED_ASSETS_DIR, "FV_Preloader_mod.swf")

@app.route("/embeds/Flash/v855097-855094/FarmGame.swf", methods=['GET'])
def prepared_game_client():
    # The derived catalog and its lazy parser must always travel together,
    # including when running directly from the source checkout.
    source = Path(EMBEDS_DIR) / "Flash/v855097-855094/FarmGame.swf"
    return Response(client_graphics.prepared_client(source),
                    mimetype="application/x-shockwave-flash",
                    headers={"Cache-Control": "no-store"})

@app.route("/embeds/<path:path>", methods=['GET'])
def embeds(path):
    return send_from_directory(EMBEDS_DIR, path)

@app.route("/assethash/<path:path>", methods=['GET'])
def assethash_path(path):
    return send_from_directory(ASSETHASH_DIR, path, mimetype="application/x-amf")

def october_style_selected():
    """Presentation follows the authenticated profile, including return trips."""
    uid = session.get("UID")
    if not isinstance(uid, str) or uid not in all_saves_uids():
        return False
    selected = player_session(uid)
    marker = selected.get(october_village.STATE_KEY) if isinstance(selected, dict) else None
    return isinstance(marker, dict) and marker.get("preset") == october_village.PRESET

@app.route("/xml/<path:path>", methods=['GET'])
def xml(path):
    if path == "gz/v855098/gameSettings.xml.gz":
        return Response(themed_client_presentation.game_settings_payload(), mimetype='text/xml',
                        headers={'Cache-Control': 'no-store'})
    if path == "gz/v855098/worldScore.amf.gz":
        return Response(themed_client_presentation.world_score_payload(), mimetype='application/x-amf',
                        headers={'Cache-Control': 'no-store'})
    if path == "gz/v855098/worldSettings.xml.gz":
        # The projection changes only this profile's Home HUD. Keep it in the
        # world settings while travelling, so returning Home has the same skin.
        raw = (Path(XML_DIR) / path).read_bytes()
        base = october_presentation.world_settings_payload(raw, active=october_style_selected())
        return Response(themed_market_presentation.world_settings_payload(base),
                        mimetype='text/xml',
                        headers={'Cache-Control': 'no-store', 'Vary': 'Cookie'})
    if path == "gz/v855098/crafting.xml.gz":
        return Response(crafting.client_payload(), mimetype='text/xml',
                        headers={'Cache-Control': 'no-store'})
    if path == "gz/v855098/postInitSequence.xml.gz":
        return Response(feature_availability.post_init_payload(), mimetype='text/xml',
                        headers={'Cache-Control': 'no-store'})
    if path == "gz/v855038/items_opt.amf":
        import client_catalog
        return Response(client_catalog.payload(), mimetype='application/x-amf',
                        headers={"Cache-Control": "no-store"})
    if path == "gz/v855098/questSettings_0.xml.gz":
        import client_england
        return Response(client_england.quest_payload(), mimetype='text/xml',
                        headers={"Cache-Control": "no-store"})
    if path == "gz/v855098/storageConfig.amf.gz":
        import client_england
        return Response(client_england.storage_payload(), mimetype='application/x-amf',
                        headers={"Cache-Control": "no-store"})
    if path == "gz/v855098/gameSettingsCMS.xml.gz":
        import client_england
        return Response(client_england.cms_payload(), mimetype='text/xml',
                        headers={"Cache-Control": "no-store"})
    return send_from_directory(XML_DIR, path, mimetype='text/xml')

@app.route("/assets/Environment/grass_themeBackground_7.swf", methods=['GET'])
def stub_grass_themeBackground_7():
    return send_from_directory(ASSETS_DIR, "Environment/df0a488eac94bee5d6eca26fd6114603.swf", mimetype='text/xml')

@app.route("/assets/Environment/grass_themeBackground_8.25.swf", methods=['GET'])
def stub_grass_themeBackground_825():
    return send_from_directory(ASSETS_DIR, "Environment/df0a488eac94bee5d6eca26fd6114603.swf", mimetype='text/xml')

@app.route("/assets/decorations/toolbar32x32.png", methods=['GET'])
def toolbar32x32():
    return send_from_directory(ASSETS_DIR, "promo_bar/8c22dd1b08e3909a073485e7fa956758.png", mimetype='image/png')

@app.route("/assets/<path:path>", methods=['GET'])
def assets(path):
    return send_from_directory(ASSETS_DIR, path)

@app.route("/masterysigns/v1/masterysign_items.amf.gz", methods=['GET'])
def stub_masterysign_items():
    # HTTP gzip is decoded by the browser before the client's ByteArray.readObject.
    # An unavailable mastery-sign catalog must still contain a valid AMF3 object:
    # gzip(empty bytes) leaves an empty ByteArray and aborts Flash initialization.
    import gzip
    catalog = pyamf.encode({}, encoding=pyamf.AMF3).getvalue()
    return Response(gzip.compress(catalog, mtime=0), mimetype='application/x-amf',
                    headers={'Content-Encoding': 'gzip'})

# Dynamic endpoints

@app.route("/report_exception.php", methods=['POST'])
def report_exception():
    print("[!] Exception:", request.data.decode("utf-8"))
    return "{}"

@app.route("/record_stats.php", methods=['POST'])
def record_stats():
    stats = json.loads(request.data)
    print("[+] Stats:")
    for i in stats["stats"]:
        print(" * ", i["statfunction"], ": ", i["data"], sep="")
    return "{}"

@app.route("/report_log.php", methods=['POST'])
def report_log():
    print("[+] Log:", request.data.decode("utf-8"))
    return "{}"

@app.route("/cb.php", methods=['POST'])
def cb():
    print("[+] Callback:", request.data.decode("utf-8"))
    return "{}"

@app.route("/sn_app_url/index.php", methods=['GET'])
def sn_app_url_index():
    ref = request.args.get("ref")
    ooscode = request.args.get("ooscode")
    oosfunc = request.args.get("oosfunc")
    oosmsg = request.args.get("oosmsg")
    print("[!] Reported Error:", ref ,":", ooscode, oosfunc, oosmsg)
    # The login page shows a fixed notice for this flag; the reported text is never echoed back.
    return redirect("/?error=1")

def _json_safe(obj):
    # pyamf request params can contain AMF-specific types (ASObject, ByteArray,
    # Undefined, dates, ...) that json.dumps doesn't know how to serialize.
    # Recurse through dict/list/tuple and fall back to str() for anything else.
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)

def log_unhandled_command(function_name, params) -> None:
    # Used to prioritize which Service.method branches to implement next -
    # see commands.ABSENT_SOCIAL_READS for known no-ops. One JSON object per line (JSON Lines) so it's easy to
    # tally the most frequent unhandled calls later.
    entry = {
        "timestamp": timestamp_now(),
        "functionName": function_name,
        "params": _json_safe(params),
    }
    try:
        with open(UNHANDLED_LOG, 'a') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[!] Failed to write to unhandled.log: {e}")

def _gateway_array(value):
    # pyamf may decode the AMF0 requests array as an ECMA (associative) array
    # (a dict keyed by index) instead of a strict array (a list) - normalize.
    if isinstance(value, dict):
        keys = sorted(value, key=int)
        if [int(key) for key in keys] != list(range(len(keys))):
            raise ValueError("An AMF array must have consecutive indices.")
        return [value[key] for key in keys]
    if not isinstance(value, (list, tuple)):
        raise ValueError("An AMF array was expected.")
    return list(value)


def _decode_gateway(contents):
    message = remoting.decode(contents)
    if len(message.bodies) != 1 or not isinstance(message.bodies[0][1], remoting.Request):
        raise ValueError("One game request body was expected.")
    body = _gateway_array(message.bodies[0][1].body)
    # FarmGame appends transport metadata after the two required fields. Keep
    # accepting that extension while validating the header and command batch.
    if len(body) < 2 or not isinstance(body[0], dict):
        raise ValueError("The game request body is incomplete.")
    raw_uid = body[0].get("uid")
    if isinstance(raw_uid, bool) or not isinstance(raw_uid, (str, int)):
        raise ValueError("Invalid village UID.")
    requests = []
    for entry in _gateway_array(body[1]):
        if (not isinstance(entry, dict) or not isinstance(entry.get("functionName"), str)
                or not entry["functionName"] or "sequence" not in entry):
            raise ValueError("The game command is incomplete.")
        command = pyamf.ASObject(entry)
        command["params"] = _gateway_array(entry.get("params"))
        requests.append(command)
    return message, str(raw_uid), requests


@app.route("/flashservices/gateway.php", methods=['POST'])
@save_transaction
def flashservices_gateway():
    try:
        resp_msg, UID, reqs = _decode_gateway(request.data)
    except (pyamf.DecodeError, OSError, ValueError, TypeError, IndexError, KeyError,
            AttributeError, EOFError, RecursionError) as error:
        print(f"[!] Invalid AMF request: {error}")
        return Response("Invalid AMF request.", status=400)
    if UID not in all_saves_uids():
        return Response("The selected village is unavailable. Return to login.", status=403)
    try:
        with village_transaction(UID):
            return _dispatch_gateway(resp_msg, UID, reqs)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as error:
        print(f"[!] Invalid game command; the farm was restored: {error}")
        return Response("Invalid game command parameters.", status=400)


def _dispatch_gateway(resp_msg, UID, reqs):
    resps = []
    for reqq in reqs:
        try:
            with village_savepoint(UID):
                # Results must not retain mutable references to a later call's
                # provisional state, especially init/world-load responses.
                response = copy.deepcopy(_dispatch_gateway_commands(UID, [reqq])[0])
                # Stage the caller while its structural and JSON validation
                # failures can still roll back only this action. Actual files
                # are published by the outer transaction after AMF encoding.
                save_session(UID)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError, RecursionError) as error:
            print(f"[!] Invalid game command {reqq.functionName}; this action was restored: {error}")
            response = {
                # Original Transaction.FORCE_RELOAD. Ordinary nonzero errors
                # reach Transaction.onFault(), which is a no-op for most game
                # actions. 29 instead shows the client's save-error dialog.
                # The client stops callbacks here; accepted later calls are
                # durable and appear when the player reloads.
                "errorType": 29,
                "errorData": str(error),
                "sequenceNumber": reqq["sequence"],
                "worldTime": timestamp_now(),
                "isDST": 0,
                "metadata": {"QuestComponent": []},
                "data": None,
            }
        resps.append(response)

    emsg = {"serverTime": timestamp_now(), "errorType": 0, "data": resps}
    ev = remoting.Envelope(pyamf.AMF0)
    ev[resp_msg.bodies[0][0]] = remoting.Response(emsg)
    # Encoding and disk failures still reject the complete outer transaction.
    ret_body = remoting.encode(ev, strict=True, logger=True).getvalue()
    return Response(ret_body, mimetype='application/x-amf')


def _dispatch_gateway_commands(UID, reqs):
    resps = []
    for reqq in reqs:

        print(f"[+] {reqq.functionName}: {reqq['params']}")
        response = {
            "errorType": 0,
            "errorData": None,
            "isDST": 0,
            "sequenceNumber": reqq["sequence"],
            "worldTime": timestamp_now(),
            # client ref.: src/ZQuest/Managers/QuestManager.as (onTransactionComplete)
            # Filled in after the command ran, so a call that changes the quest list answers with the new one.
            "metadata": {
                "QuestComponent": [],
            },
            # "zySig": {
            #     "zy_user": resp_msg.bodies[0][1].body[0]["zy_user"],
            #     "zy_ts": timestamp_now(),
            #     "zy_session": resp_msg.bodies[0][1].body[0]["zy_session"]
            # },
            "data": None
        }

        if reqq.functionName == 'UserService.initUser':
            firstName = reqq['params'][0]
            timezoneOffset = reqq['params'][1]
            needsToLoadWorld = reqq['params'][2]
            flashControllerInit = reqq['params'][3]
            response["data"] = commands.init_user(UID)
            resps.append(response)

        elif reqq.functionName == 'UserService.postInit':
            response["data"] = commands.post_init_user(UID)
            resps.append(response)

        elif reqq.functionName == 'UserService.getMOTD':
            motd_seen_flag = reqq['params'][0]
            response["data"] = commands.get_motd(UID, motd_seen_flag)
            resps.append(response)

        elif reqq.functionName == 'FriendSetService.getBatchFriendSetData':
            # client ref.: src/Transactions/TBatchInitializeFriendSets.as (onComplete)
            # The response is indexed by friend-set code (result[friendSet.code].uids/.pending), so the
            # "nothing to hand back" answer is an empty map, not an empty list. Friend sets are not
            # modelled server-side: no set ever initializes, which only leaves each one at 0 friends
            # (nothing retries and nothing blocks on FriendSet.initialized).
            response["data"] = {}
            resps.append(response)
        
        elif reqq.functionName == 'UserService.r2InterstitialPostInit':
            response["data"] = {
                "r2InterstitialItems": [],
                "r2InterstitialFeedItems": [],
                "r2InterstitialMinigameIndex": [],
                "r2InterstitialTypeIndex": None,
                "r2InterstitialFriendCount": None
            }
            resps.append(response)
        
        elif reqq.functionName == 'FriendListService.getFriendsForR2FlashNeighborFlow':
            response["data"] = {
                "requestedFriends": {
                    "GhostNeighbor": [],
                    "FarmVille": [],
                    "Facebook": [],
                    "PossibleCommunity": [],
                    "CurrentAllNeighbor": [],
                }
            }
            resps.append(response)

        elif reqq.functionName == 'DailyStatsService.incrementCounter':
            commands.increment_daily_counter(UID, *reqq['params'])
            resps.append(response)

        elif reqq.functionName == 'UserService.incrementActionCount':
            action = reqq['params'][0]
            commands.increment_action_count(UID, action)
            resps.append(response)
        
        elif reqq.functionName == 'UserService.setActionCount':
            action = reqq['params'][0]
            value = reqq['params'][1]
            commands.set_action_count(UID, action, value)
            resps.append(response)

        elif reqq.functionName == 'UserService.resetActionCount':
            action = reqq['params'][0]
            commands.reset_action_count(UID, action)
            resps.append(response)

        elif reqq.functionName == 'UserService.updateWorldScoreLevelUp':
            commands.acknowledge_world_score_level_up(UID, *reqq['params'])
            resps.append(response)

        elif reqq.functionName == 'UserService.setSeenFlag':
            flag = reqq['params'][0]
            commands.set_seen_flag(UID, flag)
            resps.append(response)

        elif reqq.functionName == 'UserService.setItemFlag':
            flag = reqq['params'][0]
            value = reqq['params'][1]
            commands.set_item_flag(UID, flag, value)
            resps.append(response)

        elif reqq.functionName == 'SNPermissionsService.setSNExtendedPermissions':
            permissions = reqq['params'][0]
            commands.set_sn_extended_permissions(UID, permissions)
            resps.append(response)

        elif reqq.functionName == 'UserService.resetSystemNotifications':
            commands.reset_system_notifications(UID)
            resps.append(response)
        
        elif reqq.functionName == 'UserContentService.onCreateImage':
            name = reqq['params'][0]
            png_b64 = reqq['params'][1]
            image_type = reqq['params'][2]
            if name == "avatar_appearance":
                commands.set_avatar_appearance(UID, name, png_b64, image_type)
            resps.append(response)

        elif reqq.functionName == 'AvatarService.saveAvatar':
            customization_data = reqq['params'][0]
            gender = reqq['params'][1]
            commands.save_avatar(UID, customization_data, gender)
            resps.append(response)

        elif reqq.functionName == 'AvatarService.buyAvatarItem':
            item_id = reqq['params'][0]
            commands.buy_avatar_item(UID, item_id)
            resps.append(response)

        elif reqq.functionName == 'UserService.saveOptions':
            options = reqq['params'][0]
            commands.save_options(UID, options)
            resps.append(response)

        elif reqq.functionName == 'UserService.saveFeatureOptions':
            feature_options.apply(player_session(UID), *reqq['params'])
            resps.append(response)

        elif reqq.functionName == 'UGCDecoService.purchaseUGCDecoration':
            response["data"] = ugc.purchase_decoration(player_session(UID), *reqq['params'])
            resps.append(response)

        elif reqq.functionName == 'UGCDecoService.purchasePart':
            response["data"] = ugc.purchase_part(player_session(UID), *reqq['params'])
            resps.append(response)

        elif reqq.functionName == 'UGCItemService.saveTemporaryUGCState':
            ugc.save_temp_state(player_session(UID), *reqq['params'])
            resps.append(response)

        elif reqq.functionName == 'UGCDecoService.setLastEditedBlueprint':
            ugc.set_last_blueprint(player_session(UID), *reqq['params'])
            resps.append(response)
        
        elif reqq.functionName == 'WorldService.performAction':
            actionName = reqq['params'][0]
            m_save = reqq['params'][1]
            params = reqq['params'][2]
            object_id = commands.world_perform_action(UID, actionName, m_save, params,
                request_id=reqq['sequence'], sequence_id=reqq.get('sequenceID'))
            # This infroms the client of the new (non-temporary) object ID
            response["id"] = object_id
            response["data"] = {"id": object_id} # onMultiComplete and onComplete treat this differently. This is a temporary workaround
            response["data"].update(pets.response_for_action(player_session(UID), actionName, object_id))
            response["data"].update(paid_buildings.take_response(player_session(UID)))
            if actionName == 'transform':
                response["data"].update(england_animals.take_response(player_session(UID)))
            response["data"].update(commands.cove_port.take_response(player_session(UID)))
            if actionName == 'store':
                # ConstructionBuilding.onStoreComplete needs finishedName to
                # transform the just-finished site in the running Flash world.
                response["data"].update(construction.take_response(player_session(UID)))
            if actionName in ('store', 'TransformBuilding'):
                response["data"].update(breeding.take_response(player_session(UID)))
            if actionName in ('sell', 'clear'):
                # GMSalvage uses the ordinary sell/clear transactions. Their
                # callbacks refresh Deco materials from this exact field.
                response["data"]["ugcdeco"] = ugc.feature_data(player_session(UID))
            resps.append(response)

        elif reqq.functionName == 'EquipmentWorldService.onUseEquipment':
            action = reqq['params'][0]
            equipment = reqq['params'][1] # The vehicle itself ({id, key}) - nothing server-side is keyed off it
            plots = reqq['params'][2]
            item_name = reqq['params'][3]
            # The response is an Array (or, for 'combine', one per sub-action) built by commands.py - every
            # element is a mini envelope of its own, see commands.equipment_use.
            response["data"] = commands.equipment_use(UID, action, plots, item_name, response["metadata"])
            resps.append(response)
        
        elif reqq.functionName == 'WorldService.loadOwnWorld':
            response["data"] = commands.load_own_world(UID, *_gateway_array(reqq['params']))
            resps.append(response)

        elif reqq.functionName == 'EnglandService.unlockEnglandWorld':
            if len(reqq['params']) != 1:
                raise ValueError("England unlock requires one access type.")
            response["data"] = world_travel.unlock_england(player_session(UID),
                reqq['params'][0], now=timestamp_now())
            resps.append(response)

        elif reqq.functionName == 'FishermansCoveService.unlockFishermanWorld':
            params = _gateway_array(reqq['params'])
            if len(params) != 1:
                raise ValueError("Lighthouse Cove unlock requires one free access type.")
            response["data"] = world_travel.unlock_fisherman(player_session(UID),
                params[0], now=timestamp_now())
            resps.append(response)

        elif reqq.functionName.startswith('FishermansCoveService.'):
            raise ValueError("Lighthouse Cove's port and feature services are not restored.")

        elif reqq.functionName == maple_frontier.UNLOCK_METHOD:
            maple_frontier.refuse_unlock()

        elif reqq.functionName in maple_frontier.INNOVATION_MUTATIONS:
            maple_frontier.refuse_innovation_mutation()

        elif reqq.functionName in crafting.METHODS:
            maple_frontier.guard_crafting_context(player_session(UID))
            response["data"] = crafting.dispatch(player_session(UID), reqq.functionName,
                _gateway_array(reqq['params']), request_id=reqq['sequence'])
            resps.append(response)

        elif reqq.functionName == 'AnimalBreedingService.onSetAnimalName':
            if len(reqq['params']) != 5:
                raise ValueError("Animal naming needs code, DNA hash, name, world ID and storage context.")
            response["data"] = breeding.rename(player_session(UID), *reqq['params'],
                request_id=reqq['sequence'])
            breeding.take_response(player_session(UID))
            resps.append(response)

        elif reqq.functionName == 'AnimalBreedingService.onBeginBreeding':
            if len(reqq['params']) != 1:
                raise ValueError("Breeding needs one serialized session.")
            response["data"] = breeding.begin(player_session(UID), reqq['params'][0])
            resps.append(response)

        elif reqq.functionName in ('AnimalBreedingService.onFinishBreeding',
                                   'AnimalBreedingService.onFinishBreedingNow'):
            if len(reqq['params']) != 1:
                raise ValueError("Breeding needs one serialized session.")
            response["data"] = breeding.finish(player_session(UID), reqq['params'][0],
                finish_now=reqq.functionName == 'AnimalBreedingService.onFinishBreedingNow')
            resps.append(response)

        elif reqq.functionName.startswith('AnimalBreedingService.'):
            raise ValueError("This animal breeding service branch is not implemented.")

        elif reqq.functionName in bushels.STALL_METHODS:
            response["data"] = bushels.dispatch_stall(player_session(UID), reqq.functionName,
                _gateway_array(reqq['params']), request_id=reqq['sequence'], now=timestamp_now())
            resps.append(response)

        elif reqq.functionName in ('CraftingService.onRefreshMarketView',
                                   'CraftingService.onRefreshUserOffering'):
            # TGetMarketView only dismisses its loading popup for non-null data.
            response["data"] = market.view()
            resps.append(response)

        elif reqq.functionName.startswith('CraftingService.'):
            raise ValueError("This crafting service branch is not implemented.")

        elif reqq.functionName == 'UserService.sellStoredItem':
            import inventory_sales
            response["data"] = inventory_sales.sell(player_session(UID), reqq['params'],
                request_id=(reqq.get('sequenceID'), reqq['sequence']))
            resps.append(response)

        elif reqq.functionName == 'UserService.sellStorageBuildingItem':
            raise ValueError('Special container sales need their original storage contract; withdraw supported contents first.')

        elif reqq.functionName == 'UserService.getGifts':
            response["data"] = commands.get_gifts(UID)
            resps.append(response)

        elif reqq.functionName == 'UserService.getGiftboxErrorState':
            # TGetGiftBoxErrors indexes this field without a null guard.
            # Local gifts wait indefinitely; nothing expires or is evicted.
            response["data"] = {"giftboxError": 0}
            resps.append(response)

        elif reqq.functionName == 'PresentService.receiveAllPresents':
            response["data"] = gifting.receive(UID)
            resps.append(response)

        elif reqq.functionName == 'PresentService.receivePresent':
            response["data"] = gifting.receive(UID, all_presents=False)
            resps.append(response)

        elif reqq.functionName == 'PresentService.buyAndSend':
            response["data"] = gifting.send(UID, reqq['params'][0],
                _gateway_array(reqq['params'][1]),
                reqq['params'][2] if len(reqq['params']) > 2 else "normal")
            resps.append(response)

        elif reqq.functionName == 'PresentService.buyAndRegift':
            response["data"] = gifting.regift(UID, reqq['params'][0], reqq['params'][1],
                reqq['params'][2] if len(reqq['params']) > 2 else "normal")
            resps.append(response)

        elif reqq.functionName in ('UserService.onGiveRetentionItem',
                                   'UserService.onGiveRetentionItemWithPrereqs'):
            # No recovered server-side retention reward table. A valid empty
            # response avoids both the null crash and invented repeated grants.
            response["data"] = {"gifts": []}
            resps.append(response)

        elif reqq.functionName == 'WorldService.loadNeighborWorld':
            neighbor_id = reqq['params'][0]
            response["data"] = commands.load_neighbor_world(UID, neighbor_id)
            resps.append(response)

        elif reqq.functionName == 'UserService.updateFeatureFrequencyTimestamp':
            feature = reqq['params'][0]
            commands.update_feature_frequency_timestamp(UID, feature)
            resps.append(response)

        elif reqq.functionName == 'UserService.updateFeatureFrequencyWithBackoff':
            feature = reqq['params'][0]
            backoff_increments = reqq['params'][1]
            commands.update_feature_frequency_with_backoff(UID, feature, backoff_increments)
            resps.append(response)

        elif reqq.functionName == 'UserService.publishUserAction':
            action = reqq['params'][0]
            params = reqq['params'][1]
            commands.publish_user_actions(UID, action, params)
            resps.append(response)

        elif reqq.functionName in minigames.METHODS:
            response["data"] = minigames.dispatch(player_session(UID), reqq.functionName,
                _gateway_array(reqq['params']), request_id=reqq['sequence'])
            resps.append(response)

        elif reqq.functionName.startswith(('SlotService.', 'ScratchCardService.', 'PigoService.')):
            raise ValueError("This minigame operation is not implemented.")

        elif reqq.functionName == 'FarmService.expandFarm':
            # client ref.: src/Transactions/TExpandFarm.as
            # The response *is* the new world payload: onComplete checks its sizeX/sizeY against the
            # bought item's `squares` and then hands it to Global.world.loadObject().
            item_name = reqq['params'][0]
            currency_unit = reqq['params'][1]
            response["data"] = commands.expand_farm(UID, item_name, currency_unit)
            resps.append(response)

        elif reqq.functionName == 'UserService.setSeenExpandFarm':
            amount = reqq['params'][0]
            commands.set_seen_expand_farm(UID, amount)
            resps.append(response)

        elif reqq.functionName in ('ZAPIClientService.grantEmailPermissionWithGift',
                                   'ZAPIClientService.grantEmailPermission'):
            # client ref.: src/Transactions/TGrantEmailPermission.as
            response["data"] = commands.grant_email_permission(UID)
            resps.append(response)

        elif reqq.functionName == 'FarmService.buyConsumablePackage':
            package_name = reqq['params'][0]
            response["data"] = commands.buy_consumable_package(UID, package_name,
                request_id=reqq['sequence'], sequence_id=reqq.get('sequenceID'))
            resps.append(response)

        elif reqq.functionName == 'IrrigationService.onIrrigationAction':
            # client ref.: src/Transactions/TIrrigationAction.as (params: action, actionItems, params)
            action = reqq['params'][0]
            # The original Ruffle/AMF0 request encodes the nested Array as an
            # ECMA object with contiguous integer keys. Validate and normalize
            # it just like the top-level command parameters.
            action_items = _gateway_array(reqq['params'][1])
            response["data"] = commands.irrigation_action(UID, action, action_items)
            resps.append(response)

        elif reqq.functionName == 'IrrigationService.consumeIrrigationPackages':
            action_type = reqq['params'][0]
            amount = reqq['params'][1]
            response["data"] = commands.consume_water_packages(UID, action_type, amount)
            resps.append(response)

        elif reqq.functionName == 'WatchToEarnRewardGrantService.getUserZid':
            response["data"] = commands.w2e_get_user_zid(UID)
            resps.append(response)

        elif reqq.functionName == 'WatchToEarnRewardGrantService.generateDailyTokens':
            response["data"] = commands.w2e_generate_daily_tokens()
            resps.append(response)

        # client ref.: src/Transactions/Quests/*.as, src/Transactions/TMarkQuestAsViewed.as
        # These carry no data of their own - what the client acts on is the refreshed quest list that every
        # response ships in metadata.QuestComponent (see the end of this loop).

        elif reqq.functionName == 'FarmQuestService.fullQuestRefresh':
            commands.full_quest_refresh(UID)
            resps.append(response)

        elif reqq.functionName == 'FarmQuestService.interactedWithQuest':
            quest_name = reqq['params'][0]
            commands.interacted_with_quest(UID, quest_name)
            resps.append(response)

        elif reqq.functionName == 'FarmQuestService.updateRecentlyCompletedQuests':
            quest_name = reqq['params'][0]
            should_generate_friend_reward = reqq['params'][1]
            response["data"] = commands.update_recently_completed_quests(UID, quest_name, should_generate_friend_reward)
            resps.append(response)

        elif reqq.functionName in ('FarmQuestService.userKillQuest', 'FarmQuestService.userPauseQuest'):
            quest_name = reqq['params'][0]
            commands.retire_quest(UID, quest_name)
            resps.append(response)

        elif reqq.functionName == 'FarmQuestService.markViewDialogTaskDone':
            quest_name = reqq['params'][0]
            commands.mark_view_dialog_task_done(UID, quest_name)
            resps.append(response)

        # client ref.: src/Classes/Quest/FarmTask.as (skip) - a few task actions skip through a TSkipQuestTask
        # subclass of their own, with the same (questName, taskIndex) params and the same price. Their onComplete
        # then changes the world client-side only (TSkipBuildingConstruction finishes the construction site,
        # TSkipExpandStorageBuilding expands the building, TSkipRewardCreditTask adds the credits), with no
        # transaction of its own, so those changes are not in the save and are gone on the next login; the
        # server does not model construction or building expansion yet. TSkipGetBushels only adds bushels when
        # the response carries bushelsAdded, which is left out for the same reason.
        elif reqq.functionName in ('FarmQuestService.skipTask', 'FarmQuestService.skipCompleteFriendSetTask'):
            quest_name = reqq['params'][0]
            task_index = reqq['params'][1]
            commands.skip_quest_task(UID, quest_name, task_index)
            resps.append(response)

        # The four client-only skips described above are not charged: the task is still marked done, which is saved,
        # but Farm Cash would be paid for a change that does not survive a login. quests.skip_task is called here
        # rather than through commands.skip_quest_task, which has no way to say so.
        elif reqq.functionName in ('FarmQuestService.skipConstructionBuildingTask',
                                   'FarmQuestService.skipExpandStorageBuildingTask',
                                   'FarmQuestService.skipRewardCreditsTask',
                                   'FarmQuestService.skipGetBushelsTask'):
            quest_name = reqq['params'][0]
            task_index = reqq['params'][1]
            quests.skip_task(player_session(UID), quest_name, task_index, charge_cash=False)
            resps.append(response)

        # client ref.: src/Transactions/Quests/TAskForQuestItem.as, src/Classes/Quest/helperactions/AskForItemByFeedHelperAction.as
        # The quest task "Ask friends" button. The server was supposed to answer with a Facebook feed post
        # (data + ts) for the client to publish, and friends answered it through Facebook, which is gone. A
        # response without data is the case onComplete already treats as "no feed to post" (it only logs a stat).
        # recordQuestItemRequest (TRecordQuestItemRequest.as) follows a published post, so it can never be sent
        # here; it is acknowledged for completeness.
        elif reqq.functionName in ('FarmQuestService.askForQuestItem', 'FarmQuestService.recordQuestItemRequest'):
            resps.append(response)

        elif reqq.functionName == 'FarmQuestService.incrementGenericFarmTask':
            task_action = reqq['params'][0]
            commands.increment_generic_farm_task(UID, task_action)
            resps.append(response)

        # client ref.: src/Transactions/TGenericTransaction.as - the Quest Manager window's Start/End
        # buttons, which send through TGenericTransaction rather than a T*.as of their own.

        elif reqq.functionName == 'FarmQuestService.questManagerStartReplayableQuestChain':
            first_quest_name = reqq['params'][0]
            commands.start_replayable_quest_chain(UID, first_quest_name)
            resps.append(response)

        # client ref.: src/Classes/Quest/FarmQuest.as (skipQuest) - the "complete now" button, also through
        # TGenericTransaction with no callback.
        elif reqq.functionName == 'FarmQuestService.skipEntireQuest':
            quest_name = reqq['params'][0]
            commands.skip_entire_quest(UID, quest_name)
            resps.append(response)

        elif reqq.functionName == 'FarmQuestService.questManagerEndReplayableQuestChain':
            quest_name = reqq['params'][0]
            commands.end_replayable_quest_chain(UID, quest_name)
            resps.append(response)

        # client ref.: src/Managers/PostInitSettings.as - the expired events' end-of-event calls, see
        # commands.feature_end_call. Only these methods: an event's other calls (sinkGold, redeemTask...)
        # are bespoke per event and stay in unhandled.log. The calls seen so far:
        #   AmsterdamInnovationService.grantBonus
        #   AnimalSanctuaryV2Service.startQuest
        #   BoatRushService.startQuest, BoatRushService.featureEnd
        #   BoraBoraInnovationService.startQuest
        #   CanadaInnovationService.startQuest
        #   CocowonderlandInnovationService.startQuest
        #   Dec19InnovationService.grantBonus
        #   FarmersMarketInnovationService.startQuest, FarmersMarketInnovationService.onRedeemStarted
        #   Halloween2019InnovationService.startQuest
        #   IrelandInnovationService.startQuest, IrelandInnovationService.fetchDailyLimit,
        #   IrelandInnovationService.getLeaderboardEntries, IrelandInnovationService.onRedeemStarted
        #   IsraelInnovationService.grantBonus
        #   RussiaInnovationService.grantBonus
        #   SouthindiaInnovationService.grantBonus
        #   TropicalMarketInnovationService.startQuest, TropicalMarketInnovationService.featureEnd,
        #   TropicalMarketInnovationService.onRedeemStarted, TropicalMarketInnovationService.updateEscapeTokensCount,
        #   TropicalMarketInnovationService.initializeTropicEscapeConnection
        #   WinterRacingFeatureService.startQuest, WinterRacingFeatureService.featureEnd
        #   WreathFestivalInnovationService.grantBonus
        elif commands.is_feature_end_call(reqq.functionName):
            method = reqq.functionName.split('.')[1]
            feature_name = reqq['params'][0]
            commands.feature_end_call(UID, method, feature_name)
            resps.append(response)

        elif reqq.functionName in commands.ABSENT_SOCIAL_READS:
            response["data"] = commands.ABSENT_SOCIAL_READS[reqq.functionName]
            resps.append(response)

        elif reqq.functionName in commands.UNRESTORED_SERVICE_CALLS:
            # Raised per call: this call is restored to its savepoint and reports errorType 29.
            raise ValueError(commands.UNRESTORED_SERVICE_CALLS[reqq.functionName])

        else:
            log_unhandled_command(reqq.functionName, reqq['params'])
            resps.append(response)

        # The response object is the one already in resps, so this reaches the client. It runs here rather
        # than where the dict is built so that the quest list reflects whatever the command just did.
        response["metadata"]["QuestComponent"] = commands.quest_component(UID, reqq.functionName)
        response["metadata"]["ActionDrops"] = bushels.take_metadata(player_session(UID))
        response.update(commands.progression_response(UID))

    assert len(resps) == len(reqs)

    return resps

@app.route("/sn_app_url/gifts.php", methods=['GET', 'POST'])
@save_transaction
def sn_app_url_gifts():
    import secrets
    import hmac
    if session.get("UID") not in all_saves_uids():
        return redirect("/")
    uid = session["UID"]
    session.setdefault("gift_token", secrets.token_urlsafe(24))
    message = None
    if request.method == 'POST':
        if not hmac.compare_digest(session["gift_token"], request.form.get("token", "")):
            return Response("Reopen the gift basket and try again.", status=400)
        try:
            with village_transaction(uid):
                result = gifting.send(uid, request.form.get("item", ""),
                                      request.form.getlist("recipients"), free=True)
                save_session(uid)
        except ValueError as error:
            result = {"complete": False}
            message = str(error)
        if not result["complete"] and message is None:
            message = "That farmer is unavailable. Choose another local farm."
        elif result["complete"]:
            return redirect("/sn_app_url/gifts.php?sent=1")
    if request.args.get("sent") == "1":
        message = "Your gift is waiting in your neighbour's inbox. It will keep until they return."
    from items import get_item_by_name
    friends = [friend for friend in social_network_friends(uid) if friend["uid"] in all_saves_uids()]
    return render_template("gifts.html", friends=friends, token=session["gift_token"],
        gifts=[get_item_by_name(name) for name in gifting.FREE_GIFTS], message=message,
        play_url="/ruffle.html" if NATIVE_WRAPPER else "/play.html")

print (" [+] Running server...")

if __name__ == '__main__':
    app.secret_key = os.urandom(24)
    app.root_path = BASE_DIR
    app.template_folder = TEMPLATES_DIR
    app.static_folder = TEMPLATES_DIR
    app.run(host=BIND_HOST, port=BIND_PORT, debug=False, threaded=True)
