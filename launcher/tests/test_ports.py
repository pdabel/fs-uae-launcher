from collections import defaultdict
from types import SimpleNamespace

import pytest

from fsgs.amiga.fsuaeamigadriver import AMIGA_PORTS
from fsgs.drivers.gamedriver import GameDriver
from launcher.option import Option


def test_amiga_port_defaults_match_the_option_table():
    for port_info in AMIGA_PORTS:
        option = Option.get(port_info["type_option"])
        assert port_info["type_default"] == option["default"]


def init_ports(options):
    driver = SimpleNamespace(options=defaultdict(str, options), ports=[])
    for index, port_info in enumerate(AMIGA_PORTS):
        GameDriver.init_port(driver, index, port_info)
    return [port.type for port in driver.ports]


def test_unset_port_types_use_the_port_defaults():
    assert init_ports({}) == ["joystick", "mouse"]


@pytest.mark.parametrize("mode", ["joystick", "mouse", "cd32 gamepad"])
def test_set_port_type_is_kept(mode):
    assert init_ports({"joystick_port_1_mode": mode})[0] == mode
