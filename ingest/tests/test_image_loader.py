from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from lasteverlm_core import MemoryRateLimitStore, ProviderError
from openai import APIConnectionError, BadRequestError

from lasteverlm_ingest.loaders import BilledLoaderError, LoaderError, default_registry
from lasteverlm_ingest.loaders.image import ImageLoader, sniff_image_type
from lasteverlm_ingest.main import create_app
from lasteverlm_ingest.worker import process_source
from tests.conftest import DEMO_TOKEN, make_settings
from tests.test_worker import USER, deps

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
REQUEST = httpx.Request("POST", "https://inference.test/v1/chat/completions")


class FakeChat:
    def __init__(self, answer: str = "Umsatz 4,2 Mio\n\nA bar chart.", error=None) -> None:
        self.answer, self.error = answer, error
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=self.answer), finish_reason="stop")
            ],
            usage=SimpleNamespace(prompt_tokens=202, completion_tokens=40),
        )


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


def test_image_becomes_one_passage_and_its_usage():
    fake = FakeChat()
    passages, usage = ImageLoader(fake, "fake-llm", max_tokens=99).load_with_usage(PNG)
    assert [p.text for p in passages] == ["Umsatz 4,2 Mio\n\nA bar chart."]
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
    with pytest.raises(LoaderError, match="not a PNG"):
        ImageLoader(FakeChat(), "m").load_with_usage(b"plain text")
    refused = BadRequestError("bad image", response=httpx.Response(400, request=REQUEST), body=None)
    with pytest.raises(LoaderError, match="could not read the image"):
        ImageLoader(FakeChat(error=refused), "m").load_with_usage(PNG)
    with pytest.raises(ProviderError):
        ImageLoader(FakeChat(error=APIConnectionError(request=REQUEST)), "m").load_with_usage(PNG)
    with pytest.raises(BilledLoaderError, match="no readable content") as caught:
        ImageLoader(FakeChat(answer=" "), "m").load_with_usage(PNG)
    assert (caught.value.usage.tokens_in, caught.value.usage.tokens_out) == (202, 40)


def _image_deps(repo, storage, embedder, fake):
    d = deps(repo, storage, embedder)
    loaders = default_registry(image=ImageLoader(fake, "fake-llm"))
    return d.__class__(**{**d.__dict__, "loaders": loaders})


def _add_image(repo, storage):
    from uuid import uuid4

    nb = repo.create_notebook(USER, "nb")
    sid = uuid4()
    repo.create_source(nb.id, sid, "chart.png", "image", "img")
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
    assert repo.get_source(sid).status == "ready"
    assert [(u.kind, u.model, u.tokens_in) for u in repo.usage][0] == ("llm", "fake-llm", 202)
    assert [u.kind for u in repo.usage] == ["llm", "embedding", "llm"]


def test_no_credit_means_no_image_call():
    from tests.fakes import FakeEmbedder, InMemoryRepository, InMemoryStorage

    repo, storage, fake = InMemoryRepository(), InMemoryStorage(), FakeChat()
    repo.default_balance = 0
    sid = _add_image(repo, storage)
    process_source(sid, _image_deps(repo, storage, FakeEmbedder(8), fake))
    source = repo.get_source(sid)
    assert source.status == "failed" and source.error == "credit exhausted"
    assert fake.calls == [] and repo.usage == []


def test_image_upload(repo, storage, embedder, summarizer):
    app = create_app(
        make_settings(),
        rate_limit_store=MemoryRateLimitStore(),
        repository=repo,
        storage=storage,
        embedder=embedder,
        summarizer=summarizer,
        loaders=default_registry(image=ImageLoader(FakeChat(), "fake-llm")),
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {DEMO_TOKEN}"
        nb = client.post("/api/ingest/notebooks", json={"title": "img"}).json()["id"]
        url = f"/api/ingest/notebooks/{nb}/sources"
        r = client.post(url, files={"file": ("Chart 1.PNG", PNG, "application/octet-stream")})
        assert r.status_code == 202 and r.json()["kind"] == "image"
        assert storage.objects[f"{nb}/{r.json()['id']}/Chart_1.PNG"] == PNG
        assert storage.types[f"{nb}/{r.json()['id']}/Chart_1.PNG"] == "image/png"
        r = client.post(url, files={"file": ("fake.png", b"<svg/>", "image/png")})
        assert r.status_code == 415


def test_blank_image_fails_at_once_and_its_call_is_billed():
    from tests.fakes import FakeEmbedder, InMemoryRepository, InMemoryStorage

    repo, storage, fake = InMemoryRepository(), InMemoryStorage(), FakeChat(answer="")
    sid = _add_image(repo, storage)
    process_source(sid, _image_deps(repo, storage, FakeEmbedder(8), fake))
    source = repo.get_source(sid)
    assert source.status == "failed" and source.error == "the image holds no readable content"
    assert len(fake.calls) == 1
    assert [(u.kind, u.model, u.tokens_in, u.tokens_out) for u in repo.usage] == [
        ("llm", "fake-llm", 202, 40)
    ]
