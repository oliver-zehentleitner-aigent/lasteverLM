# Audio sources

## A recording is transcribed whole, into one passage without positions

**Id:** c0aa7899-b54a-4daf-b231-666f676eaeac
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-14; the platform catalog's limits for the transcription model (MP3 and WAV only, 26214400 bytes, 4 hours)
**Revisit when:** the platform's transcription model returns timestamps or segments, or accepts more formats

An MP3 or WAV upload is sent to the platform's transcription model in
one call; the transcript becomes one passage without a page number and
is chunked like a text file. The platform answers with plain text and
no timestamps, so there is nothing to cite inside a recording beyond
the passage itself: a citation names the recording and quotes the
chunk. The model takes only MP3 and WAV; since the same day other audio
is converted to MP3 before it is transcribed (entry
0dbe2dcc-c149-4c5a-92f9-31509c436828), where it was first refused at
upload by name. The model's limits (25 MiB, four hours)
are core's `probe_audio`, and the API runs it at upload, separate from
`MAX_UPLOAD_BYTES`: a file the model would refuse never costs a stored
object and a queued job, and ingest keeps no second copy of the numbers.
A transcription can run for minutes, so it gets its own client with one
attempt and `STT_TIMEOUT_SECONDS` below the claim timeout: with the SDK's
retries, or a timeout above the claim's, another worker would take the
job over mid-call and the recording would be billed twice.

**Alternatives:**
- Splitting the audio client-side into fixed slices to fake page numbers
  ("minute 3"): the slices would be numbers ingest made up, not
  positions the platform reported; a cut through a word damages the
  transcript at every boundary, and each slice is a billed call of its
  own.
- Transcoding other formats (M4A, Ogg, WebM) to MP3 with ffmpeg: a large
  native dependency in the image and a decoder for user-supplied files
  in the worker, for formats nobody has asked for yet. (Asked for the
  same day: the refusal of other formats is replaced by conversion, entry
  0dbe2dcc-c149-4c5a-92f9-31509c436828; whole-file transcription stands.)

## Other audio formats are converted by a minimal ffmpeg, the MP3 kept beside the original

**Id:** 0dbe2dcc-c149-4c5a-92f9-31509c436828
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-14 (conversion, both files kept and offered); the build variant chosen the same day on the measured sizes below
**Revisit when:** the platform's transcription model accepts more formats, or a format users upload is not among the built demuxers and decoders

M4A/MP4 (a video's audio track too), AAC, Ogg (Vorbis, Opus), FLAC and
WebM are accepted and converted by the worker to mono 16 kHz MP3 at
32 kbit/s, which is all speech recognition needs. The MP3 is stored
beside the original and is what is transcribed, so the user can listen
to exactly what the model heard (`preview_url`) and still download the
upload (`original_url`, presigned as an attachment, because a
cross-origin link cannot ask for a download itself). Core's limits apply
to the MP3. The original is capped separately (60 MiB, below the ingress
body limit). A retry reuses the stored MP3.

A WAV over the model's 25 MiB is converted the same way instead of being
refused (maintainer decision, 2026-10-14); a WAV within the cap and every
MP3 pass through. Transcription is billed per second of audio, so the
format does not change what a recording costs; it only decides whether
it fits the cap, and a 44.1 kHz stereo WAV reaches 25 MiB after about
2.5 minutes, the converted MP3 after about two hours. The build gained
the WAV demuxer and its PCM decoders (+1.4 MB).

ffmpeg reads user-supplied bytes, so it is a subprocess (a crash takes
the conversion, not the worker), with the demuxer forced from the
sniffed magic bytes (no probing into playlist or concat formats that
open other files or URLs), only the `file` protocol, a private directory
under `/tmp` and a time limit. The image builds ffmpeg 7.1.5 from the
release tarball, checked against its sha256 (the signature was checked
against the FFmpeg release key when the version was pinned), with
`--disable-everything` plus only the demuxers, parsers and decoders of
these formats, the resampler and the MP3 encoder. Measured: Debian's
`ffmpeg` package took the image from 495 MB to 1122 MB (+627 MB, mostly
LLVM and Mesa pulled in through libavdevice); the minimal build makes it
499 MB (+5 MB). It is also the smaller parser surface for untrusted
uploads.

**Alternatives:**
- Refusing the other formats ("audio must be MP3 or WAV"), the state
  before: users had to convert recordings themselves.
- Converting in the browser (ffmpeg.wasm or WebAudio): a large download
  for every visitor, and the server would still have to trust and check
  what the browser sends.
- Debian's `ffmpeg` package: +627 MB and every codec Debian ships as
  parser surface, for one decoding path.
- A third-party static ffmpeg binary: about +80 MB, all codecs, and a
  build nobody here can reproduce or audit.
