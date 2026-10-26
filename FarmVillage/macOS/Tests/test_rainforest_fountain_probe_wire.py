"""Original owned-Fountain startup probe; read-only signed AMF callbacks."""
import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_rainforest_containers_wire as containers
import test_persistence as fixtures
import storage
import world_travel


class RainforestFountainProbeWireTests(unittest.TestCase):
    base = containers.RainforestContainerWireTests
    setUpClass = classmethod(base.setUpClass.__func__)
    setUp = base.setUp
    fixture = base.fixture
    write_fixture = base.write_fixture
    command = staticmethod(base.command)
    gateway_payload = base.gateway_payload
    gateway = base.gateway
    save = base.save
    persist = base.persist
    prepare = base.prepare
    obj = base.obj
    snapshot = staticmethod(base.snapshot)
    send = base.send
    reject = base.reject
    gift = base.gift
    reload_travel = base.reload_travel

    def fountain(self):
        self.prepare()
        self.gift('xrf_fountainofyouth')
        ident = self.send('place', self.snapshot('xrf_fountainofyouth'),
                          [{'isGift': True}], sequence=70)['id']
        owner = self.obj(ident)
        owner.update(state='bare', plantTime=1792897361082,
                     position={'x': 36, 'y': 34, 'z': 0},
                     imported={'keep': ['clock', {'visualOnly': True}]})
        self.persist()
        return owner

    def probe(self, owner):
        # Original packet 135 after an ordinary God Barn return: this is a
        # TUpgradeStorage(TYPE_UPDATE) read, not a replacement saved snapshot.
        return dict(owner, contents={}, buildTime=0, tempId=math.nan)

    def test_original_startup_nan_probe_and_retry_preserve_every_saved_field(self):
        owner = self.fountain()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        packet = self.probe(owner)
        options = [{}, {'firstWA': True}]
        self.assertEqual(self.send('getStorageInfo', packet, options, sequence=71),
                         {'id': owner['id']})
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)
        self.send('getStorageInfo', packet, options, sequence=71)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)
        self.reload_travel()

    def test_original_gift_place_empty_object_contents_reload_and_retry(self):
        self.prepare()
        self.gift('xrf_fountainofyouth')
        packet = self.snapshot('xrf_fountainofyouth')
        packet.update(contents={}, buildTime=math.nan, state='bare',
                      plantTime=1792897361082, tempId=-1)
        options = [{'currency': '', 'expansionLevel': 1, 'giftMetadataIndex': -1,
                    'isGift': True, 'isInventoryWithdrawal': False,
                    'isStorageWithdrawal': -1}]
        ident = self.send('place', packet, options, sequence=80)['id']
        self.assertEqual(self.obj(ident)['contents'], [])
        self.assertNotIn('rvi', self.save['userInfo']['player']['storageData']['-1'])
        self.assertEqual(self.save['userInfo']['player']['cash'], 1000)
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send('place', packet, options, sequence=80)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)
        self.reload_travel()
        self.send('getStorageInfo', self.probe(self.obj(ident)),
                  [{}, {'firstWA': True}], sequence=81)

    def test_empty_fountain_normalizer_never_interprets_nonempty_imported_contents(self):
        for contents in ([{'legacy': ['original', 1]}], {'legacy': {'keep': True}}, None):
            packet = self.snapshot('xrf_fountainofyouth')
            packet.update(contents=contents, plantTime=12345,
                          imported={'preserve': True})
            before = copy.deepcopy(packet)
            storage.normalize_empty_building_snapshot(packet)
            self.assertEqual(packet, before)
        for name, cls in (('xrf_hiddenpalace', 'FeatureBuilding'),
                          ('xrf_fountainofyouth', 'Building')):
            packet = {'itemName': name, 'className': cls, 'contents': {}}
            before = copy.deepcopy(packet)
            storage.normalize_empty_building_snapshot(packet)
            self.assertEqual(packet, before)

    def test_untrusted_optional_snapshot_fields_never_replace_owned_visual_state(self):
        owner = self.fountain()
        packet = self.probe(owner)
        packet.update(plantTime=math.nan, buildTime=math.nan, state='ripe',
                      contents=[{'itemCode': 'HB', 'numItem': 999}],
                      capacity=99999, featuredItems={'forged': True},
                      imported={'forged': True})
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        self.send('getStorageInfo', packet, [{}, {'firstWA': True}], sequence=72)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)

    def test_wrong_identity_unknown_or_nonfinite_owner_ids_refuse_atomically(self):
        owner = self.fountain()
        packets = [dict(self.probe(owner), **change) for change in (
            {'id': 9999}, {'id': math.nan}, {'id': True},
            {'itemName': 'xrf_hiddenpalace'}, {'className': 'StorageBuilding'})]
        for packet in packets:
            with self.subTest(packet=packet):
                self.reject('getStorageInfo', packet, [{}, {'firstWA': True}], sequence=73)

    def test_inactive_wrong_world_deleted_and_ambiguous_owners_do_not_admit_probe(self):
        owner = self.fountain()
        packet = self.probe(owner)
        owner['deleted'] = True
        self.persist()
        self.reject('getStorageInfo', packet, [{}, {'firstWA': True}], sequence=74)
        owner = self.obj(owner['id'])
        owner['deleted'] = False
        self.save['world']['objectsArray'].append(copy.deepcopy(owner))
        # The persistence validator cannot publish this ambiguous identity.
        # A malformed in-memory caller still cannot obtain the read callback.
        self.reject('getStorageInfo', packet, [{}, {'firstWA': True}], sequence=74)
        self.save['world']['objectsArray'].pop()
        world_travel.switch(self.save, 'farm', now=containers.NOW)
        self.persist()
        self.reject('getStorageInfo', packet, [{}, {'firstWA': True}], sequence=74)

    def test_probe_does_not_admit_harvest_rewards_or_other_unrestored_feature(self):
        owner = self.fountain()
        self.send('getStorageInfo', self.probe(owner), [{}, {'firstWA': True}], sequence=75)
        self.reject('harvest', owner, sequence=76)
        self.reject('CompleteNow', owner, sequence=76)
        owner = self.obj(owner['id'])
        owner['itemName'] = 'xrf_hiddenpalace'
        # The persistence validator also refuses this unrecovered identity.
        self.reject('getStorageInfo', self.probe(owner), [{}, {'firstWA': True}], sequence=77)

    def test_failed_read_in_mixed_batch_does_not_change_saved_visual_or_currency(self):
        owner = self.fountain()
        before, disk = copy.deepcopy(self.save), self.path.read_bytes()
        result = self.gateway([
            self.command('WorldService.performAction',
                         ['getStorageInfo', self.probe(owner), [{}, {'firstWA': True}]], 78),
            self.command('WorldService.performAction',
                         ['harvest', owner, []], 79)])
        from pyamf import remoting
        callbacks = remoting.decode(result.data).bodies[0][1].body['data']
        self.assertEqual(callbacks[0]['errorType'], 0)
        self.assertNotEqual(callbacks[1]['errorType'], 0)
        self.assertEqual(self.save, before)
        self.assertEqual(self.path.read_bytes(), disk)


if __name__ == '__main__':
    unittest.main()
