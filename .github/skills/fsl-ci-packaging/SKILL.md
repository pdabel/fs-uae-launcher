---
name: fsl-ci-packaging
description: 'CI workflows, Dependabot, release flow, and packaging for FS-UAE Launcher: reusable GitHub Actions workflows, SHA-pinned actions, fsbuild/PyInstaller bundles, the fsnp-server binary in packaged builds, and the fsnp-server container image. Use when editing .github/workflows, .github/dependabot.yml, fsbuild/, fsnp-server/Dockerfile or Makefile, Pipfile, or when a CI build fails.'
---

# CI and Packaging

## Workflow Architecture

```text
ci.yml  (push to main/release-*, PRs to main/release-*, dispatch)
  lint                   ruff check (version from Pipfile.lock, rules in pyproject.toml)
  format                 black --check . (version from Pipfile.lock)
  typecheck              pipenv sync --dev, then mypy ([tool.mypy] in pyproject.toml); doesn't gate the tests
  -> linux-test.yml      needs lint and format. Python 3.12 + 3.15 matrix: apt deps, pipenv sync --dev, test_python_support.py,
                         the Python suite, then fsui/test, both with QT_QPA_PLATFORM=offscreen
  -> macos-test.yml      needs lint and format; same on macOS; installs Go with setup-go from fsnp-server/go.mod
  -> linux.yml           needs test-linux; called with run-tests: false. fsbuild/version -> bootstrap ->
                         configure -> build -> bundle -> archive, upload (not on PRs)
  -> macos.yml           needs test-macos; same shape on macOS
  -> container.yml       buildx fsnp-server/Dockerfile (target base) for linux/amd64, arm64, arm/v7 on every run ->
                         ghcr.io/<owner>/fs-uae-netplay; pushes edge from main only, never on PRs
  -> source.yml          source bundle
  -> netplay-server.yml  make -C fsnp-server check, then make -C fsnp-server build
  -> agent-instructions.yml  fails if .github/copilot-instructions.md differs from AGENTS.md
  -> dependency-audit.yml    pip-audit on every package in Pipfile.lock (default and develop);
                            fails on any known vulnerability. Also runs weekly on its own schedule

release.yml  (dispatch: type=branch creates a release branch; type=release tags and builds)
  -> linux.yml, macos.yml, container.yml, source.yml with a version input
     (run-tests defaults to true, so release builds run the tests inside the build job)
```

The test workflows are `workflow_call` only. The build workflows are `workflow_call` + `workflow_dispatch` with a `run-tests` input (default `true`) that runs the same test steps before building; `ci.yml` turns it off because the test jobs already ran. A change to the test command goes in all four (`linux-test.yml`, `macos-test.yml`, `linux.yml`, `macos.yml`). Add a new check as its own reusable workflow called from `ci.yml`, as `netplay-server.yml` is.

`.github/release.yml` maps PR labels to release-note sections (`change`, `enhancement`, `bug`, `chore`, `documentation`, `dependencies`; `skip changelog` excludes).

## Workflow Rules

| Rule | Detail |
| --- | --- |
| Pin actions to a full commit SHA with a version comment | `uses: actions/checkout@<40-hex> # v7.0.1`. Dependabot (`github-actions`, daily, grouped) bumps them; keep the comment in step |
| Least privilege | Top-level `permissions: contents: read`; widen per job only (`packages: write` for GHCR push, `contents: write` for tagging) and say why in a comment |
| Called workflows declare their own `permissions` | The caller's job `permissions` must cover them |
| Nothing publishes on `pull_request` | Pushes, uploads, SBOM and provenance are gated on `github.event_name != 'pull_request'` |
| Run what developers run | Use `make -C fsnp-server ...` and the same pytest paths, not hand-written equivalents, so CI can't drift from local |
| `shell: bash` default | Set in `defaults.run` |
| Untrusted expressions | Don't interpolate `${{ github.event.* }}` text (PR titles, branch names from forks) into `run:`; pass it through `env:` |

## Packaging

`fsbuild/` drives packaged builds: `version` -> `bootstrap` -> `configure` -> `build` (PyInstaller via `build.sh`) -> `bundle` -> `archive`, plus `sign`/`notarize` on macOS.

- `fsbuild/build.sh` compiles `fsnp-server` into `$BINDIR`, the PyInstaller output directory, right after PyInstaller. It **fails loudly** if `go` is missing rather than shipping a bundle without the server.
- `fsnp-server` build flags appear in three places that must match: `fsnp-server/Makefile`, `fsbuild/build.sh`, and `fsnp-server/Dockerfile` (`CGO_ENABLED=0 -trimpath -ldflags="-s -w"`).
- No cross-compile matrix: each runner builds natively for itself.
- A new Python dependency needs `Pipfile` + `Pipfile.lock`, and a check that PyInstaller picks it up (hidden imports go in `fs-uae-launcher.spec`, or as the dummy imports at the end of the `fs-uae-launcher` entry script). `pipenv sync --dev` in CI installs exactly the lock.
- The launcher finds the server through `PluginExecutableFinder` (`"fsnp-server": "FS-UAE-Netplay-Server"`). Renaming the binary or plugin directory breaks packaged and dev lookup alike.

