"""
DUST AI – WebSearchTool v2.0
Perplexity Sonar API con:
- Routing automatico sonar vs sonar-pro per tipo di query
- Budget cap mensile: max 10 query sonar-pro/mese (€5 budget)
- Parametri ottimizzati: max_tokens=400, search_context="low"
- Counter persistente in A:\\dustai_stuff\\memory\\perplexity_usage.json
"""
import json
import logging
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

log = logging.getLogger("WebSearchTool")

# Keyword che giustificano sonar-pro (query complesse)
PRO_KEYWORDS = [
    "analizza", "confronta", "ricerca approfondita", "spiega in dettaglio",
    "storia di", "perché", "come funziona", "differenza tra",
    "analisi", "ricerca", "approfondisci", "spiega", "panoramica",
    "tutorial", "guida completa", "best practice", "architettura",
]

MONTHLY_PRO_CAP = 10   # max sonar-pro al mese — €5 budget


class WebSearchTool:
    def __init__(self, config):
        self.config    = config
        self._api_key  = config.get_api_key("perplexity")
        self._usage_f  = config.get_memory_dir() / "perplexity_usage.json"
        self._usage    = self._load_usage()

    # ─── Usage tracking ──────────────────────────────────────────────────────

    def _load_usage(self) -> dict:
        if self._usage_f.exists():
            try:
                return json.loads(self._usage_f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"month": "", "sonar_count": 0, "sonar_pro_count": 0,
                "total_cost_usd": 0.0, "queries": []}

    def _save_usage(self):
        try:
            self._usage_f.write_text(
                json.dumps(self._usage, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            log.warning("Usage save error: " + str(e))

    def _check_month_reset(self):
        current_month = datetime.now().strftime("%Y-%m")
        if self._usage.get("month") != current_month:
            self._usage = {
                "month":           current_month,
                "sonar_count":     0,
                "sonar_pro_count": 0,
                "total_cost_usd":  0.0,
                "queries":         [],
            }
            self._save_usage()

    def _select_model(self, query: str) -> str:
        """Routing automatico: sonar-pro solo per query complesse e se budget disponibile."""
        self._check_month_reset()

        is_complex = any(kw in query.lower() for kw in PRO_KEYWORDS)
        pro_used   = self._usage.get("sonar_pro_count", 0)

        if is_complex and pro_used < MONTHLY_PRO_CAP:
            return "sonar-pro"
        if is_complex and pro_used >= MONTHLY_PRO_CAP:
            log.info("sonar-pro cap raggiunto (" + str(MONTHLY_PRO_CAP) + "/mese) → uso sonar")
        return "sonar"

    def _record_usage(self, model: str, query: str,
                      input_tokens: int, output_tokens: int):
        """Registra uso e calcola costo."""
        cost = 0.0
        if model == "sonar":
            cost = (input_tokens / 1_000_000) + (output_tokens / 1_000_000) + 0.005
        elif model == "sonar-pro":
            cost = (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000) + 0.006

        if model == "sonar-pro":
            self._usage["sonar_pro_count"] = self._usage.get("sonar_pro_count", 0) + 1
        else:
            self._usage["sonar_count"] = self._usage.get("sonar_count", 0) + 1

        self._usage["total_cost_usd"] = round(
            self._usage.get("total_cost_usd", 0.0) + cost, 6
        )
        self._usage.setdefault("queries", []).append({
            "ts":    datetime.now().isoformat(),
            "model": model,
            "query": query[:100],
            "cost":  round(cost, 6),
        })
        # Mantieni solo ultimi 200 record
        self._usage["queries"] = self._usage["queries"][-200:]
        self._save_usage()

    # ─── web_search ──────────────────────────────────────────────────────────

    def web_search(self, query: str, max_results: int = 5,
                   force_model: str = "") -> list:
        """
        Cerca sul web tramite Perplexity Sonar API.
        Ritorna lista di risultati: [{"title": str, "url": str, "snippet": str}]
        """
        if not self._api_key:
            return [{"error": "❌ PERPLEXITY_API_KEY non configurata in .env"}]

        model = force_model or self._select_model(query)
        log.info("Perplexity " + model + ": " + query[:60])

        try:
            import requests

            payload = {
                "model":   model,
                "messages": [{"role": "user", "content": query}],
                "max_tokens": 400,
                "search_context_size":    "low",      # risparmia request fee
                "return_related_questions": False,    # elimina token inutili
            }

            headers = {
                "Authorization": "Bearer " + self._api_key,
                "Content-Type":  "application/json",
            }

            resp = requests.post(
                "https://api.perplexity.ai/chat/completions",
                json=payload,
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"]
            usage   = data.get("usage", {})
            self._record_usage(
                model, query,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

            # Estrai citazioni se presenti
            citations = data.get("citations", [])
            results   = []

            if citations:
                for i, url in enumerate(citations[:max_results]):
                    results.append({
                        "title":   "Fonte " + str(i + 1),
                        "url":     url,
                        "snippet": content[:300] if i == 0 else "",
                    })
            else:
                # Nessuna citazione → ritorna il testo direttamente
                results = [{"title": "Risultato", "url": "", "snippet": content}]

            # Mostra costo stimato
            pro_left = MONTHLY_PRO_CAP - self._usage.get("sonar_pro_count", 0)
            cost_tot = self._usage.get("total_cost_usd", 0.0)
            log.info(
                "Search OK | costo mese: $" + str(round(cost_tot, 4)) +
                " | sonar-pro rimasti: " + str(pro_left)
            )

            return results

        except Exception as e:
            log.error("WebSearch error: " + str(e))
            return [{"error": "❌ Ricerca fallita: " + str(e)}]

    def get_budget_status(self) -> dict:
        """Ritorna stato budget Perplexity corrente."""
        self._check_month_reset()
        return {
            "month":           self._usage.get("month"),
            "sonar_queries":   self._usage.get("sonar_count", 0),
            "sonar_pro_used":  self._usage.get("sonar_pro_count", 0),
            "sonar_pro_left":  MONTHLY_PRO_CAP - self._usage.get("sonar_pro_count", 0),
            "total_cost_usd":  round(self._usage.get("total_cost_usd", 0.0), 4),
            "total_cost_eur":  round(self._usage.get("total_cost_usd", 0.0) * 0.92, 4),
            "budget_eur":      5.0,
            "budget_left_eur": round(5.0 - self._usage.get("total_cost_usd", 0.0) * 0.92, 4),
        }
