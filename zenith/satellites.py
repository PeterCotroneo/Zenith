"""Live satellite layer: buffer computed positions and flush to a memory layer
in batches so the map stays responsive.

Positions arrive as normalised satellite dicts (see providers/base.py), keyed by
NORAD catalogue id. Markers are stars coloured by category (constellation / type
derived from the name). Satellites not refreshed for a while are expired.
"""

import time

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsMarkerSymbol,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
    QgsPointClusterRenderer,
    QgsPalLayerSettings,
    QgsVectorLayerSimpleLabeling,
    QgsMessageLog,
    Qgis,
)

LAYER_NAME = "Zenith — Live Satellites"

_FIELDS = [
    ("norad", QVariant.String),
    ("name", QVariant.String),
    ("category", QVariant.String),
    ("altitude", QVariant.Int),
    ("speed", QVariant.Double),
    ("last_seen", QVariant.String),
]
_FIELD_INDEX = {name: i for i, (name, _t) in enumerate(_FIELDS)}

_ALIASES = {
    "norad": "NORAD ID", "name": "Name", "category": "Category",
    "altitude": "Altitude (km)", "speed": "Speed (km/s)",
    "last_seen": "Computed (UTC)",
}

_MAP_TIP = (
    "<b>[% \"name\" %]</b> <span style='color:gray'>NORAD [% \"norad\" %]</span><br/>"
    "[% \"category\" %]<br/>"
    "Altitude [% coalesce(\"altitude\",'?') %] km · [% coalesce(\"speed\",'?') %] km/s"
)

# category -> colour (also the order shown in the legend)
CATEGORY_COLORS = [
    ("Starlink", "#1f77b4"),
    ("OneWeb", "#17becf"),
    ("Navigation", "#2ca02c"),
    ("Weather", "#ff7f0e"),
    ("Station", "#d62728"),
    ("Science", "#9467bd"),
    ("Debris/Rocket", "#8c564b"),
    ("Other", "#7f7f7f"),
]

_NAV = ("GPS", "NAVSTAR", "GLONASS", "GALILEO", "BEIDOU", "GSAT", "QZS", "IRNSS", "NVS")
_WX = ("NOAA", "METEOR", "GOES", "METOP", "HIMAWARI", "FENGYUN", "DMSP", "ELEKTRO", "INSAT")
_STATION = ("ISS", "ZARYA", "CSS", "TIANGONG", "TIANHE", "WENTIAN", "MENGTIAN",
            "PROGRESS", "SOYUZ", "DRAGON", "CYGNUS", "SHENZHOU", "TIANZHOU")
_SCIENCE = ("HUBBLE", "HST", "TERRA", "AQUA", "LANDSAT", "SENTINEL", "SWOT", "ICESAT", "JASON")
_DEBRIS = ("R/B", "DEB", "ROCKET", "COOLANT", "WESTFORD")


def category_for(name):
    n = (name or "").upper()
    if "STARLINK" in n:
        return "Starlink"
    if "ONEWEB" in n:
        return "OneWeb"
    if any(k in n for k in _NAV):
        return "Navigation"
    if any(k in n for k in _WX):
        return "Weather"
    if any(k in n for k in _STATION):
        return "Station"
    if any(k in n for k in _SCIENCE):
        return "Science"
    if any(k in n for k in _DEBRIS):
        return "Debris/Rocket"
    return "Other"


