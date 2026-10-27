#!/usr/bin/env python3
"""Build an isolated GitHub candidate, without changing or publishing the source repo.

Replays the local linear fork onto the unchanged upstream base, excludes added
launcher media/fonts, and removes the owner's deployment identifiers. The source
checkout and its Git refs/config remain untouched. No network requests are made.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

BASE = "2dc25ca24032041a8b68d299b861eb2d4d449653"
OWNER_NAME = "jannsenburke"
OWNER_EMAIL = "342811002+jannsenburke@users.noreply.github.com"
LEGACY_OWNER_COMMITS = ("2e52311", "b00027c", "f7a0fa0", "53bdef1")
UPSTREAM_URL = "https://github.com/AcidCaos/farmvillage.git"
IGNORE = """
# Local preservation resources are excluded from this fork's published history.
/BADABB__.TTF
/macOS/Resources/Heritage/*.png
/macOS/Resources/Heritage/*.mp3
/macOS/Resources/Heritage/*.ttf
/templates/img/farm-gate/
"""


def git(root, *arguments, data=None, environment=None):
    env = dict(os.environ, **(environment or {}))
    return subprocess.run(["git", "-C", str(root), *arguments], input=data,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True, env=env).stdout


def entries(root, revision):
    result = {}
    for record in git(root, "ls-tree", "-rz", revision).split(b"\0"):
        if record:
            header, path = record.split(b"\t", 1)
            mode, kind, oid = header.decode().split()
            if kind != "blob":
                raise ValueError("Git submodules require a separate publication review")
            result[path.decode()] = (mode, oid)
    return result


def excluded(path):
    return (path == "BADABB__.TTF"
            or path.startswith("templates/img/farm-gate/")
            or (path.startswith("macOS/Resources/Heritage/")
                and Path(path).suffix.lower() not in (".md", ".json")))


def deployment_identifiers(root, revision):
    """Discover private values locally; never embed them in this tool/report."""
    text = git(root, "show", f"{revision}:portable/manage-bifrost.sh").decode()
    match = re.search(r"([A-Za-z0-9_.-]+)@(\d+\.\d+\.\d+\.\d+):(/home/[^\s/]+/farmville-test)", text)
    if not match:
        raise ValueError("Cannot identify the legacy deployment target; review before publishing")
    user, host, remote_root = match.groups()
    return {"target": f"{user}@{host}", "user": user, "host": host, "root": remote_root,
            "workspace": str(Path(root).resolve().parent)}


def sanitize_portable(path, payload, identifiers):
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload
    text = text.replace(identifiers["target"], "farmvillage@192.168.50.80")
    text = text.replace(identifiers["host"], "192.168.50.80")
    text = text.replace(identifiers["root"], "/home/farmvillage/farmville-test")
    text = text.replace(identifiers["workspace"], "/path/to/farmvillage-workspace")
    text = text.replace(identifiers["user"] + "@", "farmvillage@")
    if path in ("portable/manage-bifrost.sh", "portable/bifrost-update/manage-bifrost.sh"):
        config = '''
# Supply your own SSH target; the published fork contains no owner's LAN login.
target="${BIFROST_TARGET:?Set BIFROST_TARGET to your Ubuntu user@private-host}"
test_root="${BIFROST_ROOT:-/home/${target%%@*}/farmville-test}"
if [[ ! "$target" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9_.-]*$ || ! "$test_root" =~ ^/[A-Za-z0-9_./-]+$ ]]; then
    printf 'Use a user@host target and an absolute root without spaces or shell characters.\\n' >&2
    exit 1
fi
if [[ ! "${BIFROST_BIND:-${target#*@}}" =~ ^[0-9.]+$ ]]; then
    printf 'Set BIFROST_BIND to the private IPv4 address used by the server.\\n' >&2
    exit 1
fi
'''
        if path == "portable/manage-bifrost.sh":
            text = text.replace('set -euo pipefail\n', 'set -euo pipefail\n' + config, 1)
            text = text.replace('farmvillage@192.168.50.80:/home/farmvillage/farmville-test/release/', '"$target:$test_root/release/"')
            text = text.replace('ssh -t farmvillage@192.168.50.80', 'ssh -t "$target"')
            text = text.replace("remote_prepare='cd /home/farmvillage/farmville-test/release && sha256sum -c farmvillage-lan-host.tar.gz.sha256 && tar -xzf farmvillage-lan-host.tar.gz --no-same-owner -C ..'",
                                'remote_prepare="cd $test_root/release && sha256sum -c farmvillage-lan-host.tar.gz.sha256 && tar -xzf farmvillage-lan-host.tar.gz --no-same-owner -C .."')
            text = text.replace('/home/farmvillage/farmville-test/release/', '$test_root/release/')
            text = text.replace('bash ../hosting/install-service.sh"', 'bash ../hosting/install-service.sh ${BIFROST_BIND:-${target#*@}}"')
        else:
            text = text.replace("target='farmvillage@192.168.50.80'\ntest_root='/home/farmvillage/farmville-test'", config.strip())
            text = text.replace("remote_install+=' && tar -xzf farmvillage-lan-host.tar.gz --no-same-owner -C .. && bash ../hosting/install-service.sh'",
                                "remote_install+=' && tar -xzf farmvillage-lan-host.tar.gz --no-same-owner -C .. && bash ../hosting/install-service.sh'\nremote_install+=\" ${BIFROST_BIND:-${target#*@}}\"")
    elif path in ("portable/Linux/start-server.sh", "portable/Linux/install-service.sh"):
        text = text.replace('bind_address="${1:-192.168.50.80}"', 'bind_address="${1:-${BIFROST_BIND:-127.0.0.1}}"')
    elif path == "portable/Linux/diagnose-saves.py":
        text = text.replace('default=Path("/home/farmvillage/farmville-test/data")',
                            'default=Path(__file__).resolve().parents[1] / "data"')
    elif path in ("portable/test_manage_bifrost.py", "portable/bifrost-update/test_bifrost_update.py"):
        text = text.replace('FV_WRAPPER_LOG=str(self.log))', 'FV_WRAPPER_LOG=str(self.log),\n                                BIFROST_TARGET="farmvillage@192.168.50.80",\n                                BIFROST_ROOT="/home/farmvillage/farmville-test")')
    return text.encode("utf-8")


def commit_metadata(root, revision):
    raw = git(root, "cat-file", "commit", revision)
    header, message = raw.split(b"\n\n", 1)
    values = {}
    for name in ("author", "committer"):
        line = next(line for line in header.splitlines() if line.startswith(name.encode() + b" "))
        match = re.fullmatch(rb"\w+ (.*) <([^>]+)> (\d+ [+-]\d+)", line)
        if not match:
            raise ValueError("Unsupported commit identity")
        who, email, date = (value.decode() for value in match.groups())
        if revision.startswith(LEGACY_OWNER_COMMITS):
            who, email = OWNER_NAME, OWNER_EMAIL
        values.update({f"GIT_{name.upper()}_NAME": who,
                       f"GIT_{name.upper()}_EMAIL": email,
                       f"GIT_{name.upper()}_DATE": date})
    return values, message


def prepare(source, output, revision="HEAD", base=BASE):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Output must be a new directory; previous candidates are never overwritten")
    base = git(source, "rev-parse", base).decode().strip()
    head = git(source, "rev-parse", revision).decode().strip()
    git(source, "merge-base", "--is-ancestor", base, head)
    commits = git(source, "rev-list", "--reverse", f"{base}..{head}").decode().splitlines()
    for commit in commits:
        if len(git(source, "rev-list", "--parents", "-n", "1", commit).split()) != 2:
            raise ValueError("Fork history must be linear; merge commits require separate review")
    identifiers = deployment_identifiers(source, head)
    upstream_files = entries(source, base)
    if any(excluded(path) for path in upstream_files):
        raise ValueError("Filter would touch an upstream file")
    output.mkdir(parents=True)
    git(output, "init", "--initial-branch=godbarn-edition")
    git(output, "fetch", "--no-tags", str(source), head)
    git(output, "config", "user.name", OWNER_NAME)
    git(output, "config", "user.email", OWNER_EMAIL)
    git(output, "remote", "add", "upstream", UPSTREAM_URL)
    git(output, "remote", "set-url", "--push", "upstream", "DISABLED")
    index_env = {"GIT_INDEX_FILE": str(output / ".git/publication-index")}
    previous = base
    mapping, removed, rewritten = {}, set(), set()
    for old in commits:
        inventory = entries(output, old)
        git(output, "read-tree", old, environment=index_env)
        for path, (mode, oid) in inventory.items():
            if excluded(path):
                git(output, "update-index", "--force-remove", "--", path, environment=index_env)
                removed.add(path)
                continue
            if path.startswith("portable/"):
                original = git(output, "cat-file", "blob", oid)
                updated = sanitize_portable(path, original, identifiers)
                if updated != original:
                    new_oid = git(output, "hash-object", "-w", "--stdin", data=updated).decode().strip()
                    git(output, "update-index", "--add", "--cacheinfo", mode, new_oid, path, environment=index_env)
                    rewritten.add(path)
        original_ignore = git(output, "show", f"{old}:.gitignore").decode()
        ignored_oid = git(output, "hash-object", "-w", "--stdin", data=(original_ignore + IGNORE).encode()).decode().strip()
        git(output, "update-index", "--add", "--cacheinfo", "100644", ignored_oid, ".gitignore", environment=index_env)
        tree = git(output, "write-tree", environment=index_env).decode().strip()
        environment, message = commit_metadata(source, old)
        new = git(output, "commit-tree", tree, "-p", previous, data=message, environment=environment).decode().strip()
        mapping[old], previous = new, new
    git(output, "update-ref", "refs/heads/godbarn-edition", previous)
    git(output, "checkout", "-f", "godbarn-edition")
    # Local launcher resources remain usable, as ignored files, without entering Git.
    local_only = set(removed)
    local_only.update(str(path.relative_to(source)) for path in (source / "templates/img/farm-gate").glob("*") if path.is_file())
    for path in local_only:
        original = source / path
        if original.is_file():
            destination = output / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, destination)
    for new in mapping.values():
        if any(excluded(path) for path in entries(output, new)):
            raise ValueError("Publication filter verification failed")
        for value in (identifiers["target"], identifiers["host"], identifiers["root"], identifiers["workspace"]):
            check = subprocess.run(["git", "-C", str(output), "grep", "-I", "-l", "-F", value, new, "--", "portable"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if check.returncode != 1:
                raise ValueError("Private deployment identifier remains in outgoing portable history")
    if git(output, "status", "--porcelain").strip():
        raise ValueError("Publication candidate checkout must be clean")
    report = {"source_head": head, "upstream_base": base, "candidate_head": previous,
              "commit_map": mapping, "removed_paths": sorted(removed),
              "sanitized_portable_paths": sorted(rewritten),
              "local_only_copies": len(local_only), "pushed": False, "deployed": False}
    (output / ".git/publication-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.source, args.output, args.revision)
    print(json.dumps({"candidate": str(args.output.resolve()), **report}, indent=2))


if __name__ == "__main__":
    main()
