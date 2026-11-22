import fsui
from fsbc.application import app
from launcher.i18n import gettext
from launcher.launcher_config import LauncherConfig
from launcher.launcher_settings import LauncherSettings
from launcher.option import Option
from launcher.settings.override_warning import OverrideWarning
from launcher.ui.HelpButton import HelpButton


class OptionUI(object):
    @classmethod
    def create_group(
        cls,
        parent,
        name,
        description=None,
        help_button=True,
        thin=False,
        expand=False,
        per_game=False,
    ):
        group = fsui.Group(parent)
        group.layout = fsui.HorizontalLayout()
        if thin:
            thin_layout = fsui.VerticalLayout()
            thin_layout.add(group.layout, fill=True)
        option = Option.get(name)
        if description == "":
            description = gettext(option["description"])
        if description and not per_game:
            group.label = fsui.Label(group, description + ":")
            if expand and not thin:
                group.label_layout = fsui.HorizontalLayout()
                group.label_layout.add(group.label, margin_right=10)
                group.label_layout.add(OverrideWarning(group, name))
                group.layout.add(group.label_layout, margin_right=20)
            else:
                group.layout.add(group.label, margin_right=10)
                group.layout.add(OverrideWarning(group, name), margin_right=10)
        elif description:
            group.label = fsui.Label(group, description + ":")
            group.layout.add(group.label, margin_right=10)
        if thin:
            group.layout = fsui.HorizontalLayout()
            if description:
                thin_layout.add(group.layout, fill=True, margin_top=6)
            else:
                thin_layout.add(group.layout, fill=True, margin_top=0)
        if per_game:
            group.game_state_label = fsui.Label(group, "")
            group.layout.add(group.game_state_label, margin_right=10)

        choice_values = []
        inherit_value = "__launcher_inherit_game_default__"
        option_default_value = "__launcher_use_option_default__"
        if per_game:
            overrides = LauncherConfig.get_game_overrides()
            stored_value = overrides.get(name)
            has_override = name in overrides
            base_value = LauncherConfig.get_game_base_value(name)
            current_value = (
                stored_value
                if has_override
                else base_value if base_value else inherit_value
            )
            if has_override and stored_value == "":
                current_value = option_default_value
            game_enabled = LauncherConfig.game_overrides_available()
        else:
            current_value = LauncherSettings.get(name)
            game_enabled = True

        def set_value(value):
            if per_game:
                LauncherConfig.set_game_override(name, value)
            else:
                LauncherSettings.set(name, value)

        def clear_value():
            if per_game:
                LauncherConfig.clear_game_override(name)
            else:
                LauncherSettings.set(name, "")

        def effective_global_value():
            value = LauncherSettings.get(name)
            if value:
                return value
            return str(option.get("default", ""))

        def value_description(value):
            if option["type"].lower() == "boolean":
                return gettext("On") if value == "1" else gettext("Off")
            for item_value, item_label in option.get("values", []):
                if item_value == value:
                    return gettext(item_label)
            return value or gettext("Default")

        def refresh_per_game_widget():
            nonlocal current_value, game_enabled
            if not per_game or not hasattr(group, "value_control"):
                return
            game_enabled = LauncherConfig.game_overrides_available()
            value_enabled = game_enabled and not (
                name == Option.VIDEO_SYNC
                and LauncherSettings.get(Option.G_SYNC) == "1"
            )
            group.value_control.set_enabled(value_enabled)
            if hasattr(group, "default_checkbox"):
                group.default_checkbox.set_enabled(game_enabled)
            if hasattr(group, "reset_button"):
                group.reset_button.set_enabled(game_enabled)
            group.value_control.set_tooltip(
                gettext(
                    "Per-game setting. Choose Default to use the game "
                    "configuration or launcher default."
                )
            )
            overrides = LauncherConfig.get_game_overrides()
            base_value = LauncherConfig.get_game_base_value(name)
            if not game_enabled:
                group.game_state_label.set_text(
                    gettext("Overrides unavailable")
                    if LauncherConfig.game_override_identity()
                    else gettext("Load a game")
                )
            elif name in overrides:
                group.game_state_label.set_text(gettext("Override"))
            elif base_value:
                group.game_state_label.set_text(gettext("Game config"))
            else:
                group.game_state_label.set_text(gettext("Inherited"))
            if name in overrides:
                current_value = overrides[name]
                if current_value == "":
                    current_value = option_default_value
            else:
                current_value = (
                    LauncherConfig.get_game_base_value(name) or inherit_value
                )
            effective_value = (
                overrides[name]
                if name in overrides
                else base_value or effective_global_value()
            )
            if option["type"].lower() == "string":
                with group.value_control.changed.inhibit:
                    group.value_control.set_text(effective_value)
            elif option["type"].lower() == "integer":
                try:
                    effective_integer = int(effective_value)
                except (TypeError, ValueError):
                    effective_integer = int(option["default"])
                effective_integer = max(
                    option["min"],
                    min(option["max"], effective_integer),
                )
                inherited = name not in overrides and not base_value
                with group.value_control.changed.inhibit:
                    group.value_control.set_value(effective_integer)
                with group.default_checkbox.changed.inhibit:
                    group.default_checkbox.check(inherited)
                group.value_control.set_enabled(game_enabled and not inherited)
            if hasattr(group, "widget") and isinstance(
                group.widget, fsui.Choice
            ):
                if name == Option.MONITOR:
                    group.widget.refresh()
                    return
                if choice_values:
                    choice_values[0] = (
                        inherit_value,
                        gettext("Default ({0})").format(
                            value_description(effective_global_value())
                        ),
                    )
                    if current_value not in {
                        inherit_value,
                        option_default_value,
                    } and all(
                        value != current_value for value, _ in choice_values
                    ):
                        choice_values.append(
                            (
                                current_value,
                                gettext("{value} (Game config)").format(
                                    value=current_value
                                ),
                            )
                        )
                    selected_override = (
                        name in overrides and overrides[name] != ""
                    )
                    with group.widget.changed.inhibit:
                        group.widget.clear()
                        for index, (_, label) in enumerate(choice_values):
                            if selected_override and (
                                choice_values[index][0] == current_value
                            ):
                                label = gettext(
                                    "{value} (Game override)"
                                ).format(value=label)
                            group.widget.add_item(label)
                        selected = next(
                            (
                                index
                                for index, (value, _) in enumerate(
                                    choice_values
                                )
                                if value == current_value
                            ),
                            0,
                        )
                        group.widget.set_index(selected)

        def on_per_game_config(value):
            refresh_per_game_widget()

        def on_per_game_settings(key, value):
            refresh_per_game_widget()

        if description:
            default_tmpl = "{0} (*)"
        else:
            default_tmpl = "{0} (*)"

        if option["type"].lower() == "boolean":
            if option["default"] == "1":
                default_desc = gettext(default_tmpl).format(gettext("On"))
            elif option["default"] == "0":
                default_desc = gettext(default_tmpl).format(gettext("Off"))
            else:
                default_desc = gettext("Default")
            choice_values.append(
                (
                    inherit_value if per_game else "",
                    (
                        gettext("Default ({0})").format(
                            value_description(effective_global_value())
                        )
                        if per_game
                        else default_desc
                    ),
                )
            )
            if per_game:
                choice_values.append(
                    (option_default_value, gettext("Use FS-UAE default"))
                )
            choice_values.append(("1", gettext("On")))
            choice_values.append(("0", gettext("Off")))

        elif option["type"].lower() == "choice":
            for i, value in enumerate(option["values"]):
                if option["default"] == value[0]:
                    default_desc = gettext(default_tmpl).format(
                        gettext(value[1])
                    )
                    break
            else:
                default_desc = gettext("Default")
            choice_values.append(
                (
                    inherit_value if per_game else "",
                    (
                        gettext("Default ({0})").format(
                            value_description(effective_global_value())
                        )
                        if per_game
                        else default_desc
                    ),
                )
            )
            if per_game:
                choice_values.append(
                    (option_default_value, gettext("Use FS-UAE default"))
                )
            for option_value in option["values"]:
                choice_values.append(
                    (option_value[0], gettext(option_value[1]))
                )

        elif option["type"].lower() == "string":

            def on_changed():
                val = text_field.get_text()
                set_value(val.strip())

            text_field = fsui.TextField(group)
            if per_game and current_value == inherit_value:
                text_field.set_text(effective_global_value())
            else:
                text_field.set_text(
                    LauncherConfig.get(name)
                    if per_game
                    else LauncherSettings.get(name)
                )
            text_field.on_changed = on_changed
            group.layout.add(text_field, expand=True)
            group.value_control = text_field
            if per_game:
                reset_button = fsui.Button(group, gettext("Default"))
                reset_button.activated.connect(clear_value)
                group.layout.add(reset_button, margin_left=8)
                group.reset_button = reset_button

        elif (
            option["type"].lower() == "integer"
            and "min" in option
            and "max" in option
        ):
            current = (
                LauncherConfig.get(name)
                if per_game
                else LauncherSettings.get(name)
            )

            if name == Option.LAUNCHER_FONT_SIZE:
                font = app.qapplication.font()
                Option.get(Option.LAUNCHER_FONT_SIZE)[
                    "default"
                ] = font.pointSize()

            current_int = int(option["default"])
            if current:
                try:
                    current_int = int(current)
                except ValueError:
                    pass
            current_int = max(option["min"], min(option["max"], current_int))
            check_box = fsui.CheckBox(
                group,
                gettext("Default" if not per_game else "Game Default"),
            )
            spin_ctrl = fsui.SpinCtrl(
                group, option["min"], option["max"], current_int
            )
            if current == "":
                check_box.check()
                spin_ctrl.disable()

            def on_checkbox():
                if check_box.is_checked():
                    spin_ctrl.set_value(int(option["default"]))
                    spin_ctrl.disable()
                    clear_value()
                else:
                    spin_ctrl.enable()

            check_box.on_changed = on_checkbox

            def on_spin():
                val = spin_ctrl.get_value()
                val = max(option["min"], min(option["max"], val))
                set_value(str(val))

            spin_ctrl.on_changed = on_spin
            if not expand:
                group.layout.add_spacer(0, expand=True)
            group.layout.add(check_box)
            group.layout.add(spin_ctrl, expand=expand, margin_left=10)
            group.value_control = spin_ctrl
            group.default_checkbox = check_box

        if choice_values:
            if (
                per_game
                and current_value
                not in {
                    inherit_value,
                    option_default_value,
                }
                and all(value != current_value for value, _ in choice_values)
            ):
                choice_values.append(
                    (
                        current_value,
                        gettext("{value} (Game config)").format(
                            value=current_value
                        ),
                    )
                )

            def on_changed():
                index = choice.get_index()
                value = choice_values[index][0]
                if per_game:
                    if value == inherit_value:
                        clear_value()
                    elif value == option_default_value:
                        set_value("")
                    else:
                        set_value(value)
                else:
                    LauncherSettings.set(name, value)

            if name == Option.MONITOR:
                from launcher.settings.monitorbutton import MonitorChoice

                choice = MonitorChoice(group, per_game=per_game)
            else:
                choice_labels = [x[1] for x in choice_values]
                choice = fsui.Choice(group, choice_labels)
                current = current_value
                for i, value in enumerate(choice_values):
                    if current == value[0]:
                        choice.set_index(i)
                        break
                choice.on_changed = on_changed
            if thin or expand:
                group.layout.add(choice, expand=True)
            else:
                group.layout.add_spacer(0, expand=True)
                group.layout.add(choice)
            group.widget = choice
            group.value_control = choice
            if per_game:
                choice.set_enabled(game_enabled)

        if per_game:
            group.game_state_label.on_settings = on_per_game_settings
            group.game_state_label.on___game_override_context_config = (
                on_per_game_config
            )
            setattr(
                group.game_state_label,
                f"on_{name}_config",
                on_per_game_config,
            )
            from launcher.ui.behaviors.configbehavior import ConfigBehavior
            from launcher.ui.behaviors.settingsbehavior import SettingsBehavior

            ConfigBehavior(
                group.game_state_label,
                [name, "__game_override_context"],
            )
            SettingsBehavior(group.game_state_label, [name])
            refresh_per_game_widget()

        if help_button:
            option_url = "https://fs-uae.net/docs/options/" + name.replace(
                "_", "-"
            )
            group.help_button = HelpButton(parent, option_url)
            group.layout.add(group.help_button, margin_left=10)

        if thin:
            group.layout = thin_layout
        return group
