# Prepared Ubuntu/Linux clean installation

Welcome back to the farm. This installer builds a fresh starting point for sixteen supported worlds. Enchanted Glen and Holiday Lights are retired; iPad development is abandoned. The normal original starter is used: there is no QA funding, pre-unlocked-world grant or previous player data in this package. Access still follows the original prices and eligibility.

This is a **full clean install**, not migration. At the exact named managed target, all old farms, snapshots, history, runtime environments and sign-in state are erased. Only selected extracted game artwork may be retained as an input. No unrelated directory is a wipe target, and this package does not deploy to a remote computer.

This reference requires a complete verified prepared release and already-extracted artwork. The source wizard prepares these from public originals first; start with the [server owner guide](docs/PLAY_ON_SERVER.md).

Extract the prepared bundle **outside** the installation being replaced, such as `~/Downloads/FarmVillage-Server-Release/`. On the Ubuntu/Linux host, open a terminal in that extracted folder and run:

```sh
bash START_HERE.sh
```

In a public source checkout, `bash START_HERE.sh` opens the resource/download installer first. After verified preparation it enters this eight-step clean installation with the generated pack and artwork selected. You do not need a private checkpoint. Advanced users can run `python3 -I -B tools/setup-wizard.py --resources /absolute/resource-pack` after preparation.

## The same eight steps as the wizard

1. **Check the tools.** Run as your normal Ubuntu user, without sudo. The entry verifies the complete prepared bundle checksums, then the wizard checks Linux, Python 3.10+, Python environments and user services before touching game data. If the entry reports missing Python tools, run `sudo apt update`, then `sudo apt install python3 python3-venv python3-pip`, and rerun `bash START_HERE.sh`. Use a normal logged-in Ubuntu/systemd user session.
2. **Choose the home for the game.** The recommended target is `~/farmvillage-server`. The full resolved target and its identification are printed. Existing folders are accepted only with this installer's matching marker, or the actual legacy FarmVillage hosting/release/data structure and matching managed service. System, source, unrelated and linked paths are refused. The wizard lists detected private IPv4 candidates labelled **Open from another computer** and a loopback choice labelled **Only this Ubuntu computer**. Pick a displayed number (the first private address is offered by default), or enter a private address manually. If none is detected, it explains `hostname -I` and the loopback limitation. Choose the port, normally 5501, and review the exact browser URL preview. Public/wildcard binds remain disabled.
3. **Bring the artwork.** Select an already extracted `assets` folder containing `Environment/` and `xpromoSupport/`. A WARC download is not an extracted folder. If old artwork is at `~/farmvillage-server/data/assets`, that path is offered. The wizard checks free space and copies the art into a temporary sibling stage before deleting the old target. It never reads or copies old farms/passwords. Copy progress shows actual file/byte counts without an invented ETA.
4. **Name the clean slate.** Read the full target path. To authorize this exact operation, type `WIPE ` followed by that exact printed path. A mismatch cancels without erasing the installation. This confirmation covers all old farms, snapshots/history, environments and authentication inside that managed folder.
5. **Make room for a new season.** The verified runtime and selected artwork are staged first. Only a service positively matched to this target may be stopped. A held data lock or an occupied unknown port blocks deletion. The installer then replaces only that managed folder with the clean stage. Unrelated services/directories are left alone.
6. **Prepare the fresh engine.** A new native Ubuntu Python environment is created at the installed target and the five pinned dependencies are installed. Pip displays its normal progress. This may use the network but downloads no game artwork. No previous Python environment, save, snapshot or authentication file is reused.
7. **Choose a new key to the gate.** Enter and repeat a new browser password in the hidden prompt. It must have at least eight characters. The runner stores its hash and a new session secret. The password is never passed as a command argument, printed in logs or included in the release.
8. **Open the gate.** The managed user service starts and its sign-in page is checked. The exact `/new.html` URL is printed and opened when a local browser is available. On a headless Ubuntu host, open that printed URL on your own computer. Sign in with the new password and create your first farm. The wizard offers user-service startup after logout/boot; accepting may ask for sudo only for the `loginctl enable-linger` setting.

## Keep playing

Normal saving, reload and process restart work for farms you create in this fresh release. To control only the installed managed service:

```sh
systemctl --user status farmvillage.service
systemctl --user stop farmvillage.service
systemctl --user restart farmvillage.service
journalctl --user -u farmvillage.service -n 50 --no-pager
```

Create a farm through the game UI. World access follows original level/currency policies; the installer does not grant all sixteen worlds. The full historical feature set is not restored; see WORLD_READINESS.md.

## If a step needs another try

- **Missing tools or user services:** follow the exact prerequisite message, log in as the installation owner without sudo, and rerun the same entry.
- **Missing/corrupt bundle or artwork:** supply the matching complete local inputs/extracted asset folder. No game artwork download is attempted by this installer.
- **Not enough staging space:** free the amount requested. Old data is not erased until verified runtime/art staging is complete.
- **An unrelated folder or service is refused:** do not rename arbitrary files to force acceptance. Select the real managed target, a new empty recommended folder, or resolve that unrelated service deliberately.
- **A game still owns the data:** close its game tabs and stop that matching game. Do not stop an unknown process merely to free a port.
- **Pip/password/startup failed after publishing:** the old state has already been intentionally erased. The new managed marker remains. Correct the stated issue and rerun this same wizard; selected art can be staged again, and a fresh environment/password are created. There is no legacy-save restore path in this clean-start release.
- **The sign-in page is slow:** use the printed service status/log commands, correct the reported issue, then restart the managed service or rerun the guided clean installation. Never disable authentication to bypass a setup failure.

The Linux installer is tested with synthetic filesystem/service/process fixtures on macOS in this handoff. Actual Ubuntu host execution is a separate acceptance step; the current source fixtures do not establish a successful real-host installation.
