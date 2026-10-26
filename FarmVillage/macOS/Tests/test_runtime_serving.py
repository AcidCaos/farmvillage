"""Execute the real runtime route against tiny source and installed packages."""

import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from flask import Flask, Response, render_template_string

ROOT = Path(__file__).resolve().parents[2]
SERVER_FILE = ROOT / "server.py"
TEMPLATE_FILE = ROOT / "templates/ruffle.html"
sys.path.insert(0, str(ROOT))
import runtime_compatibility as runtime


class RuntimeServingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="farmvillage-runtime-route-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.payload = self.root / "payload"
        self.runtime_id = "0.7.1-farmvillage-route-fixture"
        self.source = self.payload / "ruffle_runtime" / self.runtime_id
        self.source.mkdir(parents=True)
        self.values = {"ruffle.js": b"reviewed loader", "core.wasm": b"\x00asm\x01\x00\x00\x00"}
        for name, value in self.values.items():
            (self.source / name).write_bytes(value)
        manifest = {"schema": 1, "runtime_id": self.runtime_id, "version": "0.7.1",
                    "upstream_commit": "89a7049965f3090e706265670df309a5128233ac",
                    "files": {name: hashlib.sha256(value).hexdigest() for name, value in self.values.items()}}
        raw = json.dumps(manifest, sort_keys=True).encode()
        (self.source / runtime.MANIFEST_NAME).write_bytes(raw)
        self.release = runtime.RuntimeRelease(self.runtime_id, "0.7.1", manifest["upstream_commit"], hashlib.sha256(raw).hexdigest())
        patcher = mock.patch.object(runtime, "ACTIVE_RELEASE", self.release)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.verified = runtime.verify_runtime(self.source)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True)
        # Compile the actual decorated function without importing unrelated
        # multi-gigabyte game catalogs or opening a server socket.
        tree = ast.parse(SERVER_FILE.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "ruffle_runtime")
        self.namespace = {"app": self.app, "runtime_compatibility": runtime,
                          "VERIFIED_RUFFLE": self.verified, "Response": Response}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(SERVER_FILE), "exec"), self.namespace)
        self.client = self.app.test_client()

    def url(self, name):
        return runtime.public_path() + name

    def test_source_and_installed_runtime_serve_identical_versioned_bytes(self):
        source = {}
        for name, value in self.values.items():
            response = self.client.get(self.url(name))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, value)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.mimetype, "application/wasm" if name.endswith(".wasm") else "text/javascript")
            source[name] = response.data
        data = self.root / "profile"
        data.mkdir()
        installed = runtime.install_runtime(self.payload, data)
        self.namespace["VERIFIED_RUFFLE"] = runtime.verify_runtime(installed)
        for name, value in source.items():
            self.assertEqual(self.client.get(self.url(name)).data, value)

    def test_poststartup_replacement_or_unknown_resource_cannot_serve_mixed_runtime(self):
        (self.source / "ruffle.js").write_bytes(b"unreviewed replacement loader")
        response = self.client.get(self.url("ruffle.js"))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"unreviewed replacement", response.data)
        for path in ("/ruffle/0.7.1/ruffle.js", self.url("unknown.js"), self.url(runtime.MANIFEST_NAME), self.url("../ruffle.js")):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_both_actual_template_modes_use_matching_local_version_paths(self):
        head = TEMPLATE_FILE.read_text().split("</head>", 1)[0] + "</head>"
        with self.app.app_context():
            for native in (False, True):
                with self.subTest(native=native):
                    rendered = render_template_string(head, native_wrapper=native, ruffle_public_path=runtime.public_path())
                    self.assertIn('src="' + self.url("ruffle.js") + '"', rendered)
                    self.assertIn('publicPath: "' + runtime.public_path() + '"', rendered)
                    self.assertNotIn("unpkg.com", rendered)

    def test_frozen_resource_selection_uses_meipass_and_native_override_remains_explicit(self):
        server_tree = ast.parse(SERVER_FILE.read_text())
        imported = next(node for node in server_tree.body if isinstance(node, ast.ImportFrom) and node.module == "bundle")
        self.assertIn("TMP_BUNDLED_DIR", [alias.name for alias in imported.names])
        # server.py derives the directory from the selected release, so run both real
        # statements, in source order, rather than a stand-in for the release.
        wanted = ("_runtime_release", "_runtime_directory")
        selection = [node for node in server_tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id in wanted for target in node.targets)]
        self.assertEqual([node.targets[0].id for node in selection], list(wanted),
                         "server.py no longer selects the runtime release and then its directory in this order")
        # No installer pin: the strict default release is selected without touching disk.
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("FARMVILLAGE_PREPARED_RUNTIME_PIN_SHA256", None)
        bundle_source = (ROOT / "bundle.py").read_text()
        extracted = str(self.payload)
        bundle_namespace = {"__name__": "isolated_frozen_bundle", "__file__": str(self.root / "executable/bundle/bundle.py")}
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "_MEIPASS", extracted, create=True):
            exec(compile(bundle_source, str(ROOT / "bundle.py"), "exec"), bundle_namespace)
        self.assertEqual(bundle_namespace["TMP_BUNDLED_DIR"], extracted)
        self.assertNotEqual(bundle_namespace["BASE_DIR"], extracted)
        namespace = dict(bundle_namespace, RUFFLE_DIR=None, Path=Path, runtime_compatibility=runtime, os=os)
        selection_code = compile(ast.Module(body=selection, type_ignores=[]), str(SERVER_FILE), "exec")
        exec(selection_code, namespace)
        self.assertEqual(namespace["_runtime_release"], self.release)
        self.assertEqual(namespace["_runtime_directory"], self.source)
        runtime.verify_runtime(namespace["_runtime_directory"])
        profile = self.root / "native-profile"
        profile.mkdir()
        installed = runtime.install_runtime(self.payload, profile)
        namespace["RUFFLE_DIR"] = str(installed)
        exec(selection_code, namespace)
        self.assertEqual(namespace["_runtime_directory"], installed)



if __name__ == "__main__":
    unittest.main()
