"""Provider registry.

Adding a satellite source: implement SatelliteProvider in a new module, declare
its ``config_fields`` if it needs any, and register it below. The plugin builds
its provider dropdown and settings dialog from PROVIDERS + each provider's
config_fields — nothing else needs to change.
"""

from .base import SatelliteProvider
from .celestrak import (
    StationsProvider, VisualProvider, GpsProvider,
    WeatherProvider, StarlinkProvider, ActiveProvider,
)

# id -> provider class (order shown in the dropdown; the first is the default)
PROVIDERS = {
    StationsProvider.id: StationsProvider,
    VisualProvider.id: VisualProvider,
    GpsProvider.id: GpsProvider,
    WeatherProvider.id: WeatherProvider,
    StarlinkProvider.id: StarlinkProvider,
    ActiveProvider.id: ActiveProvider,
}

__all__ = ["SatelliteProvider", "PROVIDERS"]
