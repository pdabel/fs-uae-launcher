import os

from fsbc.settings import Settings
from fsgs import Option
from fsgs.amiga.fsuae import FSUAE
from fsgs.amiga.launchhandler import LaunchHandler
from fsgs.drivers.gamedriver import GameDriver

AMIGA_JOYSTICK = {
    "type": "joystick",
    "description": "Joystick",
    "mapping_name": "amiga",
}
AMIGA_MOUSE = {
    "type": "mouse",
    "description": "Mouse",
    "mapping_name": "amiga_mouse",  # FIXME ...
}
CD32_CONTROLLER = {
    "type": "cd32 gamepad",
    "description": "CD32 Gamepad",
    "mapping_name": "cd32",
}
# FIXME: NO_DEVICE
AMIGA_PORTS = [
    {
        "description": "Joystick Port",
        "types": [AMIGA_JOYSTICK, AMIGA_MOUSE, CD32_CONTROLLER],
        "type_option": "joystick_port_1_mode",
        "device_option": "joystick_port_1",
    },
    {
        "description": "Mouse Port",
        "types": [AMIGA_JOYSTICK, AMIGA_MOUSE, CD32_CONTROLLER],
        "type_option": "joystick_port_0_mode",
        "device_option": "joystick_port_0",
    },
    # FIXME: ADDITIONAL PORTS...
]


class FSUAEAmigaDriver(GameDriver):
    PORTS = AMIGA_PORTS

    def __init__(self, fsgc):
        super().__init__(fsgc)
        self.temp_config_file = None
        self.launch_handler = None

    def prepare(self):
        print("FSUAEAmigaDriver.prepare")

        model = self.options[Option.AMIGA_MODEL]
        if model.startswith("CD32"):
            platform = "CD32"
        elif model == "CDTV":
            platform = "CDTV"
        else:
            platform = "Amiga"

        from fsgs.saves import SaveHandler

        save_state_handler = SaveHandler(self.fsgc, self.get_name(), platform)

        print(
            "[INPUT] joystick_port_1",
            self.options["joystick_port_1"],
            "->",
            self.ports[0].device_id or "none",
        )
        print(
            "[INPUT] joystick_port_0",
            self.options["joystick_port_0"],
            "->",
            self.ports[1].device_id or "none",
        )
        self.options["joystick_port_1"] = self.ports[0].device_id or "none"
        self.options["joystick_port_0"] = self.ports[1].device_id or "none"

        self.launch_handler = LaunchHandler(
            self.fsgc,
            self.get_name(),
            self.options,
            save_state_handler,
            temp_dir=self.cwd.path,
        )

        if self.use_fullscreen():
            self.launch_handler.config["fullscreen"] = "1"
            if not self.launch_handler.config.get("fullscreen_mode", ""):
                # Check if fullscreen mode is overridden by temporary setting.
                if Settings.instance()["__fullscreen_mode"]:
                    self.launch_handler.config[
                        "fullscreen_mode"
                    ] = Settings.instance()["__fullscreen_mode"]
            if Settings.instance()["__arcade"]:
                # Remove window border when launched from FS-UAE Arcade in
                # order to reduce flickering
                self.launch_handler.config["window_border"] = "0"
                # Set fade out duration to 500, if not already specified.
                if not self.launch_handler.config.get("fade_out_duration", ""):
                    self.launch_handler.config["fade_out_duration"] = "500"
        else:
            self.launch_handler.config["fullscreen"] = "0"

        self.launch_handler.prepare()

    def run(self):
        print("FSUAEAmigaDriver.run, cwd =", self.cwd.path)
        config = self.launch_handler.create_config()
        self.emulator.process, self.temp_config_file = FSUAE.start_with_config(
            config, cwd=self.cwd.path
        )
        self.write_emulator_pid_file(
            self.emulator_pid_file(), self.emulator.process
        )

    def finish(self):
        print("FSUAEAmigaDriver.finish: Removing", self.temp_config_file)
        if self.temp_config_file is not None:
            try:
                os.remove(self.temp_config_file)
            except Exception:
                print("Could not remove config file", self.temp_config_file)

        self.launch_handler.update_changes()
        self.launch_handler.cleanup()

    def get_game_refresh_rate(self):
        # FIXME: Now assuming that all games are PAL / 50 Hz
        # - make configurable?
        return 50.0

    def get_supported_filters(self):
        supported = []
        return supported
