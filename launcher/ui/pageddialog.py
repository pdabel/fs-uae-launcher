import fsui
from launcher.ui.widgets import CloseButton
from .skin import LauncherTheme


class PagedDialog(fsui.Window):
    page_changed = fsui.Signal()

    def __init__(self, parent, title):
        super().__init__(parent, title, minimizable=False, maximizable=False)
        self.theme = LauncherTheme.get()
        self.layout = fsui.VerticalLayout()

        layout = self.layout

        h_layout = fsui.HorizontalLayout()
        layout.add(h_layout, fill=True, expand=True)

        layout_2 = fsui.VerticalLayout()

        self.list_view = fsui.ListView(self, border=False)
        self.list_view.set_min_width(240)
        self.list_view.item_selected.connect(self.on_select_item)

        self.list_view.set_row_height(
            self.window.theme.sidebar_list_row_height
        )
        self.list_view.setStyleSheet(
            f"""
        QListView {{
            padding-top: 20px;
            background-color: {self.window.theme.sidebar_list_background.to_hex()};
            outline: none;
        }}
        QListView::item {{
            padding-left: 20px;
            border: 0px;
        }}
        QListView::item:selected {{
            background-color: {self.window.theme.sidebar_list_row_background.to_hex()};
            color: {self.window.theme.sidebar_list_row_text.to_hex()};
        }}
        """
        )
        if fsui.theme_variant in ("modern", "plain", "windows311", "workbench"):
            from fsui.qt import QSize, Qt

            self.list_view.set_min_width(216)
            self.list_view.set_row_height(42)
            self.list_view.setIconSize(QSize(20, 20))
            self.list_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.list_view.setStyleSheet("""
                QListView { background: #1c1e2b; color: #aeb8ce;
                    border: 0; border-right: 1px solid #303447;
                    padding: 20px 10px; outline: none; }
                QListView::item { padding-left: 12px; margin: 2px 0;
                    border: 0; border-left: 3px solid transparent;
                    border-radius: 4px; }
                QListView::item:hover { background: #282d40; color: white; }
                QListView::item:selected { background: #253e54;
                    color: #73cef8; border-left: 3px solid #46b7ee; }
            """)
            if fsui.theme_variant != "modern":
                self.list_view.set_row_height(44)
                self.list_view.setIconSize(QSize(20, 20) if fsui.theme_variant == "plain" else QSize(24, 24))
                stylesheet = """
                    QListView { background: palette(window);
                        color: palette(window-text); border: 0;
                        border-right: 2px solid palette(shadow);
                        padding: 20px 10px; outline: none; }
                    QListView::item { background: palette(button);
                        color: palette(button-text); padding-left: 8px;
                        margin: 2px 0; border: 2px solid;
                        border-top-color: palette(light);
                        border-left-color: palette(light);
                        border-right-color: palette(shadow);
                        border-bottom-color: palette(shadow); }
                    QListView::item:hover { border-color: palette(highlight); }
                    QListView::item:selected {
                        background: palette(highlight); color: palette(highlighted-text);
                        border-top-color: palette(shadow);
                        border-left-color: palette(shadow);
                        border-right-color: palette(light);
                        border-bottom-color: palette(light); }
                """
                if fsui.theme_variant == "workbench":
                    stylesheet += """
                        QListView::item { border: 2px solid #000000; }
                        QListView::item:hover { border-color: palette(highlight); }
                        QListView::item:selected { border: 2px solid #000000; }
                    """
                self.list_view.setStyleSheet(stylesheet)
        layout_2.add(self.list_view, fill=True, expand=True)
        h_layout.add(layout_2, fill=True)

        v_layout = fsui.VerticalLayout()
        h_layout.add(v_layout, fill=True, expand=True)

        use_scrolling = False
        if use_scrolling:
            # FIXME: Problems with page height
            scroll_area = fsui.VerticalScrollArea(self)
            self.page_container = fsui.Panel(scroll_area)
            self.page_container.layout = fsui.VerticalLayout()
            scroll_area.set_widget(self.page_container)
            v_layout.add(scroll_area, fill=True, expand=True)
        else:
            self.page_container = fsui.Panel(self)
            self.page_container.layout = fsui.VerticalLayout()
            v_layout.add(self.page_container, fill=True, expand=True)

        self.page_titles = []
        self.pages = []

        self.button_layout = fsui.HorizontalLayout()
        v_layout.add(self.button_layout, fill=True, margin=20, margin_top=0)
        if self.window.theme.has_close_buttons:
            self.button_layout.add_spacer(expand=True)
            self.close_button = CloseButton(self)
            self.button_layout.add(
                self.close_button, fill=True, margin_left=10
            )

        self.current_page = None

        self.set_size((840, 640))
        self.center_on_parent()

    def on_select_item(self, index):
        self.set_page(index)

    @property
    def index(self):
        return self.list_view.get_index()

    @property
    def page(self):
        return self.current_page

    def get_index(self):
        return self.list_view.get_index()

    def get_page_title(self, index):
        return self.page_titles[index]["label"]

    def get_page_index_by_title(self, title):
        for i, item in enumerate(self.page_titles):
            if item["label"] == title:
                return i
        return None

    def add_page(self, title, function, icon=None, bold=False):
        self.page_titles.append({"label": title, "icon": icon, "bold": bold})
        self.pages.append(function)
        self.list_view.set_items(self.page_titles)

    def set_page(self, index):
        if self.current_page:
            self.current_page.hide()
            self.page_container.layout.remove(self.current_page)
        if callable(self.pages[index]):
            page = self.pages[index](self.page_container)
            self.pages[index] = page
        else:
            page = self.pages[index]
        self.page_container.layout.add(page, fill=True, expand=True)
        self.current_page = page
        page.show()
        self.page_container.layout.update()
        self.layout.update()

        self.page_changed.emit()

    def set_page_by_title(self, title):
        index = self.get_page_index_by_title(title)
        if index is not None:
            self.list_view.set_index(index)
        return index
