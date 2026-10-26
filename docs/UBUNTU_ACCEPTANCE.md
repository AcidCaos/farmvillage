# Ubuntu acceptance run sheet

This page is a form to fill in during the first real installation on the Ubuntu host. **Nothing on it has been run on that host.** Actual Ubuntu installation, managed-service operation and gameplay stay **UNRUN** until you record them here with evidence. It does not repeat the installer steps: follow [BIFROST_SETUP.md](../BIFROST_SETUP.md) exactly, and use this page to prepare, observe and record.

Keep the platforms separate. A native Mac window, a browser on the Mac, and this Ubuntu host are three different results (see [Wave 3](<../Wave 3.md>), lane R02, and [current status](../HANDOVER_STATUS.md)). Preparing a package does not authorize a live deployment. That decision, and the decision to wipe the named managed folder, are yours.

## What counts as evidence

| Result | Meaning |
| --- | --- |
| PASS | You watched it happen on the Ubuntu host and the evidence column says how. |
| FAIL | You watched it not happen. Record the exact message and the step number. |
| UNRUN | You did not perform it, or could not. This is neither a pass nor a defect. |
| NOT APPLICABLE | It cannot apply, for a stated reason (for example, no earlier service exists on a first install). |

## Optional rehearsal first

[`tools/rehearse-linux-host.py`](../tools/rehearse-linux-host.py) is a **rehearsal**. It starts the real host runner as separate processes on loopback against a stub game and checks sign-in, the request fences, the single-owner lock, address refusal, the sign-in throttle, a SIGTERM that lets an in-flight save finish, restart persistence and password rotation. It takes a few seconds and changes nothing outside a temporary folder.

```sh
"$FV_CHECK_ENV/bin/python" -B tools/rehearse-linux-host.py --receipt "$HOME/farmvillage-rehearsal-receipt.json"
```

Exit status 0 means every check passed, 1 means at least one failed, and 2 means this host cannot run it, which is UNRUN. A pass is **not** a Bifrost install, not the setup wizard, not gameplay, not a LAN address and not systemd. It tells you the runner behaves on this machine, so a failure in the real run is less likely to be the runner itself. Its first lines also report, without scoring it, what step 1 of the wizard says on this host.

## Pre-flight checklist

Tick each item and note the output in the ledger below.

- [ ] You are logged in on the Ubuntu host itself, as your normal user, not through sudo. `id -u` does not print `0`.
- [ ] `python3 --version` is 3.10 or newer, and `python3 -m venv --help` works.
- [ ] The systemd user session works: `systemctl --user show-environment` exits 0, and `loginctl` exists.
- [ ] The prepared bundle is extracted **outside** the installation target.
- [ ] The artwork is an already extracted `assets` folder containing `Environment/` and `xpromoSupport/`. A WARC archive is not.
- [ ] Free space is recorded with `df -h`. The wizard requires the artwork plus the bundle plus 1 GiB free on the target's parent filesystem, and refuses before erasing anything if there is not enough. Resource preparation needs far more; see the [server owner guide](PLAY_ON_SERVER.md).
- [ ] PyPI is reachable for step 6. No game artwork is downloaded by the installer.
- [ ] The target is the managed folder you intend to wipe, normally `~/farmvillage-server`, and you have written down that you authorize erasing everything inside it.
- [ ] The port (normally 5501) is free: `ss -ltn` shows nothing on it. `hostname -I` gives the private address you will choose.
- [ ] Baselines saved so you can prove nothing unrelated changed:

```sh
systemctl --user list-units --type=service --no-pager > "$HOME/services-before.txt"
ls -la "$HOME" > "$HOME/home-before.txt"
```

## Record before you start

Fill these in first. They are what make a later PASS reproducible.

| Field | Value |
| --- | --- |
| Date, time zone, operator | |
| `grep PRETTY_NAME /etc/os-release`, `uname -r` | |
| `python3 --version` | |
| Source commit the bundle was built from (`git rev-parse HEAD` in the source checkout) | |
| `reviewedFromCommit` in `SOURCE_MANIFEST.json` | |
| `sha256sum PRIVATE_RELEASE_MANIFEST.json` in the extracted bundle | |
| Target path, bind address, port, printed browser URL | |
| `df -h` for the target's parent folder | |

## Evidence

