#!/usr/bin/env python3
"""Download, verify and assemble public originals in a chosen external folder."""
import argparse, json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from resource_pipeline import check_pack, plan, setup, target_path

def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', required=True, type=Path)
    parser.add_argument('--audience', choices=('mac', 'server'), required=True)
    parser.add_argument('--accept-downloads', action='store_true', help='Consent to printed public downloads and builds in this folder')
    parser.add_argument('--check', action='store_true', help='Verify a complete pack without downloading')
    args = parser.parse_args(arguments)
    pack = target_path(args.resources)
    if args.check:
        state = check_pack(pack)
        print('Complete %s resource pack verified: %s' % (state['audience'], pack))
        return 0
    print(json.dumps({'target': str(pack), **plan(args.audience)}, indent=2), flush=True)
    if not args.accept_downloads:
        print('Plan only. Nothing was created. Rerun with --accept-downloads to proceed.')
        return 0
    setup(pack, args.audience)
    print('Resources ready: ' + str(pack))
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyboardInterrupt) as error:
        print('Resource setup paused: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
