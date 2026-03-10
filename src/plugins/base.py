"""
DUST AI – Plugin Base
Classe base per tutti i plugin. Ogni plugin estende questa classe.

Per creare un nuovo plugin:
1. Crea cartella: src/plugins/nome_plugin/
2. Crea file: src/plugins/nome_plugin/plugin.py
3. Definisci classe che estende PluginBase
"""
from abc import ABC, abstractmethod
from typing import dict as Dict, list as List


class PluginBase(ABC):
    # Metadati del plugin — da sovrascrivere
    NAME = "base"
    DESCRIPTION = "Plugin base"
    VERSION = "1.0.0"
    ENABLED = True

    def __init__(self, config):
        self.config = config

    @abstractmethod
    def get_tools(self) -> Dict:
        """
        Restituisce dizionario {nome_tool: metodo} da registrare.
        Esempio: {"roblox_launch": self.roblox_launch}
        """
        pass

    def on_load(self):
        """Chiamato quando il plugin viene caricato."""
        pass

    def on_unload(self):
        """Chiamato quando il plugin viene scaricato."""
        pass

    def __repr__(self):
        return f"Plugin({self.NAME} v{self.VERSION})"
