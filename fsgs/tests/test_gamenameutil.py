import pytest

from fsgs.util.gamenameutil import GameNameUtil


def test_already_commaed_name():
    name, variant = GameNameUtil.extract_names("Name (A, B, C).adf")
    assert name == "Name"
    assert variant == "A, B, C"


def test_name_without_variant():
    name, variant = GameNameUtil.extract_names("Name.adf")
    assert name == "Name"
    assert variant == ""


def test_tosec_name():
    full_name = (
        "Lotus Turbo Challenge 2 (1991)(Gremlin)[cr CPY][t +4 Goonies].adf"
    )
    name, variant = GameNameUtil.extract_names(full_name)
    assert name == "Lotus Turbo Challenge 2"
    assert variant == "1991, Gremlin, cr CPY, t +4 Goonies"


def test_tosec_name_with_comma_in_publisher():
    full_name = "Zero Gravity (1997)(Hollemans, M.)(AGA).adf"
    name, variant = GameNameUtil.extract_names(full_name)
    assert name == "Zero Gravity"
    assert variant == "1997, M. Hollemans, AGA"


def test_tosec_name_with_comma_in_publisher_2():
    full_name = "Ziriax (1990)(Software Business, The)[3001].dummy"
    name, variant = GameNameUtil.extract_names(full_name)
    assert name == "Ziriax"
    assert variant == "1990, The Software Business, 3001"


def test_leather_goddesses_of_phobos():
    full_name = "Leather Goddesses of Phobos r59 (1986)(Infocom).adf"
    name, variant = GameNameUtil.extract_names(full_name)
    assert name == "Leather Goddesses of Phobos"
    assert variant == "r59, 1986, Infocom"


def test_hitchhikers_guide_to_the_galaxy():
    full_name = "Hitchhiker's Guide to the Galaxy, The r58 (1986)(Infocom).adf"
    name, variant = GameNameUtil.extract_names(full_name)
    assert name == "Hitchhiker's Guide to the Galaxy, The"
    assert variant == "r58, 1986, Infocom"


def test_deep_core():
    name, variant = GameNameUtil.extract_names_from_file_name(
        "Deep Core (Europe)(v1.00).dummy", style=GameNameUtil.NOINTRO
    )
    assert name == "Deep Core"
    assert variant == "Europe, v1.00"


# Index terms ending in "n" also get a "g" added, so "Leavin'" can be found
# as "leaving". That's where "alieng" and "burng" come from.
@pytest.mark.parametrize(
    "name, terms",
    [
        ("King's Quest IV", {"king", "kings", "s", "quest", "4"}),
        ("Alien Breed II", {"alieng", "breed", "2"}),
        ("Alien Breed 2", {"alieng", "breed", "2"}),
        (
            "Project-X SE '92",
            {"projectx", "project", "10", "special", "editiong", "1992"},
        ),
        ("Leavin' Teramis", {"leaving", "teramis"}),
        (
            "F/A-18 Interceptor",
            {"f", "fa", "fa18", "f18", "a18", "18", "interceptor"},
        ),
        (
            "Sensible Soccer '95/'96",
            {"sensible", "soccer", "1995", "1996", "9596"},
        ),
        (
            "Sensible Soccer 1995-96",
            {"sensible", "soccer", "1995", "1996", "199596"},
        ),
        ("Bump 'n' Burn", {"bump", "burng"}),
        ("Bump'n' Burn", {"bump", "burng", "bumpng"}),
        ("Bump'n Burn", {"bump", "burng", "bumpng"}),
    ],
)
def test_extract_index_terms(name, terms):
    assert GameNameUtil.extract_index_terms(name) == terms


def finds(game_name, search):
    """Whether searching for search finds game_name. Database.find_games_new
    matches each search term as a prefix of an index term."""
    index_terms = GameNameUtil.extract_index_terms(game_name)
    return all(
        any(index_term.startswith(term) for index_term in index_terms)
        for term in GameNameUtil.extract_search_terms(search)
    )


@pytest.mark.parametrize(
    "game_name, search",
    [
        ("Bump 'n' Burn", "Bump'n Burn"),
        ("Bump 'n' Burn", "Bump and Burn"),
        ("Lotus Turbo Challenge 2", "Lotus II"),
        ("Sensible Soccer '95/'96", "soccer 95/96"),
        ("F/A-18 Interceptor", "fa 18"),
        ("Formula 1", "formula one"),
        ("Formula one", "formula 1"),
        ("Project-X SE", "project x special"),
        ("Project-X Special Edition", "projectx se"),
        ("Yo! Joe!", "yo joe"),
        ("Alien 3", "Alien³"),
    ],
)
def test_search_finds_game(game_name, search):
    assert finds(game_name, search)


def test_search_does_not_find_other_game():
    assert not finds("Alien Breed", "lotus")
