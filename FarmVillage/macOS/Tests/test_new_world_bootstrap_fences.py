"""Source-backed Beat and missing-feature tutorial gates in actual game bootstraps."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import re
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
import zlib
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_persistence as fixtures  # Install synthetic data paths before product imports.

FENCES={'fv_beat_hlights':0,'fv_beat_atlantis':0,'fv_beat_enchanted_glen':0,'fv_hlights_ftue':0,'fv_xeg_starter':0}
ACCESS={'fv_hlights':0,'fv_hlights_for_all':0,'fv_atlantis':1,'fv_atlantis_for_all':1,'fv_glen':0,'fv_glen_for_all':0}

def experiments(text):
    rows=re.findall(r'"(fv_[A-Za-z0-9_]+)"\s*:\s*(-?\d+)',text)
    return rows,{key:int(value) for key,value in rows}

class NewWorldBootstrapTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.RuntimeFixtureTests.setUpClass.__func__)
    setUp=fixtures.RuntimeFixtureTests.setUp
    fixture=fixtures.RuntimeFixtureTests.fixture
    write_fixture=fixtures.RuntimeFixtureTests.write_fixture

    def test_both_actual_rendered_routes_emit_five_fences_and_preserve_access(self):
        path=self.write_fixture();before=path.read_bytes()
        with self.client.session_transaction() as session:session['UID']='fixture-farmer'
        for route in ('/play.html','/ruffle.html'):
            with self.subTest(route=route),mock.patch.object(self.server,'NATIVE_WRAPPER',False),redirect_stdout(io.StringIO()):
                response=self.client.get(route)
            self.assertEqual(response.status_code,200)
            rows,values=experiments(response.get_data(as_text=True))
            for key,value in {**FENCES,**ACCESS}.items():
                self.assertEqual(sum(name==key for name,_ in rows),1,key)
                self.assertEqual(values[key],value,key)
            self.assertEqual(values['fv_xlg_motd_generalaccess'],0)
            self.assertEqual(values['fv_xlg_starter'],0)
            self.assertEqual(values['fv_xal_starter'],2)
            self.assertEqual(path.read_bytes(),before)

    def test_unauthenticated_bootstraps_still_redirect_without_creating_players(self):
        path=self.write_fixture();before=path.read_bytes()
        for route in ('/play.html','/ruffle.html'):
            with self.subTest(route=route),mock.patch.object(self.server,'NATIVE_WRAPPER',False):
                response=self.client.get(route)
            self.assertEqual(response.status_code,302)
            self.assertEqual(response.headers['Location'],'/')
        self.assertEqual(path.read_bytes(),before)

    def test_original_three_beat_prerequisites_keep_worlds_and_variants(self):
        root=ET.fromstring(zlib.decompress((Path(self.bundle.XML_DIR)/'gz/v855098/gameSettingsCMS.xml.gz').read_bytes()))
        for world,name,experiment,variant in [('hlights','beatHlights','fv_beat_hlights','2'),('atlantis','beatAtlantis','fv_beat_atlantis','1'),('glen','beatEnchantedGlen','fv_beat_enchanted_glen','1')]:
            found=[n for n in root.iter('prereq') if n.get('name')==name]
            self.assertEqual(len(found),1)
            self.assertEqual([dict(n.attrib) for n in found[0]],[{'type':'location','value':world},{'type':'experiment','value':experiment,'variant':variant}])

    def test_original_hlights_tutorial_requires_missing_feature_not_score_or_grants(self):
        root=ET.fromstring(zlib.decompress((Path(self.bundle.XML_DIR)/'gz/v855098/gameSettingsCMS.xml.gz').read_bytes()))
        for name,suffix,seen in [('holidayLights','EA','holiday_lights_ftue_seen'),('holidayLightsGA','GA','holiday_lightsGA_ftue_seen')]:
            found=[n for n in root.iter('ftue') if n.get('name')==name]
            self.assertEqual(len(found),1)
            node=found[0]
            self.assertEqual(node.attrib,{'name':name,'asset':'assets/dialogs/xhg/FV_xhg_FTUE_bubble.swf','hudWindowHidden':'true','skipButton':'false','replay':'false','seenFlag':seen,'persistantProgress':'true'})
            self.assertEqual([dict(n.attrib) for n in node],[{'name':'ftue_0','className':'OpenTutWindowState','asset':f'assets/dialogs/HLights/FV_xhl_FTUE_{suffix}.swf'},{'name':'ftue_1','className':'OpenFeatureBuildingWindowState','itemCode':'oud'},{'name':'ftue_2','className':'EventTutState','message':'Dialogs:FishingDerby_Tut2','eventType':'bldg_hollybrightcity_close'}])
        import items
        building=items.get_item_by_code('oud')
        self.assertEqual((building['name'],building['className']),('bldg_hollybrightcity','RuntimeDrivenLootableFixedFeatureBuilding'))
        import themed_worlds
        self.assertNotIn(building['className'], themed_worlds.BASIC_CLASSES)

    def test_glen_live_starter_pack_invitation_is_distinct_from_access_and_ftue(self):
        root=ET.fromstring(zlib.decompress((Path(self.bundle.XML_DIR)/'gz/v855098/gameSettingsCMS.xml.gz').read_bytes()))
        found=[n for n in root.iter('icon') if n.get('name')=='GlenStarter']
        self.assertEqual(len(found),1)
        node=found[0]
        self.assertEqual(node.get('code'),'233')
        self.assertEqual(node.findtext('action'),'miniMarket')
        self.assertEqual(node.findtext('experiment'),'fv_xeg_starter')
        self.assertEqual([n.text for n in node.findall('itemList/item')],['pkg_xeg_starterpack_1','pkg_xeg_starterpack_2','pkg_xeg_starterpack_3'])
        prereqs={n.get('name'):n for n in root.iter('prereq') if n.get('name')}
        for suffix in ('1','2','3'):
            row=prereqs['fv_xeg_starterpack_'+suffix]
            self.assertEqual(row.get('type'),'OR')
            self.assertEqual(row[-1].attrib,{'type':'experiment','value':'fv_xeg_starter','variant':'2'})
        import feature_availability
        self.assertNotIn('GlenStarter',feature_availability.blocked_hud_icons())
        self.assertEqual([n for n in root.iter('ftue') if n.get('name') in ('glen','glenGA','atlantis','atlantisGA')],[])

    def test_actual_farms_route_discloses_each_local_theme_using_its_own_name(self):
        path=self.write_fixture();before=path.read_bytes()
        with self.client.session_transaction() as session:session['UID']='fixture-farmer'
        import themed_worlds
        candidates={
            'atlantis':{'name':'Atlantis','prefix':'xal','storageId':-19,'xmlStorageId':None,'xmlPrefix':None,'xmlTheme':None,'theme':'atlantis_theme','localThemeChoice':True},
            'glen':{'name':'Enchanted Glen','prefix':'xeg','storageId':-18,'xmlStorageId':None,'xmlPrefix':None,'xmlTheme':None,'theme':'glen_theme','localThemeChoice':True},
        }
        with mock.patch.dict(themed_worlds.SPECS,candidates),mock.patch.object(themed_worlds,'ACTIVE_WORLDS',frozenset({'htown','atlantis','glen'})):
            response=self.client.get('/farms')
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        self.assertEqual(path.read_bytes(),before)
        for name in ('Mistletoe Lane','Atlantis','Enchanted Glen'):
            match=re.search(r'<section class="farm-card">\s*<h2>'+re.escape(name)+r'</h2>(.*?)</section>',html,re.S)
            self.assertIsNotNone(match,name)
            self.assertIn('We chose the archived '+name+' theme; the original starting layout was not recovered.',match.group(1))
            if name!='Mistletoe Lane':self.assertNotIn('archived Mistletoe Lane theme',match.group(1))
