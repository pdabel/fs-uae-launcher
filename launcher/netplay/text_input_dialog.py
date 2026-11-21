import fsui
from launcher.i18n import gettext


class SimpleTextInputDialog(fsui.Dialog):
    def __init__(self, parent, title, label_text, default_text="new"):
        super().__init__(parent, title)
        self.layout = fsui.VerticalLayout()
        self.label = fsui.Label(self, label_text)
        self.layout.add(self.label, margin=10)
        self.text_field = fsui.TextField(self)
        self.text_field.set_text(default_text)
        self.text_field.select_all()
        self.layout.add(self.text_field, fill=True, margin=10)
        button_row = fsui.HorizontalLayout()
        self.ok_button = fsui.Button(self, gettext("OK"))
        self.ok_button.activated.connect(self.on_ok)
        button_row.add(self.ok_button, fill=True, margin_right=10)
        self.cancel_button = fsui.Button(self, gettext("Cancel"))
        self.cancel_button.activated.connect(self.reject)
        button_row.add(self.cancel_button, fill=True)
        self.layout.add(button_row, margin=10)
        self.text_field.activated.connect(self.on_ok)
        self.result_text = None

    def on_ok(self):
        self.result_text = self.text_field.get_text()
        self.accept()

    @staticmethod
    def get_text(parent, title, label_text, default_text="new"):
        dialog = SimpleTextInputDialog(
            parent, title, label_text, default_text=default_text
        )
        if dialog.exec():
            return dialog.result_text
        return None
