"""
DUST AI – Plugin Loader
Auto-discovery e caricamento plugin dalla cartella src/plugins/.
"""
import importlib
import logging
from pathlib import Path
from typing import Dict

from .base import PluginBase


class PluginLoader:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("PluginLoader")
        self._plugins: Dict[str, PluginBase] = {}
        self._extra_tools: Dict[str, callable] = {}

    def load_all(self) -> Dict[str, callable]:
        """Carica tutti i plugin disponibili e restituisce i tool aggiuntivi."""
        plugins_dir = Path(__file__).parent

        for item in plugins_dir.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                plugin_file = item / "plugin.py"
                if plugin_file.exists():
                    self._load_plugin(item.name, f"src.plugins.{item.name}.plugin")

        self.log.info(f"Plugin caricati: {list(self._plugins.keys())}")
        return self._extra_tools

    def _load_plugin(self, name: str, module_path: str):
        """Carica un singolo plugin."""
        try:
            module = importlib.import_module(module_path)
            # Cerca classe che estende PluginBase
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                        issubclass(attr, PluginBase) and
                        attr is not PluginBase):
                    instance = attr(self.config)
                    if instance.ENABLED:
                        instance.on_load()
                        self._plugins[name] = instance
                        tools = instance.get_tools()
                        self._extra_tools.update(tools)
                        self.log.info(f"Plugin '{name}' caricato con {len(tools)} tool")
                    break
        except Exception as e:
            self.log.warning(f"Plugin '{name}' non caricato: {e}")

    def list_plugins(self) -> list:
        return [(name, p.DESCRIPTION) for name, p in self._plugins.items()]
