from __future__ import annotations

import pytest

from lasteverlm_core import email_for, mask_email, masks_emails


@pytest.mark.parametrize(
    ("address", "masked"),
    [
        ("jane.doe@example.com", "j***e@example.com"),
        ("ab@example.com", "a*@example.com"),
        ("a@example.com", "*@example.com"),
        ("abc@example.com", "a***c@example.com"),
        ("averyverylonglocalpart@x.io", "a***t@x.io"),  # three stars whatever the length
        ("max+lasteverlm@example.com", "m***m@example.com"),  # plus-addressing is local part
        ("jürgen@exämple.de", "j***n@exämple.de"),  # unicode counted per character
        ("ö@example.com", "*@example.com"),
        ("名前@例え.jp", "名*@例え.jp"),
        ('"a@b"@example.com', '"***"@example.com'),  # the last @ splits
    ],
)
def test_mask_email(address: str, masked: str) -> None:
    assert mask_email(address) == masked


@pytest.mark.parametrize("bad", ["", "no-at-sign", "@example.com", "jane@", "@"])
def test_malformed_input_is_masked_whole(bad: str) -> None:
    assert mask_email(bad) == "***"


def test_only_viewers_see_masked_addresses() -> None:
    assert masks_emails("viewer") is True
    assert masks_emails("admin") is False and masks_emails("user") is False
    assert email_for("viewer", "jane@example.com") == "j***e@example.com"
    assert email_for("admin", "jane@example.com") == "jane@example.com"
