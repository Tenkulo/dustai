# DUST AI – Fase 1.0: Bootstrap Locale

## Stato Attuale

| Step | Stato | Note |
|---|---|---|
| PyGPT 2.7.12 installato | ✅ | |
| models.json ottimizzato | ✅ | gemini-2.5-flash/pro default=true |
| profile.json ottimizzato | ✅ | workdir → %APPDATA% |
| API key Google (Gemini) | ✅ | |
| API key Perplexity | ✅ | |
| gemini-2.5-flash in Agent mode | ✅ | tool_calls funzionanti |
| sys_exec operativo | ✅ | cmd /c confermato |
| Desktop OneDrive identificato | ✅ | %OneDrive%\Desktop |
| Ollama installato | ⬜ | |
| qwen3:8b scaricato | ⬜ | fallback locale |
| iGPU AMD accelerazione | ⬜ | OLLAMA_GPU_LAYERS=18 |
| Open Interpreter configurato | ⬜ | |
| Autonomia ≥93% verificata | ⬜ | 10 task test |
| Repo GitHub completa | 🟡 | In corso |

## Prossimi Step

1. **Installa Ollama** → scarica `qwen3:8b` per fallback offline
2. **Abilita iGPU** → imposta `OLLAMA_GPU_LAYERS=18` nelle variabili d'ambiente Windows
3. **Configura Open Interpreter** → copia `config/open_interpreter.yaml`
4. **Esegui 10 task di test** → misura autonomia reale
5. **Prepara Fase 2.0** → attiva account Oracle Cloud Free Tier
