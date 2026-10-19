---
name: fsl-ci-packaging
description: 'CI workflows, Dependabot, release flow, and packaging for FS-UAE Launcher: reusable GitHub Actions workflows, SHA-pinned actions, fsbuild/PyInstaller bundles, the fsnp-server binary in packaged builds, and the fsnp-server container image. Use when editing .github/workflows, .github/dependabot.yml, fsbuild/, fsnp-server/Dockerfile or Makefile, Pipfile, or when a CI build fails.'
---

# CI and Packaging

## Workflow Architecture

```text
ci.yml  (push to main/release-*, PRs to main/release-*, dispatch)
  -> linux.yml           apt deps, Python 3.12, pipenv sync --dev, pytest fsbc fstd fspy launcher/netplay,
                         fsbuild/version -> bootstrap -> configure -> build -> bundle -> archive, upload (not on PRs)
  -> macos.yml           same shape on macOS; installs Go with setup-go from fsnp-server/go.mod
  -> container.yml       buildx fsnp-server/Dockerfile (target base) -> ghcr.io/<owner>/fs-uae-netplay; push not on PRs
  -> source.yml          source bundle
  -> netplay-server.yml  make -C fsnp-server check, then make -C fsnp-server build

release.yml  (dispatch: type=branch creates a release branch; type=release tags and builds)
  -> linux.yml, macos.yml, container.yml, source.yml with a version input
```

Every platform workflow is `workflow_call` + `workflow_dispatch`, called from `ci.yml` and `release.yml`. Add a new check as its own reusable workflow called from `ci.yml`, as `netplay-server.yml` is.

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

- `fsnp-server/Dockerfile`: build stage `FROM --platform=$BUILDPLATFORM golang:<ver>-alpine`, cross-compiles with `GOOS`/`GOARCH` from `TARGETOS`/`TARGETARCH`, so no QEMU step. Final stage `FROM scratch AS base`, numeric uid 101, one port (25101), lobby mode by default.
- Build context is `fsnp-server/`, not the repo root.
- Configuration is by environment (`LOBBY`, `PORT`, `MAX_GAMES`, ...); there is no entrypoint script. Secret-shaped names (`PASSWORD`) are not declared with `ENV`.
- `make -C fsnp-server image` builds the same target locally.

## Go and Python Versions

| Where | Pins | Updated by |
| --- | --- | --- |
| `fsnp-server/go.mod` | Minimum Go language version; also the Go that `macos.yml` installs (`setup-go` with `go-version-file`) | Hand; keep low unless a feature needs it |
| `fsnp-server/Dockerfile` | Build image tag | Dependabot (`docker`, daily) |
| `fsnp-server/Makefile` `GO_VERSION` | Container fallback for local builds | Hand |
| Ubuntu CI runners | Preinstalled Go with `GOTOOLCHAIN=auto` | Runner image |
| Workflows | Python 3.12 | Hand |
| Local `venv/` | Whatever created it (currently 3.13) | Hand |

The module has no third-party Go dependencies, so the `gomod` Dependabot entry should stay quiet; a PR adding a `require` is a design change, not a bump.

## Dependabot

`.github/dependabot.yml` groups updates per ecosystem: `github-actions` (daily), `docker` in `/fsnp-server` (daily), `gomod` in `/fsnp-server` (weekly), `pip` at `/` (weekly). Grouped PRs touch `Pipfile.lock` or many workflow pins at once; review them for major-version behaviour changes (e.g. an action's inputs renamed), not line by line.

## When CI fails

| Failure | First check |
| --- | --- |
| Python tests fail in CI only | CI uses Python 3.12 and `pipenv sync --dev`; locally you may be on 3.13 with a different venv |
| `gofmt clean` fails | Run `make -C fsnp-server fmt` |
| `go test -race` fails | A data race; see `fsl-debugging` |
| PyInstaller bundle missing a module | Hidden import; add it to the spec or the entry script's dummy imports |
| macOS/Linux build says Go is missing | `fsbuild/build.sh` requires Go; on macOS check the `setup-go` step, on Linux the runner image |
| Container build fails on PRs only | PRs `load` instead of `push` and skip SBOM/provenance; check conditionals |
