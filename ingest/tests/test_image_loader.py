import httpx
import pytest
from fastapi.testclient import TestClient
from lasteverlm_core import DEMO_USER_ID, MemoryRateLimitStore, ProviderError
from openai import APIConnectionError, BadRequestError

from lasteverlm_ingest.loaders import LoaderError, default_registry
from lasteverlm_ingest.loaders.image import ImageLoader, VisionReader, sniff_image_type
from lasteverlm_ingest.main import create_app
from lasteverlm_ingest.worker import process_source
from tests.conftest import DEMO_TOKEN, make_settings
from tests.fakes import FakeChat
from tests.test_worker import USER, deps

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
REQUEST = httpx.Request("POST", "https://inference.test/v1/chat/completions")


@pytest.mark.parametrize(
    ("data", "media_type"),
    [
        (PNG, "image/png"),
        (b"\xff\xd8\xff\xe0rest", "image/jpeg"),
        (b"GIF89a....", "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"%PDF-1.4", None),
        (b"", None),
    ],
)
def test_sniff_image_type(data, media_type):
    assert sniff_image_type(data) == media_type


def _loader(fake, model="fake-llm", **kwargs) -> ImageLoader:
    return ImageLoader(VisionReader(fake, model, **kwargs))


def test_image_becomes_one_passage_and_its_usage():
    fake, billed = FakeChat(), []
    passages = _loader(fake, max_tokens=99).load_billed(PNG, billed.append)
    assert [p.text for p in passages] == ["Umsatz 4,2 Mio\n\nA bar chart."]
    [usage] = billed
    assert (usage.kind, usage.model, usage.tokens_in, usage.tokens_out) == (
        "llm",
        "fake-llm",
        202,
        40,
    )
    [call] = fake.calls
    assert call["model"] == "fake-llm" and call["max_tokens"] == 99
    image = call["messages"][1]["content"][0]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")


def test_image_failures_are_classified():
    billed: list = []
    with pytest.raises(LoaderError, match="not a PNG"):
        _loader(FakeChat()).load_billed(b"plain text", billed.append)
    refused = BadRequestError("bad image", response=httpx.Response(400, request=REQUEST), body=None)
    with pytest.raises(LoaderError, match="could not read the image"):
        _loader(FakeChat(error=refused)).load_billed(PNG, billed.append)
    with pytest.raises(ProviderError):
        _loader(FakeChat(error=APIConnectionError(request=REQUEST))).load_billed(PNG, billed.append)
    assert billed == []
    # An empty answer is the model's answer: billed, then failed for good.
    with pytest.raises(LoaderError, match="no readable content"):
        _loader(FakeChat(answer=" ")).load_billed(PNG, billed.append)
    assert [(u.tokens_in, u.tokens_out) for u in billed] == [(202, 40)]


def _image_deps(repo, storage, embedder, fake):
    d = deps(repo, storage, embedder)
    loaders = default_registry(vision=VisionReader(fake, "fake-llm"))
    return d.__class__(**{**d.__dict__, "loaders": loaders})


def _add_image(repo, storage):

    nb = repo.create_notebook(USER, "nb")
    sid = repo.add_source(nb.id, "chart.png", "image", "img").library_id
    storage.put("img", PNG, "image/png")
    return sid


def test_worker_bills_the_image_call_then_embeds_and_summarizes():
    from tests.fakes import FakeEmbedder, InMemoryRepository, InMemoryStorage

    repo, storage, embedder, fake = (
        InMemoryRepository(),
        InMemoryStorage(),
        FakeEmbedder(8),
        FakeChat(),
    )
    sid = _add_image(repo, storage)
    process_source(sid, _image_deps(repo, storage, embedder, fake))
    assert repo.library[sid].status == "ready"
    assert [(u.kind, u.model, u.tokens_in) for u in repo.usage][0] == ("llm", "fake-llm", 202)
    assert [u.kind for u in repo.usage] == ["llm", "embedding", "llm"]
    # The image call, the embeddings and the summary are one action.
    assert {(u.action, u.action_id) for u in repo.usage} == {("source:image", sid)}


def test_no_credit_means_no_image_call():
    from tests.fakes import FakeEmbedder, InMemoryRepository, InMemoryStorage

    repo, storage, fake = InMemoryRepository(), InMemoryStorage(), FakeChat()
    repo.default_balance = 0
    sid = _add_image(repo, storage)
    process_source(sid, _image_deps(repo, storage, FakeEmbedder(8), fake))
    source = repo.library[sid]
    assert source.status == "processing" and source.error is None
    assert fake.calls == [] and repo.usage == []


def test_image_upload(repo, storage, embedder, summarizer):
    app = create_app(
        make_settings(),
        rate_limit_store=MemoryRateLimitStore(),
        repository=repo,
        storage=storage,
        embedder=embedder,
        summarizer=summarizer,
        loaders=default_registry(vision=VisionReader(FakeChat(), "fake-llm")),
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {DEMO_TOKEN}"
        nb = client.post("/api/ingest/notebooks", json={"title": "img"}).json()["id"]
        url = f"/api/ingest/notebooks/{nb}/sources"
        r = client.post(url, files={"file": ("Chart 1.PNG", PNG, "application/octet-stream")})
        assert r.status_code == 202 and r.json()["kind"] == "image"
        key = f"{DEMO_USER_ID}/{r.json()['library_id']}/Chart_1.PNG"
        assert storage.objects[key] == PNG and storage.types[key] == "image/png"
        r = client.post(url, files={"file": ("fake.png", b"<svg/>", "image/png")})
        assert r.status_code == 415


def test_blank_image_fails_at_once_and_its_call_is_billed():
    from tests.fakes import FakeEmbedder, InMemoryRepository, InMemoryStorage

    repo, storage, fake = InMemoryRepository(), InMemoryStorage(), FakeChat(answer="")
    sid = _add_image(repo, storage)
    process_source(sid, _image_deps(repo, storage, FakeEmbedder(8), fake))
    source = repo.library[sid]
    assert source.status == "failed" and source.error == "the image holds no readable content"
    assert len(fake.calls) == 1
    assert [(u.kind, u.model, u.tokens_in, u.tokens_out) for u in repo.usage] == [
        ("llm", "fake-llm", 202, 40)
    ]


def test_each_answered_call_and_embedding_batch_refreshes_the_claim():
    """A long job (a vision PDF) must not look stale while it makes progress."""
    from tests.fakes import FakeEmbedder, InMemoryRepository, InMemoryStorage

    repo, storage = InMemoryRepository(), InMemoryStorage()
    sid = _add_image(repo, storage)
    process_source(sid, _image_deps(repo, storage, FakeEmbedder(8), FakeChat()))
    assert repo.library[sid].status == "ready"
    assert repo.refreshed == [sid, sid]  # the image call, one embedding batch


def test_without_an_exchange_rate_the_image_is_not_read():
    from lasteverlm_core import PricingRules

    from tests.fakes import FakeEmbedder, InMemoryRepository, InMemoryStorage

    repo, storage, fake = InMemoryRepository(), InMemoryStorage(), FakeChat()
    repo.rules = PricingRules()
    sid = _add_image(repo, storage)
    process_source(sid, _image_deps(repo, storage, FakeEmbedder(8), fake))
    assert repo.library[sid].status == "processing"  # waits for the rate
    assert fake.calls == [] and repo.usage == []
