from .window import Window


class DialogWindow(Window):
    def __init__(self, parent, title):
        super().__init__(parent, title, maximizable=False, minimizable=False)
