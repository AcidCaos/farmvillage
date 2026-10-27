"""conftest.py may only turn a failure into UNRUN when the input is genuinely absent.

Runs real pytest in a throwaway tree that holds the repository's actual
conftest.py plus synthetic modules shaped like the real raising sites. Source-only:
no game files, network or private inputs. The pytest-driven class is reported as
skipped (UNRUN) when pytest is not installed in this Python environment.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
HAVE_PYTEST = importlib.util.find_spec("pytest") is not None
RUNTIME_MESSAGE = "Select the accepted Runtime using FARMVILLAGE_TEST_RUNTIME."
ITEMS_AMF = "FarmVillage/xml/gz/v855038/items_opt.amf"
RULES = "GodBarn/data/rules.json"
PRIVATE_BIN = "FarmVillage/xml/synthetic-private.bin"
ARTIFACT = "FarmVillage/macOS/.build/PortablePreparation/x-final.tar.gz"

SYNTHETIC_ITEMS = '''
import os
ITEMS_AMF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xml/gz/v855038/items_opt.amf")
_cached_items = None
def get_items(mode="none"):
    if mode == "message":
        raise TypeError("a different TypeError")
    return _cached_items["settings"]["items"]["item"]
def other_lookup():
    return _cached_items["settings"]
'''

SYNTHETIC_COMPANION = '''
def _bundle_into(name, path):
    raise ValueError("Missing regular companion resource: " + name)
'''

SYNTHETIC_NEIGHBORHOOD = '''
import unittest
class NeighborhoodRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise RuntimeError("%s")
    def test_runtime_setup(self):
        pass
''' % RUNTIME_MESSAGE

SYNTHETIC_TESTS = '''
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def load(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_items_absent_catalog():
    load("FarmVillage/items.py", "syn_items").get_items()

def test_items_same_message_other_function():
    load("FarmVillage/items.py", "syn_items").other_lookup()

def test_items_other_message():
    load("FarmVillage/items.py", "syn_items").get_items("message")

def test_companion_private_data_resource():
    load("GodBarn/scripts/bundle_companion.py", "syn_comp")._bundle_into("data/rules.json", ROOT / "%(rules)s")

def test_companion_static_resource_is_a_real_defect():
    load("GodBarn/scripts/bundle_companion.py", "syn_comp")._bundle_into("static/index.html", ROOT / "GodBarn/static/index.html")

def test_companion_data_file_not_listed_as_private():
    load("GodBarn/scripts/bundle_companion.py", "syn_comp")._bundle_into("data/other.json", ROOT / "GodBarn/data/other.json")

def test_runtime_message_raised_from_another_file():
    raise RuntimeError("%(runtime)s")

def test_built_artifact():
    raise FileNotFoundError(2, "No such file or directory", str(ROOT / "%(artifact)s"))

def test_missing_file_elsewhere():
    raise FileNotFoundError(2, "No such file or directory", str(ROOT / "elsewhere/missing.bin"))

def test_listed_private_path():
    raise FileNotFoundError(2, "No such file or directory", str(ROOT / "%(private)s"))

def test_genuine_assertion_failure():
    assert 1 == 2

def test_genuine_other_exception():
    1 / 0

def test_absent_input_hidden_behind_an_assertion():
    try:
        raise FileNotFoundError(2, "No such file or directory", str(ROOT / "%(private)s"))
    except FileNotFoundError as error:
        raise AssertionError("a real problem that must not be hidden") from error
''' % {"rules": RULES, "runtime": RUNTIME_MESSAGE, "artifact": ARTIFACT, "private": PRIVATE_BIN}

# What a public clone shows: every input is absent.
EXPECTED_UNRUN = {
    "test_items_absent_catalog": "UNRUN: needs private input " + ITEMS_AMF,
    "test_companion_private_data_resource": "UNRUN: needs private input " + RULES,
    "test_built_artifact": "UNRUN: needs built artifact " + ARTIFACT,
    "test_listed_private_path": "UNRUN: needs private input " + PRIVATE_BIN,
    "test_runtime_setup": "UNRUN: needs an accepted Runtime",
}
EXPECTED_FAILURES_WHEN_ABSENT = {
    "test_items_same_message_other_function", "test_items_other_message",
    "test_companion_static_resource_is_a_real_defect", "test_companion_data_file_not_listed_as_private",
    "test_runtime_message_raised_from_another_file", "test_missing_file_elsewhere",
    "test_genuine_assertion_failure", "test_genuine_other_exception", "test_absent_input_hidden_behind_an_assertion",
}


class SignatureSitesStillExist(unittest.TestCase):
    """If a raising site is renamed the hook silently stops matching; catch that early."""

    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_items_site(self):
        text = self.read("FarmVillage/items.py")
        self.assertIn("def get_items(", text)
        self.assertIn("ITEMS_AMF =", text)

    def test_companion_site(self):
        text = self.read("GodBarn/scripts/bundle_companion.py")
        self.assertIn("def _bundle_into(", text)
        self.assertIn('"Missing regular companion resource: " + name', text)
        self.assertIn("path = root / name", text)

    def test_runtime_site(self):
        self.assertIn(RUNTIME_MESSAGE, self.read("FarmVillage/portable/neighborhood/test_neighborhood_host.py"))
        self.assertIn("FARMVILLAGE_TEST_RUNTIME", self.read("conftest.py"))

    def test_private_inputs_list_names_the_files_the_hook_relies_on(self):
        listed = json.loads(self.read("PrivateInputs.expected.json"))["files"]
        for name in (ITEMS_AMF, RULES):
            self.assertIn(name, listed)


@unittest.skipUnless(HAVE_PYTEST, "UNRUN: pytest is not installed in this Python environment (python -m pip install pytest)")
class ConftestUnrunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="fv-conftest-unrun-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.tree = Path(cls.temporary.name).resolve()

    def build(self, name):
        root = self.tree / name
        for source in ("conftest.py", "pytest.ini"):
            shutil.copyfile(ROOT / source, root_file(root, source))
        listed = {ITEMS_AMF: {}, RULES: {}, PRIVATE_BIN: {}}
        root_file(root, "PrivateInputs.expected.json").write_text(json.dumps({"files": listed}))
        for relative, text in (("FarmVillage/items.py", SYNTHETIC_ITEMS),
                               ("GodBarn/scripts/bundle_companion.py", SYNTHETIC_COMPANION),
                               ("FarmVillage/portable/neighborhood/test_neighborhood_host.py", SYNTHETIC_NEIGHBORHOOD),
                               ("FarmVillage/macOS/Tests/test_signatures.py", SYNTHETIC_TESTS)):
            root_file(root, relative).write_text(textwrap.dedent(text))
        return root

    def run_pytest(self, root, environment=None):
        env = {key: value for key, value in os.environ.items()
               if key not in ("FARMVILLAGE_TEST_RUNTIME", "PYTEST_ADDOPTS", "PYTHONPATH")}
        env.update(environment or {}, PYTHONDONTWRITEBYTECODE="1")
        report = root / "junit.xml"
        subprocess.run([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--junitxml=" + str(report),
                        "FarmVillage", "GodBarn"], cwd=root, env=env, capture_output=True, text=True, timeout=120)
        outcomes = {}
        for case in ET.parse(report).getroot().iter("testcase"):
            skipped, failed = case.find("skipped"), [case.find("failure"), case.find("error")]
            if skipped is not None:
                outcomes[case.get("name")] = ("skipped", skipped.get("message", ""))
            elif any(item is not None for item in failed):
                outcomes[case.get("name")] = ("failed", "")
            else:
                outcomes[case.get("name")] = ("passed", "")
        return outcomes

    def test_every_signature_is_unrun_when_its_input_is_absent_and_nothing_else_is_hidden(self):
        outcomes = self.run_pytest(self.build("absent"))
        for name, reason in EXPECTED_UNRUN.items():
            with self.subTest(name):
                kind, message = outcomes[name]
                self.assertEqual(kind, "skipped")
                self.assertTrue(message.startswith(reason), message)
        for name in EXPECTED_FAILURES_WHEN_ABSENT:
            with self.subTest(name):
                self.assertEqual(outcomes[name][0], "failed")
        self.assertEqual(set(outcomes), set(EXPECTED_UNRUN) | EXPECTED_FAILURES_WHEN_ABSENT)

    def test_the_same_signatures_still_fail_when_the_input_is_present(self):
        root = self.build("present")
        for relative in (ITEMS_AMF, RULES, PRIVATE_BIN, ARTIFACT):
            root_file(root, relative).write_bytes(b"present")
        outcomes = self.run_pytest(root, {"FARMVILLAGE_TEST_RUNTIME": str(root)})
        for name in EXPECTED_UNRUN:
            with self.subTest(name):
                self.assertEqual(outcomes[name][0], "failed", outcomes[name])

    def test_an_ambiguous_runtime_is_a_failure_not_an_absence(self):
        root = self.build("ambiguous")
        for name in ("a-final.tar.gz", "b-final.tar.gz"):
            root_file(root, "FarmVillage/macOS/.build/PortablePreparation/" + name).write_bytes(b"x")
        self.assertEqual(self.run_pytest(root)["test_runtime_setup"][0], "failed")

    def test_a_configured_runtime_variable_alone_makes_it_a_failure_not_an_absence(self):
        root = self.build("variable")
        self.assertEqual(self.run_pytest(root, {"FARMVILLAGE_TEST_RUNTIME": str(root)})["test_runtime_setup"][0], "failed")

    def test_a_present_artifact_directory_alone_does_not_hide_a_missing_file_elsewhere(self):
        root = self.build("elsewhere")
        root_file(root, "FarmVillage/macOS/.build/PortablePreparation/keep").write_bytes(b"x")
        self.assertEqual(self.run_pytest(root)["test_missing_file_elsewhere"][0], "failed")


def root_file(root, relative):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


if __name__ == "__main__":
    unittest.main()
