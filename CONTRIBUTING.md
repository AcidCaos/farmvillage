# Contributing

Contributions are welcome: bug reports, documentation improvements, resource setup work, tests and carefully scoped game restoration all help.

Start with the [README](README.md), [current priorities](HANDOVER_STATUS.md) and [maintainer guide](TAKEOVER.md). The continuing targets are native macOS and browser/Ubuntu. Read [AGENTS.md](AGENTS.md) for the project’s standing development rules.

## Choose a focused change

Describe one concrete problem, its expected behavior and the smallest useful correction. Include reproduction steps and relevant platform/version information in a bug report. For restoration work, identify the original data or client behavior supporting the change.

Keep original prices, timers, imported metadata, save identities and transaction boundaries intact. Use synthetic data and unused ports for tests. Unknown or unsupported game behavior should remain an explicit refusal rather than an invented success. Never use real player farms or modify timers to manufacture a passing test.

## Check your work

Follow the source-check and external Python-environment commands in the [README](README.md#get-started-with-the-source). Run the tests appropriate to your change. Rendering, input, save/load and travel changes also need actual client checks when resources are available.

`SOURCE_MANIFEST.json` detects changes to the reviewed source snapshot. After reviewing your intentional edits, update it from the repository root:

```sh
"$FV_CHECK_ENV/bin/python" -B tools/refresh-source-manifest.py --reviewed
```

For a new text source file, add `--add path/to/new-file`. Rerun the publication check after resealing. This records source integrity; it does not grant new gameplay or platform acceptance. See [development checks](docs/DEVELOPMENT.md) for resource-dependent suites and build prerequisites.

Keep original game files, generated catalogues, compiled players, builds, logs, saves, credentials and private development history out of commits. Preserve GPL attribution and third-party notices; original game resources have separate rights.

## Open a pull request

Explain the problem, resulting behavior, checks performed and remaining limits. Include source/resource identities when a change affects prepared game files. Report native macOS, browser and actual Ubuntu results separately; a unit test or build does not prove gameplay on another target.

Use [world readiness](WORLD_READINESS.md) and the [restoration backlog](<Wave 3.md>) to avoid expanding a change into unrelated work. iPad/iOS and the two retired worlds remain outside the active scope. Deployment is a separate maintainer decision.
