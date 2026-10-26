#!/usr/bin/env python3
"""Build the small Bifrost hosting update without including assets or saves."""

from __future__ import annotations

import gzip
import hashlib
import io
from pathlib import Path
import shutil
import tarfile


def main() -> None:
    workspace = Path(__file__).resolve().parents[2]
    sources = {
        "server_runner.py": workspace / "FarmVillage/portable/Linux/server_runner.py",
        "start-server.sh": workspace / "FarmVillage/portable/Linux/start-server.sh",
        "install-service.sh": workspace / "FarmVillage/portable/Linux/install-service.sh",
        "diagnose-saves.py": workspace / "FarmVillage/portable/Linux/diagnose-saves.py",
        "neighborhood_host.py": workspace / "FarmVillage/portable/Linux/neighborhood_host.py",
        "preloader_timing.py": workspace / "FarmVillage/portable/Linux/preloader_timing.py",
        "install-fresh-world.py": workspace / "FarmVillage/portable/Linux/install-fresh-world.py",
        "GodBarn/integration.py": workspace / "GodBarn/integration.py",
    }
    contents = {name: path.read_bytes() for name, path in sources.items()}
    contents["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in sorted(contents.items())
    ).encode()
    destination = workspace / "Bifrost LAN Update"
    destination.mkdir(exist_ok=True)
    archive = destination / "farmvillage-lan-host.tar.gz"
    temporary = destination / "farmvillage-lan-host.tar.gz.partial"
    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as output:
                for name, data in sorted(contents.items()):
                    member = tarfile.TarInfo("hosting/" + name)
                    member.mode = 0o755 if name.endswith(".sh") else 0o644
                    member.size = len(data)
                    output.addfile(member, io.BytesIO(data))
    with tarfile.open(temporary, "r:gz") as check:
        if set(check.getnames()) != {"hosting/" + name for name in contents}:
            raise ValueError("Unexpected hosting update inventory.")
        for name, data in contents.items():
            member = check.getmember("hosting/" + name)
            if not member.isfile() or check.extractfile(member).read() != data:
                raise ValueError("Hosting update failed verification: " + name)
    temporary.replace(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_name(archive.name + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n")
    delivery_helper = destination / "manage-bifrost.sh"
    delivery_helper.write_bytes((workspace / "FarmVillage/portable/manage-bifrost.sh").read_bytes())
    delivery_helper.chmod(0o755)
    (destination / "READ ME.txt").write_bytes((workspace / "FarmVillage/portable/bifrost-instructions.txt").read_bytes())
    fresh = workspace / "Bifrost Fresh Start"
    for name in ("farmvillage-fresh-world.tar.gz", "farmvillage-fresh-world.tar.gz.sha256"):
        if (fresh / name).is_file():
            shutil.copyfile(fresh / name, destination / name)
    print(f"Created {archive} ({archive.stat().st_size:,} bytes)")
    print(f"SHA256 {digest}")


if __name__ == "__main__":
    main()
