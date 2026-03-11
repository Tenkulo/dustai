"""
DUST AI – BudgetMonitor v2.0
Monitoraggio uso token Google Gemini + Perplexity mensile.
Legge i log debug_*.jsonl e produce report JSON + testo.

Uso:
  python budget_monitor.py           → stampa report
  python budget_monitor.py --json    → output JSON puro
  python budget_monitor.py --watch   → aggiorna ogni 60s
"""
import json
import sys
import time
from pathlib import Path
from datetime import datetime, date
from collections import defaultdict


# ─── Configurazione ───────────────────────────────────────────────────────────
BASE_PATH          = Path(r"A:\dustai_stuff")
LOG_DIR            = BASE_PATH / "logs"
MEMORY_DIR         = BASE_PATH / "memory"
PERPLEXITY_USAGE_F = MEMORY_DIR / "perplexity_usage.json"

# Limiti Free Tier Gemini (per progetto, per giorno)
GEMINI_FREE_LIMITS = {
    "gemini-2.5-flash":      {"rpm": 15, "rpd": 1000, "tpm": 250_000},
    "gemini-2.5-flash-lite": {"rpm": 15, "rpd": 1000, "tpm": 250_000},
    "gemini-2.5-pro":        {"rpm": 5,  "rpd": 50,   "tpm": 100_000},
}
N_PROJECTS = 3   # numero progetti AI Studio

# Budget Perplexity
PERPLEXITY_MONTHLY_EUR = 5.0
SONAR_PRO_MONTHLY_CAP  = 10


def load_logs(days_back: int = 30) -> list:
    """Carica eventi dai log JSONL degli ultimi N giorni."""
    events = []
    if not LOG_DIR.exists():
        return events
    for log_file in sorted(LOG_DIR.glob("debug_*.jsonl")):
        try:
            date_str = log_file.stem.replace("debug_", "")
            log_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            if (date.today() - log_date).days > days_back:
                continue
            for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
    return events


def analyze_gemini(events: list) -> dict:
    """Analizza le chiamate Gemini dai log."""
    today_str = date.today().isoformat()
    month_str = date.today().strftime("%Y-%m")

    calls_today = defaultdict(int)
    calls_month = defaultdict(int)

    for ev in events:
        if ev.get("type") != "model_call":
            continue
        ts    = ev.get("ts", "")
        model = ev.get("data", {}).get("model", "unknown")
        # Normalizza nome modello
        for m in GEMINI_FREE_LIMITS:
            if m in model:
                model = m
                break

        if ts.startswith(today_str):
            calls_today[model] += 1
        if ts.startswith(month_str):
            calls_month[model] += 1

    # Calcola limiti e percentuali
    report = {}
    for model, limits in GEMINI_FREE_LIMITS.items():
        rpd_total  = limits["rpd"] * N_PROJECTS
        today_used = calls_today.get(model, 0)
        month_used = calls_month.get(model, 0)
        report[model] = {
            "today_calls":    today_used,
            "today_limit":    rpd_total,
            "today_pct":      round(today_used / rpd_total * 100, 1) if rpd_total else 0,
            "today_left":     max(0, rpd_total - today_used),
            "month_calls":    month_used,
            "month_limit":    rpd_total * 30,
            "month_pct":      round(month_used / (rpd_total * 30) * 100, 1) if rpd_total else 0,
        }
    return report


def analyze_perplexity() -> dict:
    """Legge il tracker Perplexity da memory/perplexity_usage.json."""
    if not PERPLEXITY_USAGE_F.exists():
        return {"error": "File usage non trovato — WebSearchTool non ancora usato"}
    try:
        data      = json.loads(PERPLEXITY_USAGE_F.read_text(encoding="utf-8"))
        cost_usd  = data.get("total_cost_usd", 0.0)
        cost_eur  = round(cost_usd * 0.92, 4)
        left_eur  = round(PERPLEXITY_MONTHLY_EUR - cost_eur, 4)
        pro_used  = data.get("sonar_pro_count", 0)

        return {
            "month":          data.get("month", "?"),
            "sonar_queries":  data.get("sonar_count", 0),
            "sonar_pro_used": pro_used,
            "sonar_pro_left": max(0, SONAR_PRO_MONTHLY_CAP - pro_used),
            "cost_eur":       cost_eur,
            "budget_eur":     PERPLEXITY_MONTHLY_EUR,
            "left_eur":       left_eur,
            "left_pct":       round(left_eur / PERPLEXITY_MONTHLY_EUR * 100, 1),
        }
    except Exception as e:
        return {"error": str(e)}


