import fsui
from .canvas import Canvas


class Button(fsui.Button):
    pass


class CustomButton(Canvas):

    activated = fsui.Signal

    def __init__(self, parent):
        super().__init__(parent)

        self.hover = False
        self.pressed = False

    def on_activate(self):
        pass

    def on_left_down(self):
        self.pressed = True
        # For menu popups
        self.on_mouse_motion()
        self.refresh()

    def on_mouse_enter(self):
        if not self.hover:
            self.hover = True
            self.refresh()

    def on_mouse_leave(self):
        # Mouse leave event is received when a menu is popped up, so we
        # explicitly check for mouse position.
        self.on_mouse_motion()

    def on_mouse_motion(self):
        new_state = self.is_mouse_over()
        if self.hover != new_state:
            self.hover = new_state
            self.refresh()

    def on_left_up(self):
        self.pressed = False
        self.refresh()
        if self.is_mouse_over():
            self.on_activate()

    def on_left_dclick(self):
        self.on_left_down()
