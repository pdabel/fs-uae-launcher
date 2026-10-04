. ./PACKAGE.FS
. fsbuild/system.sh

make

BUILDDIR=fsbuild/_build

# Remove files from PyQt5 that we don't want to bundle (before pyinstaller
# pulls in their dependencies).
python3 fsbuild/fix-pyqt5.py

rm -Rf $BUILDDIR/pyinstaller
if [ "$SYSTEM_OS" = "Windows" ]; then
pyinstaller \
	--specpath pyinstaller \
	--distpath $BUILDDIR/pyinstaller \
	--log-level DEBUG \
	--windowed \
	$PACKAGE_NAME
BINDIR=fsbuild/_build/pyinstaller/$PACKAGE_NAME
elif [ "$SYSTEM_OS" = "macOS" ]; then
pyinstaller \
	--specpath pyinstaller \
	--distpath $BUILDDIR/pyinstaller \
	--log-level DEBUG \
	--windowed \
	--osx-bundle-identifier no.fengestad.fs-uae-launcher \
	$PACKAGE_NAME
BINDIR=fsbuild/_build/pyinstaller/$PACKAGE_NAME.app/Contents/MacOS
else
pyinstaller \
	--specpath pyinstaller \
	--distpath $BUILDDIR/pyinstaller \
	--log-level DEBUG \
	$PACKAGE_NAME
BINDIR=fsbuild/_build/pyinstaller/$PACKAGE_NAME
# Fontconfig in particular can crash the application because it conflicts
# with system font cache or config files. For now, assume these library are
# always present and use the system ones.
echo "rm $BINDIR/libfreetype.so.6"
rm -f $BINDIR/libfreetype.so.6
echo "rm $BINDIR/libfontconfig.so.1"
rm -f $BINDIR/libfontconfig.so.1
fi

# These do not work with macOS notarization, but might as well remove for all
# platforms.
rm -Rf $BINDIR/PyQt5/Qt/translations
rm -Rf $BINDIR/PyQt5/Qt/qml

# In case the Qt dir is Qt5...
rm -Rf $BINDIR/PyQt5/Qt5/translations
rm -Rf $BINDIR/PyQt5/Qt5/qml

# FS-UAE Netplay Server (Go), built into the same directory as the launcher
# executable. In a frozen build fsboot.executable_dir() resolves to exactly
# this directory, so PluginExecutableFinder's side-by-side branch finds the
# binary without a second plugin archive to version and release. bundle.sh
# copies this directory (or, on macOS, the .app containing it) into the
# plugin, so nothing downstream needs to know about it. On macOS,
# fsbuild/sign runs codesign --deep over the bundle, which covers it too.
# See "Locating the binary" in docs/netplay-go-server-design.md.
if ! command -v go > /dev/null 2>&1; then
	echo "ERROR: the Go toolchain is required to build the netplay server" >&2
	echo "       (fsnp-server). Install Go, or see the Distribution note in" >&2
	echo "       docs/netplay-go-server-design.md." >&2
	exit 1
fi
echo "Building fsnp-server using `go version`"
# go build has to run inside the module, so the -o path must be absolute.
# $BINDIR is relative in this script, but do not assume it.
case "$BINDIR" in
	/*) FSNP_SERVER_OUT="$BINDIR/fsnp-server$SYSTEM_EXE" ;;
	*)  FSNP_SERVER_OUT="`pwd`/$BINDIR/fsnp-server$SYSTEM_EXE" ;;
esac
(cd fsnp-server && CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" \
	-o "$FSNP_SERVER_OUT" ./cmd/fsnp-server)
echo "Built $FSNP_SERVER_OUT"