def analyze_errors(events: list) -> dict:
    """Conta errori e tipi di anomalia."""
    errors     = [e for e in events if e.get("severity") in ("error", "fatal")]
    warnings   = [e for e in events if e.get("severity") == "warning"]
    parse_fails = [e for e in events if e.get("type") == "parse_fail"]
    heals      = [e for e in events if e.get("type") == "heal"]

    return {
        "total_errors":   len(errors),
        "total_warnings": len(warnings),
        "parse_fails":    len(parse_fails),
        "heals":          len(heals),
        "heal_success":   sum(1 for h in heals if h.get("data", {}).get("success")),
        "last_error":     errors[-1].get("data", {}).get("error", "")[:150] if errors else "",
    }


def build_report(days_back: int = 30) -> dict:
    events   = load_logs(days_back)
    gemini   = analyze_gemini(events)
    pplx     = analyze_perplexity()
    errs     = analyze_errors(events)
    sessions = len(set(e.get("session", "") for e in events))

    return {
        "generated_at": datetime.now().isoformat(),
        "period_days":  days_back,
        "total_events": len(events),
        "sessions":     sessions,
        "gemini":       gemini,
        "perplexity":   pplx,
        "errors":       errs,
    }


def print_report(report: dict):
    SEP = "─" * 56
    g   = report["gemini"]
    p   = report["perplexity"]
    e   = report["errors"]

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║          DUST AI – Budget Monitor                    ║")
    print("╚══════════════════════════════════════════════════════╝")
    print("Generato: " + report["generated_at"][:16])
    print("Periodo:  ultimi " + str(report["period_days"]) + " giorni | "
          + str(report["sessions"]) + " sessioni | "
          + str(report["total_events"]) + " eventi")
    print()

    # Gemini
    print("GEMINI API FREE TIER (" + str(3) + " progetti)")
    print(SEP)
    for model, stats in g.items():
        name  = model.replace("gemini-2.5-", "").ljust(12)
        bar   = _bar(stats["today_pct"])
        print("  " + name + " oggi: " + str(stats["today_calls"]) + "/" +
              str(stats["today_limit"]) + " " + bar + " " + str(stats["today_pct"]) + "%")
        print("          mese: " + str(stats["month_calls"]) + "/" +
              str(stats["month_limit"]) + " (" + str(stats["month_pct"]) + "%)")
    print()

    # Perplexity
    print("PERPLEXITY API (€" + str(PERPLEXITY_MONTHLY_EUR) + "/mese)")
    print(SEP)
    if "error" in p:
        print("  ⚠ " + p["error"])
    else:
        spent_pct = round((1 - p["left_pct"] / 100) * 100, 1)
        print("  Sonar query:    " + str(p["sonar_queries"]))
        print("  Sonar Pro:      " + str(p["sonar_pro_used"]) + "/" +
              str(SONAR_PRO_MONTHLY_CAP) + " (" + str(p["sonar_pro_left"]) + " rimasti)")
        print("  Speso:          €" + str(p["cost_eur"]) + " / €" + str(p["budget_eur"]))
        print("  Rimasto:        €" + str(p["left_eur"]) + " " + _bar(spent_pct))
    print()

    # Errori
    print("DIAGNOSTICA")
    print(SEP)
    print("  Errori:         " + str(e["total_errors"]))
    print("  Warning:        " + str(e["total_warnings"]))
    print("  Parse fail:     " + str(e["parse_fails"]))
    heals_ok = str(e["heal_success"]) + "/" + str(e["heals"])
    print("  Heal successi:  " + heals_ok)
    if e["last_error"]:
        print("  Ultimo errore:  " + e["last_error"][:80])
    print()

    # Stima residua
    flash_left = g.get("gemini-2.5-flash", {}).get("today_left", 0)
    print("STIMA OGGI")
    print(SEP)
    print("  Flash rimasti:  " + str(flash_left) + " req")
    if flash_left < 100:
        print("  ⚠ ATTENZIONE: pochi token Flash disponibili oggi")
    print()


def _bar(pct: float, width: int = 20) -> str:
    filled = int(min(pct, 100) / 100 * width)
    return "[" + "█" * filled + "░" * (width - filled) + "]"


def save_report(report: dict):
    try:
        out = BASE_PATH / "budget_report.json"
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print("⚠ Save report: " + str(e))


if __name__ == "__main__":
    args        = sys.argv[1:]
    json_mode   = "--json"  in args
    watch_mode  = "--watch" in args

    if watch_mode:
        print("Budget Monitor attivo (Ctrl+C per uscire)")
        while True:
            r = build_report()
            if not json_mode:
                print("\033c", end="")  # clear console
                print_report(r)
            save_report(r)
            time.sleep(60)
    else:
        r = build_report()
        if json_mode:
            print(json.dumps(r, indent=2, ensure_ascii=False))
        else:
            print_report(r)
        save_report(r)
