# FS-UAE Launcher Architecture

A map of the launcher's Python packages, how they depend on each other, how
the application starts, and where its data lives. Diagrams are Mermaid and
render on GitHub and in VS Code's Markdown preview.

| | |
|---|---|
| **Date** | 2026-10-31 |
| **Scope** | The Python launcher (`fs-uae-launcher`). The Go netplay server has its own notes in [fsnp-server/README.md](../fsnp-server/README.md) and [netplay-go-server-design.md](netplay-go-server-design.md). |
| **Out of scope** | `venv-*/`, `oyoyo/` internals |

## Layers

The code is layered from the bottom up. Each package imports only from the
layers below it; the counts are `from X import` / `import X` statements.

```mermaid
flowchart TB
    subgraph app["Application layer"]
        launcher["launcher/<br/>Main window, dashboard, settings,<br/>config panels, scanning, netplay client"]
        workspace["workspace/<br/>Tool windows: ADF/HDF creator,<br/>joystick config, login, locker upload"]
        arcade["arcade/<br/>Arcade front-end (minimal)"]
    end

    subgraph domain["Game-systems layer"]
        fsgs["fsgs/<br/>Platforms, drivers, databases,<br/>archives, downloads, OpenRetro client"]
        amitools["amitools/<br/>Amiga filesystem and ROM tools"]
    end

    subgraph ui["UI toolkit layer"]
        fsui["fsui/<br/>Widget abstraction over Qt 6 (QtPy/PySide6),<br/>themes, dialogs, layouts"]
    end

    subgraph base["Base layer"]
        fsbc["fsbc/<br/>Application, Settings, Signal,<br/>paths, tasks, logging"]
        fspy["fspy/<br/>zipfile patches"]
        fstd["fstd/<br/>desktop helpers"]
        fsboot["fsboot/<br/>sys.path, base dir,<br/>portable mode"]
    end

    subgraph ext["External"]
        qt["Qt 6 / PySide6 / QtAwesome"]
        fsuae["FS-UAE emulator process"]
        fsnp["fsnp-server (Go)"]
        irc["IRC lobby (oyoyo/)"]
        openretro["OpenRetro / oagd.net"]
    end

    launcher -- "20+" --> fsui
    launcher -- "25+" --> fsgs
    launcher -- "15+" --> fsbc
    launcher --> fsboot
    launcher --> irc
    launcher --> fsnp
    launcher --> workspace
    workspace --> fsui
    workspace --> fsgs
    arcade --> fsgs
    arcade --> fsui
    fsgs -- "10+" --> fsbc
    fsgs --> fspy
    fsgs --> amitools
    fsgs --> fsuae
    fsgs --> openretro
    fsui --> fsbc
    fsui --> qt
    fsbc --> fsboot
```

### Package responsibilities

| Package | Responsibility | Key modules |
|---|---|---|
| `fsboot/` | First thing imported. Fixes `sys.path`, finds the base directory (`~/FS-UAE` or a portable marker), exposes `fsboot.init()`. | [fsboot/__init__.py](../fsboot/__init__.py) |
| `fsbc/` | Framework base: `Application`, `Settings` (persisted key/value), `Signal`, `Task`, path and desktop helpers, logging setup. | [application.py](../fsbc/application.py), [settings.py](../fsbc/settings.py), [signal.py](../fsbc/signal.py), [init.py](../fsbc/init.py) |
| `fspy/`, `fstd/` | Small stdlib patches and desktop-environment helpers. | [fspy/zipfile.py](../fspy/zipfile.py) |
| `fsui/` | Toolkit-neutral widget API (`Panel`, `Button`, `Choice`, layouts, dialogs) implemented on Qt in `fsui/qt/`. Owns the theme engine. | [fsui/qt/qt.py](../fsui/qt/qt.py), [modern_theme.py](../fsui/qt/modern_theme.py), [retro_theme.py](../fsui/qt/retro_theme.py) |
| `fsgs/` | Everything about games and emulators that is not UI: the `fsgs` context singleton, platforms and drivers, SQLite databases, archive reading, file scanning, OpenRetro sync, plugin discovery. | [context.py](../fsgs/context.py), [Database.py](../fsgs/Database.py), [amiga/launchhandler.py](../fsgs/amiga/launchhandler.py), [drivers/gamedriver.py](../fsgs/drivers/gamedriver.py) |
| `amitools/` | Vendored Amiga tooling used for ADF/HDF and ROM inspection. | `amitools/fs`, `amitools/rom` |
| `launcher/` | The application: `LauncherApp`, `LauncherWindow`, the dashboard shell, configuration panels, the Settings dialog, startup scans, netplay client, option metadata. | [launcherapp.py](../launcher/launcherapp.py), [ui/launcherwindow.py](../launcher/ui/launcherwindow.py), [ui/dashboard.py](../launcher/ui/dashboard.py), [option.py](../launcher/option.py) |
| `workspace/` | Secondary tool windows opened from the launcher (ADF and HDF creators, joystick configuration, OpenRetro login/logout, locker upload, refresh), with their own small widget set in `workspace/ui`. | [workspace/apps](../workspace/apps) |
| `oyoyo/` | Vendored IRC client used by the netplay lobby. | |
| `fsnp-server/` | Go netplay server, run as a child process when hosting a game. | [fsnp-server/README.md](../fsnp-server/README.md) |
| `fsbuild/` | Build and packaging scripts (PyInstaller, DMG, deb). Not imported at runtime. | |

## Startup sequence

