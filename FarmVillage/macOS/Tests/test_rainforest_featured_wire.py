"""Original Garden batch-display callback; signed AMF, synthetic saves only."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_rainforest_containers_wire as containers
import test_persistence as fixtures
import items
import rainforest_features
import world_travel


class RainforestFeaturedWireTests(unittest.TestCase):
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

    def garden(self):
        self.prepare()
        ident = self.send('place', self.snapshot('xrf_gnomegarden_finished'))['id']
        owner = self.obj(ident)
        self.code = items.get_item_by_name('gnome_xrf_headdresstte')['code']
        owner.update(plantTime=1700000000123, imported={'keep': [1, {'clock': 'original'}]},
                     featuredItems={'0': {'itemCode': self.code, 'metaHash': self.code + ':'}})
        self.save['userInfo']['player']['storageData'][str(ident)] = {
            self.code: [1, ['original-container-sender'], []]}
        self.persist()
        return owner

    def options(self, selection=None):
        return [{'featuredItems': selection if selection is not None else {
            '5': {'itemCode': self.code, 'metaHash': self.code + ':'}}}]

    def expected_selection_only(self, before, ident, selection):
        expected = copy.deepcopy(before)
        next(obj for obj in expected['world']['objectsArray'] if obj['id'] == ident)['featuredItems'] = selection
        self.assertEqual(self.save, expected)

    def test_original_packet_shape_reuses_slot_engine_and_preserves_every_other_field(self):
        owner = self.garden()
        before = copy.deepcopy(self.save)
        # Packet 72 deliberately omitted contents and carried the client's bare
        # state. None of that snapshot is authority over the saved container.
        snapshot = dict(owner, contents={}, state='bare', capacity=99999,
                        expansionLevel=999, plantTime=0, imported={'forged': True},
                        featuredItems={'4': {'itemCode': 'HB', 'metaHash': 'HB:'}})
        result = self.send('setMultipleFeaturedItems', snapshot, self.options(), sequence=10)
        self.assertEqual(result, {'id': owner['id']})
        selection = {'5': {'itemCode': self.code, 'metaHash': self.code + ':'}}
        self.expected_selection_only(before, owner['id'], selection)
        disk, accepted = self.path.read_bytes(), copy.deepcopy(self.save)
        self.send('setMultipleFeaturedItems', snapshot, self.options(), sequence=10)
        self.assertEqual(self.save, accepted)
        self.assertEqual(self.path.read_bytes(), disk)
        self.reload_travel()

    def test_default_owned_occupant_without_a_synthesized_ledger_is_read_only_authority(self):
        owner = self.garden()
        self.save['userInfo']['player']['storageData'].pop(str(owner['id']))
        self.persist()
        before = copy.deepcopy(self.save)
        self.send('setMultipleFeaturedItems', owner, self.options(), sequence=11)
        self.expected_selection_only(before, owner['id'], self.options()[0]['featuredItems'])
        self.assertNotIn(str(owner['id']), self.save['userInfo']['player']['storageData'])

    def test_imported_owner_metadata_without_a_ledger_and_legacy_anonymous_hash_are_preserved(self):
        owner = self.garden()
        self.save['userInfo']['player']['storageData'].pop(str(owner['id']))
        owner['storageMetadata'] = {self.code + ':legacy-owned': [{'legacyUnit': 1}]}
        self.persist()
        selection = {'5': {'itemCode': self.code, 'metaHash': self.code + ':legacy-owned'}}
        before = copy.deepcopy(self.save)
        self.send('setMultipleFeaturedItems', owner, self.options(selection), sequence=14)
        self.expected_selection_only(before, owner['id'], selection)
        owner = self.obj(owner['id'])
        owner.pop('storageMetadata')
        self.persist()
        before = copy.deepcopy(self.save)
        selection = {'5': {'itemCode': self.code, 'metaHash': self.code}}
        self.send('setMultipleFeaturedItems', owner, self.options(selection), sequence=15)
        self.expected_selection_only(before, owner['id'], selection)

    def test_full_map_replacement_and_empty_clear_do_not_reset_imported_state_or_clock(self):
        owner = self.garden()
        before = copy.deepcopy(self.save)
        self.send('setMultipleFeaturedItems', owner, self.options({}), sequence=12)
        self.expected_selection_only(before, owner['id'], {})
        self.send('setMultipleFeaturedItems', owner, self.options({}), sequence=12)
        self.expected_selection_only(before, owner['id'], {})

    def test_real_metadata_variant_and_anonymous_unit_require_existing_positive_authority(self):
        owner = self.garden()
        variant = {'importedVariant': ['one', 2]}
        owner['contents'][0]['numItem'] = 2
        owner['storageMetadata'] = {self.code + ':owned-variant': [copy.deepcopy(variant)]}
        self.save['userInfo']['player']['storageData'][str(owner['id'])][self.code] = [
            2, ['original-container-sender'], [copy.deepcopy(variant)]]
        self.persist()
        selection = {'4': {'itemCode': self.code, 'metaHash': self.code + ':owned-variant'},
                     '5': {'itemCode': self.code, 'metaHash': self.code + ':'}}
        before = copy.deepcopy(self.save)
        self.send('setMultipleFeaturedItems', owner, self.options(selection), sequence=13)
        self.expected_selection_only(before, owner['id'], selection)
        self.reload_travel()

    def test_gifts_ordinary_stock_and_forged_metadata_cannot_authorize_display_units(self):
        owner = self.garden()
        other = self.gift('gnome_xrf_ancienthelm')
        self.save['userInfo']['player']['storageData']['-26'][other['code']] = [5, [], []]
        self.persist()
        invalid = (
            {'5': {'itemCode': other['code'], 'metaHash': other['code'] + ':'}},
            {'5': {'itemCode': self.code, 'metaHash': self.code + ':forged'}},
            {'4': {'itemCode': self.code, 'metaHash': self.code + ':'},
             '5': {'itemCode': self.code, 'metaHash': self.code + ':'}},
        )
        for selection in invalid:
            with self.subTest(selection=selection):
                self.reject('setMultipleFeaturedItems', owner, self.options(selection), sequence=20)

    def test_unmatched_imported_metadata_and_inconsistent_ledger_are_preserved_on_refusal(self):
        owner = self.garden()
        owner['storageMetadata'] = {self.code + ':forged-owned': [{'variant': 'not-in-ledger'}]}
        self.persist()
        self.reject('setMultipleFeaturedItems', owner, self.options(), sequence=21)
        owner = self.obj(owner['id'])
        owner.pop('storageMetadata')
        self.save['userInfo']['player']['storageData'][str(owner['id'])][self.code][0] = 2
        self.persist()
        self.reject('setMultipleFeaturedItems', owner, self.options(), sequence=22)

    def test_malformed_or_aliased_slots_and_mixed_selection_roll_back_as_one_change(self):
        owner = self.garden()
        row = {'itemCode': self.code, 'metaHash': self.code + ':'}
        selections = ([], {'6': row}, {'-1': row}, {'05': row},
                      {'5': dict(row, extra='forged')},
                      {'5': {'itemCode': self.code}}, {'5': dict(row, metaHash=1)},
                      {'5': row, '4': {'itemCode': 'HB', 'metaHash': 'HB:'}})
        for selection in selections:
            with self.subTest(selection=selection):
                self.reject('setMultipleFeaturedItems', owner, self.options(selection), sequence=23)
        # AMF serializes property names as strings, so these Python-only
        # aliases must be tested before that lossy transport conversion.
        for selection in ({True: row}, {1: row, '1': row}):
            before, disk = copy.deepcopy(self.save), self.path.read_bytes()
            with self.assertRaises(ValueError):
                rainforest_features.garden_featured_items(self.save, owner, self.options(selection))
            self.assertEqual(self.save, before)
            self.assertEqual(self.path.read_bytes(), disk)
        for params in ([], [{'featuredItems': {}}, {'extra': True}],
                       [{'featuredItems': {}, 'inventory': {}}]):
            with self.subTest(params=params):
                self.reject('setMultipleFeaturedItems', owner, params, sequence=24)

    def test_wrong_owner_identity_container_and_world_keep_the_existing_fence(self):
        owner = self.garden()
        for snapshot in (dict(owner, id=99999), dict(owner, className='Plot'),
                         self.snapshot('xrforchard_finished', owner['id']),
                         self.snapshot('xrf_gnomegarden', owner['id'])):
            with self.subTest(snapshot=snapshot):
                self.reject('setMultipleFeaturedItems', snapshot, self.options(), sequence=25)
        world_travel.switch(self.save, 'farm', now=containers.NOW)
        self.persist()
        self.reject('setMultipleFeaturedItems', owner, self.options(), sequence=26)

    def test_mixed_signed_batch_keeps_prior_success_and_rolls_back_rejected_feature_map(self):
        owner = self.garden()
        good = self.options()[0]['featuredItems']
        bad = {'4': {'itemCode': 'HB', 'metaHash': 'HB:'}}
        before = copy.deepcopy(self.save)
        response = self.gateway([
            self.command('WorldService.performAction', ['setMultipleFeaturedItems', copy.deepcopy(owner), self.options(good)], 30),
            self.command('WorldService.performAction', ['setMultipleFeaturedItems', copy.deepcopy(owner), self.options(bad)], 31),
        ])
        self.assertEqual(response.status_code, 200)
        from pyamf import remoting
        callbacks = remoting.decode(response.data).bodies[0][1].body['data']
        self.assertEqual([row['errorType'] for row in callbacks], [0, 29])
        self.expected_selection_only(before, owner['id'], good)
        persisted = copy.deepcopy(self.save)
        world_travel.clear_temporary_ids(persisted)
        self.assertEqual(json.loads(self.path.read_text()), persisted)

    def test_late_original_selection_cannot_restore_a_withdrawn_occupant(self):
        owner = self.garden()
        options = self.options()
        self.send('setMultipleFeaturedItems', owner, options, sequence=40)
        self.send('place', self.snapshot('gnome_xrf_headdresstte', 64010, 30, 30),
                  [{'isStorageWithdrawal': owner['id']}], sequence=41)
        self.reject('setMultipleFeaturedItems', owner, options, sequence=40)


if __name__ == '__main__':
    unittest.main()
