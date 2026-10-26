"""Stable local definitions for previously served missing crop mastery gifts.

These remain derived records, not recovered original sign records or artwork.
Pinned gift/crop identities retain earned, placed and stored items independently
of current seed purchase policy. Each still comes from its original mastery
ladder and crop icon, rendered by the recovered DynamicMasterySign/frame. The
source catalog, reward ladders and all market admission remain untouched.
"""

import hashlib
from pathlib import Path


CODE_PREFIX = "fvlocal_mastery_"
FRAME_URL = "assets/misc/animalmastery_sign.swf"

# Previously served local gift identities, pinned from the original mastery
# ladders in catalog SHA256 14987fd4c07f9de35ff5092aeab58584802fd7fbeca1131ad1a5e3eee381a4d7.
# Definition retention is independent of whether its seed can now be purchased
# on Home. A pair still requires the source seed, authored gift and valid icon.
PRESERVED_GIFTS = frozenset({
    ('masterbubblebeans', 'c8O'),
    ('mastercarrotgold', 'c9p'),
    ('mastercoral', 'c7x'),
    ('masterdazzlers', 'ieb'),
    ('masterflavacorn', 'h66'),
    ('masterjellyfruit', 'c7d'),
    ('masterlavalotus', 'c9s'),
    ('mastermantamushrooms', 'c7b'),
    ('mastermilkystrawberries', 'ieF'),
    ('mastermoonmischief', 'icZ'),
    ('mastermynemelon', 'ieN'),
    ('masterovaltomato', 'iff'),
    ('masterpiratepotato', 'c8C'),
    ('masterplankton', 'c8a'),
    ('masterpodpeas', 'h60'),
    ('masterruzberries', 'iey'),
    ('mastersaltysquash', 'c8H'),
    ('masterseacucumber', 'c8J'),
    ('masterseasponge', 'c4V'),
    ('masterseawatermelon', 'c8Q'),
    ('masterseaweed', 'c7j'),
    ('mastershardskinonions', 'idV'),
    ('mastershellfish', 'c5r'),
    ('mastersolarflarebean', 'ib6'),
    ('masterspacedustsugarcane', 'ieI'),
    ('masterstarpuffcotton', 'ib4'),
    ('masterstarspeckles', 'ifg'),
    ('mastersundippedpepper', 'ia0'),
    ('mastersunfadebarley', 'idD'),
    ('mastersunfingers', 'ibg'),
    ('masterthuckwheat', 'idw'),
    ('mastertritonturnip', 'c6U'),
    ('mastertulipice', '0sf'),
    ('masterturnicarrot', 'idf'),
    ('masterurchinberry', 'c76'),
    ('mastervioletveinspinach', 'idT'),
    ('masterwhitedwarfsunflower', 'ieL'),
    ('masterxalambrosia', 'djQ'),
    ('masterxhl_auroralcorn', 'n29'),
    ('masterxhl_auroralrosemary', 'ocn'),
    ('masterxhl_blazingpeppers', 'oha'),
    ('masterxhl_borealisblueberries', 'n5e'),
    ('masterxhl_borealisroseflower', 'pfq'),
    ('masterxhl_candlelightcranberries', 'n82'),
    ('masterxhl_cinnabursts', 'n8h'),
    ('masterxhl_dazzleapple', 'o29'),
    ('masterxhl_falalalalavender', 'obc'),
    ('masterxhl_frostedpoinsettia', 'o7e'),
    ('masterxhl_glasscandle', 'o4t'),
    ('masterxhl_glasscandycane', 'pb3'),
    ('masterxhl_glassicicle', 'o6w'),
    ('masterxhl_glasspinwheel', 'o8i'),
    ('masterxhl_holidaystainedglass', 'umU'),
    ('masterxhl_hollybrightberries', 'ph3'),
    ('masterxhl_hollybrightpoinsettia', 'n38'),
    ('masterxhl_hollybrightsnowpeas', 'ocx'),
    ('masterxhl_kindleonions', 'n1e'),
    ('masterxhl_luminousginger', 'og3'),
    ('masterxhl_moonlitmistletoe', 'n5w'),
    ('masterxhl_radiantradish', 'nyo'),
    ('masterxhl_roastingchestnuts', 'n9n'),
    ('masterxhl_romancandlecauliflower', 'n7s'),
    ('masterxhl_santaberries', 'nxz'),
    ('masterxhl_seasonalspirits', 'obs'),
    ('masterxhl_shinysprouts', 'n9y'),
    ('masterxhl_silverysquash', 'oay'),
    ('masterxhl_sleighguidercherries', 'obx'),
    ('masterxhl_sparkwheat', 'pgh'),
    ('masterxhl_sugarnsprites', 'oec'),
    ('masterxhl_winterturnip', 'pdn'),
    ('masterxma_blackvelvetpetunia', '09ga'),
    ('masterxma_bloodroot', '09ba'),
    ('masterxma_borage', '09gt'),
    ('masterxma_englishlavender', '099l'),
    ('masterxma_fairmaid', '09ez'),
    ('masterxma_fluerdelis', '0958'),
    ('masterxma_frenchfingerlingpotato', '099h'),
    ('masterxma_frenchpetiteplum', '09f1'),
    ('masterxma_goldenbeet', '09ff'),
    ('masterxma_goodkinghenry', '09d9'),
    ('masterxma_ilexberry', '092t'),
    ('masterxma_laurelberry', '091f'),
    ('masterxma_loquat', '09cn'),
    ('masterxma_loveliesbleeding', '097c'),
    ('masterxma_ornamentalcabbage', '0995'),
    ('masterxma_purplepassion', '096j'),
    ('masterxma_purplequeenbean', '09bx'),
    ('masterxma_royalmandrake', '09dk'),
    ('masterxma_scarletpimpernal', '09de'),
    ('masterxma_tansy', '09gc'),
    ('masterxma_wildleek', '09ct'),
    ('masterxsa_botanica', '0h64'),
    ('masterxsa_buccaneerpumpkin', '0gv9'),
    ('masterxsa_floralblush', '0gz3'),
    ('masterxsa_glowcoral', '0h1k'),
    ('masterxsa_grapeswirls', '0h4t'),
    ('masterxsa_hookedflora', '0gws'),
    ('masterxsa_hydrabloom', '0h0f'),
    ('masterxsa_krakenbloom', '0h7d'),
    ('masterxsa_larvalanemone', '0h5p'),
    ('masterxsa_oysterpearl', '0h61'),
    ('masterxsa_pinkastilbe', '0h8d'),
    ('masterxsa_piratesprism', '0h4h'),
    ('masterxsa_seashellweed', '0h1w'),
    ('masterxsa_seasprout', '0h38'),
    ('masterxsa_seawaveorange', '0h0r'),
    ('masterxsa_skullpoppy', '0h11'),
    ('masterxsa_sparklebubble', '0h53'),
    ('masterxsa_tiarelli', '0gxr'),
    ('masterxsa_toxicapple', '0h43'),
    ('masterxsa_tropicalblooms', '0h0s'),
    ('masterxsa_xeronemalily', '0h2s'),
    ('masterxtr_batflower', '0lng'),
    ('masterxtr_brownknapweed', '0l9q'),
    ('masterxtr_buddhashandcitron', '0lht'),
    ('masterxtr_creepycreepers', '0lcd'),
    ('masterxtr_devilshandflower', '0lip'),
    ('masterxtr_devilspaintbrush', '0lgd'),
    ('masterxtr_evilhead', '0ln9'),
    ('masterxtr_eyeballflower', '0l8s'),
    ('masterxtr_frankenkiwis', '0lpa'),
    ('masterxtr_grinningblooms', '0lq0'),
    ('masterxtr_hornedkiwano', '0l43'),
    ('masterxtr_marbledredeggs', '0lnb'),
    ('masterxtr_meringuebones', '0lnd'),
    ('masterxtr_mummiedbananas', '0lno'),
    ('masterxtr_nastypineapple', '0lk4'),
    ('masterxtr_osiriarose', 'io4s'),
    ('masterxtr_pinwheelblooms', '0ljc'),
    ('masterxtr_rampion', '0loa'),
    ('masterxtr_skullpods', '0lmu'),
    ('masterxtr_trappeddews', '0l93'),
    ('masterxtr_whitebaneberry', '0loh'),
    ('masterxtr_yarrow', '0loj'),
    ('masterxwa_barrelcactus', '0e4q'),
    ('masterxwa_bloomingsneezeweed', '0e1y'),
    ('masterxwa_blueagave', '0e4u'),
    ('masterxwa_cactusflower', '0dux'),
    ('masterxwa_chickpeabloom', '0e47'),
    ('masterxwa_daisybush', '0dxv'),
    ('masterxwa_desertfloweret', '0dq1'),
    ('masterxwa_evergreenfrangipani', '0e0h'),
    ('masterxwa_exoticpineapple', '0dya'),
    ('masterxwa_flamingchilli', '0duy'),
    ('masterxwa_flintcorn', '0dys'),
    ('masterxwa_mistflower', '0e31'),
    ('masterxwa_pinkbuckeye', '0e4r'),
    ('masterxwa_radiantsunflower', '0e32'),
    ('masterxwa_slicertomato', '0e2d'),
    ('masterxwa_sungold', '0e1i'),
    ('masterxwa_sunshinerye', '0dyf'),
    ('masterxwa_terrainblossom', '0dzi'),
    ('masterxwa_victoriamealysage', '0e3p'),
    ('masterxwa_wildflorescence', '0dz9'),
    ('masterxwa_wildpoppy', '0dsn'),
})
# Optional reviewed Glen ordinary-seed fallback gifts: derived local records,
# using only each original ladder's gift identity and recovered crop images.
GLEN_GIFTS = frozenset({
    ('masterambrosiatulip', 'aur'),
    ('masterboggartbulb', 'UhP'),
    ('masterbutterflyrose', 'qJ0'),
    ('masterdarkdahlia', 'avJ'),
    ('masterdreamcotton', 'avE'),
    ('masterelfintea', 'auj'),
    ('masterfairyfoxglove', 'dug'),
    ('mastergoblinvine', 'avF'),
    ('mastergossamerivy', 'avA'),
    ('masterhoneymelon', 'avk'),
    ('masternectarkin', 'al1'),
    ('masterpixieberry', 'atH'),
})
DEFINITION_GIFTS = PRESERVED_GIFTS | GLEN_GIFTS


