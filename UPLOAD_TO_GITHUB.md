# Publishing source changes

This is a maintainer reference for reviewing and publishing source. New contributors should start with the [README](README.md) and [contribution guide](CONTRIBUTING.md).

## Review the outgoing source

Keep original game resources, generated catalogues, compiled runtimes, built apps, logs, saves, credentials and private history out of the repository. `.gitignore` helps prevent accidental additions; review staged changes as well.

After reviewing intentional source edits, update the source manifest. Use `--add path/to/file` for a newly reviewed text source file:

```sh
python3 -B tools/refresh-source-manifest.py --reviewed
python3 -I -B tools/check-source.py --for-publication
git diff --stat
git diff --cached --stat
```

Run affected tests as described in [CONTRIBUTING.md](CONTRIBUTING.md). Preserve licences and attribution.

## Publish from a clone or fork

Commit reviewed changes on a development branch and push it to a repository you can write to, then open a pull request. Use your normal Git client and authentication method. Source validation does not configure account access or publish anything.

A separately extracted source archive may lack Git metadata. Initialize a new repository only for that case, using your own empty destination repository. Do not import unrelated private development history into a source export. For general instructions, use [GitHub’s command-line import guide](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

## Optional automated checks

The workflow template is `.github/source-checks.yml.example`. It runs the selected asset-free checks on an Ubuntu runner; this is separate from actual game hosting or native gameplay qualification.

To enable it deliberately:

```sh
mkdir -p .github/workflows
cp .github/source-checks.yml.example .github/workflows/source-checks.yml
python3 -B tools/refresh-source-manifest.py --reviewed --add .github/workflows/source-checks.yml
python3 -I -B tools/check-source.py --for-publication
```

Review and commit those changes before pushing. GitHub requires suitable workflow permissions when adding or modifying files in `.github/workflows/`; see its [scope reference](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps#available-scopes). Use the template’s workflow commands when recording new CI results rather than assuming a template has already run.
