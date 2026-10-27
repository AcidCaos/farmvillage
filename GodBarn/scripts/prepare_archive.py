#!/usr/bin/env python3
"""Preserve price/history evidence in God Barn's copied catalog, without game writes.

Read the original AMF snapshot, not the lossy prepared copy. All output stays in
GodBarn/data. Raw values, absent fields, source record order and hashes survive.
"""
import argparse
from datetime import datetime
import hashlib
import json
import math
import shutil
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('market', 'cost', 'cash', 'cashMarket', 'cashInfo', 'saleCost', 'saleCash', 'saleCoins',
          'limitedStart', 'limitedEnd', 'limitedIcon', 'marketCardDescriptor', 'marketEntries',
          'marketPrereqs', 'prereqs', 'purchasePrereqs', 'buyable', 'giftable', 'present', 'archived', 'cmsmeta')
COLLECTIONS = [
    {'id': 'winter-2010', 'name': 'Winter 2010', 'kind': 'Recovered seasonal metadata',
     'note': 'Winter descriptor and a recorded 2010 availability window. Item dates are not a complete event calendar.'},
    {'id': 'halloween-2010', 'name': 'Halloween 2010 finds', 'kind': 'Curated archive selection',
     'note': 'Selected recovered Halloween records. Includes the separately recorded train sale variant; original release offers are unverified.'},
    {'id': 'adobe-village', 'name': 'Adobe & village keepsakes', 'kind': 'Curated archive selection',
     'note': 'An editorial pairing of the Adobe Barn and Bench. The bench records a FarmVillage rerelease prerequisite, not the barn’s 2010 offer.'},
]
CURRENCIES = {'cash': 'Farm Cash', 'coins': 'Farm Coins', 'gold': 'Farm Coins',
              'villageCoins': 'Village Coins', 'berry': 'Berries'}


def scalar_price(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
        if not math.isfinite(number) or number < 0 or (isinstance(value, str) and not value.strip()):
            return None
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError, OverflowError):
        return None


def price(raw):
    market = raw.get('market')
    if market is None or market == '':
        # FarmItem.marketIsCoin explicitly includes an empty selector. Never
        # infer a second cash offer from an unrelated cash-looking field.
        market, basis = 'coins', 'FarmItem.marketIsCoin default for an empty selector'
    elif not isinstance(market, str):
        return {'recorded': False, 'label': 'Price not recorded', 'reason': 'Non-scalar market selector'}
    else:
        basis = 'Recorded market selector'
    if market == 'both':
        offers = []
        for currency, field in (('coins', 'cost'), ('cash', 'cash')):
            amount = scalar_price(raw.get(field))
            if amount is not None:
                offers.append({'amount': amount, 'currency': currency, 'currencyLabel': CURRENCIES[currency], 'sourceField': field})
        return {'recorded': bool(offers), 'label': 'Archive price' if offers else 'Price not recorded',
                'offers': offers, 'basis': basis}
    field = 'cash' if market == 'cash' else 'cost'
    amount = scalar_price(raw.get(field))
    if amount is None:
        return {'recorded': False, 'label': 'Price not recorded', 'currency': market,
                'sourceField': field, 'reason': 'Selected price missing, negative, or non-scalar'}
    return {'recorded': True, 'label': 'Archive price', 'amount': amount, 'currency': market,
            'currencyLabel': CURRENCIES.get(market, market), 'sourceField': field, 'basis': basis}


def date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%Y %H:%M:%S'):
        try:
            parsed = datetime.strptime(value, fmt)
            if 2009 <= parsed.year <= 2020:
                return parsed.date().isoformat()
        except ValueError:
            pass
    return None


