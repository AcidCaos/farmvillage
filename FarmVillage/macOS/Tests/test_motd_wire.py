"""MOTD replies must survive the original membership callback without enabling a popup."""

from pathlib import Path
import sys
import unittest

from pyamf import remoting

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures


class MOTDWireTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp = fixtures.RuntimeFixtureTests.setUp
    fixture = fixtures.RuntimeFixtureTests.fixture
    write_fixture = fixtures.RuntimeFixtureTests.write_fixture
    command = staticmethod(fixtures.RuntimeFixtureTests.command)
    gateway_payload = fixtures.RuntimeFixtureTests.gateway_payload
    gateway = fixtures.RuntimeFixtureTests.gateway

    def test_membership_callbacks_leave_unavailable_campaigns_detached_and_allow_next_batch(self):
        self.write_fixture()
        pending = {
            "item_membership_tree": "MOTD_ITEM_MEMBERSHIP_TREES_2013",
            "item_membership_horse": "MOTD_ITEM_MEMBERSHIP_HORSES_2013",
        }
        response = self.gateway([
            self.command("UserService.getMOTD", [flag], sequence)
            for sequence, flag in enumerate(pending.values(), 1)
        ])
        self.assertEqual(response.status_code, 200)
        # Ruffle's AMF0 reader cannot use object-reference marker 07 here.
        # Each callback must receive its own actual empty object (marker 03).
        self.assertEqual(response.data.count(b"\x00\x08motdData\x03"), 2)
        replies = remoting.decode(response.data).bodies[0][1].body["data"]
        self.assertEqual(len(replies), 2)
        callbacks = []
        for sequence, reply in enumerate(replies, 1):
            self.assertEqual(reply["errorType"], 0)
            motd = reply["data"]["motdData"]
            self.assertIsInstance(motd, dict)
            self.assertNotIn("motdSeenFlag", motd)
            # Recovered ItemMembershipManager.as:1129-1136 dereferences the
            # callback's motdSeenFlag without a null guard. Only a matching flag
            # replaces the pending string with an object; conditionallyOnboard
            # (991-995) requires an Object that is not a String to show a MOTD.
            for feature, flag in pending.items():
                if flag == motd.get("motdSeenFlag"):
                    pending[feature] = motd
                    break
            callbacks.append(sequence)
        self.assertEqual(callbacks, [1, 2])
        self.assertTrue(all(isinstance(value, str) for value in pending.values()))
        # Both callbacks returned; the client can now send its next transaction.
        followup = self.gateway([
            self.command("UserService.incrementActionCount", ["after-membership-motd"], 3)
        ])
        self.assertEqual(followup.status_code, 200)
        saved = fixtures.persistence.read_json(self.saves / "custom-export.json")
        self.assertEqual(saved["userInfo"]["player"]["actionCounts"]["after-membership-motd"], 1)
        for flag in pending.values():
            self.assertGreater(saved["motdSeenFlags"][flag], 0)

    def test_other_unavailable_campaigns_keep_null_no_popup_response(self):
        self.write_fixture()
        response = self.gateway([
            self.command("UserService.getMOTD", ["unavailable-campaign"])
        ])
        self.assertEqual(response.status_code, 200)
        reply = remoting.decode(response.data).bodies[0][1].body["data"][0]
        self.assertEqual(reply["errorType"], 0)
        self.assertIsNone(reply["data"]["motdData"])


if __name__ == "__main__":
    unittest.main()
