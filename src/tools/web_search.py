"""
DUST AI – Tool: web_search
Ricerca web via Perplexity Sonar API.
Fallback: DuckDuckGo via requests se Perplexity non disponibile.
"""
import logging
import json


class WebSearchTool:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("WebSearchTool")

    def web_search(self, query: str, model: str = "sonar-pro", max_results: int = 5) -> str:
        """
        Cerca informazioni sul web.
        
        Usa Perplexity Sonar se API key disponibile,
        altrimenti DuckDuckGo come fallback.
        """
        api_key = self.config.get_api_key("perplexity")

        if api_key:
            return self._search_perplexity(query, model, api_key)
        else:
            self.log.warning("Perplexity API key non trovata, uso DuckDuckGo")
            return self._search_duckduckgo(query)

    def _search_perplexity(self, query: str, model: str, api_key: str) -> str:
        try:
            import requests
            url = "https://api.perplexity.ai/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": query}],
                "return_citations": True,
                "search_recency_filter": "month",
            }
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]

            # Aggiungi citations se presenti
            citations = data.get("citations", [])
            if citations:
                content += "\n\nFonti:\n" + "\n".join(f"• {c}" for c in citations[:5])

            return content
        except Exception as e:
            return f"❌ Errore Perplexity: {e}"

    def _search_duckduckgo(self, query: str) -> str:
        """Fallback DuckDuckGo via HTML scraping."""
        try:
            import requests
            from html.parser import HTMLParser

            url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=15)

            # Estrai testo base
            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                    self.in_result = False

                def handle_data(self, data):
                    if data.strip():
                        self.text.append(data.strip())

            parser = TextExtractor()
            parser.feed(response.text)
            result = " ".join(parser.text[:100])[:2000]
            return f"[DuckDuckGo] {result}"
        except Exception as e:
            return f"❌ Errore ricerca web: {e}"