def context(raw, index, source_hash):
    start, end = date(raw.get('limitedStart')), date(raw.get('limitedEnd'))
    valid_window = start is not None and end is not None and start <= end
    collections = []
    if raw.get('marketCardDescriptor') == 'winter' and valid_window and start.startswith('2010-'):
        collections.append('winter-2010')
    if raw.get('code') == 'v4' or (raw.get('marketCardDescriptor') == 'halloween' and valid_window and start.startswith('2010-')):
        collections.append('halloween-2010')
    if raw.get('code') in ('Fg', 'Ev'):
        collections.append('adobe-village')
    notes = []
    if raw.get('code') == 'UF':
        notes.append('Winter descriptor; snapshot selects a 7 Farm Cash offer. The separate cost field does not establish a coin offer.')
    if raw.get('code') == 'v4':
        notes.append('Source record is the Halloween Train Engine Sale variant, available 28 October–3 November 2010. Original release price unverified.')
    if raw.get('code') == 'Fg':
        notes.append('Snapshot records a 30 Farm Cash offer with an 11–12 August 2010 availability window.')
    if raw.get('code') == 'Ev':
        notes.append('Snapshot selects Village Coins and records a farmVillageRerelease prerequisite. Original release offer unverified.')
    acquisition = 'Market offer' if raw.get('buyable') in ('true', True, '1') else 'Acquisition not recorded'
    if raw.get('marketPrereqs') == 'farmVillageRerelease':
        acquisition = 'Recorded rerelease offer'
    elif raw.get('giftable') in ('true', True, '1') and raw.get('buyable') in ('false', False, '0'):
        acquisition = 'Giftable; no market offer recorded'
    return {'price': price(raw), 'collections': collections,
            'availability': {'start': start, 'end': end} if valid_window else None,
            'acquisition': acquisition, 'note': ' '.join(notes) or 'Price and availability reflect this recovered catalog snapshot; original release history is unverified.',
            'source': {'file': 'xml/gz/v855038/items_opt.amf', 'sha256': source_hash, 'recordIndex': index,
                       'code': raw.get('code'), 'name': raw.get('name')},
            'raw': {key: raw[key] for key in FIELDS if key in raw}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Read-only FarmVillage checkout')
    args = parser.parse_args()
    source = args.source.resolve()
    payload = (source / 'xml/gz/v855038/items_opt.amf').read_bytes()
    import pyamf
    raw = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(payload)).readElement()['settings']['items']['item']
    digest = hashlib.sha256(payload).hexdigest()
    manifest = pyamf.get_decoder(pyamf.AMF3, zlib.decompress((source / 'assethash/v9/assethash.master.amf.gz').read_bytes())).readElement()
    provenance_path = ROOT / 'data/provenance.json'
    provenance = json.loads(provenance_path.read_text())
    asset_records = {entry['path']: entry for entry in provenance.get('assets', [])}
    contexts = {}
    originals = {}
    for index, item in enumerate(raw):
        contexts.setdefault(item['name'], context(item, index, digest))
        originals.setdefault(item['name'], item)
    target = ROOT / 'data/catalog.json'
    catalog = json.loads(target.read_text())
    for item in catalog:
        item['archive'] = contexts.get(item['name'], {'price': {'recorded': False, 'label': 'Price not recorded'}, 'collections': []})
    names = {'UF': 'Candy Cane Gate', 'v4': 'Halloween Train Engine Sale', 'Fg': 'Adobe Barn', 'Ev': 'Adobe Bench'}
    for item in catalog:
        if item.get('code') in names:
            item['displayName'] = names[item['code']]
        if not item['archive'].get('collections'):
            continue
        raw_item = originals[item['name']]
        images = raw_item.get('image') or []
        if isinstance(images, dict):
            images = [images]
        images = sorted((im for im in images if isinstance(im, dict) and str(im.get('url', '')).endswith('.png')),
                        key=lambda im: (im.get('name') != 'icon', '200' in im.get('url', '')))
        for image in images:
            logical = image['url'].removeprefix('assets/')
            group, relative = logical.split('/', 1)
            hashed = manifest.get(group, {}).get(relative)
            if not isinstance(hashed, str):
                continue
            original = source / 'LocalData/assets' / group / Path(relative).parent / (hashed + Path(relative).suffix)
            if not original.is_file():
                continue
            copied = 'static/assets/items/' + original.name
            destination = ROOT / copied
            if destination.is_symlink():
                raise ValueError('Archive thumbnail destination must not be a symlink')
            shutil.copyfile(original, destination)
            data = destination.read_bytes()
            item.update(image='/' + copied, hasOriginalThumbnail=True)
            asset_records[copied] = {'logical': image['url'], 'originalPath': str(original), 'path': copied,
                                     'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            break
    provenance['assets'] = list(asset_records.values())
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
    temporary = target.with_suffix('.preparing.json')
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')) + '\n')
    temporary.replace(target)
    metadata = {'schema': 1, 'source': 'xml/gz/v855038/items_opt.amf', 'source_sha256': digest,
                'records': len(raw), 'collections': COLLECTIONS,
                'policy': 'Archive prices are context for gifts, never charges. Original release prices are unverified.'}
    (ROOT / 'data/archive-provenance.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print('Preserved archive context for', len(catalog), 'copied item records.')


if __name__ == '__main__':
    main()
