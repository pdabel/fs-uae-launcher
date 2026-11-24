import unittest

import fsui as fsui
from fsui.qt import QEvent


class WidgetTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.application = fsui.qt.init_qt()

    # noinspection PyPep8Naming
    def __init__(self, methodName="runTest"):
        unittest.TestCase.__init__(self, methodName=methodName)
        self.dialog = None

    def setup_dialog(self):
        self.dialog = fsui.LegacyDialog()

    def run_dialog(self):
        def run_in_dialog():
            self.dialog.end_modal(True)

        fsui.call_after(run_in_dialog)
        self.dialog.show_modal()
        # Delete the dialog and its widgets now, through Qt. Left to the
        # garbage collector, they go at an arbitrary point in a later test,
        # and a later application-wide setStyleSheet() can then crash.
        self.dialog.deleteLater()
        self.application.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.dialog = None
