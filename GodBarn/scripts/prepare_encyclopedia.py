#!/usr/bin/env python3
"""Copy additional archive facts and source-backed prize shelves into God Barn.

Only the GodBarn copy is written. The source AMF, localization SWF, game files,
and saves are read-only. Historical prize labels/dates are a small, attributed
curation; they never replace the later sale dates in archive.raw.
"""
from __future__ import annotations

import argparse
import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import re
import zlib

ROOT = Path(__file__).resolve().parents[1]
FACT_FIELDS = (
    'XP', 'buyXp', 'sellPrice', 'mastery', 'masteryYield', 'masteryTarget',
    'harvestYield', 'harvestItem', 'actionText', 'animalType', 'capacity',
    'storageType', 'storageSize', 'baby', 'nextLevel', 'expansion',
)
SNAPSHOT_SOURCE = 'recovered-item-snapshot'


def first_records(records):
    """The game selects the first record with a name, including duplicate names."""
    result = {}
    for index, item in enumerate(records):
        if isinstance(item, dict) and isinstance(item.get('name'), str):
            result.setdefault(item['name'], (index, item))
    return result


def related_names(item, by_name, by_code):
    related = []
    for field in ('baby', 'expansion', 'nextLevel', 'harvestItem'):
        value = item.get(field)
        if not isinstance(value, str):
            continue
        name = value if value in by_name else by_code.get(value)
        if name and name != item['name'] and name not in related:
            related.append(name)
    levels = item.get('masteryLevel', [])
    if isinstance(levels, dict):
        levels = [levels]
    if isinstance(levels, list):
        for level in levels:
            gift = level.get('gift') if isinstance(level, dict) else None
            if isinstance(gift, str):
                name = gift if gift in by_name else by_code.get(gift)
                if name and name != item['name'] and name not in related:
                    related.append(name)
    return related


def build_overlay(records, curation, digest):
    if (not isinstance(curation, dict) or curation.get('schema') != 1
            or not isinstance(curation.get('sources'), list) or not isinstance(curation.get('shelves'), list)):
        raise ValueError('Historical curation must contain sources and shelves.')
    source_ids = {entry['id'] for entry in curation['sources'] if isinstance(entry, dict) and isinstance(entry.get('id'), str)}
    shelf_ids = set()
    for shelf in curation['shelves']:
        if (not isinstance(shelf, dict) or not isinstance(shelf.get('id'), str)
                or shelf['id'] in shelf_ids or not isinstance(shelf.get('name'), str)
                or not isinstance(shelf.get('sourceId'), str) or shelf['sourceId'] not in source_ids
                or not isinstance(shelf.get('prizes'), list)):
            raise ValueError('Historical shelves require unique ids, prizes and a known source.')
        shelf_ids.add(shelf['id'])
        try:
            date.fromisoformat(shelf['releaseDate'])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError('A historical shelf requires a real ISO release date.') from error
        for prize in shelf['prizes']:
            if not isinstance(prize, dict) or not isinstance(prize.get('label'), str) or not prize['label'].strip():
                raise ValueError('Historical prizes require a display label.')
    by_name = first_records(records)
    by_code = {}
    for name, (_, item) in by_name.items():
        if isinstance(item.get('code'), str):
            by_code.setdefault(item['code'], name)
    sources = [{
        'id': SNAPSHOT_SOURCE, 'title': 'Recovered FarmVille item catalog',
        'kind': 'Original game data', 'file': 'xml/gz/v855038/items_opt.amf',
        'sha256': digest,
    }] + curation.get('sources', [])
    result = {'schema': 1, 'sources': sources, 'items': {}, 'shelves': [],
              'policy': 'Game facts retain source values. Wiki prize history and recovered sale windows are separate evidence. No historical odds or random draws are recreated.'}
    for name, (index, item) in by_name.items():
        facts = {key: copy.deepcopy(item[key]) for key in FACT_FIELDS if key in item}
        related = related_names(item, by_name, by_code)
        if not facts and not related:
            continue
        entry = {'facts': facts, 'sourceIds': [SNAPSHOT_SOURCE],
                 'recordIndex': index, 'code': item.get('code')}
        if related:
            entry['relatedItems'] = related
        result['items'][name] = entry
    for source_shelf in curation.get('shelves', []):
        shelf = {key: copy.deepcopy(value) for key, value in source_shelf.items() if key != 'prizes'}
        shelf.update(items=[], unmatchedItems=[])
        for prize in source_shelf.get('prizes', []):
            name = prize.get('name')
            if not isinstance(name, str) or name not in by_name or by_name[name][1].get('code') != prize.get('code'):
                shelf['unmatchedItems'].append({'label': prize['label'],
                                               'reason': 'No verified matching item name and code in this archive.'})
                continue
            if name in shelf['items']:
                continue
            shelf['items'].append(name)
            index, raw = by_name[name]
            entry = result['items'].setdefault(name, {
                'facts': {}, 'sourceIds': [SNAPSHOT_SOURCE],
                'recordIndex': index, 'code': raw.get('code'),
            })
            # These labels were checked against the original item identities.
            # The wiki's "Sneaky Scarecrow" differs from the recovered label.
            entry['displayName'] = prize.get('displayName', prize['label'])
            entry.setdefault('shelves', []).append(shelf['id'])
            entry.setdefault('releaseHistory', []).append({
                'date': shelf['releaseDate'], 'event': shelf['name'],
                'acquisition': 'Possible Mystery Box prize',
                'sourceId': shelf['sourceId'], 'shelfId': shelf['id'],
            })
            if shelf['sourceId'] not in entry['sourceIds']:
                entry['sourceIds'].append(shelf['sourceId'])
            if prize.get('note'):
                entry.setdefault('notes', []).append(prize['note'])
        result['shelves'].append(shelf)
    return result


