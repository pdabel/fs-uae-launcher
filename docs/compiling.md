# Compiling FS-UAE Launcher

The target is Python 3.12+ on Ubuntu 24.04+ and macOS, using Qt 6/PySide6.
Windows packaging is outside this support target. CI is configured for Python
3.12 and 3.15 on Ubuntu 24.04 and macOS 15 Intel. Those jobs have not run for
this stack: Python 3.15 is not yet claimed as supported. Python 3.13/3.14 and
macOS ARM are not separately validated.

Use the locked Pipenv environment, not an unpinned installation:

        python3.12 -m pip install pipenv
        pipenv --python 3.12
        pipenv sync --dev
        pipenv run python fs-uae-launcher

Pipenv's 3.12 requirement selects the default development interpreter; the
generated package metadata specifies `>=3.12` without an upper bound. For
3.15 validation, explicitly create a separate environment with
`pipenv --python /path/to/python3.15` before syncing the same lockfile.

### Side-by-side Python 3.15 On Ubuntu

Do not replace Ubuntu's `/usr/bin/python3` or reuse a virtual environment
created for another Python minor version. With the user-local
[uv installer](https://docs.astral.sh/uv/getting-started/installation/), create
an isolated compatibility-test environment from the repository root:

    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
    ~/.local/bin/uv python install 3.15
    ~/.local/bin/uv venv --python 3.15 --seed .venv-3.15
    .venv-3.15/bin/python --version

This leaves the system interpreter and existing environments unchanged.
Activate it with `source .venv-3.15/bin/activate`; `python3 --version` then
reports the test interpreter only in that shell. Use `deactivate` to return.
Installing the interpreter alone does not validate launcher dependencies or
establish Python 3.15 support. Install the same locked dependencies into this
environment without regenerating the lockfile:

    ~/.local/bin/uv tool install --python 3.15 pipenv
    VIRTUAL_ENV="$PWD/.venv-3.15" PIPENV_IGNORE_VIRTUALENVS=0 ~/.local/bin/pipenv sync --dev
    QT_QPA_PLATFORM=offscreen .venv-3.15/bin/python -Wd -m pytest launcher/tests/test_python_compatibility.py
    .venv-3.15/bin/python fs-uae-launcher

Pipenv warns about the manifest's Python 3.12 development default; keep that
default unchanged for this separate test environment. Pipenv is installed in
its own tool environment to avoid conflicts with the launcher's locked packages.
Local Ubuntu validation
on Python 3.15.1 installed the locked dependencies, passed all 10 focused Python
compatibility tests, and constructed an offscreen PySide6/Qt 6.12 application.
The test run emitted one subprocess ResourceWarning. These checks do not
validate the full test suite, native desktop behavior, or frozen builds.

Frozen builds use PyInstaller through `fsbuild/build`, `fsbuild/bundle`, and
`fsbuild/archive`, as shown in the platform workflows under `.github/workflows`.
Go (see `fsnp-server/go.mod`) is needed for the bundled netplay server. The
tracked `bootstrap` generates the ignored legacy setup file using setuptools;
do not edit the generated file. Debian package generation and native desktop
testing still need separate validation.

## Running without installing

You can run fs-uae launcher from the source directory as long as the
dependencies are installed. In this case, you should have FS-UAE compiled in
it's own `fs-uae` source directory next to the fs-uae-launcher source
directory, for example:

    src/fs-uae/
    src/fs-uae-launcher/

See the next sections for installing requirements on the diffent supported
platforms.

## Ubuntu 24.04+

Install build tools and use the locked environment described above:

    sudo apt install python3.12 python3.12-venv gettext dos2unix

The Linux workflow lists Qt's additional X11/OpenGL system libraries required
by both GUI startup and PyInstaller collection. Debian-family package metadata
now requires Python 3.12+, but a Debian package build has not been run here.

To add support for .lha archives, you also need to have the lhafile
python package installed. You can get `python3-lhafile` from Frode's PPA,
or you can install with pip: `pip3 install lhafile`.

To compile some required files:

    ./bootstrap
    make

You can run the launcher directly from the source directory:

    ./fs-uae-launcher

In this case you should have a matching fs-uae source directory in
`../fs-uae`, and successully compiled fs-uae with `make` (no installation
needed). FS-UAE Launcher will then find the fs-uae and fs-uae-device-helper
binaries from this parallel source directory.

To install to /usr/local, you can run:

    ./bootstrap
    sudo make install

Remember to also install FS-UAE itself.

## Windows (Historical, Outside Support Target)

The former Python 3.6/PyQt5/cx_Freeze recipe is retired. It does not describe
the current launcher and must not be used to assemble a Qt 6 environment.
Historical instructions remain available in Git history; there is no
supported replacement Windows build recipe in this document.

The unused Qt 5 bundle-cleaning scripts have also been removed on all
platforms. Supported Ubuntu/macOS bundles use `fsbuild/fix-qt.py` and the
PySide6-specific cleanup in `fsbuild/build.sh`. Do not mix PyQt5 or another
Qt binding into the locked PySide6 environment. Windows packaging support
would require separate dependency, startup, and frozen-build validation.

## macOS

Install Xcode command-line tools, Python 3.12+, and Homebrew. Use the same
locked Pipenv setup as above. Native build tools include:

    brew install gettext dos2unix go
    export PATH="$(brew --prefix gettext)/bin:$PATH"

Use the `macos.yml` workflow's fsbuild sequence for PyInstaller app bundles,
not the historical cx_Freeze recipe. The current CI runner is macOS 15 Intel;
both Python matrix entries are configured but unverified for this stack.
