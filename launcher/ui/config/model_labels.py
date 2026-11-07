"""Plain-language names for Amiga models.

The configuration editor shows these instead of codes like "A500 / 1.3 ROM,
512 KB", and keeps the technical title and subtitle as tooltips so expert
users can still see exactly what each entry means.
"""

from launcher.i18n import gettext
from launcher.option import N_

# Family id (the part before "/") -> short everyday name and a one-line hint.
MODEL_LABELS = {
    "A1000": (N_("Amiga 1000"), N_("The original 1985 Amiga; rarely needed")),
    "A500": (N_("Amiga 500"), N_("Classic model; works with most games")),
    "A500+": (N_("Amiga 500 Plus"), N_("1991 update; for Kickstart 2.0 games")),
    "A600": (N_("Amiga 600"), N_("Compact model with a hard drive")),
    "A1200": (N_("Amiga 1200"), N_("Faster AGA model; for later and HD games")),
    "A3000": (N_("Amiga 3000"), N_("Workstation; for Workbench and productivity")),
    "A4000": (N_("Amiga 4000"), N_("Most powerful classic Amiga")),
    "CD32": (N_("Amiga CD32"), N_("Games console; uses CD images")),
    "CDTV": (N_("Commodore CDTV"), N_("Early CD multimedia player")),
}

# Full model id -> what makes this variant different from the base model.
VARIANT_LABELS = {
    "A1000": N_("Standard"),
    "A500/512K": N_("Basic memory (512 KB)"),
    "A500": N_("Standard (1 MB total memory)"),
    "A500+": N_("Standard"),
    "A600": N_("Standard"),
    "A1200/3.0": N_("Older system ROM (3.0)"),
    "A1200": N_("Standard"),
    "A1200/020": N_("Full 68020 processor (standard A1200 has the 68EC020)"),
    "A1200/1230": N_("Blizzard 1230 accelerator"),
    "A1200/1240": N_("Blizzard 1240 accelerator"),
    "A1200/1260": N_("Blizzard 1260 accelerator"),
    "A1200/PPC": N_("Blizzard PowerPC accelerator"),
    "A3000": N_("Standard"),
    "A4000": N_("Standard"),
    "A4000/040": N_("Faster processor (68040)"),
    "A4000/PPC": N_("PowerPC accelerator"),
    "A4000/OS4": N_("PowerPC with AmigaOS 4"),
    "CD32": N_("Standard"),
    "CD32/FMV": N_("With video (FMV) module"),
    "CDTV": N_("Standard"),
}


def model_label(model_id):
    """Everyday name for a model family, falling back to the id."""
    name, _ = MODEL_LABELS.get(model_id, (model_id, ""))
    return gettext(name)


def model_hint(model_id):
    _, hint = MODEL_LABELS.get(model_id, (model_id, ""))
    return gettext(hint) if hint else ""


def variant_label(model_id, subtitle):
    """Everyday description for a variant, falling back to its subtitle."""
    label = VARIANT_LABELS.get(model_id)
    return gettext(label) if label else subtitle


def technical_tooltip(title, subtitle=""):
    text = title if not subtitle else f"{title} \u2014 {subtitle}"
    return gettext("Technical: {details}").format(details=text)
