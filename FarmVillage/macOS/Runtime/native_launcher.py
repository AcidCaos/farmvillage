"""Native farm creation/import; authenticated to this exact owned runtime."""

from __future__ import annotations

import copy
import os
from pathlib import Path
import secrets
import uuid

from flask import jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from native_paths import owned_path


def register_launcher(app, *, player_module, bundle_module):
    from persistence import (CommittedSaveError, atomic_bytes, commit_json_batch,
                             decode_json, save_transaction)

    player = player_module
    root = Path(bundle_module.DATA_DIR).resolve()
    saves = owned_path(root, root / "saves")
    token = os.environ.get("FARMVILLAGE_INSTANCE_TOKEN", "")

    def authorize():
        supplied = request.headers.get("X-FarmVillage-Token", "")
        return bool(token and supplied and secrets.compare_digest(token.encode("utf-8"), supplied.encode("utf-8")))

    def result(uid, warning=None):
        value = {"uid": uid, "farm": player.save_info(uid),
                 "committed": True, "durabilityConfirmed": not bool(warning)}
        if warning:
            value["warning"] = warning
        return jsonify(value)

    def import_path(path):
        try:
            return owned_path(root, path)
        except RuntimeError as error:
            # Path guards deliberately fail closed; keep their actionable
            # message in the API's JSON error contract instead of an HTML 500.
            raise ValueError(str(error)) from error

    def available_presets():
        presets = [{"id": "classic", "name": "Classic farm"}]
        october = getattr(player, "october_village", None)
        if october is not None and october.AVAILABLE:
            presets.append({"id": october.PRESET, "name": october.DISPLAY_NAME})
        return presets

    @app.get("/launcher/presets")
    def launcher_presets():
        if not authorize():
            return jsonify(error="This action belongs to a different local server session."), 403
        response = jsonify(presets=available_presets())
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/launcher/create")
    @save_transaction
    def launcher_create():
        if not authorize():
            return jsonify(error="This action belongs to a different local server session."), 403
        request.max_content_length = 4096
        try:
            value = request.get_json(silent=True)
            name = value.get("name") if isinstance(value, dict) else None
            if not isinstance(name, str) or not name.strip() or len(name) > 80:
                return jsonify(error="Use a farmer name between 1 and 80 characters."), 400
            preset = value.get("preset", "classic")
            if not isinstance(preset, str) or preset not in {entry["id"] for entry in available_presets()}:
                return jsonify(error="Choose an available village style."), 400
            before = set(player.all_saves_uids())
            warning = None
            try:
                uid = (player.new_village(name=name) if preset == "classic"
                       else player.new_village(name=name, preset=preset))
            except CommittedSaveError:
                # new_village retains a committed farm in its registry. The
                # outer save lock makes this delta unambiguous: do not invite
                # another creation by reporting that a successful save failed.
                created = set(player.all_saves_uids()) - before
                if len(created) != 1:
                    raise
                uid = created.pop()
                warning = ("Your farm was created, but the filesystem could not confirm the save's durability. "
                           "Do not create it again. Check Activity before restarting.")
                app.logger.warning("Native farm creation committed with a storage durability warning for %s", uid)
            return result(uid, warning)
        except RequestEntityTooLarge:
            return jsonify(error="The farmer-name request must be smaller than 4 KiB."), 413
        except (ValueError, TypeError) as error:
            return jsonify(error=str(error)), 400
        except OSError:
            app.logger.exception("Native farm creation failed")
            return jsonify(error="The farm could not be saved. Check free disk space and Activity."), 500

    @app.post("/launcher/import")
    @save_transaction
    def launcher_import():
        if not authorize():
            return jsonify(error="This action belongs to a different local server session."), 403
        request.max_content_length = 64 * 1024 * 1024
        try:
            original = request.get_data(cache=False)
            imported = decode_json(original)
            uid = player._validate_save(imported)
            saves.mkdir(parents=True, exist_ok=True)
            target = import_path(saves / f"{uid}.save.json")
            if uid in player.all_uids() or target.exists():
                return jsonify(error="A farm with this identity already exists. Import leaves it unchanged."), 409
            # Also detect legacy filenames and duplicate-UID files which the game
            # deliberately omits from its in-memory registry.
            for file in saves.iterdir():
                filename = file.name.lower()
                if (file.name.startswith((".", "~")) or file.is_symlink() or not filename.endswith(".json")
                        or filename.endswith((".bak.json", ".backup.json", ".tmp.json")) or not file.is_file()):
                    continue
                try:
                    if player._validate_save(decode_json(file.read_bytes())) == uid:
                        return jsonify(error="A farm with this identity already exists. Import leaves it unchanged."), 409
                except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
                    continue
            candidate = copy.deepcopy(imported)
            player.migrate_loaded_save(candidate)
            if player._validate_save(candidate, ready=True) != uid:
                raise ValueError("Import migration changed the farm identity.")
            backups = import_path(saves / ".import-backups")
            backups.mkdir(exist_ok=True)
            backups = import_path(backups)
            atomic_bytes(import_path(backups / f"{uid}.{uuid.uuid4().hex}.original"), original)
            warning = None
            try:
                commit_json_batch(saves, {target: player._save_contents(candidate)}, indent=4)
            except CommittedSaveError as error:
                warning = str(error)
            player.load_saves()
            if uid not in player.all_saves_uids():
                raise ValueError("The imported farm could not be loaded; its source backup is preserved.")
            return result(uid, warning)
        except RequestEntityTooLarge:
            return jsonify(error="Choose a JSON save smaller than 64 MiB."), 413
        except (ValueError, TypeError, UnicodeError, RecursionError) as error:
            return jsonify(error=f"This save could not be imported: {error}"), 400
        except OSError:
            app.logger.exception("Native farm import failed")
            return jsonify(error="The import could not be saved. Original farms are unchanged; check Activity."), 500
