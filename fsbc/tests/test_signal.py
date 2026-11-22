import threading

import fsbc.signal


def test_mypy():
    import fstd.mypy

    fstd.mypy.check_module(fsbc.signal.__name__)


class Listener:
    def __init__(self):
        self.values = []

    def on_test_signal(self, value):
        self.values.append(value)


def test_disconnecting_twice_is_a_no_op():
    signal = fsbc.signal.Signal()
    listener = Listener()
    signal.connect(listener.on_test_signal)
    signal.notify(1)
    signal.disconnect(listener.on_test_signal)
    signal.disconnect(listener.on_test_signal)
    signal.notify(2)
    assert listener.values == [1]


def test_a_notification_from_another_thread_goes_through_dispatch(
    monkeypatch,
):
    dispatched = []
    monkeypatch.setattr(fsbc.signal, "_dispatch", dispatched.append)
    signal = fsbc.signal.Signal()
    listener = Listener()
    signal.connect(listener.on_test_signal)
    thread = threading.Thread(target=signal.notify, args=(1,))
    thread.start()
    thread.join()
    assert listener.values == []
    assert dispatched == [fsbc.signal.Signal.process_all_signals]
    dispatched[0]()
    assert listener.values == [1]
