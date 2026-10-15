# URL sources

## The worker fetches URLs, through a guard that only connects to public addresses

**Id:** d13f741c-2133-447b-91a7-491fa15f202b
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-13
**Revisit when:** the cluster gets an egress policy that already blocks internal ranges for the worker, or URL sources need a proxy

A URL source is stored as the URL itself; the worker fetches it, not
the request handler. Every TCP connection, each redirect hop included,
goes through a network backend that resolves the host itself, refuses
it unless every resolved address is public, and connects to the address
it checked.

**Reason:** the worker runs inside the Kubernetes cluster, next to the
managed database, the other services and the cloud metadata endpoint
(169.254.169.254). Fetching an address a user typed is a server-side
request forgery path into all of them. Resolving and connecting in one
step closes DNS rebinding (a second, internal answer between check and
connect); checking every hop closes redirects to internal addresses.
Fetching in the worker keeps the API pods fast and lets fetch failures
use the existing retry classification.

**Alternatives:**
- Fetch in the request handler and store the page like an upload: a
  slow site holds an API request open, and a transient failure would
  need its own retry path.
- Rely on a Kubernetes NetworkPolicy for egress only: infra owns it,
  it is not in place, and a policy cannot tell the metadata endpoint
  from a public site without the same address list; worth adding as a
  second layer, not instead.
- Check the URL's host before fetching with a normal HTTP client: the
  client resolves again on connect, which is exactly the rebinding gap.

## Web page text comes from the standard library's HTML parser

**Id:** fbe8d9da-997c-4867-8c93-4e3d9e5f98f2
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** service author's implementation decision, 2026-10-13
**Revisit when:** users report pages whose text arrives with menus, cookie banners or comments mixed in, or pages that render their content with JavaScript

The HTML loader is a small `html.parser` subclass: it drops scripts,
styles and page chrome (nav, header, footer, aside, forms), keeps only
`<main>`/`<article>` when the page marks its content that way, and
leads with the page title.

**Reason:** no new dependency in an image that already carries the
fetch path of untrusted input, and behaviour that fits on one screen
and is fully tested. Pages that use semantic markup — most current
sites, Wikipedia included — come out clean; on the first live check the
German Wikipedia article on Vienna came out as article text without
navigation.

**Alternatives:**
- An article-extraction library (trafilatura or a readability port):
  better on old table layouts and comment sections, but several
  transitive packages (lxml, date and URL parsers) to keep patched for
  a gain the current pages do not need. The first candidate if the
  revisit condition fires.
- A headless browser for JavaScript-rendered pages: a browser in the
  worker image is the wrong weight for this step.

