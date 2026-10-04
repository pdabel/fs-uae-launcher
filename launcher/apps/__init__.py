#!/usr/bin/env python3
import sys

import launcher.version

try:
    import typing
except ImportError:
    # Workaround to make import typing work without having it on the
    # default python path (would confuse mypy).
    import fstd.typing

    sys.modules["typing"] = fstd.typing


def find_app(app):
    if app in ["launcher", "fs-uae-launcher"]:
        from launcher.apps.fs_uae_launcher import app_main
    elif app == "list-plugins":
        from launcher.apps.listplugins import app_main
    elif app == "list-dirs":
        from launcher.apps.listdirs import app_main
    else:
        return None
    return app_main


def main():
    app_name = ""
    # Check deprecated/legacy app options.
    if len(sys.argv) > 1:
        if sys.argv[1] == "xdftool":
            app_name = "xdftool"
            del sys.argv[1]
    if "--xdftool" in sys.argv:
        sys.argv.remove("--xdftool")
        app_name = "xdftool"
    # Check new app option.
    for arg in sys.argv:
        if arg.startswith("--app="):
            app_name = arg[6:]
            sys.argv.remove(arg)

    # Check for (fake) version override
    for arg in sys.argv:
        if arg.startswith("--") and "=" in arg:
            key, value = arg[2:].split("=", 1)
            key = key.replace("-", "_")
            if key == "fake_version":
                launcher.version.VERSION = value

    if app_name == "xdftool":
        sys.argv[0] = "xdftool"
        import amitools.tols.xdftool

        sys.exit(amitools.tools.xdftool.main())

    app_main = None
    if app_main is None:
        if app_name:
            app_main = find_app(app_name)
        elif len(sys.argv) > 1:
            app_main = find_app(sys.argv[1])
            if app_main is not None:
                # Remove app name from sys.argv
                del sys.argv[1]

    if app_main is None and not app_name:
        app_name = "fs-uae-launcher"
        app_main = find_app(app_name)

    import socket

    socket.setdefaulttimeout(30.0)
    from fsbc.init import initialize_application

    initialize_application(app_name, version=launcher.version.VERSION)

    if app_main is None:
        print("No valid app specified", file=sys.stderr)
        sys.exit(1)
    app_main()
