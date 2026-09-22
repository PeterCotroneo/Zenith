def classFactory(iface):
    """Entry point required by QGIS to load the plugin."""
    from .zenith_plugin import ZenithPlugin
    return ZenithPlugin(iface)