Step numbers refer to the eight steps in [BIFROST_SETUP.md](../BIFROST_SETUP.md). Commands marked read-only change nothing. Commands that use `systemctl`, `journalctl` or `loginctl` were **not run** while this page was written, because the writing environment had no systemd; check their output rather than trusting this page.

Set `T` to your target for the commands below:

```sh
T="$HOME/farmvillage-server"
```

| ID | What must be true | How to observe it | Result | Evidence |
| --- | --- | --- | --- | --- |
| E01 | Step 1 finishes without refusing. | The terminal shows step 1 of 8 and the wizard continues. | UNRUN | |
| E02 | Step 2 names the target and what it is, and touches nothing else. | The wizard prints `Installation target` and `Identified as`. After the run, compare `ls -la "$HOME"` with `home-before.txt`: only the target differs, apart from any `.farmvillage-stage-*` folder while it runs. | UNRUN | |
| E03 | Step 3 stages every artwork file. | The last `Artwork:` line shows equal counts. Compare with `find <assets> -type f \| wc -l`. | UNRUN | |
| E04 | Optional: a wrong confirmation in step 4 erases nothing. | Type anything but the phrase. The wizard says the old installation is untouched. `find "$T" -type f \| wc -l` is the same before and after. Then rerun. | UNRUN | |
| E05 | Step 4 accepts only `WIPE ` followed by the exact printed path. | Type it exactly as printed. | UNRUN | |
| E06 | Step 5 stops only the matching service. | `systemctl --user list-units --type=service --no-pager` against `services-before.txt`: only `farmvillage.service` changes. NOT APPLICABLE on a first install with no earlier service. | UNRUN | |
| E07 | After step 5 no earlier farm, snapshot, history or sign-in remains. | `python3 -m json.tool "$T/.farmvillage-clean-install.json"` shows `"cleanStart": true`, `"activeWorlds": 16` and `retiredWorlds` listing `glen` and `hlights`, the two retired worlds. `ls "$T/data/saves"` shows no earlier farm. | UNRUN | |
| E08 | Step 6 installs the five pinned dependencies in a new environment. | Read-only: `"$T/release/.venv/bin/python" -m pip freeze > installed.txt` then `grep -Fixf FarmVillage/requirements.txt installed.txt \| wc -l` prints `5`. | UNRUN | |
| E09 | Step 7 stores a hash and a new secret privately and never shows the password. | The prompt is hidden. `ls -ld "$T/data/.lan-server"` is `drwx------`, and `ls -l "$T/data/.lan-server"` shows `password.hash` and `session.secret` as `-rw-------`. Never type the password into a command line to look for it. | UNRUN | |
| E10 | Step 8: the service is running and the sign-in page answers. | `systemctl --user status farmvillage.service` is `active (running)`. `curl -s -o /dev/null -w '%{http_code}\n' <origin>/server-login` prints `200`. | UNRUN | |
| E11 | The served files are the files the release lists. | Run the identity check below. It must print that every file matches. It applies the same size-and-hash rule as the wizard's own `verify_payload`, which also runs each time the service starts. | UNRUN | |
| E12 | Signed-out requests are refused. | `curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' <origin>/` prints `303` and the `/server-login` address. | UNRUN | |
| E13 | Sign-in works from another computer at the printed address, and a wrong password does not. | In a browser on a different computer. Record both attempts. | UNRUN | |
| E14 | A new farm is created through the game page. World access follows original eligibility, not all sixteen granted. | Create it at `<origin>/new.html`. Record which worlds are offered. | UNRUN | |
| E15 | A real cycle works at original prices and timers. | Plow, plant, wait the natural crop timer (or use the original paid rush), harvest. Record crop, price, timer and the before and after balances. Synthetic funding is not earned play. | UNRUN | |
| E16 | Save and reload keep the state. | Reload the browser tab so it loads a fresh document. The farm and balances are unchanged. | UNRUN | |
| E17 | An owned-process restart keeps the farm and the sign-in. | `systemctl --user show -p MainPID farmvillage.service`, then `systemctl --user restart farmvillage.service`, then the same command again: the process id changes. The farm is intact and the open tab still works. | UNRUN | |
| E18 | A stop (SIGTERM) shuts down cleanly and loses nothing. | Stop right after a harvest: `systemctl --user stop farmvillage.service`. Then `systemctl --user show -p Result -p ExecMainStatus farmvillage.service` shows `Result=success` and `ExecMainStatus=0`. Start it again and confirm the last action is saved. You cannot prove a request was in flight at that instant; the rehearsal checks that logic with a stub. | UNRUN | |
| E19 | Password rotation revokes old sign-ins. | Not in the guide. Derived from the wizard's own start command. Stop the service, run the command printed by the rotation snippet below at a terminal, type a new password twice, start the service. The old tab goes back to sign-in, the old password fails and the new one works. | UNRUN | |
| E20 | Optional: the service survives logout and boot. | Only if you accepted the boot setting: `loginctl show-user "$USER" -p Linger` prints `Linger=yes`; after a reboot the service is active. | UNRUN | |