## fsnp-server Image

- `fsnp-server/Dockerfile`: build stage `FROM --platform=$BUILDPLATFORM golang:<ver>-alpine`, cross-compiles with `GOOS`/`GOARCH`/`GOARM` from `TARGETOS`/`TARGETARCH`/`TARGETVARIANT`, so no QEMU step. Final stage `FROM scratch AS base`, numeric uid 101, one port (25101), lobby mode by default.
- Platforms: `linux/amd64`, `linux/arm64`, `linux/arm/v7` (`PLATFORMS` in `container.yml`). PRs build them all without pushing, so a break on one shows before main.
- Tags: `edge` from `main` only (a `release-*` branch's CI builds but doesn't push); a release pushes `<version>` and `latest`, and `edge` is never `latest`. `release.yml` passes `push: false` on a dry run.
- Build context is `fsnp-server/`, not the repo root.
- Configuration is by environment (`LOBBY`, `PORT`, `MAX_GAMES`, ...); there is no entrypoint script. Secret-shaped names (`PASSWORD`) are not declared with `ENV`.
- `make -C fsnp-server image` builds the same target locally.

## Go and Python Versions

| Where | Pins | Updated by |
| --- | --- | --- |
| `fsnp-server/go.mod` | Minimum Go language version; also the Go that `macos-test.yml` and `macos.yml` install (`setup-go` with `go-version-file`) | Hand; keep low unless a feature needs it |
| `fsnp-server/Dockerfile` | Build image tag | Dependabot (`docker`, daily) |
| `fsnp-server/Makefile` `GO_VERSION` | Container fallback for local builds | Hand |
| Ubuntu CI runners | Preinstalled Go with `GOTOOLCHAIN=auto` | Runner image |
| Test and build workflows | Python 3.12 and 3.15 (matrix); `ruff` job 3.12 | Hand |
| Local `venv/` | Whatever created it (currently 3.13) | Hand |

The module has no third-party Go dependencies, so the `gomod` Dependabot entry should stay quiet; a PR adding a `require` is a design change, not a bump.

## Dependabot

`.github/dependabot.yml` groups updates per ecosystem: `github-actions` (daily), `docker` in `/fsnp-server` (daily), `gomod` in `/fsnp-server` (weekly), `pip` at `/` (weekly). Grouped PRs touch `Pipfile.lock` or many workflow pins at once; review them for major-version behaviour changes (e.g. an action's inputs renamed), not line by line.

## When CI fails

| Failure | First check |
| --- | --- |
| Python tests fail in CI only | CI uses Python 3.12 and 3.15 with `pipenv sync --dev`; locally you may be on 3.13 with a different venv. Check which matrix leg failed |
| Qt tests fail in CI only | CI runs them headless with `QT_QPA_PLATFORM=offscreen`; run locally the same way |
| `Lint` fails | A Pyflakes or pycodestyle error (unused import or variable, undefined name, bare `except`), or `%`/`.format()` formatting where an f-string is expected; run `venv/bin/ruff check` locally. The tests don't start until it passes |
| `Type check` fails | Run `venv/bin/mypy` locally. Usually an unannotated empty list or dict at module or class level, or a PySide6 enum by its old short name (`Qt.AlignLeft` -> `Qt.AlignmentFlag.AlignLeft`). A package without type information goes in the `ignore_missing_imports` override, not a blanket setting |
| `Format` fails | A file isn't black-clean; run `venv/bin/black .` and commit the result. The tests don't start until it passes |
| `gofmt clean` fails | Run `make -C fsnp-server fmt` |
| `go test -race` fails | A data race; see `fsl-debugging` |
| PyInstaller bundle missing a module | Hidden import; add it to the spec or the entry script's dummy imports |
| macOS/Linux build says Go is missing | `fsbuild/build.sh` requires Go; on macOS check the `setup-go` step, on Linux the runner image. Without Go the contract tests skip rather than fail, so check the test jobs too |
| `Dependency Audit` fails | A package in `Pipfile.lock` has a published advisory; the job summary lists it with the fixed version. Bump it (`pipenv upgrade <pkg>` rewrites the Pipfile and drops `sys_platform` markers, so check the diff) and run both suites. Only an advisory with no fix that can't affect the launcher goes in the workflow's `ignore` list, with a comment saying why |
| Container build fails on PRs only | PRs build without pushing and skip SBOM/provenance; check the `PUSH` conditionals |
| Container build fails for one platform | Run `docker buildx build --platform <it> --target base fsnp-server` locally; Go cross-compiles, so it doesn't need QEMU |
