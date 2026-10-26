#!/usr/bin/env python3
"""Launch the standalone companion; never discovers or contacts a game server."""
from __future__ import annotations

import argparse
import errno
from pathlib import Path
import threading
import webbrowser

from server import GodBarnServer, GodBarn


def main():
    parser = argparse.ArgumentParser(description="Open the God Barn copied-save companion.")
    parser.add_argument("--no-browser", action="store_true", help="Print the local URL without opening a browser.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    # Only this companion's workspace is ever opened. No game paths or game ports.
    workspace = GodBarn(root=root, workspace=root / "workspace")
    server = None
    for port in range(8877, 8897):
        try:
            server = GodBarnServer(("127.0.0.1", port), workspace)
            break
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
    if server is None:
        raise SystemExit("God Barn's local ports are busy. Close an earlier companion window and try again.")
    url = "http://127.0.0.1:{}/".format(server.server_address[1])
    print("\n  GOD BARN · FarmVillage Companion", flush=True)
    print("  " + url, flush=True)
    print("  Copied saves only. Keep this terminal open while using the barn.", flush=True)
    print("  Press Control-C to close the companion.\n", flush=True)
    if not args.no_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nThe barn is closed. Your copies and snapshots are saved.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
