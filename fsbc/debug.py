import os
import sys
import threading
import traceback
from .signal import Signal

main_thread_id = threading.current_thread().ident
already_run = False


class AdditionalInfo:
    pass


def is_running_in_debugger():
    return bool(sys.gettrace())


def enable_exception_handler(force=False):
    global already_run
    if already_run:
        return
    already_run = True

    if not force and is_running_in_debugger():
        print(
            "running in debugger, not enabling exception handler " "after all."
        )
        _let_thread_exceptions_be_unhandled()
        return False

    sys.excepthook = _handle_exception
    _enable_thread_exception_handler()
    return True


def _let_thread_exceptions_be_unhandled():
    """Replace method in Thread class to let exceptions be picked up by
    the debugger. This is done by replacing the bootstrap function,
    which normally catches all exceptions."""

    print("let thread exceptions be unhandled (for debugger)")
    print(
        "WARNING: no Thread bootstrap replacement for this "
        "python version. The debugger will not break on unhandled"
        "exceptions in threads other than the main thread."
    )


def _enable_thread_exception_handler():
    def run():
        self = threading.current_thread()
        try:
            self._run_()
        except:
            _handle_exception(*sys.exc_info())

    def set_ident(self):
        self._run_ = self.run
        self.run = run
        self._set_ident_()

    # noinspection PyProtectedMember
    threading.Thread._set_ident_ = threading.Thread._set_ident
    threading.Thread._set_ident = set_ident


def _handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        print("handle_exception: KeyboardInterrupt caught")
        sys.exit(1)

    # FIXME: PYTHON3
    tb = traceback.extract_tb(exc_traceback)
    filename, line, function, dummy = tb.pop()
    try:
        filename = filename.decode(sys.getfilesystemencoding())
    except:
        pass
    try:
        filename = str(filename)
    except:
        pass
    filename = os.path.basename(filename)
    thread = threading.current_thread()
    error_id = f"{exc_type.__name__}:{filename}:{function}:{line}"

    backtrace_string = "".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)
    )

    message = f"\nUnhandled exception detected in thread {thread.name}:\n  {error_id}\n"

    print(message)
    print(backtrace_string)

    print(message, file=sys.stderr)
    print(backtrace_string, file=sys.stderr)

    if thread.ident == main_thread_id:
        try:
            Signal("quit").notify()
        except Exception as e:
            print(repr(e))
