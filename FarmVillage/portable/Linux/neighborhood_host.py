"""Activate an authored persistent neighbourhood beside the sealed Runtime."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
import uuid


def _ordinary(path: Path, *, directory=False):
    if path.is_symlink() or (not path.is_dir() if directory else not path.is_file()):
        raise RuntimeError(f"The neighbourhood needs an ordinary {'folder' if directory else 'file'}: {path}")
    return path


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 1:
        raise ValueError("Unsupported neighbourhood manifest.")
    if not isinstance(manifest.get("updateId"), str) or not manifest["updateId"]:
        raise ValueError("The neighbourhood update needs an identity.")
    residents = manifest.get("residents")
    if not isinstance(residents, list) or len(residents) != 5:
        raise ValueError("The neighbourhood must contain exactly five residents.")
    identifiers = [manifest.get("playerUid")]
    for resident in residents:
        if not isinstance(resident, dict) or not isinstance(resident.get("name"), str) or not resident["name"].strip():
            raise ValueError("Each resident needs a name.")
        identifiers.append(resident.get("uid"))
    for identifier in identifiers:
        if not isinstance(identifier, str) or str(uuid.UUID(identifier)) != identifier:
            raise ValueError("Every farm needs a canonical UUID.")
    if len(set(identifiers)) != 6:
        raise ValueError("Neighbourhood farm identities must be unique.")
    files = manifest.get("saveFiles")
    if not isinstance(files, dict) or set(files) != set(identifiers):
        raise ValueError("The neighbourhood must identify all six save files.")
    if any(files[identifier] != identifier + ".save.json" for identifier in identifiers):
        raise ValueError("Neighbourhood save filenames must match their farm identities.")
    return tuple(identifiers)


def activate_neighborhood(data: Path, runtime: Path):
    """Select external initial templates before importing the game's player registry."""
    root = data / "neighborhood"
    if not root.exists() and not root.is_symlink():
        return None
    _ordinary(root, directory=True)
    source = _ordinary(root / "manifest.json")
    if source.stat().st_size > 1024 * 1024:
        raise ValueError("The neighbourhood manifest is too large.")
    manifest = json.loads(source.read_text(encoding="utf-8"))
    identifiers = validate_manifest(manifest)
    templates = _ordinary(root / "templates", directory=True)
    initial = _ordinary(templates / "initial.json")
    if initial.read_bytes() != (runtime / "villages" / "initial.json").read_bytes():
        raise ValueError("The neighbourhood initial farm must match the accepted game template.")
    if {path.name for path in templates.iterdir()} != {"initial.json"}:
        raise ValueError("The neighbourhood templates must contain only the initial farm.")
    for identifier in identifiers:
        _ordinary(data / "saves" / manifest["saveFiles"][identifier])
    bundle = importlib.import_module("bundle")
    bundle.VILLAGES_DIR = str(templates)
    return manifest


def configure_neighborhood(server, player, manifest):
    """Keep one playable owner while the five residents remain writable neighbours."""
    if manifest is None:
        return
    identifiers = validate_manifest(manifest)
    owner = manifest["playerUid"]
    if set(map(str, player.all_saves_uids())) != set(identifiers):
        raise RuntimeError("The active saves do not match the fresh neighbourhood manifest.")
    if set(map(str, player.neighbor_uids(owner))) != set(identifiers[1:]):
        raise RuntimeError("The player must have exactly the five authored neighbours.")
    original_choices = player.all_saves_info

    def player_choices():
        return [farm for farm in original_choices() if str(farm.get("uid")) == owner]

    player.all_saves_info = player_choices
    server.all_saves_info = player_choices
    bridge = server.app.extensions.get("god_barn")
    if bridge is None:
        raise RuntimeError("Register God Barn before configuring the neighbourhood.")
    bridge._uids = lambda: [owner]
    server.app.config["FARMVILLAGE_NEIGHBORHOOD"] = manifest

    from flask import Response, request

    @server.app.before_request
    def owner_requests_only():
        if request.path == "/new.html":
            return Response("Your fresh farm is already available on the home page.\n", status=403, mimetype="text/plain")
        if request.path == "/" and request.method == "POST" and request.form.get("UID") != owner:
            return Response("Choose your own farm to play.\n", status=403, mimetype="text/plain")
        if request.path == "/flashservices/gateway.php" and request.method == "POST":
            try:
                _, identifier, _ = server._decode_gateway(request.get_data(cache=True))
            except Exception:
                return None  # The game's decoder supplies the original malformed-request response.
            if str(identifier) != owner:
                return Response("Resident farms are available through neighbour visits.\n", status=403, mimetype="text/plain")

    @server.app.after_request
    def fresh_farm_selector(response):
        if request.path == "/" and request.method == "GET" and response.status_code == 200 and response.mimetype == "text/html":
            html = response.get_data(as_text=True)
            html = html.replace('<input type="checkbox" id="RUFFLE" name="RUFFLE"', '<input type="checkbox" id="RUFFLE" name="RUFFLE" checked')
            html = html.replace('<b><a href="/new.html">Create a new Village</a></b>', '<span>Your five resident neighbours are waiting at the farm gate.</span>')
            html = html.replace('<p style="font-size:13px; display: inline;">Or </p>', '')
            response.set_data(html)
        return response
