"""Provider abstraction for Zenith.

A provider delivers live satellite positions for a group of satellites. Unlike a
vessel/aircraft feed, positions are not received — the provider fetches orbital
elements (TLEs, keyless from CelesTrak) and computes each satellite's position
locally with SGP4 on a timer, emitting them in batches.

Normalised satellite dict (keys a provider emits; all optional except norad):
    norad (str)        - NORAD catalogue id, unique
    name (str)         - satellite name
    category (str)     - constellation / type group (for colouring)
    lat, lon (float)   - sub-satellite point (WGS84)
    altitude (float)   - altitude above the ellipsoid, km
    speed (float)      - orbital speed, km/s
    last_seen (str)    - computation timestamp
"""

from qgis.PyQt.QtCore import QObject, pyqtSignal


class SatelliteProvider(QObject):
    """Abstract live-satellite source. Subclasses implement start()/stop()."""

    satellites_update = pyqtSignal(list)  # a batch of normalised satellite dicts
    status_changed = pyqtSignal(str)
    error = pyqtSignal(str)

    id = "base"
    label = "Abstract provider"
    help_text = ""
    config_fields = []

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self.settings = settings or {}

    @classmethod
    def needs_config(cls):
        return bool(cls.config_fields)

    def start(self, bboxes):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def update_area(self, bboxes):
        pass
