import pytest

from launcher.implicit_handler import ExpandFunctions
from launcher.ui.config.expand import expand_config
from launcher.ui.config.model import ImplicitConfig


class Values(dict):
    def __getitem__(self, key):
        return self.get(key, "")


@pytest.mark.parametrize("sana2", ["true", "false", "custom"])
@pytest.mark.parametrize("rtc", ["", "MSM6242B"])
@pytest.mark.parametrize("source", ["config", "settings"])
def test_explicit_sana2_is_preserved_independently_of_rtc(sana2, rtc, source):
    config = Values(uae_rtc=rtc)
    settings = Values()
    (config if source == "config" else settings)["uae_sana2"] = sana2
    implicit = ImplicitConfig(config, settings)

    expand_config(implicit, ExpandFunctions())

    assert dict(implicit.items())["uae_sana2"] == sana2


@pytest.mark.parametrize("rtc", ["", "MSM6242B"])
def test_sana2_defaults_to_false_independently_of_rtc(rtc):
    implicit = ImplicitConfig(Values(uae_rtc=rtc), Values())

    expand_config(implicit, ExpandFunctions())

    assert dict(implicit.items())["uae_sana2"] == "false"
