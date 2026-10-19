# Python and Dependency Modernization TODO

Review date: 2026-10-18

This is an implementation queue, not a claim that the proposed versions have
already been tested. Python 3.15 is the latest stable release on the review
date. Validate the GUI, freezer, and platform packaging stack on it before
declaring support.

## Priority 0: Make Dependency Installation Reproducible

- [x] Reconcile `Pipfile` and `Pipfile.lock`. `Pipfile` declares PySide6,
  QtPy, and QtAwesome, while the lockfile contained PyQt5 and none of those
  three Qt 6 packages. The lock now has them and no PyQt5, and CI runs the
  Qt tests from a clean `pipenv sync --dev`.
- [ ] Choose one supported Qt binding and version family. Qt 6/PySide6 it
  is: `fsbuild/fix-qt.py` (was `fix-pyqt5.py`), `fsbuild/build.sh`,
  `debian/control`, the RPM spec, and the Linux and macOS sections of
  `docs/compiling.md` now use it. Still Qt 5/PyQt5: the Windows section of
  `docs/compiling.md` and `fsbuild/bundle-clean-*.sh`, which `bundle.sh` no
  longer calls. Update or explicitly retire each; do not mix bindings in one
  environment.
- [ ] Regenerate the lockfile from the agreed manifest with the supported
  Python version(s), then verify a clean `pipenv sync --dev` and the CI build.
  Do not hand-edit generated lock data.
- [ ] Replace unconstrained `*` requirements in `Pipfile` with deliberate
  dependency policy: compatible ranges in package metadata and a reproducible
  lock for applications/builds. Separate runtime, optional, and development
  dependencies. Keep platform-only packages conditional.

## Priority 1: Set a Supported Python Policy

- [ ] Declare the actual minimum and tested Python versions consistently.
  `Pipfile` only says Python `3`; `setup.py` has no Python requirement;
  Debian metadata claims `>= 3.2`; and CI currently builds on Python 3.12.
- [ ] Validate Python 3.15 first against PySide6, QtPy, QtAwesome,
  PyInstaller, and the Linux/macOS packaging workflows. If any essential
  dependency or platform build is not ready, use Python 3.14 as the immediate
  supported baseline and keep 3.15 as an explicit follow-up, rather than
  claiming unverified support.
- [ ] Pick a support window (recommended: test the oldest supported Python
  plus the latest stable Python) and encode it in CI. Preserve the oldest
  version only while its OS packages and all required dependencies remain
  supported. The current Python 3.12 CI baseline is still in CPython security
  support, but does not test newer versions.
- [ ] Set matching `requires-python`/`python_requires`, Python classifiers,
  Pipenv requirements, Debian package constraints, developer setup docs, and
  release-build interpreters. Update these together when the support window
  changes.
- [ ] Run the full tests and source/frozen builds on each claimed Python
  version and supported OS. Include GUI startup and offscreen tests; the
  existing CI Python test step covers only `fsbc`, `fstd`, and `fspy`.

## Priority 1: Modernize Packaging

- [ ] Replace the legacy `setup.py`/`distutils` packaging path with a
  `pyproject.toml` build configuration using a maintained backend such as
  setuptools. `distutils` was removed from the standard library in Python
  3.12, and the current `setup.py` still imports it for its non-freezer path.
- [ ] Move project name, version, Python requirement, dependencies, and
  package/resource declarations into maintained packaging metadata. Keep the
  FS-UAE source/build scripts working while migrating; test Debian packaging
  and frozen builds separately.
- [ ] Remove or update stale installation and compilation instructions,
  including Python 3.6, cx_Freeze, Qt 5, and package commands that no longer
  describe the supported workflow.

## Priority 2: Audit and Maintain Dependencies

- [ ] Inventory direct imports and build-time imports against the declared
  dependencies. Confirm whether Pillow, PyOpenGL, Sentry SDK, typing
  extensions, PyInstaller helpers, and platform-specific packages are still
  needed, then remove only dependencies proven unused across all build paths.
- [ ] Review each retained direct dependency for current maintenance,
  supported Python versions, supported platforms, and security advisories.
  Prefer maintained releases compatible with the chosen Qt and Python
  versions; document any intentional pins or legacy platform exceptions.
- [ ] Configure automated dependency update PRs for both manifest and lock
  changes. Require the relevant unit tests and platform build checks before
  merging updates.
- [ ] Add a repeatable dependency/security report to CI (for example, an
  audited SBOM plus vulnerability scanning) and establish how findings are
  triaged. Avoid treating every transitive package alert as an automatic
  upgrade without build/test validation.

## Priority 2: Standardize Python Code Quality

- [ ] Establish one formatter/linter configuration in `pyproject.toml`.
  Consider Ruff for linting and formatting, migrating existing Black/Pylint
  usage deliberately rather than running overlapping formatters.
- [ ] Add CI checks for formatting, linting, and the project's existing
  type-checking approach. Begin with changed files or a documented baseline
  so legacy findings do not obscure new regressions.
- [ ] Adopt typing incrementally at module and public API boundaries. Use
  modern built-in generic and union syntax only after the declared minimum
  Python version supports it; do not bulk-rewrite syntax without tests.
- [ ] Enable deprecation warnings in focused test jobs and resolve warnings
  from Python and maintained dependencies before they become removals.

## Completion Criteria

- One authoritative dependency manifest and a matching regenerated lockfile.
- One documented Python support window reflected in package metadata, CI,
  installer/build scripts, and user/developer documentation.
- Clean environment setup, tests, GUI startup, and release artifacts succeed
  on every version and OS the project claims to support.
- A repeatable style/type/security workflow runs in CI without hiding
  unresolved baseline failures.

## Review Evidence

- `Pipfile` and `Pipfile.lock`: Qt 6 manifest versus Qt 5 lock mismatch;
  dependencies are otherwise unconstrained in the manifest.
- `.github/workflows/linux.yml`, `.github/workflows/macos.yml`, and
  `.github/workflows/source.yml`: Python 3.12 CI setup.
- `setup.py` and `debian/control`: legacy packaging and Python `>= 3.2`
  metadata.
- `docs/compiling.md`, `fsbuild/fix-pyqt5.py`, and `fsbuild/build.sh`:
  older Qt 5/Python 3.6 packaging instructions and build assumptions.
- [Python downloads](https://www.python.org/downloads/) and
  [Python version support status](https://devguide.python.org/versions/):
  Python 3.15.0 released 2026-10-09 and is in bugfix support; Python 3.12 is
  in security support.