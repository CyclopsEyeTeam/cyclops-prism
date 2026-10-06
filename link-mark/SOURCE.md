# Mark sheets

A presence never draws another presence. Each sheet here is a presence's own small look, rendered by her own
terminal renderer and exported by her own tool (Cyclops Link V1 §12). The host places it at that presence's seat
and draws nothing of it herself. Sheets are display data only: never part of a Link record, never read from the Link
directory.

| File | Whose | Rendered by | Exported by |
| --- | --- | --- | --- |
| `spark.json` | Spark | Cyclops Spark `plugins/cyclops-spark/hooks/render-raster.js` | Cyclops Spark `tools/export-link-mark.mjs` |
| `keeper.json` | Keeper | Cyclops Keeper `plugins/cyclops-keeper/scripts/terminal_art.py` | Cyclops Keeper `tools/export-link-mark.py` |
| `prism.json` | Prism | Cyclops Prism `scripts/terminal.py` | Cyclops Prism `tools/export-link-mark.py` |

The host's own sheet is the original; the others are vendored copies, unchanged. To refresh one, re-run that
presence's exporter in her own repository and copy the file here as it is.

SHA-256:

    9708da383f7fc4638d5ac67af7d0632e65cdd7435fbcc35348f0452630940a24  keeper.json
    01ca03d0169c28c0cff40682fdc33ab2a34cf6cd783bb60ea510aceef2377196  prism.json
    e9e20e8deae71c269d61fbe133a0ebccc667537f714d22a0922e45b780d263b1  spark.json
