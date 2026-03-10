"""
DUST AI – Console UI
Interfaccia terminale interattiva.
Supporta comandi speciali e modalità agent/chat.
"""
import logging
import sys


BANNER = """
╔══════════════════════════════════════════╗
║           🤖  DUST AI  v1.0.0            ║
║   Desktop Unified Smart Tool             ║
║   Gemini 2.5 Flash + Tool Calling        ║
╚══════════════════════════════════════════╝

Comandi speciali:
  /agent <task>  – Esegui task in modalità agente autonomo
  /chat <msg>    – Chat semplice (risposta singola)
  /tools         – Lista tool disponibili
  /memory        – Mostra memoria corrente
  /clear         – Svuota memoria sessione
  /help          – Mostra questo messaggio
  /exit          – Esci

Senza prefisso = modalità agent (default)
"""


class ConsoleUI:
    def __init__(self, agent):
        self.agent = agent
        self.log = logging.getLogger("ConsoleUI")
        self._mode = "agent"   # "agent" | "chat"

    def run(self):
        """Loop principale UI."""
        print(BANNER)
        self._check_config()

        while True:
            try:
                user_input = input("\n🧠 DUST > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\n👋 Uscita. Arrivederci!")
                sys.exit(0)

            if not user_input:
                continue

            self._handle_input(user_input)

    def _handle_input(self, text: str):
        """Gestisce l'input utente."""
        # Comandi speciali
        if text.startswith("/"):
            parts = text.split(None, 1)
            cmd = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            if cmd == "/exit":
                print("👋 Arrivederci!")
                sys.exit(0)

            elif cmd == "/help":
                print(BANNER)

            elif cmd == "/tools":
                tools = self.agent.tools.list_tools()
                print(f"\n🔧 Tool disponibili ({len(tools)}):")
                for t in tools:
                    print(f"  • {t}")

            elif cmd == "/memory":
                ctx = self.agent.memory.get_context()
                print(f"\n🧠 Memoria:\n{ctx if ctx else '[vuota]'}")

            elif cmd == "/clear":
                self.agent.memory.clear()
                print("✅ Memoria sessione svuotata")

            elif cmd == "/chat":
                if not args:
                    print("❌ Specifica un messaggio: /chat <messaggio>")
                    return
                print("\n💬 Chat...")
                response = self.agent.chat(args)
                print(f"\n{response}")

            elif cmd == "/agent":
                task = args if args else input("Task: ").strip()
                if task:
                    self._run_agent_task(task)

            else:
                print(f"❌ Comando sconosciuto: {cmd}. Usa /help")

        else:
            # Input senza prefisso = modalità agent (default)
            self._run_agent_task(text)

    def _run_agent_task(self, task: str):
        """Esegue un task in modalità agente con feedback visivo."""
        print(f"\n🚀 Avvio task agente...")
        print(f"   Task: {task[:100]}{'...' if len(task) > 100 else ''}")
        print("─" * 50)

        response = self.agent.run_task(task)

        print("─" * 50)
        print(f"\n✅ Risultato:\n{response}")

    def _check_config(self):
        """Verifica configurazione e avvisa se mancano API keys."""
        api_key = self.agent.config.get_api_key("google")
        if not api_key:
            print("⚠️  ATTENZIONE: GOOGLE_API_KEY non configurata!")
            print("   Crea il file: %APPDATA%\\dustai\\.env")
            print("   Contenuto: GOOGLE_API_KEY=la_tua_api_key\n")

        desktop = self.agent.config.get_desktop()
        print(f"📁 Desktop rilevato: {desktop}")
        print(f"💾 Workdir: {self.agent.config.get_workdir()}")
