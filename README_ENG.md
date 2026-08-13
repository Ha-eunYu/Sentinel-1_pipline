# Sentinel-1 SLC Search & Download Pipeline

A pipeline that searches the Copernicus Data Space Ecosystem (CDSE) STAC API for the Sentinel-1
SLC scene closest to a given area of interest (AOI) and target time, then downloads the SAFE
(zip) product via the OData (zipper) API. It is currently configured for **monitoring the July
2026 Korea flood**, targeting the Sentinel-1A/C/D satellites.

(한국어 버전: [README_KR.md](README_KR.md) — the Korean README is the complete one:
RTC preprocessing, per-orbit Otsu water detection, drought comparison, data inventory,
and known issues. This English README covers the search/download stage plus the
repository layout.)

## TL;DR: steps after cloning

```bash
git clone <repo-url>
cd Sentinel-1_pipline

conda env create -f env/environment.yml
conda activate s1_pipeline

cp .env.example .env
# Open .env and fill in CDSE_USERNAME / CDSE_PASSWORD

python -m s1.tools.download.main_s1_list
```

Yes — after cloning, **running `s1.tools.download.main_s1_list` alone** does the search (manifest saved) and the
download in one go. Please still read "Before you run it" and "Caveats" below first, especially
the disk-space note.

## Requirements

- conda (miniconda/anaconda)
- A CDSE (Copernicus Data Space Ecosystem) account — sign up for free at
  <https://dataspace.copernicus.eu>
  - `s1.tools.download.main_s1_list` authenticates with `CDSE_USERNAME`/`CDSE_PASSWORD` (username/password),
    not an OAuth client id/secret.
- Free disk space (see "Caveats" below — each SLC product is roughly 5-8 GB).

## Setup

```bash
conda env create -f env/environment.yml   # env name: s1_pipeline
conda activate s1_pipeline
```

`.env` is not committed to git (see `.gitignore`). Copy `.env.example` and fill in your own
credentials.

```bash
cp .env.example .env
```

```dotenv
# .env
CDSE_USERNAME=your_cdse_username
CDSE_PASSWORD=your_cdse_password
```

## Project layout

Everything runnable lives in the **`s1/` Python package** (restructured 2026-08-13).
Run tools from the repository root as modules:

```bash
python -m s1.tools.download.main_s1_list          # search + download (SLC)
python -m s1.tools.download.main_s1_list_grd      # same for GRD
```

```text
s1/
  core/
    paths.py                # Every path defined once, relative to the repo root
    scene.py                # S1 filename parsing (date, absolute orbit, scene id)
    aoi.py                  # Footprint (map-overlay.kml) coverage against a boundary
    config.py               # Loads .env, CDSEConfig / OutputConfig
  stac/
    client.py               # Opens the CDSE STAC client via pystac_client
    models.py               # S1SearchConfig, datetime parsing, datetime-range helpers
    search_s1.py            # STAC search + closest-to-target ranking + per-satellite coverage
    download_s1.py          # CDSE token, OData zipper download (resume support)
  footprint/                # Footprint-based scene selection (not bbox — see below)
  preprocess/               # SNAP gpt graphs (RTC/GTC) + shared batch runner
  tools/
    download/               # main_s1_list*, search_*, download_*
    preprocess/             # batch_grd_rtc*, batch_grd_gtc, batch_slc_rtc, ...
    water/                  # water/flood detection, area reporting
    mosaic/  dem/  audit/  monitor/  scratch/
docs/                       # Korean docs by topic (pipeline/water/flood/drought/worklog/review)
geojson/
  Korea_Peninsula.geojson   # Whole Korean peninsula polygon (broad monitoring)
  Korea_flood_AOI.geojson   # Narrow AOI around confirmed flood-damage locations
downloads/                  # Run outputs (not committed to git)
  s1_stac_list_manifest.json
  sentinel1/*.zip
temp/logs/                  # Batch run logs (not committed)
```

Optional editable install so `import s1` works from any directory:

```bash
pip install -e .
```

## Why footprint, not bbox

A Sentinel-1 IW frame is a **parallelogram** tilted by the orbit azimuth. Wrapping it in an
axis-aligned bbox adds triangular slivers the sensor never imaged. When those slivers overlap
the coastline, a frame that is 100 % ocean is misjudged as "it imaged land" — which once turned
flood-area numbers into artifacts. `s1/core/aoi.py` and `s1/footprint/` read the real footprint
polygon from `preview/map-overlay.kml` inside each product and test coverage with
point-in-polygon instead.

## Setting the AOI (area of interest)

`s1.tools.download.main_s1_list` defaults to `Korea_flood_AOI.geojson` — a narrow bounding box around the 4
confirmed flood-damage points.

```python
korea_geojson = Path(__file__).resolve().parent / "Korea_flood_AOI.geojson"
```

To monitor the whole Korean peninsula instead, just switch this one line to
`Korea_Peninsula.geojson`. Note that a wider AOI returns more results and may pick up scenes over
open water (East Sea/West Sea) that aren't relevant — prefer narrowing to your actual area of
interest, as `Korea_flood_AOI.geojson` does.

To build a new AOI for different points, edit the `coordinates` in `Korea_flood_AOI.geojson`
(order is `[lon, lat]`; it's a buffered bounding-box rectangle).

## Setting the target acquisition time

The `targets` list in `s1/tools/download/main_s1_list.py` takes a **date only** — results are ranked by date
proximity, so no time or timezone is needed.

```python
targets = [
    ("Korea_flood", "2026-07-20"),   # date only
]
```

- `window_days` (currently 15) only bounds the search window (±N days); you rarely need to touch it.
- `MAX_DOWNLOADS` (top of `main_s1_list*.py`, default 10, `None` = all found) is the **only knob**.

## How results are ranked (date proximity)

- Candidates are sorted by **how close their acquisition date is** to the target date, then by
  acquisition time as a stable tiebreak (`score_item` in `stac/search_s1.py`).
- `list_s1_items_for_date` returns all found candidates sorted this way; the driver then keeps the
  nearest `MAX_DOWNLOADS`. The old "top-k + per-satellite guarantee" logic was removed because it
  could drop frames of the same pass; give a generous `MAX_DOWNLOADS` (or `None`) to pull a whole
  date's frames.

## Running it

```bash
python -m s1.tools.download.main_s1_list
```

This will:

1. Search CDSE STAC using the Korea AOI and the date set in `targets`.
2. Save the search results to `downloads/s1_stac_list_manifest.json`.
3. Download the **nearest-date `MAX_DOWNLOADS` candidates**, in order, into
   `downloads/sentinel1/*.zip` (already-downloaded files are skipped automatically; an interrupted
   download resumes on the next run).

## Caveats (read before running)

- **Running `s1.tools.download.main_s1_list` as-is downloads every candidate found**, not just one. Each
  Sentinel-1 SLC product is typically 5-8 GB, so a handful of candidates can require tens of GB.
  Check free disk space first (`df -h`). To limit how many get downloaded, reduce `k` in
  `list_s1_items_for_date(..., k=...)` or cap the `selected_items` loop in `main()`.
- CDSE downloads can occasionally drop with a network read timeout partway through.
  `download_odata_cdse` supports resuming from the `.part` temp file, so if it errors out, just
  **re-run the same command**.
- The target satellites are not hardcoded — the script follows whatever CDSE STAC actually
  returns. So only satellites (S1A/S1C/S1D) that actually have an acquisition over the given AOI
  and time window will show up as candidates. If one satellite is missing, that's most likely a
  real tasking gap (or catalog publishing lag after acquisition), not a bug — try widening
  `window_days` or re-searching later.