def copy_thumbnails(source, manifest, records, overlay, provenance):
    """Copy original icons for this small curation and preserve their hashes."""
    by_name = first_records(records)
    assets = {entry['path']: entry for entry in provenance.get('assets', [])
              if isinstance(entry, dict) and isinstance(entry.get('path'), str)}
    for shelf in overlay['shelves']:
        for name in shelf['items']:
            images = by_name[name][1].get('image') or []
            if isinstance(images, dict):
                images = [images]
            images = sorted((image for image in images if isinstance(image, dict)
                             and str(image.get('url', '')).endswith('.png')),
                            key=lambda image: (image.get('name') != 'icon', '200' in image.get('url', '')))
            for image in images:
                logical = image['url'].removeprefix('assets/')
                if '/' not in logical:
                    continue
                group, relative = logical.split('/', 1)
                hashed = manifest.get(group, {}).get(relative)
                if not isinstance(hashed, str) or not re.fullmatch(r'[0-9a-fA-F]{32,64}', hashed):
                    continue
                original = source / 'LocalData/assets' / group / Path(relative).parent / (hashed + Path(relative).suffix)
                if not original.is_file():
                    continue
                copied = 'static/assets/items/' + original.name
                destination = ROOT / copied
                if destination.is_symlink():
                    raise ValueError('Thumbnail output must not be a symlink.')
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, destination)
                payload = destination.read_bytes()
                digest = hashlib.sha256(payload).hexdigest()
                overlay['items'][name]['thumbnail'] = {'image': '/' + copied,
                    'logical': image['url'], 'sha256': digest}
                assets[copied] = {'path': copied, 'logical': image['url'],
                    'originalPath': str(original), 'bytes': len(payload), 'sha256': digest}
                break
    provenance['assets'] = list(assets.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Read-only FarmVillage checkout')
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    payload = (source / 'xml/gz/v855038/items_opt.amf').read_bytes()
    import pyamf
    records = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(payload)).readElement()['settings']['items']['item']
    curation_bytes = (ROOT / 'data/historical-prizes.json').read_bytes()
    curation = json.loads(curation_bytes)
    overlay = build_overlay(records, curation, hashlib.sha256(payload).hexdigest())
    overlay['curationSha256'] = hashlib.sha256(curation_bytes).hexdigest()
    manifest = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(
        (source / 'assethash/v9/assethash.master.amf.gz').read_bytes())).readElement()
    provenance_path = ROOT / 'data/provenance.json'
    provenance = json.loads(provenance_path.read_text())
    copy_thumbnails(source, manifest, records, overlay, provenance)
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
    output = ROOT / 'data/encyclopedia.json'
    temporary = output.with_suffix('.preparing.json')
    temporary.write_text(json.dumps(overlay, ensure_ascii=False, separators=(',', ':')) + '\n')
    temporary.replace(output)
    print(json.dumps({'enrichedItems': len(overlay['items']), 'historicalShelves': len(overlay['shelves']),
                      'matchedPrizes': sum(len(shelf['items']) for shelf in overlay['shelves']),
                      'unmatchedPrizes': sum(len(shelf['unmatchedItems']) for shelf in overlay['shelves']),
                      'bytes': output.stat().st_size}, indent=2))


if __name__ == '__main__':
    main()
