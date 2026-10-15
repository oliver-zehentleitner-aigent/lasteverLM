"""Without a voice of the user's own, an audio's voices follow its output
language, as chosen by listening (German: Dylan and Ono Anna; English: Ryan
and Vivian); other languages keep the deployment's default. The catalogue
lists the defaults and the recommended voices per language."""

import pytest

from lasteverlm_rag.options import (
    VOICE_DEFAULTS,
    VOICES,
    VOICES_RECOMMENDED,
    OutputOptions,
    catalogue,
    resolve,
)


def audio(**options):
    return resolve("audio", OutputOptions(**options), "ryan")


@pytest.mark.parametrize(
    ("language", "first", "second"),
    [("de", "dylan", "ono_anna"), ("en", "ryan", "vivian")],
)
def test_the_language_picks_both_voices(language, first, second):
    resolved = audio(language=language, audio_style="conversation")
    assert (resolved["voice"], resolved["audio_voice_2"]) == (first, second)


def test_a_voice_the_user_chose_always_wins():
    assert audio(language="de", voice="serena")["voice"] == "serena"
    both = audio(language="de", audio_style="faq", voice="eric", audio_voice_2="sohee")
    assert (both["voice"], both["audio_voice_2"]) == ("eric", "sohee")
    # the second default never repeats the first
    same = audio(language="de", audio_style="faq", voice="ono_anna")
    assert same["audio_voice_2"] != "ono_anna"


def test_other_languages_and_no_language_keep_the_deployment_default():
    assert audio(language="fr")["voice"] == "ryan"
    assert audio()["voice"] == "ryan"


def test_every_listed_voice_is_one_of_the_platform():
    ids = {v.id for v in VOICES}
    for picks in VOICE_DEFAULTS.values():
        assert set(picks.values()) <= ids
    for listed in VOICES_RECOMMENDED.values():
        assert set(listed) <= ids
    assert VOICES_RECOMMENDED == {
        "de": ["dylan", "eric", "uncle_fu", "ono_anna", "sohee"],
        "en": ["ryan", "aiden", "vivian", "serena"],
    }


def test_the_catalogue_shows_defaults_and_recommendations_by_language():
    spec = catalogue("ryan", {})["audio"]
    assert spec["default_voice"] == "ryan"
    assert spec["defaults_by_language"]["de"] == {"voice": "dylan", "audio_voice_2": "ono_anna"}
    assert spec["recommended"]["en"] == ["ryan", "aiden", "vivian", "serena"]