Re-checked 2026-10-15, after the revisit condition fired (the starter's
price page is a single-page app whose HTML holds no text): the decision
holds. Such a page now fails with a reason the user can act on ("no
readable text without JavaScript"), and the fix belongs to the page,
a server-rendered version of it, not to a browser in the worker.

## A changed web page becomes a new version; the old one stays for its citations

**Id:** 9b572655-c22f-47b1-8ba1-ecdffad01088
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-14 (refetch, versions, old version kept read-only); the hash and the inline comparison chosen by the ingest author
**Revisit when:** pages are refetched often enough that old versions pile up in storage, or users want to see or restore an older version

A web page can be fetched again. The worker compares the hash of the
extracted text (whitespace normalized) with the stored one before any
model call:

- **Unchanged:** only `fetched_at` moves, and nothing is charged.
- **Changed:** a new library row (`version + 1`) takes the dedupe key and
  every link and is read like a new source, charged as a web page. The
  old row keeps its chunks and stays reachable by id but out of every
  list, so the citations of outputs made from it still open their
  passages.

The new version is read by its own job, which fetches the page once
more. That costs nothing, and every failure of reading it lands on the
new row, not on the version that worked. Pages read before versions
existed have no hash; their first refetch counts as changed.

**Alternatives:**
- Overwriting the entry's chunks with the new text: every citation into
  the old text would point at chunks that no longer exist or now say
  something else.
- Re-embedding on every refetch without comparing: charges for a page
  that did not change.

## Each read web page keeps an inert snapshot of what was read

**Id:** 7415f6ff-549f-4580-aaad-092b42bae168
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-14 (snapshot as the cache, "Original" shows what was read); the allowlist chosen by the ingest author
**Revisit when:** users need the page's images or layout in the snapshot, or the viewer shows snapshots outside a sandbox

Every read of a web page version stores the fetched HTML beside the
source, so the viewer's "Original" shows exactly the page the chunks
came from. The snapshot is rebuilt from an allowlist of text and
structure tags rather than cleaned with a blocklist: what is not known
to be harmless is dropped, including images and every other resource
that would load from elsewhere, so the file renders inert and tells no
third party it was opened. An unchanged refetch keeps the snapshot of
its version; a version read before snapshots existed gets one then (the
same text, so still what was read).

**Alternatives:**
- Linking the live page: it may have changed since it was read, or be
  gone, and opening it reveals the reader to the site.
- Storing the HTML as fetched and relying on the viewer's iframe sandbox
  alone: one missing sandbox flag, or a direct open of the presigned
  URL, would run the page's scripts.
- Keeping images: a faithful page, but every image is a request to the
  site, or the snapshot would have to fetch and store them, at a cost
  for every read.


## Structured data behind a URL is read as lines that name their context

**Id:** c5d9c848-f07c-40e6-bc2e-f4b6ea07a22d
**Type:** decision
**Status:** active
**Evidence:** confirmed
**Source:** maintainer decision, 2026-10-15 (a URL that returns structured data must be readable: the formats, the citation rule, the limits and the hostile-input cases); the line-per-value rendering and the limit values are the ingest author's
**Revisit when:** users ask about datasets larger than 10,000 values, or core's chunker learns to cut at record boundaries

JSON, NDJSON, YAML, XML (RSS and Atom included), CSV and TSV are read.
Every value becomes one line that names its context: JSON, NDJSON and
YAML by the key path (`languages.Python: 12345`), XML by the element
path (`rss/channel/item[2]/title: …`), CSV and TSV by the column, with
the header repeated on every row (`row 3: city: Graz; price: 12`). One
object, element or row is one passage. The snapshot shows the same
rendering. A `text/plain` body that parses cleanly as a JSON object or
array is read as JSON.

**Reason:** the chunker windows text over passages, so it can cut a
document anywhere. A line that carries its own path or column keeps its
meaning in any chunk, and a number is never cited without saying what it
measures. The request named pretty-printed JSON and YAML; indented text
was not chosen because a chunk that starts inside a nested object would
hold values without the keys above them, which the same request ruled
out ("the key path kept in each chunk"). The line form was accepted in review
on 2026-10-15.

Parsing is bounded beyond the body cap: 32 levels of nesting, 10,000
values (XML: elements), 500 CSV columns and 100,000 characters per CSV
field. Exceeding a limit fails the source with that reason. XML goes
through defusedxml, which refuses entity declarations and external
references, so neither a billion-laughs document nor an external
entity is expanded or fetched. YAML is read with `safe_load` only, and
an alias counts every time it is used, so an alias bomb hits the value
cap.

**Alternatives:**
- Refusing structured data, the previous behaviour: an API answer such
  as a repository's language statistics failed with "unsupported content
  type", although it is exactly the kind of fact a user wants cited.
- Pretty-printed JSON or YAML as the text: readable as a whole, but a
  chunk cut inside a nested object loses the path of its values.
- A CSV table with its header once at the top: every chunk after the
  first would hold numbers without their columns.
- The standard library's XML parser alone: the bundled expat limits
  entity amplification, but defusedxml refuses entity declarations and
  external references outright, whatever the expat build allows.
