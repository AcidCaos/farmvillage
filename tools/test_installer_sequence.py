"""The Bifrost guide and the setup wizard must tell the same story.

Source-only: reads documents and code, never runs the wizard, never touches a
service, a home folder or a network. Failing here means one side drifted.
"""
import ast
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / 'BIFROST_SETUP.md'
WIZARD = ROOT / 'tools/setup-wizard.py'
RUNNER = ROOT / 'FarmVillage/portable/Linux/server_runner.py'
SERVICE_SCRIPT = ROOT / 'FarmVillage/portable/Linux/install-service.sh'
REQUIREMENTS = ROOT / 'FarmVillage/requirements.txt'
NUMBER_WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}


def wizard_steps():
    """(step, title) for every say(...) call, in source order."""
    tree = ast.parse(WIZARD.read_text(encoding='utf-8'))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'say'
             and len(node.args) >= 2 and isinstance(node.args[0], ast.Constant) and isinstance(node.args[1], ast.Constant)]
    calls.sort(key=lambda node: (node.lineno, node.col_offset))
    return [(node.args[0].value, node.args[1].value) for node in calls]


def wizard_declared_total():
    """The N in the wizard's 'Step %d of N' banner."""
    tree = ast.parse(WIZARD.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'say':
            for constant in ast.walk(node):
                if isinstance(constant, ast.Constant) and isinstance(constant.value, str):
                    found = re.search(r'Step %d of (\d+)', constant.value)
                    if found:
                        return int(found.group(1))
    raise AssertionError('setup-wizard.py say() no longer prints a "Step %d of N" banner')


def guide_section():
    text = GUIDE.read_text(encoding='utf-8')
    found = re.search(r'^## The same (\w+) steps as the wizard\s*$(.*?)(?=^## )', text, re.S | re.M)
    if not found:
        raise AssertionError('BIFROST_SETUP.md lost its "The same <number> steps as the wizard" section')
    return found.group(1), found.group(2)


def guide_steps():
    _, body = guide_section()
    return [(int(number), title.rstrip('.').strip())
            for number, title in re.findall(r'^(\d+)\. \*\*(.+?)\*\*', body, re.M)]


class InstallerSequenceTests(unittest.TestCase):
    def test_wizard_steps_are_numbered_one_to_n_in_source_order(self):
        steps = wizard_steps()
        self.assertEqual([number for number, _ in steps], list(range(1, len(steps) + 1)))
        self.assertEqual(len({title for _, title in steps}), len(steps), 'Duplicate wizard step title')

    def test_guide_step_titles_match_wizard_titles_exactly_and_in_order(self):
        self.assertEqual(guide_steps(), wizard_steps())

    def test_every_step_count_in_text_agrees_with_the_wizard(self):
        total = len(wizard_steps())
        self.assertEqual(wizard_declared_total(), total, 'The wizard banner says a different total than it has steps')
        word, _ = guide_section()
        self.assertEqual(NUMBER_WORDS[word], total, 'BIFROST_SETUP.md heading')
        for relative in ('BIFROST_SETUP.md', 'docs/PLAY_ON_SERVER.md', 'START_HERE.sh'):
            text = (ROOT / relative).read_text(encoding='utf-8')
            for spelled in re.findall(r'\b(\w+)-step\b', text):
                if spelled in NUMBER_WORDS:
                    self.assertEqual(NUMBER_WORDS[spelled], total, relative + ' says "' + spelled + '-step"')

    def test_guide_defaults_match_what_the_wizard_offers(self):
        guide = GUIDE.read_text(encoding='utf-8')
        code = WIZARD.read_text(encoding='utf-8')
        self.assertIn('`~/farmvillage-server`', guide)
        self.assertRegex(code, r"ask\('Installation folder', home / 'farmvillage-server'\)")
        self.assertIn('normally 5501', guide)
        self.assertRegex(code, r"ask\('Game port', 5501\)")
        self.assertIn('/new.html', guide)
        self.assertIn("'/new.html'", code)
        self.assertIn('enable-linger', guide)
        self.assertIn('enable-linger', code)

    def test_service_name_in_guide_commands_is_the_one_both_installers_use(self):
        unit = re.search(r"^UNIT = '([^']+)'", WIZARD.read_text(encoding='utf-8'), re.M).group(1)
        script_unit = re.search(r"^unit_name='([^']+)'", SERVICE_SCRIPT.read_text(encoding='utf-8'), re.M).group(1)
        self.assertEqual(unit, script_unit)
        guide = GUIDE.read_text(encoding='utf-8')
        commands = re.findall(r'(?:systemctl --user \w+|journalctl --user -u) (\S+)', guide)
        self.assertTrue(commands, 'The guide lost its service control commands')
        self.assertEqual({name for name in commands if name.endswith('.service')}, {unit})

    def test_five_pinned_dependencies_claim_matches_requirements(self):
        pins = [line for line in REQUIREMENTS.read_text(encoding='utf-8').splitlines() if line.strip()]
        self.assertTrue(all('==' in line for line in pins), 'Every dependency must be exactly pinned')
        self.assertIn('five pinned dependencies', GUIDE.read_text(encoding='utf-8'))
        self.assertIn('five pinned dependencies', WIZARD.read_text(encoding='utf-8'))
        self.assertEqual(len(pins), 5)

    def test_typed_wipe_phrase_is_the_one_the_guide_teaches(self):
        self.assertIn('type `WIPE ` followed by that exact printed path', GUIDE.read_text(encoding='utf-8'))
        phrases = re.findall(r"challenge = '(WIPE )' \+ str\(target\)", WIZARD.read_text(encoding='utf-8'))
        self.assertEqual(len(phrases), 2, 'Prompt and publish check must both build the same challenge')

    def test_password_minimum_in_guide_is_enforced_by_the_runner(self):
        self.assertIn('at least eight characters', GUIDE.read_text(encoding='utf-8'))
        spec = importlib.util.spec_from_file_location('fv_sequence_runner', RUNNER)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)

        def attempt(password):
            answers = iter([password, password])
            with tempfile.TemporaryDirectory(prefix='fv-sequence-') as directory:
                return runner.load_credentials(Path(directory), prompt=lambda _text: next(answers))

        with self.assertRaises(RuntimeError):
            attempt('seven77')
        secret, password_hash = attempt('eight888')
        self.assertEqual(len(secret), 32)
        self.assertTrue(password_hash.startswith(('scrypt:', 'pbkdf2:')))


if __name__ == '__main__':
    unittest.main()
