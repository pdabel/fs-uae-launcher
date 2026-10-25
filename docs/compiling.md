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

The following legacy notes are retained for reference only. They are not
current support or build instructions and have not been modernized or tested.

The following instructions / notes assume that an MSYS2 shell has been
installed and configured for building FS-UAE. Though the dependencies
for FS-UAE Launcher do not depend on MSYS2 nor MINGW, the build scripts
are run from an MSYS2 shell.

FIXME: Write about dependencies for running the launcher from the source
directory:

    pacman -S mingw-w64-x86_64-python3 mingw-w64-x86_64-python3-lhafile \
    mingw-w64-x86_64-python3-pillow mingw-w64-x86_64-python3-pyqt5 \
    mingw-w64-x86_64-python3-requests mingw-w64-x86_64-python3-setuptools

And finally, from the fs-uae-launcher source directory:

    ./bootstrap
    make

This will allow you to run fs-uae-launcher from the source directory by
executing (See also the section "Running without installing"):

    ./fs-uae-launcher

The following instructions must be followed in order to build the
distributable version.

Download Python 3.6.8 (or a newer _3.6.x_ version)

- https://www.python.org/ftp/python/3.6.8/python-3.6.8-amd64.exe
- Install to default path (...\AppData\Local\Programs\...)
- Default settings, do _not_ add to PATH
- Answer yes to increase max path limit at the end?

Install Visual Studio Build Tools 2019 (vs_buildtools_xxx.yyy.exe)

- FIXME: Link to download page
- Install invidual components:
  - MSVC v140 - VS 2015 C++ build tools (v14.00)
  - Windows 10 SDK (10.0.18362)

Start Windows cmd shell (_not_ MSYS2) and run:

    SET PATH=%PATH%;C:\Program Files (x86)\Windows Kits\10\bin\10.0.18362.0\x64
    rc.exe

You might need to replace the version number `10.0.18362.0` in the PATH if you
installed a newer version. We run rc.exe just check that it exists (verify
thatyou do not get errors here). Then follow with:

    cd %LOCALAPPDATA%\Programs\Python\Python36
    python -m pip install --upgrade pip
    python -m pip install lhafile requests pillow PyQt5==5.12.2

In the MSYS2 MinGW 64-bit shell:

    git clone git@github.com:FrodeSolheim/cx_Freeze.git
    cd cx_Freeze
    ./install-windows.sh

## macOS

Install Xcode command-line tools, Python 3.12+, and Homebrew. Use the same
locked Pipenv setup as above. Native build tools include:

    brew install gettext dos2unix go
    export PATH="$(brew --prefix gettext)/bin:$PATH"

Use the `macos.yml` workflow's fsbuild sequence for PyInstaller app bundles,
not the historical cx_Freeze recipe. The current CI runner is macOS 15 Intel;
both Python matrix entries are configured but unverified for this stack.
