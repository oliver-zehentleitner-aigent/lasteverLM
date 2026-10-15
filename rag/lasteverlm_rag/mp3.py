"""The duration of an MP3 stream, from its frame headers, without decoding.

Every MPEG audio frame starts with a 4-byte header that gives its version,
layer, bitrate, sample rate and padding; from those follow its length in
bytes and the number of samples it holds. Walking the frames and adding up
their samples gives the duration exactly, whatever speed the speech was
generated at. An ID3v2 tag at the start is skipped.

Frames are counted as a player plays them when segments are joined: each
segment's encoder delay and its Xing/LAME header frame are real (silent)
frames of the joined file, so they count here, where a tool reading one
file on its own (mutagen) leaves them out (about 0.1 s per segment).
"""

from __future__ import annotations

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


def _skip_id3(data: bytes) -> int:
    if data[:3] != b"ID3" or len(data) < 10:
        return 0
    size = (data[6] << 21) | (data[7] << 14) | (data[8] << 7) | data[9]
    return 10 + size + (10 if data[5] & 0x10 else 0)


def duration(data: bytes) -> float:
    """Seconds of audio in ``data``; raises ``NotMp3`` on a broken frame."""
    pos, seconds = _skip_id3(data), 0.0
    while pos + 4 <= len(data):
        b1, b2 = data[pos + 1], data[pos + 2]
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
        seconds += samples / rate
        pos += length
    return seconds
