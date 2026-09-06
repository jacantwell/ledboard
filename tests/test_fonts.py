import pytest

from ledboard import fonts


@pytest.mark.parametrize("name", fonts.NAMES)
def test_load_returns_a_measurable_font(name):
    font = fonts.load(name)
    assert hasattr(font, "getbbox"), "loaded fonts must be measurable"
    left, top, right, bottom = font.getbbox("hi")
    assert right > left and bottom > top, "a two-character string has a non-empty box"


@pytest.mark.parametrize("name", fonts.NAMES)
def test_load_is_cached(name):
    assert fonts.load(name) is fonts.load(name), "loading twice reuses the compiled font"


@pytest.mark.parametrize("name", ["", "8x8", "6x10 ", "comic-sans", "6X10"])
def test_load_rejects_unknown_names(name):
    with pytest.raises(ValueError, match="unknown font"):
        fonts.load(name)


@pytest.mark.parametrize("name,expected", [("4x6", (4, 6)), ("5x7", (5, 7)), ("6x10", (6, 10))])
def test_size_parses_the_name(name, expected):
    assert fonts.size(name) == expected, "size comes straight from the name"


@pytest.mark.parametrize("name", fonts.NAMES)
def test_size_matches_the_rendered_glyph_height(name):
    _, height = fonts.size(name)
    _, top, _, bottom = fonts.load(name).getbbox("Ag")
    assert bottom - top <= height, "glyphs fit inside the declared cell height"


def test_default_is_a_known_font():
    assert fonts.DEFAULT in fonts.NAMES, "the default font must be loadable"
