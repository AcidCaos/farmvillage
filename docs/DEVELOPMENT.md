# Development and builds

For player-facing instructions, choose [local Mac play](PLAY_ON_MAC.md) or [server hosting](PLAY_ON_SERVER.md). This page covers contributor/build work, with historical matching-resource interfaces retained below.

This guide is for contributors working beyond the source-only checks. Start with the [README](../README.md#get-started-with-the-source) to create the external Python environment. Its examples set `FV_CHECK_ENV`; set that variable to the same environment path in each new terminal.

## Source-only test prerequisites

The selected synthetic tests need Python 3.10+, Bash and the packages in `FarmVillage/requirements.txt`. One staging test also runs the macOS script `FarmVillage/macOS/Scripts/bundle-runtime.sh`, which calls `/usr/bin/rsync`. macOS includes it; on Ubuntu install it with `sudo apt install rsync`. Without it, that single test is reported as skipped with an `UNRUN` reason, so the run finishes with `OK (skipped=1)`. A skipped test is not a pass: install `rsync` and rerun to include it.

## Running the broad suite on a public clone

The README check runs a curated set of source-only suites. The wider test folders also run on a public clone, but many of their tests need the original game files, or files built from them, which a public clone deliberately lacks. `conftest.py` reports those tests as **UNRUN** so that a missing input is not mistaken for a defect. pytest is not in `FarmVillage/requirements.txt`, so install it into the same external environment first:

```sh
"$FV_CHECK_ENV/bin/python" -m pip install pytest
export PYTHONDONTWRITEBYTECODE=1
"$FV_CHECK_ENV/bin/python" -m pytest FarmVillage/macOS/Tests
"$FV_CHECK_ENV/bin/python" -m pytest FarmVillage/portable
"$FV_CHECK_ENV/bin/python" -m pytest tools
(cd GodBarn && "$FV_CHECK_ENV/bin/python" -m pytest tests)
```

- **God Barn tests must run from inside `GodBarn/`.** They import its modules by bare name, so `pytest GodBarn/tests` from the repository root stops with a collection error. That is a wrong working directory, not a defect.
- **Use `python -m pytest`**, so the current folder is on the import path. `pytest.ini` turns off pytest's `.pytest_cache` folder, which the publication check refuses as an unexpected file. Compiled-bytecode folders pass that check; `PYTHONDONTWRITEBYTECODE=1` just keeps the checkout tidy.
- **Run as your normal user, not root.** The update activation script refuses to run as root, so two `test_bifrost_update` tests fail under sudo.

| Outcome | What it means |
| --- | --- |
| passed | The test ran and its checks held. |
| skipped: `UNRUN: needs private input <path>` | An original file listed in `PrivateInputs.expected.json` is absent. This is neither a pass nor a defect. |
| skipped: `UNRUN: needs built artifact <path>` | A file a build would create under `FarmVillage/macOS/.build` is absent. |
| skipped: `UNRUN: needs an accepted Runtime` | The neighborhood host tests need `FARMVILLAGE_TEST_RUNTIME`, or exactly one built tarball. |
| skipped: any other reason | The test chose to skip. Read its reason. |
| failed or error | Treat as real until shown otherwise. |

The UNRUN conversion is narrow on purpose. It applies only to the exact failure signatures listed at the top of `conftest.py`, and only when the input they name is really absent when the result is reported. Everything else still fails: an assertion error, a different message, the same message raised somewhere else, and any of these when the input is present. One consequence is that a test which fails an assertion because absent data made a result empty still shows as failed. Failures that happen while collecting tests are recognised only for a missing listed private path.

Counts belong to their own run; do not add them together. One dated measurement for orientation, not a standing promise: on 26 October 2026, a public clone at `46ee71f` plus the UNRUN extension, Ubuntu 24.04, Python 3.13, run as root:

| Folder | Passed | Failed | UNRUN |
| --- | --- | --- | --- |
| `FarmVillage/macOS/Tests` | 284 | 0 | 1878 |
| `FarmVillage/portable` | 82 | 3 | 20 |
| `GodBarn/tests` | 296 | 1 | 9 |
| `tools` | 168 | 0 | 0 |

The four failures then were these. Re-check before relying on this list.

- Two `test_bifrost_update` tests failed only because the run was root. Run as an unprivileged user they passed.
- `test_current_client_pin_matches_preparation_and_keeps_a4_review_historical` reads `FarmVillage/macOS/Documentation/ClientPatches/provenance.json`, which is not tracked, not in the manifest and not listed as a private input. That is an undeclared dependency to resolve.
- `test_shipped_shelves_have_exact_archived_identities_and_honest_unmatched_reward` asserts on God Barn data that a public clone does not contain.

## Public-resource build path

Use the [resource installer](RESOURCE_SETUP.md) to prepare a new external pack. It downloads and verifies originals, generates metadata and records a source-built Ruffle identity. The source launcher then builds/installs the selected product. To build/stage separately after preparation:

```sh
bash FarmVillage/macOS/Scripts/build.sh Release --resources /absolute/resource-pack --output /absolute/resource-pack/macos-build --python /absolute/resource-pack/python/bin/python
python3 -I -B tools/prepare-browser-runtime.py --resources /absolute/resource-pack --output /absolute/new-browser-release
```

The following matching-resource import commands are retained for the older prepared baseline. They are optional maintainer interfaces; players do not need private files or an old checkpoint.

## Compatible prepared resources

`PrivateInputs.expected.json` records the paths, sizes and hashes accepted by the existing importer. It does not contain the original files or provide a download source. With compatible game and companion resources already available, import them from separate local directories:

```sh
"$FV_CHECK_ENV/bin/python" -B tools/private-inputs.py import   --runtime-source /absolute/path/to/prepared/Runtime   --godbarn-source /absolute/path/to/prepared/GodBarn
"$FV_CHECK_ENV/bin/python" -B tools/private-inputs.py check
"$FV_CHECK_ENV/bin/python" -B tools/check-source.py --with-private-inputs
```

The importer checks the complete expected set before copying, refuses links and mismatches, and does not import player farms. The extracted `assets/` artwork tree is an additional external input, including `Environment/` and `xpromoSupport/`. Keep resource work in a development checkout; use a clean source checkout for publication checks.

The recorded prepared set is a compatibility baseline, not a promise that independently generated resources will have identical hashes. Review and validate a new resource baseline when completing the public bootstrap.

## Native macOS

Requirements: macOS 14+, Xcode with its macOS SDK, and Python 3.10+ with venv/pip. The recorded build used Xcode 27.1; other toolchains need their own validation. Import and check resources first. The build script now stops before Python/compiler work when representative inputs are absent, then verifies the complete prepared-input manifest before compilation. It does not download the missing set. Run from the repository root:

```sh
bash FarmVillage/macOS/Scripts/build.sh Release
```

The unsigned app output is `FarmVillage/macOS/.build/DerivedData/Build/Products/Release/FarmVillage.app`. Alternatively, open `FarmVillage/macOS/FarmVillage.xcodeproj`, select the shared **FarmVillage** scheme and **My Mac**, then build.

In the app, complete **Prepare Runtime** and create a new synthetic farm for testing. Verify actual window interactions, save/reload, God Barn return and process restart separately from compilation. Signing/notarization and execution on Intel hardware require separate qualification.

## Browser hosting and Ubuntu

Once the complete matching resource set is present, the existing staging tool can create a new external browser release directory:

```sh
"$FV_CHECK_ENV/bin/python" -B tools/prepare-browser-runtime.py   --output /absolute/path/to/new-browser-release
```

The output must be new and outside the source checkout. Staging verifies inputs; it does not deploy or qualify a server.

The existing prepared-release installer is documented in [BIFROST_SETUP.md](../BIFROST_SETUP.md). That historical filename refers to a managed release workflow, not a host every contributor must have. It requires a complete prepared bundle and extracted artwork; running `START_HERE.sh` in a source clone first prepares its resources through the public installer.

The current release policy uses fresh farms. The installer must identify its managed installation, request explicit confirmation before wiping it, and refuse unrelated, system, source and linked paths. Do not run destructive installation steps to test documentation. Actual Ubuntu installation, managed-service operation and gameplay remain separate open qualification tasks.

## God Barn

Read [God Barn’s README](../GodBarn/README.md) and [integration contracts](../GodBarn/Documentation/INTEGRATION_CONTRACTS.md). The integrated editor operates through the game server’s ownership and transaction boundaries. Standalone mode edits explicitly imported copies in its own workspace and does not attach to a running farm.

With compatible companion resources prepared, run standalone mode from `GodBarn/`:

```sh
"$FV_CHECK_ENV/bin/python" -B launcher.py --no-browser
```

Use fresh synthetic data for testing. No example player farm is bundled.

## Resource-dependent regression suites

The source-only tests in the README cover selected synthetic contracts. Full application and companion suites require matching resources and, for some tools, Node.js. Do not interpret missing resource errors as a completed game test.

From the repository root, the active-release runner selects the current sixteen-world suite and lists retired-only cases separately:

```sh
mkdir -p "$HOME/farmvillage-test-results"
WAVE2_GODBARN_ROOT="$(pwd)/GodBarn"   "$FV_CHECK_ENV/bin/python" -I -B -W error::ResourceWarning   FarmVillage/macOS/Scripts/run-active-release-regressions.py   --report "$HOME/farmvillage-test-results/new-active-release-result.json"
```

Choose a new report filename. `--list-only` lists the selected tests and still needs the matching inputs. Complete God Barn tests run from `GodBarn/` with `"$FV_CHECK_ENV/bin/python" -B -m unittest discover -s tests -v` after its resources are available.

Record source revision, resource identities, command, platform, result and unrun checks. Keep native macOS, browser, actual Ubuntu and synthetic fixtures distinct. [ACCEPTANCE.md](../ACCEPTANCE.md) is a historical validation record, not evidence that a new checkout or build has passed those checks.