def _list(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def _image(item, name):
    images = [image for image in _list(item.get("image"))
              if isinstance(image, dict) and image.get("name") == name]
    if len(images) != 1:
        return None
    url = images[0].get("url")
    if (not isinstance(url, str) or not url.startswith("assets/")
            or not url.endswith(".png") or ".." in url.split("/")):
        return None
    return url


def _code(gift):
    # ':' is the original StorageItem metadata separator. The explicit local
    # namespace and full digest avoid claiming or colliding with original codes.
    return CODE_PREFIX + hashlib.sha256(gift.encode("utf-8")).hexdigest()


def derive(records):
    """Return append-only gift definitions from the unmodified recovered rows.

    Gift definition identity is append-only across purchase-policy changes.
    The pinned source-backed pairs are separate from Home seed admission; no
    crop price, World requirement, ladder or existing definition is rewritten.
    """
    names = {item.get("name") for item in records}
    codes = {item.get("code") for item in records}
    gifts = {}
    for crop in records:
        if (not isinstance(crop, dict) or crop.get("type") != "seed"
                or crop.get("className") is not None
                or crop.get("mastery") not in (True, "true")):
            continue
        icon = _image(crop, "icon")
        if icon is None:
            continue
        for level in _list(crop.get("masteryLevel")):
            gift = level.get("gift") if isinstance(level, dict) else None
            if (not isinstance(gift, str) or not gift or gift in names
                    or (gift, crop.get("code")) not in DEFINITION_GIFTS):
                continue
            previous = gifts.get(gift)
            if previous is not None and previous != (crop["code"], icon, _image(crop, "feed")):
                raise ValueError("A missing mastery gift has conflicting recovered crop owners.")
            gifts[gift] = (crop["code"], icon, _image(crop, "feed"))

    additions = []
    preserved_names = {gift for gift, _ in PRESERVED_GIFTS}
    for gift, (crop_code, icon, feed) in sorted(
            gifts.items(), key=lambda row: (row[0] not in preserved_names, row[0])):
        code = _code(gift)
        if code in codes:
            raise ValueError("A local mastery-sign code conflicts with the recovered catalog.")
        codes.add(code)
        additions.append({
            "name": gift, "code": code, "type": "decoration",
            "className": "DynamicMasterySign", "masteredItemCode": crop_code,
            "placeable": "true", "rareItem": "true", "sizeX": "1", "sizeY": "1",
            "requiredLevel": "1", "giftable": "false", "buyable": "false",
            "overrideExportName": "animalmastery", "imageScale": "1.5",
            "multiplace": "false", "sox": {"type": "decoration"},
            # Gift-only: unlike the original animal template these derived
            # definitions have no purchase price. Home's legacy purchase gate
            # rejects a missing price even where it does not inspect buyable.
            "archived": "no", "disallowDelete": "1",
            "image": [
                {"name": "static", "url": FRAME_URL, "loadClass": "mc"},
                {"name": "icon", "url": icon},
                {"name": "feed", "url": feed or icon},
                {"name": "masteredItem", "url": icon},
            ],
        })
    return additions


def apply(records):
    """Append definitions in memory; never rewrite the original AMF or cache."""
    additions = derive(records)
    records.extend(additions)
    return len(additions)


def policy_digest():
    """Bind derived client caches to this stable definition policy and roster.

    client_catalog separately binds its Home market overlay digest.
    """
    return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
