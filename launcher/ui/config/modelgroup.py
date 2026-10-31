import fsui
from fsbc.util import unused
from fsgs.amiga.amiga import Amiga
from fsui.qt import Qt
from launcher.option import Option
from launcher.cd_manager import CDManager
from launcher.floppy_manager import FloppyManager
from launcher.i18n import gettext
from launcher.launcher_config import LauncherConfig
from launcher.panels.additionalconfigpanel import CustomConfigButton
from launcher.ui.behaviors.configbehavior import ConfigBehavior
from launcher.ui.behaviors.platformbehavior import (
    AMIGA_PLATFORMS,
    AmigaShowBehavior,
)
from launcher.ui.config.ConfigCheckBox import ConfigCheckBox
from launcher.ui.config.model_labels import (
    model_hint, model_label, technical_tooltip, variant_label,
)


class ModelGroup(fsui.Group):

    # FIXME: remove with_more_button=True
    def __init__(self, parent, with_more_button=True):
        unused(with_more_button)
        fsui.Group.__init__(self, parent)
        self.layout = fsui.VerticalLayout()

        self.model_ids = [x["id"] for x in Amiga.models if "/" not in x["id"]]
        self.model_titles = [
            x["title"] for x in Amiga.models if "/" not in x["id"]
        ]
        self.model_labels = [model_label(x) for x in self.model_ids]

        self.sub_model_ids = []
        self.sub_model_titles = []
        self.sub_model_updating = False

        self.model_choice = fsui.Choice(self, self.model_labels)
        for index, model_id in enumerate(self.model_ids):
            hint = model_hint(model_id)
            technical = technical_tooltip(self.model_titles[index])
            self.model_choice.setItemData(
                index, f"{hint}\n{technical}" if hint else technical,
                Qt.ToolTipRole,
            )
        self.model_choice.set_tooltip(
            gettext("Which Amiga to emulate. Amiga 500 runs most games.")
        )
        self.sub_model_choice = fsui.Choice(self, self.sub_model_titles)
        self.sub_model_choice.set_tooltip(
            gettext("Memory, processor and ROM variant of this model")
        )
        self.accuracy_label = fsui.Label(self, gettext("Accuracy:"))
        self.accuracy_choice = fsui.Choice(
            self, [gettext("High"), gettext("Medium"), gettext("Low")]
        )
        self.accuracy_choice.set_tooltip(gettext(
            "High is most faithful to real hardware. Lower settings run "
            "faster on slow computers but some games may misbehave."
        ))
        self.ntsc_checkbox = ConfigCheckBox(self, "NTSC", Option.NTSC_MODE)
        self.ntsc_checkbox.set_tooltip(gettext(
            "Use the American 60 Hz video mode. Leave off for European "
            "(PAL) games."
        ))

        AmigaShowBehavior(self.accuracy_label)
        AmigaShowBehavior(self.accuracy_choice)
        AmigaShowBehavior(self.ntsc_checkbox)

        self.model_title_layout = fsui.HorizontalLayout()
        self.layout.add(self.model_title_layout, fill=True)

        heading_label = fsui.HeadingLabel(self, gettext("Amiga Model"))
        self.model_title_layout.add(heading_label, margin=10)

        self.model_title_layout.add_spacer(0, expand=True)
        self.model_title_layout.add(
            self.ntsc_checkbox, expand=False, margin_left=10, margin_right=10
        )
        self.model_title_layout.add_spacer(20)

        self.model_title_layout.add(self.accuracy_label, margin_right=10)
        self.model_title_layout.add(self.accuracy_choice, margin_right=10)
        self.model_title_layout.add(CustomConfigButton(self), margin_right=10)

        self.model_layout = fsui.HorizontalLayout()

        def dummy_min_width():
            return 0

        # Not sure why this is needed, but on startup, the min width
        # seems to be set too large due to something in the model layout.
        self.model_layout.get_min_width = dummy_min_width
        self.layout.add(self.model_layout, fill=True)

        self.model_layout.add(self.model_choice, expand=False, margin=10)
        AmigaShowBehavior(self.model_choice)
        self.model_layout.add(self.sub_model_choice, expand=True, margin=10)
        AmigaShowBehavior(self.sub_model_choice)

        ConfigBehavior(
            self, [Option.ACCURACY, Option.AMIGA_MODEL, Option.PLATFORM]
        )

        self.model_choice.on_changed = self.on_model_changed
        self.sub_model_choice.on_changed = self.on_sub_model_changed
        self.accuracy_choice.on_changed = self.on_accuracy_changed

    def on_platform_config(self, _):
        # Update layout after widgets have been shown/hidden.
        self.model_title_layout.update()
        self.model_layout.update()

    def on_model_changed(self):
        print("ModelGroup.on_model_change\n")
        index = self.model_choice.get_index()
        model = self.model_ids[index]
        if model == "A500":
            # The default model (A500) can be specified with the empty string
            model = ""
        LauncherConfig.set("amiga_model", model)

    def on_sub_model_changed(self):
        print("ModelGroup.on_sub_model_change\n")
        if self.sub_model_updating:
            print("sub model list is currently updating")
            return
        index = self.sub_model_choice.get_index()
        self.update_sub_model_tooltip(index)
        model = self.model_ids[self.model_choice.get_index()]
        sub_model = self.sub_model_ids[index]
        if sub_model:
            LauncherConfig.set("amiga_model", model + "/" + sub_model)
        else:
            LauncherConfig.set("amiga_model", model)

        if Amiga.is_cd_based(LauncherConfig):
            FloppyManager.clear_all()
        else:
            CDManager.clear_all()

    def on_accuracy_changed(self):
        index = self.accuracy_choice.get_index()
        if index == 0:
            LauncherConfig.set("accuracy", "")
        else:
            LauncherConfig.set("accuracy", str(1 - index))

    def update_sub_models(self, model_id, sub_model_id):
        sub_model_index = 0
        model_id_s = model_id + "/"
        self.sub_model_ids.clear()
        self.sub_model_titles.clear()
        technical = []

        for i, config in enumerate(Amiga.models):
            if config["id"] == model_id:
                self.sub_model_ids.append("")
            elif config["id"].startswith(model_id_s):
                self.sub_model_ids.append(config["id"].split("/", 1)[1])
            else:
                continue
            self.sub_model_titles.append(
                variant_label(config["id"], config["subtitle"])
            )
            technical.append(
                technical_tooltip(config["title"], config["subtitle"])
            )
            if sub_model_id == self.sub_model_ids[-1]:
                sub_model_index = len(self.sub_model_ids) - 1

        self.sub_model_choice.clear()
        for index, title in enumerate(self.sub_model_titles):
            self.sub_model_choice.add_item(title)
            self.sub_model_choice.setItemData(
                index, technical[index], Qt.ToolTipRole
            )
        self.sub_model_technical = technical
        self.sub_model_choice.enable(
            LauncherConfig.get(Option.PLATFORM) in AMIGA_PLATFORMS
            and len(self.sub_model_ids) > 1
        )
        self.update_sub_model_tooltip(sub_model_index)
        return sub_model_index

    def update_sub_model_tooltip(self, index):
        """Show the technical details on the control itself.

        Single-variant families disable the combo, so its item tooltips
        cannot be opened.
        """
        text = gettext("Memory, processor and ROM variant of this model")
        technical = getattr(self, "sub_model_technical", [])
        if 0 <= index < len(technical):
            text += "\n" + technical[index]
        self.sub_model_choice.set_tooltip(text)

    def on_amiga_model_config(self, value):
        if value == "":
            value = "A500"

        if "/" in value:
            model_id, sub_model_id = value.split("/", 1)
        else:
            model_id = value
            sub_model_id = ""

        model_index = 0
        sub_model_index = 0
        self.sub_model_updating = True
        for i, config in enumerate(Amiga.models_config):
            if config == value:
                # find main model index
                model_index = self.model_ids.index(model_id)
                sub_model_index = self.update_sub_models(
                    model_id, sub_model_id
                )
                break
        self.model_choice.set_index(model_index)
        self.sub_model_choice.set_index(sub_model_index)
        self.update_sub_model_tooltip(sub_model_index)
        self.sub_model_updating = False

    def on_accuracy_config(self, value):
        if not value:
            index = 0
        else:
            index = 1 - int(value)
        self.accuracy_choice.set_index(index)
