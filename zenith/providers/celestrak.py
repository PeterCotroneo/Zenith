"""CelesTrak satellite providers — keyless live orbits.

Each provider fetches a CelesTrak group's TLEs once (orbital elements change
slowly), then computes every satellite's position locally with SGP4 on a timer
and emits the ones inside the tracked map area. No feed to poll, no rate limits,
global coverage. Different groups (stations, GPS, Starlink…) are separate
entries in the Source dropdown.
"""

import datetime

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl, QTimer
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

from .base import SatelliteProvider
from .._debug import dbg
from ..orbits import parse_tles, propagate
from ..satellites import category_for

COMPUTE_MS = 2000          # recompute satellite positions every 2 s
USER_AGENT = "ZenithQGIS/0.1 (QGIS plugin)"


class CelesTrakGroupProvider(SatelliteProvider):
    """Shared logic for a CelesTrak group. Subclasses set ``group``."""

    group = "stations"

    def __init__(self, settings=None, parent=None):
        super().__init__(settings, parent)
        self._sats = []       # [(name, satrec)]
        self._bbox = None
        self._want = False
        self._nam = QgsNetworkAccessManager.instance()
        self._timer = QTimer(self)
        self._timer.setInterval(COMPUTE_MS)
        self._timer.timeout.connect(self._compute)

    def start(self, bboxes):
        self._bbox = bboxes[0] if bboxes else None
        self._want = True
        self.status_changed.emit("Fetching orbits…")
        dbg(f"Fetching {self.group} orbital elements from CelesTrak")
        self._fetch_tles()

    def stop(self):
        self._want = False
        self._timer.stop()

    def update_area(self, bboxes):
        self._bbox = bboxes[0] if bboxes else None

    def _fetch_tles(self):
        url = ("https://celestrak.org/NORAD/elements/gp.php"
               f"?GROUP={self.group}&FORMAT=tle")
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", USER_AGENT.encode())
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._on_tles(reply))

    def _on_tles(self, reply):
        reply.deleteLater()
        if not self._want:
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.error.emit(f"CelesTrak unreachable ({reply.errorString()}).")
            return
        text = bytes(reply.readAll()).decode("utf-8", "replace")
        self._sats = parse_tles(text)
        if not self._sats:
            self.error.emit(f"No orbital elements returned for {self.group}.")
            return
        dbg(f"{len(self._sats)} satellites in {self.group}")
        self.status_changed.emit("Tracking")
        self._compute()
        self._timer.start()

    def _compute(self):
        if not self._want or not self._sats:
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        stamp = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        bbox = self._bbox
        batch = []
        for name, sat in self._sats:
            pos = propagate(sat, now)
            if not pos:
                continue
            lat, lon = pos["lat"], pos["lon"]
            if bbox and not (bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3]):
                continue
            batch.append({
                "norad": str(getattr(sat, "satnum", "")),
                "name": name,
                "category": category_for(name),
                "lat": lat, "lon": lon,
                "altitude": pos["alt"], "speed": pos["speed"],
                "last_seen": stamp,
            })
        if batch:
            self.satellites_update.emit(batch)


class StationsProvider(CelesTrakGroupProvider):
    id = "stations"
    label = "Space stations (ISS, CSS)"
    group = "stations"
    help_text = ("Crewed stations and their visiting vehicles (ISS, Tiangong, "
                 "Dragon, Progress…). Free and keyless — no account needed.")


class VisualProvider(CelesTrakGroupProvider):
    id = "visual"
    label = "Brightest / visible"
    group = "visual"
    help_text = ("The ~150 brightest satellites — the ones you can see with the "
                 "naked eye. Free and keyless.")


class GpsProvider(CelesTrakGroupProvider):
    id = "gps"
    label = "GPS constellation"
    group = "gps-ops"
    help_text = "The operational GPS navigation constellation. Free and keyless."


class WeatherProvider(CelesTrakGroupProvider):
    id = "weather"
    label = "Weather satellites"
    group = "weather"
    help_text = ("Weather and earth-observation satellites (NOAA, MetOp, "
                 "Meteor…). Free and keyless.")


class StarlinkProvider(CelesTrakGroupProvider):
    id = "starlink"
    label = "Starlink"
    group = "starlink"
    help_text = ("The Starlink constellation (thousands of satellites). Free and "
                 "keyless; computed locally, so it stays smooth.")


class ActiveProvider(CelesTrakGroupProvider):
    id = "active"
    label = "All active satellites"
    group = "active"
    help_text = ("Every active catalogued satellite (~11,000). Computed locally "
                 "so it handles the full catalogue; zoom in to a region for the "
                 "clearest view. Free and keyless.")
