"""AMF startup must select its XML backend before the first threaded response."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures


class AMFXMLBootstrapTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def test_server_has_one_explicit_safe_backend_before_the_first_response(self):
        from defusedxml import ElementTree
        from pyamf import xml
        self.assertIs(xml.ET, ElementTree)
        self.assertEqual(xml.types, (type(ElementTree.fromstring('<ready/>')),))

    def test_xml_amf_round_trip_does_not_probe_optional_backends(self):
        import pyamf
        from pyamf import xml
        from defusedxml import ElementTree
        element = ElementTree.fromstring('<ready>farm</ready>')
        with mock.patch('pyamf.util.get_module', side_effect=AssertionError('Unexpected lazy XML discovery')):
            payload = pyamf.encode(element, encoding=pyamf.AMF3).getvalue()
            restored = pyamf.get_decoder(pyamf.AMF3, payload).readElement()
        self.assertEqual(ElementTree.tostring(restored), b'<ready>farm</ready>')
        self.assertIs(xml.ET, ElementTree)

    def test_xml_entities_remain_refused(self):
        from defusedxml.common import DTDForbidden
        from pyamf import xml
        with self.assertRaises(DTDForbidden):
            xml.fromstring('<!DOCTYPE farm [<!ENTITY x "expanded">]><farm>&x;</farm>')

    def test_init_user_returns_valid_amf_without_optional_xml_backend_discovery(self):
        self.write_fixture()
        with mock.patch('pyamf.util.get_module', side_effect=AssertionError('Unexpected lazy XML discovery')):
            response = self.gateway([self.command('UserService.initUser', ['QA', 0, True, {}], 1)])
        results = fixtures.gateway_results(self, response, errors=[0])
        self.assertIn('userInfo', results[0]['data'])


if __name__ == '__main__': unittest.main()
