"""Tool registry with _safe_params v4 — filters private keys, non-scalars, class/callable distinction."""
import inspect
import logging
from typing import Any, Callable

logger = logging.getLogger("dust.registry")

_SINGLETON_CACHE: dict = {}


def _safe_params(fn: Callable, params: dict) -> dict:
    """Keep only params accepted by fn; drop _xxx keys and non-JSON-serializable values."""
    try:
        sig = inspect.signature(fn)
        accepted = set(sig.parameters.keys())
        # Check for **kwargs — if present, pass everything (filtered)
        has_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
    except (ValueError, TypeError):
        accepted = set(); has_kwargs = True

    out = {}
    for k, v in params.items():
        if k.startswith("_"):
            continue
        if not has_kwargs and k not in accepted:
            continue
        if isinstance(v, (str, int, float, bool, list, dict, type(None))):
            out[k] = v
        # silently drop non-scalar values (e.g. Config._cfg dicts with non-serializable items)
    return out


class Registry:
    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register_function(self, name: str, fn: Callable, description: str = "") -> None:
        self._tools[name] = {"fn": fn, "desc": description}
        logger.debug(f"Registered tool: {name}")

    def register_module(self, module) -> None:
        """Auto-register all public callables (functions, not classes) from a module."""
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            attr = getattr(module, attr_name)
            # callable but NOT a class
            if callable(attr) and not isinstance(attr, type):
                desc = (getattr(attr, "__doc__", "") or "").strip().split("\n")[0]
                self._tools[attr_name] = {"fn": attr, "desc": desc}

    def call(self, name: str, **kwargs) -> Any:
        if name not in self._tools:
            available = ", ".join(self._tools.keys())
            raise ValueError(f"Tool '{name}' not found. Available: {available}")

        entry = self._tools[name]
        fn    = entry["fn"]

        # Lazy singleton for classes
        if isinstance(fn, type):
            if fn not in _SINGLETON_CACHE:
                _SINGLETON_CACHE[fn] = fn()
            instance = _SINGLETON_CACHE[fn]
            safe = _safe_params(instance.__call__, kwargs)
            return instance(**safe)

        safe = _safe_params(fn, kwargs)
        return fn(**safe)

    def list_tools(self) -> dict[str, str]:
        return {name: t["desc"] for name, t in self._tools.items()}

    def tools_prompt(self) -> str:
        lines = ["Strumenti disponibili:"]
        for name, t in self._tools.items():
            lines.append(f"  {name}: {t['desc']}")
        return "\n".join(lines)
