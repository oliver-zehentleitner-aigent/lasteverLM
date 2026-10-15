"""Large images are read in tiles: the platform scales every image to the
same small budget, so a large screenshot's text is only legible in parts
(docs/vision-eval.md)."""

import io

import httpx
import pytest
from lasteverlm_core import ProviderError
from openai import APIConnectionError
from PIL import Image

from lasteverlm_ingest.loaders import LoaderError
from lasteverlm_ingest.loaders.degeneration import REASON
from lasteverlm_ingest.loaders.image import ImageLoader, VisionReader
from lasteverlm_ingest.loaders.tiles import (
    MAX_PIXELS,
    OVERLAP,
    crops,
    image_tiles,
    join,
    tile_boxes,
)
from tests.fakes import FakeChat

REQUEST = httpx.Request("POST", "https://inference.test/v1/chat/completions")


def _png(width: int, height: int, fmt: str = "PNG", mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, (width, height), "white" if mode == "RGB" else 1).save(buffer, fmt)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("size", "count"),
    [
        ((1440, 900), 1),
        ((1000, 1500), 1),
        ((1920, 1080), 2),
        ((1241, 1754), 2),  # an A4 page at the render DPI
        ((2880, 1800), 4),  # a retina screenshot
        ((1170, 2532), 3),  # a tall phone screenshot
        ((3840, 2160), 6),
    ],
)
def test_the_fewest_tiles_under_the_pixel_cap_cover_the_image(size, count):
    width, height = size
    boxes = tile_boxes(width, height)
    assert len(boxes) == count
    covered = set()
    for left, top, right, bottom in boxes:
        assert (right - left) * (bottom - top) <= max(
            MAX_PIXELS, width * height if count == 1 else 0
        )
        assert 0 <= left < right <= width and 0 <= top < bottom <= height
        covered |= {(left, top), (right, bottom)}
    assert (0, 0) in covered and (width, height) in covered


def test_tiles_overlap_and_come_in_reading_order():
    boxes = tile_boxes(2880, 1800)
    assert [(b[0], b[1]) for b in boxes] == [(0, 0), (1416, 0), (0, 876), (1416, 876)]
    first, second, third = boxes[0], boxes[1], boxes[2]
    assert first[2] - second[0] == OVERLAP and first[3] - third[1] == OVERLAP


def test_an_image_needing_too_many_tiles_is_refused():
    with pytest.raises(ValueError, match="more than"):
        tile_boxes(20000, 20000)


def test_crops_keep_png_sharp_and_leave_a_small_image_untouched():
    small = _png(800, 600)
    assert crops(small) == ([small], "")
    tiles, media_type = crops(_png(2880, 1800))
    assert media_type == "image/png" and len(tiles) == 4
    assert {Image.open(io.BytesIO(t)).size for t in tiles} == {(1464, 924)}
    tiles, media_type = crops(_png(1920, 1080, "JPEG"))
    assert media_type == "image/jpeg" and len(tiles) == 2
    assert image_tiles(_png(2880, 1800)) == 4 and image_tiles(b"\x89PNG not an image") is None


def test_join_drops_the_overlap_read_twice_and_keeps_real_repetitions():
    upper_left = "Quarterly report, page heading\nRevenue grew by 12 percent in Q3\nOK"
    upper_right = "Right column title, section two\nOK"
    lower_left = "Revenue grew by 12 percent in Q3\nOK\nCosts fell by 3 percent overall"
    lower_right = "Right column title, section two\nFooter of the right column"
    joined = join([upper_left, upper_right, lower_left, lower_right], columns=2)
    assert joined.count("Revenue grew by 12 percent in Q3") == 1
    assert joined.count("Right column title, section two") == 1
    assert joined.count("OK") == 3  # a short label may really repeat: kept
    assert joined.index("Quarterly report") < joined.index("Right column title, section two")
    assert joined.index("Right column title, section two") < joined.index("Costs fell")


class _ByTile(FakeChat):
    """Answers each tile with a text of its own, the call count as its id."""

    def create(self, **kwargs):
        self.answer = f"Tile text number {len(self.calls) + 1} of the screenshot."
        return super().create(**kwargs)


def test_a_large_image_is_read_in_tiles_and_every_call_is_billed():
    chat, billed = _ByTile(), []
    passages = ImageLoader(VisionReader(chat, "fake-llm")).load_billed(
        _png(2880, 1800), billed.append
    )
    assert len(chat.calls) == 4 and len(billed) == 4
    [passage] = passages
    assert sorted(passage.text.split("\n\n")) == sorted(
        f"Tile text number {n} of the screenshot." for n in range(1, 5)
    )
    sent = [c["messages"][1]["content"][0]["image_url"]["url"] for c in chat.calls]
    assert all(url.startswith("data:image/png;base64,") for url in sent)


def test_a_failing_tile_fails_the_image_after_billing_the_answered_ones():
    class OneFails(FakeChat):
        def create(self, **kwargs):
            if not self.calls:
                self.calls.append(kwargs)
                raise APIConnectionError(request=REQUEST)
            return super().create(**kwargs)

    billed: list = []
    with pytest.raises(ProviderError):
        ImageLoader(VisionReader(OneFails(), "fake-llm")).load_billed(
            _png(2880, 1800), billed.append
        )
    assert len(billed) == 3


def test_a_looping_tile_fails_the_image_naming_the_tile():
    loop = "SPACES Internet-UI " + "Internet-UI " * 700
    chat, billed = FakeChat(answer=loop), []
    with pytest.raises(LoaderError, match=rf"{REASON} \(tile 1 of 4\)"):
        ImageLoader(VisionReader(chat, "fake-llm")).load_billed(_png(2880, 1800), billed.append)
    assert len(billed) == 8  # two attempts on each of four tiles


def test_upload_records_the_tiles_and_the_estimate_and_view_use_them(client, repo, run_queue):
    nb = client.post("/api/ingest/notebooks", json={"title": "nb"}).json()["id"]
    r = client.post(
        f"/api/ingest/notebooks/{nb}/sources",
        # A 1-bit image: the test upload cap is small.
        files={"file": ("screen.png", _png(2880, 1800, mode="1"), "image/png")},
    )
    assert r.status_code == 202, r.text
    lib, source = r.json()["library_id"], r.json()["id"]
    from uuid import UUID

    assert repo.library[UUID(lib)].page_count == 4
    item = client.post("/api/ingest/sources/estimate", json={"library_ids": [lib]}).json()
    small = client.post(
        f"/api/ingest/notebooks/{nb}/sources",
        files={"file": ("small.png", _png(800, 600, mode="1"), "image/png")},
    ).json()
    single = client.post(
        "/api/ingest/sources/estimate", json={"library_ids": [small["library_id"]]}
    ).json()
    [tiled], [whole] = item["items"], single["items"]
    assert tiled["basis"] == "image, read in 4 tiles" and whole["basis"] == "image"
    # Four calls instead of one (the summary is the same once for both).
    assert float(tiled["charge_cents_max"]) > 3 * float(whole["charge_cents_max"])
    run_queue()
    view = client.get(f"/api/ingest/sources/{source}/chunks").json()
    assert view["tiles"] == 4
    assert client.get(f"/api/ingest/sources/{small['id']}/chunks").json()["tiles"] is None
