# DUST AI – Fase 1.0/1.1: Bootstrap Locale

## Stato Attuale (aggiornato v1.4)

| Componente | Stato | Note |
|---|---|---|
| Python agent custom | ✅ | `src/agent.py` v1.4 |
| GUI PySide6 | ✅ | `src/ui/gui.py` — dark theme, output colorato |
| Config OneDrive-aware | ✅ | `Config.get_desktop()` risolve path corretto |
| API key Google (Gemini) | ✅ | `%APPDATA%\dustai\.env` |
| API key Perplexity | ✅ | `%APPDATA%\dustai\.env` |
| Rate limiting 429 | ✅ | retry automatico + fallback Ollama |
| Stall detection | ✅ | abort se loop "in attesa" |
| Loop detection | ✅ | abort se risposta identica ripetuta |
| Path injection runtime | ✅ | Desktop reale nel system prompt |
| SelfHealEngine | ✅ | web search + patch + hot-reload |
| Bootstrap auto-install | ✅ | pip + Playwright + Ollama + iGPU |
| Ollama installato | 🟡 | da verificare sul sistema |
| qwen3:8b scaricato | 🟡 | pull manuale se Bootstrap crasha |
| iGPU AMD (OLLAMA_GPU_LAYERS=18) | 🟡 | Bootstrap configura le env vars |
| Ollama pull resiliente (streaming) | ⬜ | v1.5 pianificata |
| Plugin system | ⬜ | struttura pronta, da popolare |
| Autonomia ≥93% verificata | ⬜ | test in corso |

---

## Prossimi Step Immediati

1. **Fix Ollama pull crash** — migrare da `subprocess.run(timeout=600)` a Ollama SDK streaming
2. **Test 10 task** — misurare autonomia reale e registrare i fallimenti
3. **Plugin system** — implementare primi plugin (es. plugin_clipboard, plugin_notify)
4. **Fase 2.0** — attivare Oracle Cloud Free Tier (EU-Frankfurt + US-Ashburn)

---

## Fase 2.0 – Piano K3s Cloud (prossima)

| Componente | Piano |
|---|---|
| Infrastruttura | Oracle Cloud Free Tier: 2 VM ARM (4 OCPU, 24 GB RAM cad.) |
| Orchestrazione | K3s (Kubernetes leggero) |
| Networking | Cloudflare Zero-Trust + WireGuard mesh |
| GitOps | ArgoCD → questa repo (Tenkulo/dustai) |
| Monitoring | Prometheus + Grafana |
| Backup | Nightly su Object Storage Oracle |
| Costo totale | €0 |

**Obiettivo:** agent-core gira su cloud, il PC locale diventa terminale zero-carico.
