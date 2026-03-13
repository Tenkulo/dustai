"""AI Conductor — higher-level AI utilities (ai_ask, ai_parallel, ai_summarize…)."""
import json
import logging
import re
import concurrent.futures

logger = logging.getLogger("dust.ai_conductor")
_gw = None

def _gateway():
    global _gw
    if _gw is None:
        from ai_gateway import AIGateway
        _gw = AIGateway()
    return _gw


def ai_ask(prompt: str, system: str = None, provider: str = None,
           json_response: bool = False) -> str | dict:
    """Ask a single question to the best available AI."""
    try:
        if json_response:
            system = (system or "") + "\nRespondi SOLO con JSON valido, nessun testo extra."
        result = _gateway().complete([{"role": "user", "content": prompt}], system=system,
                                     provider=provider)
        if json_response:
            try:
                m = re.search(r'\{.*\}', result, re.DOTALL)
                if m:
                    return json.loads(m.group())
            except Exception:
                pass
        return result
    except Exception as exc:
        logger.error(f"ai_ask: {exc}")
        return {"error": str(exc)} if json_response else f"Errore: {exc}"


def ai_parallel(prompts, system: str = None, max_workers: int = 3) -> dict:
    """Execute multiple prompts in parallel. prompts can be dict or list."""
    if isinstance(prompts, dict):
        items = list(prompts.items())
    else:
        items = list(enumerate(prompts))

    results = {}

    def _ask(item):
        k, p = item
        try:
            return k, ai_ask(p, system=system)
        except Exception as exc:
            return k, f"Errore: {exc}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        for k, v in ex.map(_ask, items):
            results[k] = v
    return results


def ai_models() -> dict:
    """List available AI models/providers."""
    try:
        return {"providers": _gateway().list_providers()}
    except Exception as exc:
        return {"error": str(exc)}


def ai_summarize(text: str, language: str = "italiano", max_words: int = 150) -> str:
    """Summarize text using AI."""
    return ai_ask(f"Riassumi in {language} in max {max_words} parole:\n\n{text}")


def ai_classify(text: str, categories: list[str]) -> str:
    """Classify text into one of the given categories."""
    cats = ", ".join(categories)
    return ai_ask(
        f"Classifica il testo in UNA categoria tra: {cats}\n\nTesto: {text}\n\n"
        f"Rispondi SOLO con il nome della categoria."
    )
