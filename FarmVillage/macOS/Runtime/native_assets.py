"""Noninteractive, resumable native startup adapter for upstream WARC assets."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sys
import time

# Load only the wrapper's trusted sibling helper, including in isolated harnesses.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_paths import owned_path


def log(message: str) -> None:
    print(f"[FarmVillage assets] {message}", flush=True)


def md5(path: Path) -> str:
    result = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def asset_paths(assets) -> tuple[Path, Path, Path, Path, Path, Path]:
    """Validate every owned path before downloads, publication, or cleanup."""
    data = Path(assets.ASSETS_DIR).parent
    destination = owned_path(data, Path(assets.ASSETS_DIR))
    temporary = owned_path(data, Path(assets.TMP_DIR))
    warcs = owned_path(data, Path(assets.WARC_PATH))
    extracted = owned_path(data, Path(assets.EXTRACTION_PATH))
    staged = owned_path(data, Path(assets.EXTRACTED_INNER_ASSETS_PATH))
    canonical_data = data.resolve()
    if destination == canonical_data or temporary == canonical_data:
        raise RuntimeError("Assets and temporary files must use separate folders inside the game data folder.")
    for directory in (warcs, extracted):
        if directory == temporary or temporary not in directory.parents:
            raise RuntimeError("Archive downloads and extraction must stay inside the owned temporary folder.")
    if warcs == extracted or warcs in extracted.parents or extracted in warcs.parents:
        raise RuntimeError("Archive downloads and extraction must use separate temporary folders.")
    if staged == extracted or extracted not in staged.parents:
        raise RuntimeError("Extracted assets must stay inside the owned extraction folder.")
    if destination == temporary or destination in temporary.parents or temporary in destination.parents:
        raise RuntimeError("Published assets and temporary files must use separate folders.")
    return canonical_data, destination, temporary, warcs, extracted, staged


def download(assets, specification: dict, directory: Path) -> None:
    import requests

    if hasattr(assets, "ASSETS_DIR"):
        data, _, _, warcs, _, _ = asset_paths(assets)
        if directory.resolve() != warcs:
            raise RuntimeError("Archive downloads must use the owned WARC folder.")
        directory = warcs
    else:
        # Standalone callers supply a trusted download root. Its leaf must not
        # be a link; production additionally validates the complete data chain.
        data = directory.parent.resolve()
        directory = owned_path(directory.parent, directory)
    name = specification["filename"]
    expected = specification["hash"]
    destination = owned_path(directory, directory / name)
    partial = owned_path(directory, directory / (name + ".part"))
    if destination.is_file():
        log(f"Verifying cached archive {name}…")
        if md5(destination) == expected:
            owned_path(data, partial).unlink(missing_ok=True)
            return
        log(f"Archive {name} is corrupt; automatically replacing the downloaded cache.")
        owned_path(data, destination).unlink()
    last_error = None
    for attempt in range(1, 4):
        offset = partial.stat().st_size if partial.exists() else 0
        # Range offsets and the upstream checksum describe the archive bytes.
        # Negotiated transport compression changes that representation and can
        # make a valid partial archive impossible to resume.
        headers = {"Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            log(f"Downloading {name} (attempt {attempt}/3, resuming at {offset:,} bytes)…")
            with requests.get(assets.BASE_URL + name, headers=headers, stream=True, timeout=(15, 60)) as response:
                if response.status_code == 416:
                    if partial.is_file() and md5(partial) == expected:
                        os.replace(owned_path(data, partial), owned_path(data, destination))
                        return
                    owned_path(data, partial).unlink(missing_ok=True)
                    raise RuntimeError("The archive server could not resume the partial download; retrying from the beginning.")
                response.raise_for_status()
                if offset and response.status_code == 206:
                    if not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                        raise RuntimeError("The archive server returned an unexpected download range.")
                elif offset:
                    offset = 0  # This mirror does not support byte-range resumption.
                # The length is only a progress hint. Some mirrors omit it or
                # return an invalid value; the upstream digest remains the
                # authority for accepting the completed archive.
                try:
                    remaining = max(0, int(response.headers.get("Content-Length", "0")))
                except ValueError:
                    remaining = 0
                total = offset + remaining if remaining else 0
                received = offset
                progress_at = time.monotonic()
                with owned_path(data, partial).open("ab" if offset else "wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        output.write(chunk)
                        received += len(chunk)
                        if time.monotonic() - progress_at >= 5:
                            log(f"{name}: {received / 1024**3:.2f} GiB" + (f" / {total / 1024**3:.2f} GiB" if total else ""))
                            progress_at = time.monotonic()
            log(f"Verifying downloaded archive {name}…")
            if md5(partial) != expected:
                owned_path(data, partial).unlink(missing_ok=True)
                raise RuntimeError(f"Archive {name} failed its upstream MD5 integrity check.")
            os.replace(owned_path(data, partial), owned_path(data, destination))
            return
        except (requests.RequestException, OSError, RuntimeError) as error:
            last_error = error
            log(f"Download interrupted: {error}")
    raise RuntimeError(f"Could not download {name}. Partial downloads are preserved for the next Start. {last_error}")


def cleanup_completed_assets(assets) -> None:
    data, _, temporary, warcs, extracted, _ = asset_paths(assets)
    marker = owned_path(data, temporary / ".farmvillage-assets-cleanup")
    if not marker.is_file():
        return
    log("Cleaning up the wrapper's downloaded archives and extraction files…")
    complete = True
    for directory in (extracted, warcs):
        try:
            if directory.exists() or directory.is_symlink():
                shutil.rmtree(owned_path(data, directory))
        except OSError as error:
            complete = False
            log(f"Temporary cleanup will be retried on the next Start: {error}")
    if complete:
        try:
            owned_path(data, marker).unlink(missing_ok=True)
        except OSError as error:
            log(f"Temporary cleanup will be retried on the next Start: {error}")


def check_assets(assets) -> None:
    external = os.environ.get("FARMVILLAGE_ASSETS_DIR")
    if external:
        # An installer-prepared archive is a shared read-only input, separate
        # from this app's writable saves/cache. Never clean or redownload it.
        destination = Path(external)
        if (not destination.is_absolute() or ".." in destination.parts
                or any(path.is_symlink() for path in (destination, *destination.parents))
                or Path(assets.ASSETS_DIR) != destination):
            raise RuntimeError("The public asset folder differs from the installer configuration.")
        for name in ("Environment", "xpromoSupport"):
            path = destination / name
            if path.is_symlink() or not path.is_dir():
                raise RuntimeError("The prepared public assets are missing or incomplete. Run START_MAC.command again; Start will not download another archive.")
        log("Using the installer-prepared public archive without copying or downloading it.")
        return
    data, destination, temporary, warcs, extracted, staged = asset_paths(assets)
    environment = owned_path(data, destination / "Environment")
    xpromo = owned_path(data, destination / "xpromoSupport")
    if environment.is_dir() and xpromo.is_dir():
        log("Using the existing local game assets.")
        cleanup_completed_assets(assets)
        return
    log("Game assets are missing or incomplete. First Start downloads the upstream archives (about 18 GiB).")
    log("Download and extraction can take an hour or more. Stop safely keeps downloaded archives for the next Start.")
    log("Additional free space is needed for the extracted game; progress appears here while the game window waits.")
    owned_path(data, warcs).mkdir(parents=True, exist_ok=True)
    for specification in assets.FILES:
        download(assets, specification, warcs)
    # A previous interrupted extraction can contain truncated SWFs. Re-extract from
    # the already verified WARC files, while preserving saves and the assets folder.
    if extracted.exists():
        shutil.rmtree(owned_path(data, extracted))
    owned_path(data, extracted).mkdir(parents=True)
    log("All archives verified. Extracting the game assets; this may take up to an hour…")
    assets.assets_extract()
    # Recheck after the extractor has populated the unpublished tree.
    _, _, _, _, _, staged = asset_paths(assets)
    if not owned_path(data, staged / "Environment").is_dir() or not owned_path(data, staged / "xpromoSupport").is_dir():
        raise RuntimeError("The extracted archive does not contain the required asset directories. Start again to retry.")
    preserved = None
    if destination.exists():
        if destination.is_dir() and not any(destination.iterdir()):
            owned_path(data, destination).rmdir()
        else:
            preserved = owned_path(data, destination.with_name(f"assets.incomplete-{time.time_ns()}"))
            os.replace(owned_path(data, destination), owned_path(data, preserved))
            log(f"Preserved the previous incomplete assets at {preserved}.")
    try:
        # Record ownership before publication. If Stop lands after the rename,
        # the next Start resumes cleanup even though the assets are now complete.
        owned_path(data, temporary / ".farmvillage-assets-cleanup").touch()
        os.replace(owned_path(data, staged), owned_path(data, destination))
    except BaseException:
        if preserved and not destination.exists():
            os.replace(owned_path(data, preserved), owned_path(data, destination))
        raise
    cleanup_completed_assets(assets)
    log("Game assets are ready. Continuing server startup…")
