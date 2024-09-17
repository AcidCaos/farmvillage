print (" [+] Loading basics...")
import os
import sys
import json

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

print (" [+] Loading players...")
from player import load_saves, load_static_villages, all_saves_info, all_saves_uids, save_info, new_village
load_saves()
print (" [+] Loading static villages...")
load_static_villages()

print (" [+] Loading server...")
from flask import Flask, render_template, send_from_directory, request, Response, redirect, session
from flask.debughelpers import attach_enctype_error_multidict
from werkzeug.utils import safe_join
from pyamf import remoting
import pyamf

import commands
from engine import timestamp_now
from version import version_name
from bundle import BASE_DIR, ASSETS_DIR, EMBEDS_DIR, ASSETHASH_DIR, PATCHED_ASSETS_DIR, TEMPLATES_DIR, XML_DIR
from player import save_session

BIND_IP = "127.0.0.1"
BIND_PORT = 5500

app: Flask = Flask(__name__)

print (" [+] Configuring server routes...")

# Templates

@app.route("/", methods=['GET', 'POST'])
def login():
    # Log out previous session
    session.pop('UID', default=None)
    # Reload saves (not static villages nor quests). Allows saves modification without server reset
    load_saves()
    # If logging in, set session UID, and go to play
    if request.method == 'POST':
        session['UID'] = request.form['UID']
        print("[LOGIN] UID:", request.form['UID'])
        return redirect("/play.html")
    # Login page
    if request.method == 'GET':
        saves_info = all_saves_info()
        return render_template("login.html",
            saves_info=saves_info,
            version=version_name
        )

@app.route("/play.html", methods=['GET'])
def play():
    if 'UID' not in session:
        return redirect("/")
    
    if session['UID'] not in all_saves_uids():
        return redirect("/")
    
    UID = session['UID']
    print("[PLAY] UID:", UID)
    return render_template("play.html", 
        version=version_name,
        base_url=f"http://{BIND_IP}:{BIND_PORT}",
        server_time=timestamp_now(),
        debug="true",
        user={
            "uid": UID,
            "name": save_info(UID)["name"]
        },
        save_info=save_info(UID)
    )

@app.route("/new.html")
def new():
    session['UID'] = new_village()
    return redirect("play.html")

@app.route("/img/<path:path>", methods=['GET'])
def img(path):
    return send_from_directory(TEMPLATES_DIR + "/img", path)

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

@app.route("/embeds/<path:path>", methods=['GET'])
def embeds(path):
    return send_from_directory(EMBEDS_DIR, path)

@app.route("/assethash/<path:path>", methods=['GET'])
def assethash_path(path):
    return send_from_directory(ASSETHASH_DIR, path, mimetype="application/x-amf")

@app.route("/xml/<path:path>", methods=['GET'])
def xml(path):
    return send_from_directory(XML_DIR, path, mimetype='text/xml')

# @app.route("/assets/Environment/grass_themeBackground_7.swf", methods=['GET'])
# def stub_grass_themeBackground_7():
#     return send_from_directory(ASSETS_DIR, "Environment/02de7becb766242e421e1430176f55a2.swf", mimetype='text/xml')

@app.route("/assets/<path:path>", methods=['GET'])
def assets(path):
    return send_from_directory(ASSETS_DIR, path)

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
    return redirect("/")

@app.route("/flashservices/gateway.php", methods=['POST'])
def flashservices_gateway():
    resp_msg = remoting.decode(request.data)
    # print("[+] Gateway AMF3 Request:", resp_msg)
    resps = []
    reqs = resp_msg.bodies[0][1].body[1]
    for reqq in reqs:

        print(f"[+] {reqq.functionName}: {reqq['params']}")
        UID = resp_msg.bodies[0][1].body[0]["uid"]

        response = {
            "errorType": 0,
            "errorData": None,
            "isDST": 0,
            "sequenceNumber": reqq["sequence"],
            "worldTime": timestamp_now(),
            "metadata": {
                "QuestComponent": {},
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
        
        elif reqq.functionName == 'FriendSetService.getBatchFriendSetData':
            response["data"] = []
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

        elif reqq.functionName == 'UserService.incrementActionCount':
            action = reqq['params'][0]
            commands.increment_action_count(UID, action)
            resps.append(response)
        
        elif reqq.functionName == 'UserService.resetActionCount':
            action = reqq['params'][0]
            commands.reset_action_count(UID, action)
            resps.append(response)

        elif reqq.functionName == 'UserService.setSeenFlag':
            flag = reqq['params'][0]
            commands.set_seen_flag(UID, flag)
            resps.append(response)

        elif reqq.functionName == 'UserService.resetSystemNotifications':
            resps.append(response)
        
        elif reqq.functionName == 'UserContentService.onCreateImage':
            name = reqq['params'][0]
            png_b64 = reqq['params'][1]
            feed_post = reqq['params'][2]
            if name == "avatar_appearance":
                commands.set_avatar_appearance(UID, name, png_b64, feed_post)
            resps.append(response)

        elif reqq.functionName == 'UserService.saveOptions':
            options = reqq['params'][0]
            commands.save_options(UID, options)
            resps.append(response)
        
        elif reqq.functionName == 'WorldService.performAction':
            actionName = reqq['params'][0]
            m_save = reqq['params'][1]
            params = reqq['params'][2]
            object_id = commands.world_perform_action(UID, actionName, m_save, params)
            # This infroms the client of the new (non-temporary) object ID
            response["id"] = object_id
            response["data"] = {"id": object_id} # onMultiComplete and onComplete treat this differently. This is a temporary workaround
            resps.append(response)
        
        elif reqq.functionName == 'UserService.updateFeatureFrequencyTimestamp':
            feature = reqq['params'][0]
            commands.update_feature_frequency_timestamp(UID, feature)
            resps.append(response)
        
        elif reqq.functionName == 'UserService.publishUserAction':
            action = reqq['params'][0]
            params = reqq['params'][1]
            commands.publish_user_actions(UID, action, params)
            resps.append(response)

        else:
            resps.append(response)
    
    assert len(resps) == len(reqs)

    save_session(UID)

    emsg = {
        "serverTime": timestamp_now(),
        "errorType": 0,
        "data": resps
    }

    req = remoting.Response(emsg)
    ev = remoting.Envelope(pyamf.AMF0)
    ev[resp_msg.bodies[0][0]] = req
    # print("[+] Response:", ev)

    ret_body = remoting.encode(ev, strict=True, logger=True).getvalue()
    return Response(ret_body, mimetype='application/x-amf')

@app.route("/sn_app_url/gifts.php", methods=['GET'])
def sn_app_url_gifts():
    template = request.args.get("template")
    ref = request.args.get("ref")
    return "{}"

print (" [+] Running server...")

if __name__ == '__main__':
    app.secret_key = os.urandom(24)
    app.root_path = BASE_DIR
    app.template_folder = TEMPLATES_DIR
    app.static_folder = TEMPLATES_DIR
    app.run(host=BIND_IP, port=BIND_PORT, debug=False, threaded=True)
