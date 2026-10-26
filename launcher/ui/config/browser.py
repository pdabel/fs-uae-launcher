from launcher.ui.config.model import create_model
import fsui
import traceback


class ConfigBrowser(fsui.VerticalItemView):
    def __init__(self, parent):
        fsui.VerticalItemView.__init__(self, parent, border=False)
        self.items = []
        self.game_icon = fsui.Image("launcher:res/16x16/controller.png")
        self.config_icon = fsui.Image("launcher:res/fsuae_config_16.png")

        self.manual_download_icon = fsui.Image(
            "launcher:res/16x16/arrow_down_yellow.png"
        )
        self.auto_download_icon = fsui.Image(
            "launcher:res/16x16/arrow_down_green.png"
        )
        self.blank_icon = fsui.Image("launcher:res/16x16/blank.png")
        self.missing_color = fsui.Color(0xA8, 0xA8, 0xA8)
        self.platform_icons = {}

        from workspace.ui.theme import WorkspaceTheme

        theme = WorkspaceTheme.instance()
        self.set_row_height(28)
        self.setStyleSheet(
            f"""
        QListView {{
            background-color: {theme.sidebar_background.to_hex()};
            outline: none;
        }}
        QListView::item {{
            padding-left: 6px;
            border: 0px;
        }}
        QListView::item:selected {{
            background-color: {theme.selection_background.to_hex()};
        }}
        """
        )

    def update_from_implicit(self, implicit):
        def flatten(item_list, level):

            for model_item in item_list:
                if model_item.active:
                    text = str(model_item.text)
                    if model_item.extra:
                        text += " [" + model_item.extra + "]"
                    items.append(text)
                if model_item.children:
                    flatten(model_item.children, level + 1)

        items = []
        try:
            model = create_model(implicit, show_all=False)
        except Exception:
            traceback.print_exc()
            print("create_model failed")
        else:
            flatten(model.items, 0)
        self.set_items(items)

    def on_select_item(self, index):
        if index is None:
            return
        pass

    def on_activate_item(self, index):
        pass

    def set_items(self, items):
        self.items = items
        self.update()

    def get_item_count(self):
        return len(self.items)

    def get_item_text(self, index):
        item = self.items[index]
        return item

    def get_item_icon(self, index):
        return self.config_icon
