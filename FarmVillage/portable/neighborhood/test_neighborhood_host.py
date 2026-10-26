"""Real sealed-runtime neighborhood checks using disposable farms only.

Run in the portable game's Python environment:
    python -B -m unittest discover -s portable/neighborhood -p test_neighborhood_host.py -v

FARMVILLAGE_TEST_RUNTIME may point to an already extracted accepted Runtime.
WAVE2_GODBARN_ROOT may select the matching companion source explicitly.
Otherwise the prepared archive is extracted into a temporary directory. Nothing
opens a browser/socket or reads/writes the player's existing saves.
"""

from contextlib import redirect_stdout
import copy
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[2]
HOSTING = SOURCE / "portable" / "Linux"
ORIGIN = "http://192.168.50.80:5501"
PLAYER = "00000000-0000-4000-8000-000000000001"
RESIDENTS = [f"00000000-0000-4000-8000-{index:012d}" for index in range(2, 7)]


def load_file_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NeighborhoodRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="farmvillage-neighborhood-tests-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        runtime_override = os.environ.get("FARMVILLAGE_TEST_RUNTIME")
        if runtime_override:
            cls.runtime = Path(runtime_override).resolve()
        else:
            archives = sorted((SOURCE / "macOS/.build/PortablePreparation").glob("*-final.tar.gz"))
            if len(archives) != 1:
                raise RuntimeError("Select the accepted Runtime using FARMVILLAGE_TEST_RUNTIME.")
            with tarfile.open(archives[0], "r:gz") as archive:
                archive.extractall(cls.root / "accepted-release", filter="data")
            cls.runtime = next((cls.root / "accepted-release").glob("*/Runtime"))
        if not (cls.runtime / "server.py").is_file():
            raise RuntimeError("The accepted Runtime is missing server.py.")

        cls.data = cls.root / "data"
        cls.saves = cls.data / "saves"
        cls.saves.mkdir(parents=True)
        templates = cls.data / "neighborhood/templates"
        templates.mkdir(parents=True)
        shutil.copyfile(cls.runtime / "villages/initial.json", templates / "initial.json")
        cls.initial = json.loads((templates / "initial.json").read_text())
        cls.manifest = {
            "schemaVersion": 1, "updateId": "bifrost-neighborhood-test-v1",
            "playerUid": PLAYER,
            "residents": [{"uid": uid, "name": name, "theme": theme}
                          for uid, name, theme in zip(RESIDENTS,
                              ["Poppy", "Production", "Animals", "Seasonal", "Starter"],
                              ["flowers", "production", "animals", "seasonal", "starter"])],
            "saveFiles": {uid: uid + ".save.json" for uid in [PLAYER, *RESIDENTS]},
        }
        (cls.data / "neighborhood/manifest.json").write_text(json.dumps(cls.manifest))
        cls.write_farms()

        environment = mock.patch.dict(os.environ, {
            "FARMVILLAGE_DATA_DIR": str(cls.data), "FARMVILLAGE_NATIVE": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        environment.start()
        cls.addClassCleanup(environment.stop)
        cls.original_path = sys.path[:]
        sys.path.insert(0, str(cls.runtime))
        cls.addClassCleanup(setattr, sys, "path", cls.original_path)
        sys.dont_write_bytecode = True
        cls.original_cwd = Path.cwd()
        os.chdir(cls.runtime)
        cls.addClassCleanup(os.chdir, cls.original_cwd)

        cls.host = load_file_module("neighborhood_host_tests", HOSTING / "neighborhood_host.py")
        cls.runner = load_file_module("neighborhood_lan_runner_tests", HOSTING / "server_runner.py")
        import assets
        cls.loaded_manifest = cls.host.activate_neighborhood(cls.data, cls.runtime)
        with mock.patch.object(assets, "check_assets"), mock.patch.object(sys, "argv", [
                "server.py", "--host", "192.168.50.80", "--port", "5501", "--public-url", ORIGIN]):
            with redirect_stdout(io.StringIO()):
                cls.server = importlib.import_module("server")
        cls.player = importlib.import_module("player")
        cls.bundle = importlib.import_module("bundle")
        cls.persistence = importlib.import_module("persistence")
        cls.server.app.root_path = str(cls.runtime)
        cls.server.app.template_folder = str(cls.runtime / "templates")
        cls.server.app.static_folder = str(cls.runtime / "templates")
        cls.server.app.config["TESTING"] = True
        cls.runner.register_lan_access(cls.server.app, origin=ORIGIN,
                                      secret=b"n" * 32, password_hash="pbkdf2:sha256:1$s$unused")
        companion = Path(os.environ.get("WAVE2_GODBARN_ROOT", str(SOURCE.parent / "GodBarn"))).resolve()
        overlay = companion / "integration.py"
        cls.provide_overlay_siblings(overlay)
        integration = cls.runner.load_integration(cls.runtime, overlay)
        cls.bridge = integration.register_god_barn(cls.server.app, game_server=cls.server,
            player_module=cls.player, bundle_module=cls.bundle,
            farming_module=importlib.import_module("barn_actions"), root=cls.runtime / "GodBarn")
        cls.host.configure_neighborhood(cls.server, cls.player, cls.loaded_manifest)
        cls.preloader = load_file_module("neighborhood_preloader_tests", HOSTING / "preloader_timing.py")
        cls.preloader.configure_preloader(cls.server.app)

    @classmethod
    def provide_overlay_siblings(cls, overlay):
        """Let the frozen Runtime's GodBarn package see the overlay's own sibling modules.

        The accepted archive predates GodBarn/catalog_tools.py, which the live
        integration overlay imports. Modules the archive ships still win; the
        overlay's folder is only a fallback for names the archive lacks.
        """
        package = importlib.import_module("GodBarn")
        if importlib.util.find_spec("GodBarn.catalog_tools") is not None:
            return
        folder = str(overlay.parent)
        package.__path__.append(folder)
        cls.addClassCleanup(package.__path__.remove, folder)

    @classmethod
    def write_farms(cls):
        for index, uid in enumerate([PLAYER, *RESIDENTS]):
            farm = copy.deepcopy(cls.initial)
            farm["userInfo"]["player"]["userId"] = uid
            farm["userInfo"]["attr"]["name"] = "Jordan" if index == 0 else cls.manifest["residents"][index - 1]["name"]
            farm["flashHotParams"]["ZYNGA_USER_ID"] = uid
            farm["userInfo"]["firstDayTimestamp"] = 1
            farm["world"]["uid"] = "world-" + uid
            (cls.saves / (uid + ".save.json")).write_text(json.dumps(farm))

    def setUp(self):
        self.write_farms()
        with redirect_stdout(io.StringIO()):
            self.player.load_saves()
        self.bridge.epochs.clear()
        self.bridge.rotated.clear()
        self.bridge.parked.clear()
        self.bridge.park_owners.clear()
        self.bridge.previews.clear()
        self.client = self.server.app.test_client()
        with self.client.session_transaction(base_url=ORIGIN) as session:
            session[self.runner.AUTH_KEY] = True
            session["UID"] = PLAYER

    def get(self, path, **kwargs):
        return self.client.get(path, base_url=ORIGIN, **kwargs)

    def post(self, path, **kwargs):
        headers = {"Origin": ORIGIN, **kwargs.pop("headers", {})}
        return self.client.post(path, base_url=ORIGIN, headers=headers, **kwargs)

    @staticmethod
    def command(name, params=(), sequence=1):
        import pyamf
        return pyamf.ASObject(functionName=name, params=list(params), sequence=sequence)

    def gateway(self, commands, uid=PLAYER):
        import pyamf
        from pyamf import remoting
        envelope = remoting.Envelope(pyamf.AMF0)
        envelope["/1"] = remoting.Request("FarmService", body=[{"uid": uid}, commands])
        with redirect_stdout(io.StringIO()):
            return self.post("/flashservices/gateway.php", data=remoting.encode(envelope).getvalue(),
                content_type="application/x-amf", headers={"X-God-Barn-Epoch": self.bridge._epoch(uid)})

    @staticmethod
    def results(response):
        from pyamf import remoting
        return remoting.decode(response.data).bodies[0][1].body["data"]

    def test_external_templates_remove_legacy_neighbor_without_changing_sealed_runtime(self):
        self.assertEqual(Path(self.bundle.VILLAGES_DIR), self.data / "neighborhood/templates")
        self.assertEqual({path.name for path in Path(self.bundle.VILLAGES_DIR).iterdir()}, {"initial.json"})
        self.assertEqual((Path(self.bundle.VILLAGES_DIR) / "initial.json").read_bytes(),
                         (self.runtime / "villages/initial.json").read_bytes())
        self.assertTrue((self.runtime / "villages/AcidCaos.json").is_file())
        self.assertNotIn("AcidCaos", self.player.all_uids())

    def test_friend_lists_contain_exactly_five_matching_residents(self):
        self.assertEqual(set(self.player.all_saves_uids()), {PLAYER, *RESIDENTS})
        self.assertEqual(set(self.player.neighbor_uids(PLAYER)), set(RESIDENTS))
        self.assertEqual(len(self.player.neighbor_uids(PLAYER)), 5)
        self.assertEqual({entry["uid"] for entry in self.player.neighbor_metadata(PLAYER)}, set(RESIDENTS))
        self.assertEqual({entry["uid"] for entry in self.player.social_network_friends(PLAYER)}, set(RESIDENTS))

    def test_served_player_has_bounded_loading_and_photo_intervals(self):
        page = self.get("/ruffle.html")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.data.count(b"fotdChangeTime=5"), 1)
        # The recovered 111k-item catalog can exceed Ruffle's 15-second script
        # default in Chromium. Keep a finite, explicit browser allowance.
        budget = self.preloader.SCRIPT_EXECUTION_SECONDS
        self.assertGreater(budget, 15)
        self.assertLessEqual(budget, 120)
        self.assertRegex(page.data, rb"maxExecutionDuration\s*:\s*" + re.escape(str(budget).encode()) + rb"\b")
        self.assertIn((self.server.RUFFLE_PUBLIC_PATH + "ruffle.js").encode(), page.data)

    def test_selector_and_login_only_allow_player_but_keep_residents_writable(self):
        self.assertEqual([entry["uid"] for entry in self.player.all_saves_info()], [PLAYER])
        self.assertEqual([entry["uid"] for entry in self.server.all_saves_info()], [PLAYER])
        with redirect_stdout(io.StringIO()):
            page = self.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(('value="' + PLAYER + '"').encode(), page.data)
        for uid in RESIDENTS:
            self.assertNotIn(('value="' + uid + '"').encode(), page.data)
            self.assertEqual(self.post("/", data={"UID": uid, "RUFFLE": "1"}).status_code, 403)
            self.assertIsNotNone(self.player.session(uid))
        self.assertEqual(self.get("/new.html", headers={"Referer": ORIGIN + "/"}).status_code, 403)
        with redirect_stdout(io.StringIO()):
            response = self.post("/", data={"UID": PLAYER, "RUFFLE": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/ruffle.html")

    def test_resident_cannot_submit_direct_player_commands(self):
        for uid in RESIDENTS:
            path = self.saves / (uid + ".save.json")
            before = path.read_bytes()
            response = self.gateway([self.command("UserService.incrementActionCount", ["forbidden"])], uid=uid)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(path.read_bytes(), before)

    def test_god_barn_only_exposes_player_and_rejects_resident_edits(self):
        state = self.get("/god-barn/api/state").get_json()
        self.assertEqual([farm["id"] for farm in state["farms"]], [PLAYER])
        self.assertEqual(state["farm"]["id"], PLAYER)
        for uid in RESIDENTS:
            original = (self.saves / (uid + ".save.json")).read_bytes()
            response = self.post("/god-barn/api/select", json={"id": uid},
                                 headers={"X-God-Barn-Token": state["csrf"]})
            self.assertIn(response.status_code, (403, 404))
            self.assertIn(self.get("/god-barn/api/export?id=" + uid).status_code, (403, 404))
            self.assertEqual((self.saves / (uid + ".save.json")).read_bytes(), original)

    def test_actual_amf_visits_all_residents_and_returns_to_player(self):
        for uid in RESIDENTS:
            response = self.gateway([self.command("WorldService.loadNeighborWorld", [uid])])
            self.assertEqual(response.status_code, 200, response.data[:200])
            result = self.results(response)[0]["data"]
            self.assertEqual(result["world"]["uid"], "world-" + uid)
            self.assertEqual(result["user"]["firstName"], self.player.session(uid)["userInfo"]["attr"]["name"])
            home = self.gateway([self.command("WorldService.loadOwnWorld", [""])])
            self.assertEqual(home.status_code, 200, home.data[:200])
            self.assertEqual(self.results(home)[0]["data"]["world"]["uid"], "world-" + PLAYER)

    def test_actual_amf_help_commits_both_farms_and_survives_process_reload(self):
        uid = RESIDENTS[0]
        player_path = self.saves / (PLAYER + ".save.json")
        host_path = self.saves / (uid + ".save.json")
        untouched = {other: (self.saves / (other + ".save.json")).read_bytes() for other in RESIDENTS[1:]}
        host = self.player.session(uid)
        obj = copy.deepcopy(next(obj for obj in host["world"]["objectsArray"] if obj["className"] == "Plot"))
        obj.update(state="plowed", neighborhoodHelpMarker="persisted-help")
        gold = self.player.session(PLAYER)["userInfo"]["player"]["gold"]
        response = self.gateway([self.command("WorldService.performAction", [
            "neighborAct", obj, [{"hostId": uid, "actionType": "plow"}]
        ])])
        self.assertEqual(response.status_code, 200, response.data[:200])
        on_disk = json.loads(host_path.read_text())
        self.assertEqual(next(item for item in on_disk["world"]["objectsArray"] if item["id"] == obj["id"])
                         ["neighborhoodHelpMarker"], "persisted-help")
        self.assertGreater(json.loads(player_path.read_text())["userInfo"]["player"]["gold"], gold)
        for other, original in untouched.items():
            self.assertEqual((self.saves / (other + ".save.json")).read_bytes(), original)

        program = """import importlib, json, pathlib, sys
sys.dont_write_bytecode = True
sys.path[:0] = [sys.argv[1], sys.argv[2]]
import neighborhood_host
neighborhood_host.activate_neighborhood(pathlib.Path(sys.argv[3]), pathlib.Path(sys.argv[1]))
owner, resident = sys.argv[4:6]
import assets
assets.check_assets = lambda: None
sys.argv = ['server.py']
import server, player
farm = player.session(resident)
assert any(obj.get('neighborhoodHelpMarker') == 'persisted-help' for obj in farm['world']['objectsArray'])
assert len(player.neighbor_uids(owner)) == 5
print('NEIGHBORHOOD_RELOAD_OK')
"""
        result = subprocess.run([sys.executable, "-B", "-c", program, str(self.runtime), str(HOSTING), str(self.data), PLAYER, uid],
                                cwd=self.runtime, env=dict(os.environ), capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-2000:])
        self.assertIn("NEIGHBORHOOD_RELOAD_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
