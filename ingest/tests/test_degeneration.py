"""A model-made transcript that degenerated into a repetition loop is
asked for once more with settings against repetition, then failed; it is
never indexed. Real text with repeated terms passes."""

from pathlib import Path

import pytest

from lasteverlm_ingest.loaders import LoaderError
from lasteverlm_ingest.loaders.degeneration import REASON, degenerated
from lasteverlm_ingest.loaders.image import (
    RETRY_BODY,
    RETRY_PENALTIES,
    RETRY_TEMPERATURE,
    DegeneratedError,
    ImageLoader,
    VisionReader,
)
from lasteverlm_ingest.loaders.pdf import VisionPdfLoader
from lasteverlm_ingest.worker import process_source
from tests.fakes import FakeChat, FakeEmbedder, FakeTranscriber, InMemoryRepository, InMemoryStorage
from tests.test_audio_loader import _add_audio, _audio_deps
from tests.test_image_loader import PNG, _add_image, _image_deps
from tests.test_loaders import minimal_pdf

# The starter screenshot as the vision model read it: a few labels, then
# one term until the output cap.
SCREENSHOT_LOOP = (
    "WEBLUI\nLibrary Settings\nNotebooks Sources Outputs\nSPACES Internet-UI "
    + "Internet-UI " * 700
)
GOOD = "Library\nSettings\n\nA screenshot of the lasteverLM library with three notebooks."


def test_the_real_screenshot_loop_is_degenerate_capped_or_not():
    assert degenerated(SCREENSHOT_LOOP, capped=True)
    assert degenerated(SCREENSHOT_LOOP)


def test_a_loop_that_runs_into_the_cap_after_real_text_is_degenerate():
    text = " ".join(f"word{i}" for i in range(400)) + " Internet-UI" * 120
    assert degenerated(text, capped=True)
    # Without the cap, 120 repeats of a two-word term are still a loop.
    assert degenerated(text)


@pytest.mark.parametrize(
    "text",
    [
        # A table of identical labels, as a settings page or a status list shows them.
        "\n".join("Status: OK" for _ in range(60)),
        "\n".join(f"Server {i}: Status OK" for _ in range(3) for i in range(100)),
        # A song: a verse and a chorus sung four times, six rounds.
        ("A verse about the sea and the sky tonight. " + "We will rock you, oh yeah. " * 4) * 6,
        # A questionnaire answered "Yes" throughout.
        " ".join(["Yes"] * 40),
        "la " * 64,
        # Long real prose: the share of distinct words falls with length.
        (Path(__file__).parent.parent / "README.md").read_text() * 20,
        # A German page with repeated domain terms.
        "Die Steuer auf die Steuer der Steuerberatung ist steuerlich absetzbar. " * 30,
    ],
)
def test_real_text_with_repeated_terms_passes(text):
    assert not degenerated(text)


def test_a_long_answer_cut_at_the_cap_without_a_loop_passes():
    prose = (Path(__file__).parent.parent / "README.md").read_text()
    assert not degenerated(prose[:8000], capped=True)
    # A table of identical rows at the end of a capped page is not enough.
    assert not degenerated(prose[:6000] + "\nStatus: OK" * 40, capped=True)


def _image(answers):
    chat = FakeChat(answers=answers)
    return chat, ImageLoader(VisionReader(chat, "fake-llm"))


def test_a_loop_is_asked_for_again_with_settings_against_repetition():
    chat, loader = _image([(SCREENSHOT_LOOP, "length"), (GOOD, "stop")])
    billed: list = []
    assert [p.text for p in loader.load_billed(PNG, billed.append)] == [GOOD]
    assert len(billed) == 2  # both calls answered, both billed
    first, second = chat.calls
    assert first["temperature"] == 0.0 and "frequency_penalty" not in first
    assert second["temperature"] == RETRY_TEMPERATURE
    assert {k: second[k] for k in RETRY_PENALTIES} == RETRY_PENALTIES
    assert second["extra_body"]["repetition_penalty"] == RETRY_BODY["repetition_penalty"]


def test_two_loops_fail_the_image_with_the_reason_and_bill_both_calls():
    _, loader = _image([(SCREENSHOT_LOOP, "length"), (SCREENSHOT_LOOP, "length")])
    billed: list = []
    with pytest.raises(DegeneratedError, match=REASON):
        loader.load_billed(PNG, billed.append)
    assert len(billed) == 2


def test_a_degenerate_image_source_fails_and_nothing_is_indexed():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    chat = FakeChat(answers=[(SCREENSHOT_LOOP, "length"), (SCREENSHOT_LOOP, "length")])
    sid = _add_image(repo, storage)
    process_source(sid, _image_deps(repo, storage, FakeEmbedder(8), chat))
    source = repo.library[sid]
    assert source.status == "failed" and source.error == REASON
    assert sid not in repo.chunks and source.summary is None
    assert [u.kind for u in repo.usage] == ["llm", "llm"]


def test_a_degenerate_pdf_page_fails_the_pdf_naming_the_tile_and_the_page():
    from tests.test_pdf_capture import T

    chat = FakeChat(answers=[(SCREENSHOT_LOOP, "length")] * (2 * T))
    loader = VisionPdfLoader(VisionReader(chat, "fake-llm"), "vision")
    billed: list = []
    where = rf"\(tile 1 of {T}\) \(page 1\)" if T > 1 else r"\(page 1\)"
    with pytest.raises(LoaderError, match=rf"{REASON} {where}"):
        loader.load_billed(minimal_pdf([""]), billed.append)
    assert len(billed) == 2 * T  # both attempts on every tile, all billed


def test_a_degenerate_transcript_fails_the_recording_and_its_call_is_billed():
    repo, storage = InMemoryRepository(), InMemoryStorage()
    sid = _add_audio(repo, storage)
    looped = "Welcome to the show. " + "Thank you. " * 150
    process_source(sid, _audio_deps(repo, storage, FakeTranscriber(answer=looped)))
    source = repo.library[sid]
    assert source.status == "failed"
    assert source.error == "the model's transcript degenerated into repetition"
    assert sid not in repo.chunks and [u.kind for u in repo.usage] == ["stt"]
