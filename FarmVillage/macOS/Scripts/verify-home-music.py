#!/usr/bin/env python3
"""Record the original home-farm playlist and verify its local archived files."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zlib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    import pyamf
    source = args.source.resolve()
    manifest_path = source / 'assethash/v9/assethash.master.amf.gz'
    settings_path = source / 'xml/gz/v855098/gameSettings.xml.gz'
    manifest = pyamf.get_decoder(pyamf.AMF3, zlib.decompress(manifest_path.read_bytes())).readElement()
    settings = ET.fromstring(zlib.decompress(settings_path.read_bytes()))
    playlist = settings.findall("./backgroundMusic/musicSet[@location='farm']/music")
    ambience = settings.findall("./ambientMusic/music[@location='farm']")
    entries = []
    for node in [*playlist, *ambience]:
        logical = node.attrib['url']
        group, relative = logical.removeprefix('assets/').split('/', 1)
        hashed = manifest[group][relative]
        path = source / 'LocalData/assets' / group / Path(relative).parent / (hashed + Path(relative).suffix)
        data = path.read_bytes()
        if not data:
            raise ValueError('Empty original audio file: ' + logical)
        entries.append({'logical_name': logical, 'source': str(path.relative_to(source)),
                        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
                        'role': 'music' if node in playlist else 'ambience'})
    if len(playlist) != 6 or not ambience:
        raise ValueError('The recovered home playlist no longer matches the reviewed six-track source.')
    result = {'schema': 1, 'provenance': 'Original recovered gameSettings playlist and asset manifest. Exact recording/first-use dates unverified; filenames include 2011.',
              'settings_sha256': hashlib.sha256(settings_path.read_bytes()).hexdigest(),
              'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(), 'entries': entries,
              'playback': 'Original game music/sfx toggles remain independent. Native master volume is remembered; opt-in launcher Barnyard stops before the game opens.'}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('Verified original playlist:', len(playlist), 'tracks and', len(ambience), 'ambience recording(s).')


if __name__ == '__main__':
    main()
