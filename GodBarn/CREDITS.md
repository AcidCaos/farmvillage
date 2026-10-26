# Credits and provenance

God Barn is an unofficial local companion for the FarmVillage preservation project.

- FarmVille artwork, sound/visual identities, and archived font resources originated with Zynga and their respective creators. These copied assets are used locally for the user's preservation workflow. This project makes no claim that the game assets are freely licensed or that God Barn is endorsed by Zynga.
- FarmVillage preservation project: https://github.com/AcidCaos/farmvillage
- Item metadata, growth rules and XP thresholds were recovered read-only from a local FarmVillage preservation archive. Separately prepared `data/provenance.json` records resource sources and hashes. The historical practice-save workflow is not shipped in this clean-start source handoff; no previous player state is included.
- The companion code was written separately for this task. Standalone mode uses its own copied workspace and does not import game modules. The optional native integration adds a God Barn tab and connects through the existing game's save transactions.

Historical inspiration includes the Unwither Ring, Storage Cellar, Gift Box, FarmVille farmhands/autoplayers, and original market/vehicle/XP imagery. Standalone controls apply to isolated copied saves; the optional native tab clearly labels its connection to the selected local farm and snapshots each change.

## Source licence

The owner selected GPL-3.0 for the original God Barn companion code on 25 October 2026, matching FarmVillage. See [LICENSE](LICENSE). Original game resources and third-party material retain their separate rights and notices.
