import fsui
from .application import Application
from .theme import WorkspaceTheme


TEXT_SPACING = 2


class WindowHeader(fsui.Panel):
    def __init__(
        self,
        parent,
        title="",
        menu=False,
        minimizable=True,
        maximizable=True,
        separator=True,
        closable=True,
        background=None,
    ):
        super().__init__(parent)

        if background is None:
            background = (0xFF, 0xFF, 0xFF)
        background_color = fsui.Color(background)
        if background_color.to_hsl().l >= 0.6:
            self.foreground_color = (0x00, 0x00, 0x00)
        else:
            self.foreground_color = (0xFF, 0xFF, 0xFF)
        self.background_color = background_color
        self.set_background_color(background_color)

        self.set_normal_cursor()

        self.layout = fsui.VerticalLayout()
        hor_layout = fsui.HorizontalLayout()
        self.layout.add(hor_layout, fill=True)

        self.menu_button = WindowMenuButton(self)
        hor_layout.add(self.menu_button)
        if not menu:
            self.menu_button.hide()
            hor_layout.add_spacer(20 - TEXT_SPACING)

        self.title_panel = WindowTitlePanel(self)
        hor_layout.add(self.title_panel, expand=True)

        self.minimize_button = WindowMinimizeButton(self)
        hor_layout.add(self.minimize_button)
        if not minimizable:
            self.minimize_button.hide()

        self.maximize_button = WindowMaximizeButton(self)
        hor_layout.add(self.maximize_button)
        if not maximizable:
            self.maximize_button.hide()

        self.close_button = WindowCloseButton(self)
        hor_layout.add(self.close_button)
        if not closable:
            self.close_button.hide()

        if separator:
            self.separator = TitleSeparator(self)
            self.layout.add(self.separator, fill=True)

    def height(self):
        return self.layout.get_min_height()


class Window(fsui.Window):
    def __init__(
        self,
        parent,
        title="",
        minimizable=True,
        maximizable=True,
        menu=False,
        border=True,
        header=True,
        below=False,
        closable=True,
        color=None,
    ):
        if isinstance(parent, Application):
            parent.add_window(self)
            parent = None
        super().__init__(
            parent,
            title,
            minimizable=minimizable,
            maximizable=maximizable,
            native=False,
            separator=False,
            menu=menu,
            border=border,
            header=header,
            below=below,
            closable=closable,
            color=color,
        )
        self.__menu = None

    def add(self, child):
        if hasattr(self, "set_layout"):
            self.set_layout(child)
        else:
            self.layout = child

    def menu(self):
        return self.__menu

    def set_menu(self, menu):
        self.__menu = menu


class WindowTitlePanel(fsui.Panel):
    def __init__(self, parent):
        super().__init__(parent, paintable=True)
        self.set_background_color(parent.background_color)
        self.set_min_width(40)
        self.set_min_height(40)

        self.pressed = False
        self.window_pos = (-1, -1)
        self.mouse_pos = (-1, -1)

    def on_paint(self):
        theme = WorkspaceTheme.instance()
        dc = self.create_dc()
        dc.set_font(theme.title_font)
        text = self.parent()._window().title()
        tw, th = dc.measure_text(text)
        # FIXME: measurements with Noto Sans is a bit off...
        th += 2
        dc.set_text_color(self.parent().foreground_color)
        dc.draw_text(text, TEXT_SPACING, (self.size()[1] - th) // 2)

    def on_left_dclick(self):
        # noinspection PyProtectedMember
        self.parent().maximize_button.on_activate()

    def on_left_down(self):
        self.pressed = True
        window = self.parent().parent()
        self.window_pos = window.position()
        self.mouse_pos = fsui.get_mouse_position()

    def on_left_up(self):
        self.pressed = False

    def on_mouse_motion(self):
        if self.pressed:
            mouse_pos = fsui.get_mouse_position()
            window_pos = (
                self.window_pos[0] + mouse_pos[0] - self.mouse_pos[0],
                self.window_pos[1] + mouse_pos[1] - self.mouse_pos[1],
            )
            window = self.parent().parent()
            window.set_position(window_pos)


class WindowButton(fsui.Panel):
    def __init__(self, parent, name):
        super().__init__(parent, paintable=True)
        self.set_background_color(parent.background_color)
        self.set_min_width(40)
        self.set_min_height(40)
        self.hover = False
        self.pressed = False

        if parent.background_color.to_hsl().l >= 0.6:
            # FIXME: static resources / share between instances
            self.image = fsui.Image(
                f"pkg://workspace.ui/data/window-{name}.png"
            )
            self.image_hover = fsui.Image(
                f"pkg://workspace.ui/data/window-{name}-hover.png"
            )
            self.image_pressed = fsui.Image(
                f"pkg://workspace.ui/data/window-{name}-pressed.png"
            )
        else:
            self.image = fsui.Image(
                f"pkg://workspace.ui/data/window-{name}-dark.png"
            )
            self.image_hover = fsui.Image(
                f"pkg://workspace.ui/data/window-{name}-hover.png"
            )
            self.image_pressed = fsui.Image(
                f"pkg://workspace.ui/data/window-{name}-pressed.png"
            )

    def on_paint(self):
        dc = self.create_dc()
        if self.pressed and self.hover:
            image = self.image_pressed
        elif self.hover:
            image = self.image_hover
        else:
            image = self.image
        dc.draw_image(image, 0, 0)

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


class WindowMenuButton(WindowButton):
    def __init__(self, parent):
        super().__init__(parent, "menu")

    def on_left_down(self):
        super().on_left_down()
        menu = self.window.menu()
        if menu is not None:
            print(menu)
            self.popup_menu(menu, (0, self.size()[1]))
            # Compensate for left up event not being received when menu is
            # closed. Also check is mouse is still hovering.
            self.pressed = False
            self.on_mouse_motion()
            self.refresh()


class WindowMinimizeButton(WindowButton):
    def __init__(self, parent):
        super().__init__(parent, "minimize")

    def on_activate(self):
        window = self.parent().parent()
        window.minimize()
        # FIXME: restore button state when window is is restored


class WindowMaximizeButton(WindowButton):
    def __init__(self, parent):
        super().__init__(parent, "maximize")

    def on_activate(self):
        if self.visible():
            window = self.parent().parent()
            print(window.is_maximized())
            window.set_maximized(not window.is_maximized())
            # FIXME: button is not refreshed when window is maximized


class WindowCloseButton(WindowButton):
    def __init__(self, parent):
        super().__init__(parent, "close")

    def on_activate(self):
        window = self.parent().parent()
        window.close()


# FIXME: Rename to TopSeparator?
class TitleSeparator(fsui.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.set_background_color(
            WorkspaceTheme.instance().title_separator_color
        )
        self.set_min_height(2)
        self.set_min_width(100)
