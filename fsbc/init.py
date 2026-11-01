import sys
import platform
import fsbc.debug
import fsbc.logging

from fsbc.application import Application


def initialize_application(
    name=None,
    version=None,
    enable_logging=True,
    enable_exception_handler=True,
):
    if name and enable_logging:
        fsbc.logging.setup_logging(name + ".log.txt")

    if name is not None:
        Application.app_name = name

    if version is not None:
        Application.app_version = version

    if enable_exception_handler:
        fsbc.debug.enable_exception_handler()