class SatelliteStore:
    def __init__(self):
        self._layer = None
        self._records = {}   # norad -> merged field dict (+ _last_update)
        self._fid = {}       # norad -> feature id
        self._pending_new = set()
        self._pending_upd = set()

    # --- layer lifecycle -------------------------------------------------
    def ensure_layer(self):
        if self._layer is not None and self._layer_valid():
            return self._layer
        fields = QgsFields()
        for name, qtype in _FIELDS:
            fields.append(QgsField(name, qtype))
        layer = QgsVectorLayer("Point?crs=EPSG:4326", LAYER_NAME, "memory")
        layer.dataProvider().addAttributes(fields.toList())
        layer.updateFields()
        for name, alias in _ALIASES.items():
            idx = layer.fields().indexOf(name)
            if idx >= 0:
                layer.setFieldAlias(idx, alias)
        layer.setMapTipTemplate(_MAP_TIP)
        self._add_actions(layer)
        self._style(layer)
        QgsProject.instance().addMapLayer(layer)

    def _add_actions(self, layer):
        """Identify action: open the satellite on N2YO, keyed by NORAD id."""
        try:
            from qgis.core import QgsAction
            try:
                url_type = Qgis.AttributeActionType.OpenUrl
            except AttributeError:
                url_type = QgsAction.ActionType.OpenUrl
            layer.actions().addAction(
                url_type, "View on N2YO",
                'https://www.n2yo.com/satellite/?s=[% "norad" %]')
        except Exception as exc:  # noqa: BLE001 - actions are a nicety
            QgsMessageLog.logMessage(f"actions skipped: {exc}", "Zenith",
                                     Qgis.MessageLevel.Warning)
        self._layer = layer
        self._records.clear()
        self._fid.clear()
        self._pending_new.clear()
        self._pending_upd.clear()
        return layer

    def _layer_valid(self):
        try:
            return self._layer is not None and self._layer.isValid()
        except RuntimeError:
            return False

    def remove_layer(self):
        if self._layer_valid():
            QgsProject.instance().removeMapLayer(self._layer.id())
        self._layer = None
        self._records.clear()
        self._fid.clear()

    def _style(self, layer):
        try:
            categories = []
            for group, color in CATEGORY_COLORS:
                sym = QgsMarkerSymbol.createSimple(
                    {"name": "star", "size": "4", "color": color,
                     "outline_color": "black", "outline_width": "0.2"})
                categories.append(QgsRendererCategory(group, sym, group))
            by_cat = QgsCategorizedSymbolRenderer("category", categories)
            cluster = QgsPointClusterRenderer()
            cluster.setEmbeddedRenderer(by_cat)
            cluster.setTolerance(3.5)
            try:
                cluster.setToleranceUnit(Qgis.RenderUnit.Millimeters)
            except (AttributeError, TypeError):
                pass
            layer.setRenderer(cluster)
            pal = QgsPalLayerSettings()
            pal.fieldName = "name"
            layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
            layer.setLabelsEnabled(True)
        except Exception as exc:  # noqa: BLE001 - styling must never block data
            QgsMessageLog.logMessage(f"styling skipped: {exc}", "Zenith",
                                     Qgis.MessageLevel.Warning)

    # --- ingest / flush --------------------------------------------------
    def ingest_many(self, records):
        for rec in records:
            self.ingest(rec)

    def ingest(self, sat):
        nid = sat.get("norad")
        if not nid:
            return
        rec = self._records.setdefault(nid, {})
        for key, val in sat.items():
            if val is not None and val != "":
                rec[key] = val
        rec["_last_update"] = time.time()
        has_pos = rec.get("lat") is not None and rec.get("lon") is not None
        if nid in self._fid:
            self._pending_upd.add(nid)
        elif has_pos:
            self._pending_new.add(nid)

    def _attrs(self, rec):
        return {
            _FIELD_INDEX["name"]: rec.get("name", ""),
            _FIELD_INDEX["category"]: rec.get("category", "Other"),
            _FIELD_INDEX["altitude"]: (int(rec["altitude"]) if rec.get("altitude") is not None else None),
            _FIELD_INDEX["speed"]: (round(rec["speed"], 3) if rec.get("speed") is not None else None),
            _FIELD_INDEX["last_seen"]: rec.get("last_seen", ""),
        }

    def flush(self):
        if not self._layer_valid() or (not self._pending_new and not self._pending_upd):
            return
        dp = self._layer.dataProvider()
        if self._pending_new:
            feats = []
            for nid in self._pending_new:
                rec = self._records.get(nid)
                if not rec:
                    continue
                feat = QgsFeature(self._layer.fields())
                feat.setGeometry(QgsGeometry.fromPointXY(
                    QgsPointXY(float(rec["lon"]), float(rec["lat"]))))
                attrs = [None] * len(_FIELDS)
                attrs[_FIELD_INDEX["norad"]] = nid
                for idx, val in self._attrs(rec).items():
                    attrs[idx] = val
                feat.setAttributes(attrs)
                feats.append(feat)
            if feats:
                ok, added = dp.addFeatures(feats)
                for f in (added or []):
                    n = f["norad"]
                    if n:
                        self._fid[n] = f.id()
            self._pending_new.clear()
        if self._pending_upd:
            geom_changes, attr_changes = {}, {}
            for nid in self._pending_upd:
                fid = self._fid.get(nid)
                rec = self._records.get(nid)
                if fid is None or not rec:
                    continue
                if rec.get("lat") is not None and rec.get("lon") is not None:
                    geom_changes[fid] = QgsGeometry.fromPointXY(
                        QgsPointXY(float(rec["lon"]), float(rec["lat"])))
                attr_changes[fid] = self._attrs(rec)
            if geom_changes:
                dp.changeGeometryValues(geom_changes)
            if attr_changes:
                dp.changeAttributeValues(attr_changes)
            self._pending_upd.clear()
        self._layer.updateExtents()
        self._layer.triggerRepaint()

    def expire(self, max_age_seconds):
        if not self._layer_valid():
            return
        now = time.time()
        stale = [n for n, rec in self._records.items()
                 if now - rec.get("_last_update", now) > max_age_seconds]
        fids = [self._fid[n] for n in stale if n in self._fid]
        if fids:
            self._layer.dataProvider().deleteFeatures(fids)
            self._layer.triggerRepaint()
        for n in stale:
            self._records.pop(n, None)
            self._fid.pop(n, None)

    def count(self):
        return len(self._fid)

    def retain_within(self, bbox):
        if not self._layer_valid():
            return
        lat_min, lon_min, lat_max, lon_max = bbox
        outside = []
        for nid, rec in self._records.items():
            try:
                lat, lon = float(rec.get("lat")), float(rec.get("lon"))
            except (TypeError, ValueError):
                continue
            if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
                outside.append(nid)
        fids = [self._fid[n] for n in outside if n in self._fid]
        if fids:
            self._layer.dataProvider().deleteFeatures(fids)
            self._layer.triggerRepaint()
        for n in outside:
            self._records.pop(n, None)
            self._fid.pop(n, None)
