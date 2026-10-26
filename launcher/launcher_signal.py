import threading

from fsbc.signal import Signal as BaseSignal

main_thread_id = threading.current_thread().ident


class LauncherSignal(object):
    listeners = {}

    @classmethod
    def add_listener(cls, signal, listener):
        BaseSignal(signal).connect(listener)

    @classmethod
    def remove_listener(cls, signal, listener):
        BaseSignal(signal).disconnect(listener)

    @classmethod
    def broadcast(cls, signal, *args):
        if signal == "config":
            # temporary, while restructuring
            from fsgs.context import fsgs

            key, value = args
            fsgs.signal.notify("fsgs:config:" + key, value)

        BaseSignal(signal).notify(*args)
