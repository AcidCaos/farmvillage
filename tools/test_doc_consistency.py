"""Current documents must agree with the code roster and the owner's decisions.

Source-only: parses Markdown and reads two constants with ast, importing nothing
from the game. A Markdown file whose first line carries the historical banner is
an archive and is exempt from the content rules; every other Markdown file is
treated as current and must follow them. The rules are a drift tripwire, not a
proof that the prose is true: they check the roster, stale world counts and the
retirement statements, not each factual claim.
"""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
BANNER = 'Historical engineering reference'
SKIPPED_DIRECTORIES = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'DerivedData', '.build'}
RETIRED_WORLDS = {'glen', 'hlights'}
STALE_COUNTS = r'(?:seventeen|eighteen|17|18)'
HISTORICAL_LINE = re.compile(r'histor|\bolder?\b|\bearlier\b|\bprevious\b|\bformer\b|\breplace[sd]?\b|superseded', re.I)
ABANDONED = re.compile(r'abandon|discontinu|dropp|retire|exclud|no longer', re.I)


def markdown_files():
    for path in sorted(ROOT.rglob('*.md')):
        if not SKIPPED_DIRECTORIES.intersection(path.relative_to(ROOT).parts):
            yield path


def is_historical(text):
    first = next((line for line in text.splitlines() if line.strip()), '')
    return BANNER in first


def current_documents():
    documents = {}
    for path in markdown_files():
        text = path.read_text(encoding='utf-8')
        if not is_historical(text):
            documents[path.relative_to(ROOT).as_posix()] = text
    return documents


def assigned_value(relative, name):
    tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    raise AssertionError(name + ' is no longer assigned at the top of ' + relative)


def code_roster():
    supported = assigned_value('FarmVillage/world_travel.py', 'SUPPORTED_WORLDS')
    active = assigned_value('FarmVillage/themed_worlds.py', 'ACTIVE_WORLDS')
    assert isinstance(supported, ast.Dict), 'SUPPORTED_WORLDS is no longer a dict literal'
    assert isinstance(active, ast.Call) and isinstance(active.args[0], ast.Set), 'ACTIVE_WORLDS is no longer frozenset({...})'
    return ({ast.literal_eval(key) for key in supported.keys}, {ast.literal_eval(item) for item in active.args[0].elts})


def table_world_ids(text, first_column):
    """Backticked id in the first cell of table rows matching first_column."""
    found = []
    for line in text.splitlines():
        cell = re.match(r'\|\s*(' + first_column + r'[^|]*)\|', line)
        if cell:
            identifier = re.search(r'\(`([a-z]+)`\)', cell.group(1))
            if identifier:
                found.append(identifier.group(1))
    return found


class RosterTests(unittest.TestCase):
    def test_code_roster_is_sixteen_worlds_and_excludes_retired_ones(self):
        supported, active = code_roster()
        roster = supported | active
        self.assertEqual(len(roster), 16, sorted(roster))
        self.assertIn('farm', roster)
        self.assertFalse(roster & RETIRED_WORLDS, 'A retired world is reachable in code')
        self.assertFalse(supported & active, 'A world is listed as both recovered and themed')

    def test_world_readiness_table_lists_exactly_the_code_roster(self):
        supported, active = code_roster()
        text = (ROOT / 'WORLD_READINESS.md').read_text(encoding='utf-8')
        listed = table_world_ids(text, r'\*\*[^|]+\*\*')
        self.assertTrue(listed, 'No world rows were parsed from WORLD_READINESS.md')
        self.assertEqual(len(listed), len(set(listed)), 'A world appears twice in WORLD_READINESS.md')
        self.assertEqual(set(listed), supported | active)

    def test_wave3_world_lanes_list_exactly_the_code_roster(self):
        supported, active = code_roster()
        text = (ROOT / 'Wave 3.md').read_text(encoding='utf-8')
        listed = table_world_ids(text, r'\*\*W\d+ [^|]+\*\*')
        self.assertTrue(listed, 'No world-lane rows were parsed from Wave 3.md')
        self.assertEqual(len(listed), len(set(listed)), 'A world lane appears twice in Wave 3.md')
        self.assertEqual(set(listed), supported | active)


class DirectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = current_documents()

    def test_the_scan_sees_the_documents_that_carry_the_decisions(self):
        for name in ('README.md', 'AGENTS.md', 'TAKEOVER.md', 'HANDOVER_STATUS.md', 'WORLD_READINESS.md', 'Wave 3.md', 'BIFROST_SETUP.md'):
            self.assertIn(name, self.documents, name + ' is missing or marked historical')

    def test_stale_world_counts_only_appear_on_lines_marked_historical(self):
        pattern = re.compile(r'\b' + STALE_COUNTS + r'[- ]worlds?\b', re.I)
        offenders = []
        for name, text in self.documents.items():
            for number, line in enumerate(text.splitlines(), 1):
                if pattern.search(line) and not HISTORICAL_LINE.search(line):
                    offenders.append('%s:%d %s' % (name, number, line.strip()[:110]))
        self.assertEqual(offenders, [], 'Mark the line historical or fix the count')

    def test_every_current_document_naming_a_dropped_direction_also_says_it_is_dropped(self):
        topics = {
            'iPad/iOS': re.compile(r'\biPad\b|\biOS\b'),
            'Enchanted Glen': re.compile(r'Enchanted Glen|`glen`', re.I),
            'Holiday Lights': re.compile(r'Holiday Lights|`hlights`', re.I),
        }
        offenders = []
        for name, text in self.documents.items():
            for topic, mention in topics.items():
                if mention.search(text):
                    said = any(mention.search(line) and ABANDONED.search(line) for line in text.splitlines())
                    if not said:
                        offenders.append(name + ' mentions ' + topic + ' but never says it is abandoned, retired or excluded')
        self.assertEqual(offenders, [])

    def test_headline_documents_state_the_sixteen_world_roster(self):
        for name in ('README.md', 'HANDOVER_STATUS.md', 'WORLD_READINESS.md', 'BIFROST_SETUP.md', 'TAKEOVER.md'):
            self.assertRegex(self.documents[name], r'(?i)\bsixteen\b', name)

    def test_agents_file_keeps_the_irreversible_decisions(self):
        agents = self.documents['AGENTS.md']
        self.assertRegex(agents, r'(?s)abandoned the iPad/iOS build')
        self.assertRegex(agents, r'(?s)Enchanted Glen and Holiday Lights are dropped')
        self.assertRegex(agents, r'(?s)No automatic push or deployment')


if __name__ == '__main__':
    unittest.main()