### Identity check (E11)

Read-only. It needs only Python 3 and compares each file listed in the release manifest by size and SHA-256.

```sh identity-check
T="${T:-$HOME/farmvillage-server}"
python3 - "$T/release" <<'PY'
import hashlib, json, sys
from pathlib import Path
release = Path(sys.argv[1])
manifest = json.loads((release / "PRIVATE_RELEASE_MANIFEST.json").read_text())
bad = []
for name, info in sorted(manifest["files"].items()):
    path = release / name
    if not path.is_file() or path.is_symlink():
        bad.append(name + " (missing)")
        continue
    raw = path.read_bytes()
    if len(raw) != info["bytes"] or hashlib.sha256(raw).hexdigest() != info["sha256"]:
        bad.append(name + " (differs)")
if bad:
    print("MISMATCH:", *bad, sep="\n  ")
    raise SystemExit(1)
print("%d files match the release manifest" % len(manifest["files"]))
PY
```

Also confirm the manifest itself is the one you extracted: `sha256sum "$T/release/PRIVATE_RELEASE_MANIFEST.json" <bundle>/PRIVATE_RELEASE_MANIFEST.json` prints two equal hashes.

### Rotation command (E19)

This prints, and does not run, the command that sets a new password. It is the start command the wizard builds, plus the two flags. Run it by hand only with the service stopped, because the runner holds a lock on the data folder.

```sh rotation-command
T="${T:-$HOME/farmvillage-server}"
python3 - "$T" <<'PY'
import json, shlex, sys
from pathlib import Path
target = Path(sys.argv[1])
marker = json.loads((target / ".farmvillage-clean-install.json").read_text())
print(shlex.join([str(target / "release/.venv/bin/python"), "-B", "-u", str(target / "release/hosting/server_runner.py"),
                  "--runtime", str(target / "release/Runtime"), "--backend-host", str(target / "release/BackendHost"),
                  "--data-dir", str(target / "data"), "--bind", marker["bind"], "--port", str(marker["port"]),
                  "--public-url", marker["origin"], "--init-only", "--set-password"]))
PY
```

## If something fails

Read "If a step needs another try" in [BIFROST_SETUP.md](../BIFROST_SETUP.md) first. This release starts clean by policy, so there is no restore path and none should be improvised.

- Record the step number and the exact message as FAIL. Do not paraphrase it.
- Do not edit the target by hand and do not rename folders to get past a refusal.
- If a step fails after the new installation was published, the earlier state is already gone by design. Fix the stated cause and rerun the same wizard.
- Record what the failure shows about the wizard or the runner separately from what it shows about your host.

## After the run

1. Fill the ledger and keep the terminal output. Do not keep any password.
2. Update [`HANDOVER_STATUS.md`](../HANDOVER_STATUS.md) and [`WORLD_READINESS.md`](../WORLD_READINESS.md) only for rows you marked PASS, naming the source commit and the bundle manifest hash. Leave every other row UNRUN.
3. Do not generalize. One farm and one session show nothing about long-session stability, other worlds, or any other host.

## Results ledger

Copy this block and fill it in.

```text
Host: ____________________   Date: ____________   Operator: ____________
Source commit: ____________   Bundle manifest sha256: ____________________
E01 __  E02 __  E03 __  E04 __  E05 __  E06 __  E07 __  E08 __  E09 __  E10 __
E11 __  E12 __  E13 __  E14 __  E15 __  E16 __  E17 __  E18 __  E19 __  E20 __
FAIL details (step, exact message):
UNRUN items and why:
```
