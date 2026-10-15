"""MP3 streams from their frame headers, without decoding: duration, and
joining segments into one file with a correct Xing header.

Every MPEG audio frame starts with a 4-byte header that gives its version,
layer, bitrate, sample rate and padding; from those follow its length in
bytes and the number of samples it holds. Walking the frames and adding up
their samples gives the duration exactly, whatever speed the speech was
generated at. An ID3v2 tag at the start is skipped.

A segment from the provider is VBR with a Xing header frame (frame count,
byte count, a seek table, a LAME tag). Concatenated as they are, the file
starts with the first segment's header, so a browser takes the first
segment's length for the whole file and cannot seek past it; the later
headers play as silent frames. ``join`` keeps one header, for the whole
stream, and drops the others. ``duration`` counts the frames a player
plays: a header frame at the start is metadata and is left out.
"""

from __future__ import annotations

from dataclasses import dataclass

# bitrates in kbit/s by (MPEG-1?, layer) and index 1..14
_BITRATES = {
    (True, 3): [32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    (True, 2): [32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384],
    (True, 1): [32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448],
    (False, 3): [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
    (False, 2): [8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],
    (False, 1): [32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256],
}
# sample rates by version bits (3: MPEG-1, 2: MPEG-2, 0: MPEG-2.5) and index 0..2
_SAMPLE_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


class NotMp3(ValueError):
    """The bytes hold no MPEG audio frame where one is expected."""


@dataclass(frozen=True)
class Frame:
    start: int
    length: int
    samples: int
    rate: int
    mpeg1: bool
    mono: bool

    def seconds(self) -> float:
        return self.samples / self.rate


def frames(data: bytes) -> list[Frame]:
    """Every frame of ``data`` in order; raises ``NotMp3`` on a broken one."""
    found = []
    pos = _skip_id3(data)
    while pos + 4 <= len(data):
        b1, b2, b3 = data[pos + 1], data[pos + 2], data[pos + 3]
        if data[pos] != 0xFF or b1 & 0xE0 != 0xE0:
            if data[pos : pos + 3] == b"TAG":  # an ID3v1 tag at the end
                break
            raise NotMp3(f"no frame header at byte {pos}")
        version, layer_bits = (b1 >> 3) & 3, (b1 >> 1) & 3
        bitrate_index, rate_index = b2 >> 4, (b2 >> 2) & 3
        if version == 1 or layer_bits == 0 or bitrate_index in (0, 15) or rate_index == 3:
            raise NotMp3(f"unsupported frame header at byte {pos}")
        mpeg1, layer = version == 3, 4 - layer_bits
        bitrate = _BITRATES[(mpeg1, layer)][bitrate_index - 1] * 1000
        rate = _SAMPLE_RATES[version][rate_index]
        padding = (b2 >> 1) & 1
        if layer == 1:
            samples, length = 384, (12 * bitrate // rate + padding) * 4
        else:
            samples = 1152 if (mpeg1 or layer == 2) else 576
            length = samples // 8 * bitrate // rate + padding
        if length < 4 or pos + length > len(data):
            raise NotMp3(f"a frame at byte {pos} runs past the end")
        found.append(Frame(pos, length, samples, rate, mpeg1, (b3 >> 6) == 3))
        pos += length
    return found


def _xing_offset(frame: Frame) -> int:
    """Where a Layer III frame's Xing tag would start: after the 4-byte
    header and the side information."""
    if frame.mpeg1:
        return 4 + (17 if frame.mono else 32)
    return 4 + (9 if frame.mono else 17)


def is_header(data: bytes, frame: Frame) -> bool:
    """A Xing/Info frame: metadata, no audio."""
    at = frame.start + _xing_offset(frame)
    return data[at : at + 4] in (b"Xing", b"Info")


def _skip_id3(data: bytes) -> int:
    if data[:3] != b"ID3" or len(data) < 10:
        return 0
    size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
    return 10 + size + (10 if data[5] & 0x10 else 0)


def duration(data: bytes) -> float:
    """Seconds of audio in ``data``: every frame but a header frame at the
    start; raises ``NotMp3`` on a broken frame."""
    found = frames(data)
    if found and is_header(data, found[0]):
        found = found[1:]
    return sum(f.seconds() for f in found)


def join(segments: list[bytes]) -> bytes:
    """One stream from MP3 segments: the first segment's header frame, if
    it has one, rewritten for the whole stream (frames, bytes, a new seek
    table, the LAME tag's length, end padding and checksums), then every
    audio frame. The other segments' header frames are dropped. Segments
    without a header are concatenated as they are."""
    parsed = [(segment, frames(segment)) for segment in segments]
    header: tuple[bytes, Frame] | None = None
    audio: list[bytes] = []
    timeline: list[Frame] = []
    last_tag: bytes | None = None
    for segment, found in parsed:
        if found and is_header(segment, found[0]):
            if header is None:
                header = (segment, found[0])
            last_tag = segment[found[0].start : found[0].start + found[0].length]
            found = found[1:]
        for frame in found:
            audio.append(segment[frame.start : frame.start + frame.length])
            timeline.append(frame)
    body = b"".join(audio)
    if header is None:
        return body
    segment, frame = header
    first = bytearray(segment[frame.start : frame.start + frame.length])
    _rewrite_xing(first, frame, timeline, body, last_tag)
    return bytes(first) + body


def _rewrite_xing(
    first: bytearray,
    frame: Frame,
    timeline: list[Frame],
    body: bytes,
    last_tag: bytes | None,
) -> None:
    total = len(first) + len(body)
    at = _xing_offset(frame)
    flags = int.from_bytes(first[at + 4 : at + 8], "big")
    pos = at + 8
    if flags & 1:
        first[pos : pos + 4] = len(timeline).to_bytes(4, "big")
        pos += 4
    if flags & 2:
        first[pos : pos + 4] = total.to_bytes(4, "big")
        pos += 4
    if flags & 4:
        first[pos : pos + 100] = _toc(timeline, len(first), total)
        pos += 100
    if flags & 8:
        pos += 4
    lame = pos
    if first[lame : lame + 4] != b"LAME" and first[lame : lame + 4] != b"Lavf":
        return
    # the LAME tag: end padding from the last segment, the music length, its CRC
    if last_tag is not None and len(last_tag) >= lame + 24:
        first[lame + 21 : lame + 24] = _padding_bytes(
            bytes(first[lame + 21 : lame + 24]), last_tag[lame + 21 : lame + 24]
        )
    if len(first) >= lame + 36:
        first[lame + 28 : lame + 32] = total.to_bytes(4, "big")
        first[lame + 32 : lame + 34] = _crc16(body).to_bytes(2, "big")
        first[lame + 34 : lame + 36] = _crc16(bytes(first[: lame + 34])).to_bytes(2, "big")


def _padding_bytes(first: bytes, last: bytes) -> bytes:
    """12 bits of encoder delay (the first segment's), 12 of end padding (the last's)."""
    delay = (first[0] << 4) | (first[1] >> 4)
    padding = ((last[1] & 0x0F) << 8) | last[2]
    return bytes([delay >> 4, ((delay & 0x0F) << 4) | (padding >> 8), padding & 0xFF])


def _toc(timeline: list[Frame], header_length: int, total: int) -> bytes:
    """The seek table: for each percent of the duration, the byte position
    in the file as a fraction of its size, times 256."""
    seconds = sum(f.seconds() for f in timeline) or 1.0
    table, elapsed, offset, i = [], 0.0, header_length, 0
    for percent in range(100):
        target = seconds * percent / 100
        while i < len(timeline) and elapsed + timeline[i].seconds() <= target:
            elapsed += timeline[i].seconds()
            offset += timeline[i].length
            i += 1
        table.append(min(255, offset * 256 // total))
    return bytes(table)


def _crc16(data: bytes) -> int:
    """CRC-16 (polynomial 0x8005, reflected), as the LAME tag stores it."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def repair(data: bytes) -> tuple[bytes, list[tuple[float, float]]] | None:
    """A stored audio joined before ``join`` existed: split at every header
    frame and join again. Returns the new bytes and, for each header frame
    that went, its start (in the old file, as the old ``duration`` counted
    it, every header frame included) and its length in seconds; or ``None``
    when the file is
    already right (at most one header, at the start, declaring every frame
    and byte). Raises ``NotMp3`` on a broken frame."""
    found = frames(data)
    headers = [i for i, f in enumerate(found) if is_header(data, f)]
    if not headers:
        return None
    if headers == [0]:
        at = found[0].start + _xing_offset(found[0])
        flags = int.from_bytes(data[at + 4 : at + 8], "big")
        declared = int.from_bytes(data[at + 8 : at + 12], "big") if flags & 1 else None
        if declared in (None, len(found) - 1):
            return None
    starts, elapsed = [], 0.0
    for frame in found:
        starts.append(elapsed)
        elapsed += frame.seconds()
    cuts = sorted({0, *headers})
    segments = [
        data[
            found[a].start : (
                found[b].start if b < len(found) else found[-1].start + found[-1].length
            )
        ]
        for a, b in zip(cuts, [*cuts[1:], len(found)], strict=True)
    ]
    return join(segments), [(starts[i], found[i].seconds()) for i in headers]


def shifted(time: float, removed: list[tuple[float, float]]) -> float:
    """A transcript time of the old file in the repaired one: every removed
    header frame that started before it moves it back by its length."""
    # a header frame starting where a turn starts belongs to that turn (times
    # are rounded to milliseconds, frame starts are sums of floats)
    gone = sum(length for start, length in removed if start < time - 0.0005)
    return round(max(0.0, time - gone), 3)
