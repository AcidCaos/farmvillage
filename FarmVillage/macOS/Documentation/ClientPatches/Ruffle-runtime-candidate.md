> **Historical engineering reference; current direction supersedes earlier instructions.** The continuing release targets native macOS and browser/Ubuntu, with sixteen worlds. iPad/iOS is abandoned; Enchanted Glen and Holiday Lights have no active unlock, travel or supported-play offers. This is a clean-start release with no previous farms, authentication or history shipped. Historical results, candidate proposals, hashes and test counts below describe their recorded revision and are not new acceptance. Use [current acceptance](../../../../ACCEPTANCE.md), [current world scope](../../../../WORLD_READINESS.md) and [the continuation backlog](<../../../../Wave 3.md>) before implementation. Original resources and raw QA evidence remain external/private; a path mentioned below is not a claim that its file is included.

# Ruffle runtime candidate review

Native acceptance is pending. This document records a verified copied runtime
candidate; it does not select or install that candidate in the product.

The existing official stable runtime is `0.7.1`, built
`2026-10-07T18:57:54.930Z` at commit
`89a7049965f3090e706265670df309a5128233ac`. Its official archive SHA-256 is
`ef12edbee135d581a9cd523837d746da30a07a64dbf1cf472d2e472c656f4b5e`.
All twelve local runtime file hashes were independently revalidated against its
existing extraction manifest, and GitHub's published archive digest matches.

The copied official nightly candidate is `0.8.0-nightly.2026.10.21`, built
`2026-10-21T00:14:58.945Z` at commit
`f725a6e7b5a40c2b16cac34191a3b688db7c8826`. Its archive SHA-256 is
`dcb2562f74b83afcfd479b9b04e64dd9c016750605b15101f08ff865f66be56a`.
The downloaded archive matches GitHub's published digest, and all eight extracted
files match the archive members byte for byte. Exact URLs, file hashes, build
metadata and the stable comparison are in
`ruffle-nightly-candidate-provenance.json`.

The 91-commit comparison contains a concrete allocation repair:
[ba92d5af, defer shape tessellation until first draw](https://github.com/ruffle-rs/ruffle/commit/ba92d5af0a9981b322b67c68ef58f59342f843fe).
The stable implementation constructed an eager mesh when every shape was defined,
then built a separate cached mesh for a shape actually drawn. The change removes
the unused eager mesh and postpones fill bitmap decoding and upload until draw.
This directly avoids duplicate or unused shape allocations. A successful native
comparison would establish the tested runtime combination's behavior; it would
not isolate this one commit from the other changes in the upgrade.

The nearby SwfMovie Arc-to-Gc commits explicitly describe preparation toward a
future movie lifetime repair. Stable weak-key library entries retain their movie
through the library value; the nightly representation still uses a traced movie
library map. These refactors alone do not establish that unloaded libraries are
reclaimed, and are not claimed as the demonstrated freeze repair.

The first nightly control uses the six-method copied client and all-record packed
catalog. A simpler production A4 client with the ordinary complete derived catalog
must be tested separately before deciding whether any packing change is needed.
Strict native evidence must include sustained idle, original Market categories,
an inspected purchase and placement, a real crop harvest, persisted rewards and
reload, with no fatal renderer or missing-asset errors. Hidden WKWebView snapshots
are qualified as rendered background evidence, not foreground visibility.

The supported legacy WebGL renderer was rejected because the actual client needs
BitmapData.draw. The original animation-memory variant 4 was also rejected: its
controlled run reached the 4 GiB limit at 232.4 seconds in a wgpu GLES command
allocation. These experiments do not justify changing the product renderer or
animation experiment flags.
