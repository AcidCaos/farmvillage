# God Barn wordmark

Record of the two wordmark images the companion page shows, so the runtime derivative can be
checked against the canonical image it came from. `GodBarn/tests/test_brand_wordmark.py` reads
this file.

The images are private inputs. They are listed with their sizes and hashes in
`PrivateInputs.expected.json`, imported by `tools/private-inputs.py`, and are not stored in Git.
The hashes below are the same ones the importer verifies.

| File (under `GodBarn/`) | Role | Pixels | Bytes | SHA-256 |
| --- | --- | --- | --- | --- |
| `static/brand/god-barn-logo-v2.png` | Canonical wordmark. Never edited. | 2065 x 761 | 1,120,734 | `3250d08acd1c1c5fd6d5d6ff40a6c9abf3e2762666a8066a97d0a42b1275c7ec` |
| `static/brand/god-barn-logo-v2@3x.png` | Runtime derivative the page loads. RGBA, keeps its alpha channel. | 438 x 161 | 87,512 | `2457a92a6b39eafef44bf31efe229d4484c3fb49de17a7d810461b0754dbc2ce` |

## Making the derivative

From the `GodBarn/` directory, on macOS:

```sh
sips -Z 438 static/brand/god-barn-logo-v2.png --out static/brand/god-barn-logo-v2@3x.png
```

`-Z 438` fits the image within 438 pixels and keeps its aspect ratio, which gives 438 x 161.
The page must reference the derivative and keep `height:auto`, so the wordmark is never
stretched or cropped. If either image changes, update `PrivateInputs.expected.json` through the
reviewed input process and update the hashes here in the same change.

## What this does not record

The authorship and licence of the wordmark are not recorded in this repository. See
`GodBarn/CREDITS.md` for the project's general attribution.
