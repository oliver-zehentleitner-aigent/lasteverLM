import pytest

from lasteverlm_rag.numbers import readings, written_in


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1906 visitors", 1906),
        ("1.906 Besucher", 1906),
        ("1,906 visitors", 1906),
        ("1.906 Besucher", 1.906),
        ("1,9 Mio. Einwohner", 1.9),
        ("1,9 Mio. Einwohner", 1_900_000),
        ("3.5 million people", 3_500_000),
        ("2 Mrd. Euro", 2_000_000_000),
        ("12,5 % der Stimmen", 12.5),
        ("12,5 % der Stimmen", 0.125),
        ("1.234.567 entries", 1_234_567),
        ("1,234.5 tons", 1234.5),
        ("1.234,5 Tonnen", 1234.5),
        ("a loss of -4.2 points", -4.2),
        ("12 000 people", 12000),
        ("in 2024 the bridge", 2024),
    ],
)
def test_a_written_number_matches_each_of_its_readings(text, value):
    assert written_in(value, [text])


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1906 visitors", 1907),  # off by one is another number
        ("1,9 Mio. Einwohner", 1_950_000),
        ("12,5 %", 12),
        ("1.906 Besucher", 19.06),
        ("version2 and abc3", 3),  # digits glued to a word are not numbers
        ("no numbers here", 0),
    ],
)
def test_a_value_not_written_does_not_match(text, value):
    assert not written_in(value, [text])


def test_readings_collects_every_number():
    assert {2019.0, 2020.0, 4.5, 0.045} <= readings("2019 and 2020: 4,5 %")


def test_positions_of_a_structured_source_are_never_values():
    # ingest's rendering (ingest/docs/README.md, "The rendering is a contract")
    csv = "row 3: city: Graz; price: 12"
    assert not written_in(3, [csv]) and written_in(12, [csv])
    json_line = "items[0].price: 12.5\nlanguages.Python: 251804"
    assert not written_in(0, [json_line])
    assert written_in(12.5, [json_line]) and written_in(251804, [json_line])
    xml = "rss/channel/item[2]/price@currency: 7"
    assert not written_in(2, [xml]) and written_in(7, [xml])
    # a numeric key is a label and stays a number
    assert written_in(2023, ["2023: 5"]) and written_in(5, ["2023: 5"])


def test_e_notation_is_read_as_its_value():
    assert written_in(0.00001, ["x: 1e-05"])
    assert written_in(2500, ["ratio: 2.5E3"])
    assert not written_in(5, ["x: 1e-05"])