```mermaid
sequenceDiagram
    autonumber
    participant S as fs-uae-launcher (script)
    participant B as fsboot
    participant M as launcher.apps.fs_uae_launcher
    participant A as LauncherApp
    participant Q as fsui / Qt
    participant W as LauncherWindow
    participant D as Dashboard

    S->>B: fsboot.init()
    Note over B: sys.path, base dir,<br/>portable marker
    S->>M: app_main()
    M->>M: fsbc.init.initialize_application()
    M->>A: LauncherApp()
    A->>Q: fsui.Application → init_qt()
    Q->>Q: initialize_qt_style()
    Note over Q: Fusion style + theme palette/QSS<br/>from Option.LAUNCHER_THEME
    M->>A: start()
    A->>A: pre_start(): load_settings, StartupScan<br/>(configs, kickstarts), load_plugins
    A->>A: run_config_or_game(argv)
    A->>W: LauncherWindow.open()
    W->>D: Dashboard(self)
    Note over D: navigation + topbar + content stack<br/>(workspace / embedded NetplayPage)
    M->>Q: app.run()  (Qt event loop)
    Q-->>M: quit
    M->>M: save settings, restart_if_requested()
```

## Main window composition

```mermaid
flowchart LR
    LW["LauncherWindow<br/>(launcher/ui/launcherwindow.py)"]
    LW --> DB["Dashboard<br/>(launcher/ui/dashboard.py)"]
    DB --> NAV["Navigation rail<br/>navigation_icons.py"]
    DB --> TOP["Top bar<br/>config name, badges"]
    DB --> STACK["QStackedWidget"]
    STACK --> WS["Workspace"]
    STACK --> NP["NetplayPage<br/>(launcher/netplay/netplay_page.py)"]
    WS --> LIB["ConfigurationsPanel<br/>(library / search)"]
    WS --> ED["Editor book<br/>MainPanel, Floppies, CD-ROM,<br/>Hard drives, ROM & RAM,<br/>Input, Expansions, Additional"]
    WS --> MEDIA["Bottom bar<br/>GameInfoPanel, ScreenshotsPanel"]
    DB --> LAUNCH["Launch bar<br/>LaunchGroup, StartButton"]
    NP --> PANEL["NetplayPanel<br/>chat, players, commands"]
    NP --> SD["ServerDetails<br/>hosted fsnp-server status"]
    LW --> SET["SettingsDialog<br/>(launcher/settings/*)"]
```

## Theme engine

Theme selection is one `Settings` key, `launcher_theme`, declared in
[launcher/option.py](../launcher/option.py) and dispatched by
`initialize_qt_style()` in [fsui/qt/qt.py](../fsui/qt/qt.py). Every theme
runs on Qt's Fusion style; themes differ by palette, stylesheet and font.

```mermaid
flowchart TD
    OPT["Option.LAUNCHER_THEME<br/>(Settings or --launcher-theme=)"] --> INIT["initialize_qt_style()"]
    INIT -->|"fusion-modern"| MOD["modern_theme.apply_modern_theme()<br/>dark palette + QSS + SVG arrows"]
    INIT -->|"fusion-plain"| PLAIN["Fusion standard palette"]
    INIT -->|"fusion-windows311<br/>fusion-workbench"| RETRO["retro_theme.apply_retro_theme()<br/>bevelled palette + QSS"]
    INIT --> VAR["fsui.theme_variant =<br/>modern | plain | windows311 | workbench"]
    VAR --> UI["Dashboard, PagedDialog, ServerDetails,<br/>navigation_icons, IconButton, WarningsElement<br/>pick layout and icon colours by variant"]
```

The Settings page offers a *Restart Launcher* button; `LauncherApp.request_restart()`
saves settings and re-executes the process so a new theme applies cleanly.

## Data and external processes

```mermaid
flowchart LR
    subgraph basedir["Base directory (~/FS-UAE or portable)"]
        conf["Data/Settings.ini<br/>(fsbc.Settings)"]
        cfg["Configurations/*.fs-uae"]
        db1[("Data/Databases/Launcher.sqlite<br/>fsgs/Database.py<br/>configs, search index")]
        db2[("Data/Databases/&lt;platform&gt;.sqlite<br/>fsgs/GameDatabase.py<br/>OpenRetro metadata")]
        db3[("Data/Databases/Files.sqlite<br/>fsgs/filedatabase.py<br/>SHA-1 → path")]
        db4[("Data/Databases/Locker.sqlite<br/>fsgs/LockerDatabase.py")]
        hist[("Data/Databases/NetplayHistory.sqlite<br/>launcher/netplay/command_history.py")]
        media["Kickstarts/, Floppies/, CD-ROMs/,<br/>Hard Drives/, Cache/"]
    end

    scan["StartupScan / FileScanner<br/>(launcher/startup_scan.py, filescanner.py)"] --> db1
    scan --> db3
    sync["GameDatabaseSynchronizer<br/>(fsgs/ogd/)"] <--> openretro["openretro.org"]
    sync --> db2
    launch["LaunchHandler<br/>(fsgs/amiga/launchhandler.py)"] --> cfgw["ConfigWriter"]
    cfgw --> fsuae["FS-UAE process"]
    launch --> media
    np["Netplay<br/>(launcher/netplay/netplay.py)"] <--> irc["IRC server"]
    np --> fsnp["fsnp-server child process<br/>(launcher/server/Server.py)"]
```

## Tests

| Suite | Command | Platform |
|---|---|---|
| Core | `python -W default::DeprecationWarning -m pytest fsbc fstd fspy fsbuild/tests launcher/netplay launcher/tests` | any |
| Qt widgets, panels and themes | `QT_QPA_PLATFORM=offscreen python -m pytest fsui/test/test_qt6.py` | offscreen |
| Lint | `ruff check` | any |
| Go server | `make -C fsnp-server check` | Go toolchain |

CI runs these in [.github/workflows/linux.yml](../.github/workflows/linux.yml).
Qt tests that build a real `LauncherWindow` use isolated temporary base
directories and mock the IRC transport and server process.
