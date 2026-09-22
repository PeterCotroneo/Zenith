# Zenith

Watch **live satellites overhead** on your map. Zenith computes real-time
satellite positions from orbital data and shows them moving across QGIS — track
your current map view, or draw an area to watch. Live only; no history replay.

It's the space-side companion to [Wake](https://github.com/PeterCotroneo/Wake)
(marine vessels) and [Contrail](https://github.com/PeterCotroneo/Contrail)
(aircraft).

## Features

- **Computed locally, not received** — satellites don't broadcast their positions. Zenith fetches their orbital elements (TLEs) free and keyless from **CelesTrak** and propagates each satellite with **SGP4** on your machine. That means **no rate limits** and **complete global coverage** — none of the receiver-coverage gaps that affect AIS/ADS-B.
- **Pick a group** — space stations (ISS, Tiangong), the brightest/visible satellites, the GPS constellation, weather satellites, Starlink, or all ~11,000 active satellites.
- **Area-based** — watch everything over your map view or a drawn box.
- **Coloured by constellation/type**, with name, NORAD id, altitude and orbital speed. Click a satellite to open it on **N2YO**.
- **Cluster badges** for busy regions; zoom in and they fan out.
- **No extra dependencies** — the SGP4 propagator (pure-Python `sgp4`, MIT) is vendored, and everything else uses QGIS's own stack, so it installs cleanly from the plugin repository.

## Install

1. Download this repository as a ZIP (or clone it).
2. In QGIS: **Plugins → Manage and Install Plugins → Install from ZIP**, and select the zipped `zenith/` folder, or copy `zenith/` into your QGIS plugins directory.
3. Enable **Zenith**. A **Zenith** panel appears on the right.

## Usage

1. Choose a **Source** (all keyless — no configuration).
2. Choose **Track the current map view** or **Draw an area on the map**.
3. Click **Start tracking**. Zenith fetches the orbital elements, then satellites stream onto the map and move in real time.

## Notes

- Positions are computed from TLEs, which are accurate to ~1 km and refresh slowly; Zenith fetches them once per session.
- "All active satellites" is the full catalogue — zoom into a region for the clearest view.

## Credits

Orbit propagation uses the pure-Python [`sgp4`](https://github.com/brandon-rhodes/python-sgp4)
library by Brandon Rhodes (MIT), vendored under `zenith/vendor/`. Orbital
elements from [CelesTrak](https://celestrak.org/).

## License

GPL-2.0-or-later.
