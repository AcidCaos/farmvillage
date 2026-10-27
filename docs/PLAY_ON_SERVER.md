# Host FarmVillage on Ubuntu/Linux

The full game lives on your server. Players visit its browser address; they do not install the full archive collection. Choose your own server name and folders. No files or accounts belonging to the project owner are required.

This is a sixteen-world alpha with incomplete features; see [world readiness](../WORLD_READINESS.md). The installer is implemented. Full clean-clone installation and gameplay on an actual Ubuntu host remain unqualified; current tests use tiny synthetic files and mocked build tools.

## Prepare your server

Use a normal Ubuntu login with a working systemd user session, Python 3.10+ and these tools:

```sh
sudo apt update
sudo apt install python3 python3-venv python3-pip git clang build-essential pkg-config libssl-dev
```

These install packages on **your server**. The wizard does not log in remotely or run them automatically. Clang must support `wasm32`. Keep **80 GiB free** for preparation, plus space for the final installation. The compressed artwork is 19.13 GB; extracted art and source-build tools need more. The exact fresh-install peak is unmeasured.

Clone/download the source onto the host, outside the resource and final installation folders:

```sh
git clone https://github.com/jannsenburke/FarmVillage-GodBarn.git
cd FarmVillage-GodBarn
bash START_HERE.sh
```

## Download and prepare the originals

Choose **1. Install or resume installation**. Choose a dedicated new folder, such as `~/FarmVillage-Resources`. The wizard prints its absolute path; type `INSTALL ` followed by that exact path to consent.

Before confirmation, you only see a plan. After confirmation it:

1. Downloads pinned client/configuration from AcidCaos’s public repository and verifies each file.
2. Downloads the four original Internet Archive WARCs one at a time, verifies sizes/checksums and extracts artwork. Successful compressed WARCs are removed to save space.
3. Creates an isolated Python environment and installs dependencies from PyPI.
4. Generates God Barn metadata, labels, interface resources and progression from originals. It needs no old farm/private catalogue. Historical prize shelves remain empty where originals cannot reconstruct their curation.
5. Downloads pinned build tools and builds reviewed Ruffle from pinned public source and its compatibility patch.
6. Seals and verifies the complete prepared resources.

Compilation and hundreds of thousands of files take time. Progress stays in the terminal. Partial downloads and completed stages survive retry. Setup keeps a 5 GiB free-space reserve and pauses at its 70 GiB resource-folder budget. Every host has not been qualified to fit within this budget. Rerun with the **same folder** after correcting the named problem.

See [resource setup](RESOURCE_SETUP.md) for exact sources/storage. No GitHub token, SSH account, Keychain access or connection to the owner’s host is needed.

## Install the prepared game

The same flow then opens the guarded clean server installer:

1. Check Python and the systemd user session.
2. Choose the final managed folder (default `~/farmvillage-server`) and private IPv4 address/port.
3. Accept the artwork folder offered from the prepared resources.
4. Review the final target and type `WIPE ` followed by its absolute path. A new target gets a fresh installation. Replacing an identified managed target erases farms and authentication **inside that target**.
5. Stage runtime/artwork and publish the named installation.
6. Create a fresh server Python environment and install packages from PyPI.
7. Choose a new browser password privately in the terminal.
8. Start the user service, check sign-in and print the browser address. The optional boot setting may ask for sudo on your host.

This phase copies artwork into the final `data/assets` folder. Budget space for that additional copy; it checks staging space before erasing an existing managed target. Resource preparation and final installation are separate owned folders. No old farms, snapshots or sign-ins are imported.

The [clean server installer reference](../BIFROST_SETUP.md) covers the same eight-step phase. Its historical filename is not a required server name.

## Play and restart

Visit the printed address, sign in and choose **Create a new farm**. Other computers need your server’s reachable private-network address. `127.0.0.1` works only on the server itself. Hosting currently supports private/loopback IPv4. Public internet/TLS/reverse-proxy deployment requires separate work and qualification.

```sh
systemctl --user status farmvillage.service
systemctl --user restart farmvillage.service
journalctl --user -u farmvillage.service -n 50 --no-pager
```

Keep the final installation: `release/` contains the runtime; `data/` contains farms, artwork and authentication. Never upload generated folders to GitHub. For local Mac play, use [the Mac guide](PLAY_ON_MAC.md).
