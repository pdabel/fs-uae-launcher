"""Plain-language names for Amiga models.

The configuration editor shows these instead of codes like "A500 / 1.3 ROM,
512 KB", and keeps the technical title and subtitle as tooltips so expert
users can still see exactly what each entry means.
"""

from launcher.i18n import gettext

# Family id (the part before "/") -> short everyday name and a one-line hint.
MODEL_LABELS = {
    "A1000": ("Amiga 1000", "The original 1985 Amiga; rarely needed"),
    "A500": ("Amiga 500", "Classic model; works with most games"),
    "A500+": ("Amiga 500 Plus", "1991 update; for Kickstart 2.0 games"),
    "A600": ("Amiga 600", "Compact model with a hard drive"),
    "A1200": ("Amiga 1200", "Faster AGA model; for later and HD games"),
    "A3000": ("Amiga 3000", "Workstation; for Workbench and productivity"),
    "A4000": ("Amiga 4000", "Most powerful classic Amiga"),
    "CD32": ("Amiga CD32", "Games console; uses CD images"),
    "CDTV": ("Commodore CDTV", "Early CD multimedia player"),
}

# Full model id -> what makes this variant different from the base model.
VARIANT_LABELS = {
    "A1000": "Standard",
    "A500/512K": "Basic memory (512 KB)",
    "A500": "Standard (1 MB total memory)",
    "A500+": "Standard",
    "A600": "Standard",
    "A1200/3.0": "Older system ROM (3.0)",
    "A1200": "Standard",
    "A1200/020": "Extra memory and speed",
    "A1200/1230": "Blizzard 1230 accelerator",
    "A1200/1240": "Blizzard 1240 accelerator",
    "A1200/1260": "Blizzard 1260 accelerator",
    "A1200/PPC": "Blizzard PowerPC accelerator",
    "A3000": "Standard",
    "A4000": "Standard",
    "A4000/040": "Faster processor (68040)",
    "A4000/PPC": "PowerPC accelerator",
    "A4000/OS4": "PowerPC with AmigaOS 4",
    "CD32": "Standard",
    "CD32/FMV": "With video (FMV) module",
    "CDTV": "Standard",
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
