"""Load upstream gameplay in a single owned process with a reserved loopback socket."""

from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import secrets
import socket
import sys

from native_assets import check_assets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    arguments = parser.parse_args()
    runtime = arguments.runtime.resolve()
    host = "127.0.0.1"
    # Reserve the port before any expensive download. No unrelated server is reused.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind((host, arguments.port))
    except OSError as error:
        listener.close()
        raise RuntimeError(f"Port {arguments.port} is unavailable. Close the application using it, then Start again.") from error
    try:
        os.chdir(runtime)
        sys.path.insert(0, str(runtime))
        # Replace only the startup asset workflow. The game logic remains upstream.
        assets = importlib.import_module("assets")
        assets.check_assets = lambda: check_assets(assets)
        sys.argv = [str(runtime / "server.py"), "--host", host, "--port", str(arguments.port),
                    "--public-url", f"http://{host}:{arguments.port}"]
        server = importlib.import_module("server")
        server.app.secret_key = secrets.token_bytes(32)
        server.app.root_path = str(runtime)
        server.app.template_folder = server.TEMPLATES_DIR
        server.app.static_folder = server.TEMPLATES_DIR
        # God Barn shares this owned server and the game's existing save locks.
        # Its implementation remains a separate namespaced companion package.
        from GodBarn.integration import register_god_barn
        register_god_barn(
            server.app, game_server=server,
            player_module=importlib.import_module("player"),
            bundle_module=importlib.import_module("bundle"),
            farming_module=importlib.import_module("barn_actions"),
        )
        from native_launcher import register_launcher
        register_launcher(server.app, player_module=importlib.import_module("player"),
                          bundle_module=importlib.import_module("bundle"))
        from werkzeug.serving import make_server
        listener.listen(128)
        httpd = make_server(host, arguments.port, server.app, threaded=True, fd=listener.fileno())
        listener.close()  # Werkzeug now owns a duplicate of the reserved descriptor.
        print("[FarmVillage] Game server ready; local Ruffle is available.", flush=True)
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()
    finally:
        listener.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        print(f"[FarmVillage] ERROR: {error}", flush=True)
        raise SystemExit(1)
