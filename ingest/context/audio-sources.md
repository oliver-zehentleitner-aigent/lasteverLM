# Audio sources

## A recording is transcribed whole, into one passage without positions

**Id:** c0aa7899-b54a-4daf-b231-666f676eaeac
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** the maintainer's go for audio sources through the coordinating agent, 2026-10-14; the platform catalog's limits for the transcription model (MP3 and WAV only, 26214400 bytes, 4 hours)
**Revisit when:** the platform's transcription model returns timestamps or segments, or accepts more formats

An MP3 or WAV upload is sent to the platform's transcription model in
one call; the transcript becomes one passage without a page number and
is chunked like a text file. The platform answers with plain text and
no timestamps, so there is nothing to cite inside a recording beyond
the passage itself: a citation names the recording and quotes the
chunk. Only MP3 and WAV are accepted, because those are the only formats
the model takes; other audio is refused at upload by name ("audio must
be MP3 or WAV"), not converted. The model's limits (25 MiB, four hours)
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
  in the worker, for formats nobody has asked for yet.
