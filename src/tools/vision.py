"""
DUST AI – VisionTool v2.0
Screenshot con mss + analisi Gemini Vision.
Usato per GUI automation quando le coordinate non sono note.
"""
import base64
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

log = logging.getLogger("VisionTool")


class VisionTool:
    def __init__(self, config):
        self.config      = config
        self.screenshots = config.get_screenshots_dir()
        self._gemini     = None
        self._setup_gemini()

    def _setup_gemini(self):
        try:
            import google.generativeai as genai
            api_key = self.config.get_api_key("google")
            if api_key:
                genai.configure(api_key=api_key)
                self._gemini = genai.GenerativeModel("gemini-2.5-flash")
        except Exception as e:
            log.warning("VisionTool Gemini setup: " + str(e))

    # ─── screenshot ──────────────────────────────────────────────────────────

    def screenshot(self, region: str = "full", save: bool = True) -> dict:
        """
        Cattura screenshot con mss.
        region: "full" | "window" | "half_top" | "half_bottom"
        Ritorna: {"path": str, "base64": str, "width": int, "height": int}
        """
        try:
            import mss
            import mss.tools
            from PIL import Image
            import io

            with mss.mss() as sct:
                monitor = sct.monitors[0]  # monitor principale

                if region == "half_top":
                    monitor = {**monitor, "height": monitor["height"] // 2}
                elif region == "half_bottom":
                    h = monitor["height"] // 2
                    monitor = {**monitor, "top": monitor["top"] + h, "height": h}

                raw = sct.grab(monitor)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

            # Ridimensiona se troppo grande (Gemini Vision: max 4MB)
            max_w = 1280
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)

            # Converti in PNG bytes
            buf = __import__("io").BytesIO()
            img.save(buf, format="PNG", optimize=True)
            png_bytes = buf.getvalue()

            b64 = base64.b64encode(png_bytes).decode("utf-8")
            path_str = ""

            if save:
                ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_path = self.screenshots / ("screenshot_" + ts + ".png")
                out_path.write_bytes(png_bytes)
                path_str = str(out_path)

            return {
                "path":   path_str,
                "base64": b64,
                "width":  img.width,
                "height": img.height,
                "format": "PNG",
            }

        except ImportError as e:
            return {"error": "❌ Dipendenza mancante: " + str(e) + " — installa mss e pillow"}
        except Exception as e:
            return {"error": "❌ Screenshot fallito: " + str(e)}

    # ─── vision_analyze ──────────────────────────────────────────────────────

    def vision_analyze(self, task: str = "", last_action: str = "",
                       screenshot_b64: str = "", region: str = "full") -> dict:
        """
        Cattura screenshot (se non fornito) e lo analizza con Gemini Vision.
        Ritorna: {screen_state, suggested_action, confidence, coordinates}
        """
        if not self._gemini:
            return {"error": "❌ Gemini Vision non configurato (GOOGLE_API_KEY mancante)"}

        # Cattura screenshot se non fornito
        if not screenshot_b64:
            snap = self.screenshot(region=region, save=True)
            if "error" in snap:
                return snap
            screenshot_b64 = snap["base64"]

        try:
            import google.generativeai as genai

            prompt = self._build_vision_prompt(task, last_action)

            image_part = {
                "mime_type": "image/png",
                "data":      screenshot_b64,
            }

            resp = self._gemini.generate_content([prompt, image_part])
            text = resp.text.strip()

            # Prova a parsare come JSON
            import json, re
            clean = re.sub(r"```json\s*|```\s*", "", text).strip()
            try:
                return json.loads(clean)
            except json.JSONDecodeError:
                return {"screen_state": text, "confidence": 0.5, "raw": True}

        except Exception as e:
            return {"error": "❌ Vision analyze fallito: " + str(e)}

    def _build_vision_prompt(self, task: str, last_action: str) -> str:
        task_section   = ("Task corrente: " + task) if task else "Analisi generale dello schermo."
        action_section = ("Ultima azione: " + last_action) if last_action else ""

        return (
            "Sei DUST AI Vision. Analizza questo screenshot di Windows 11.\n\n"
            + task_section + "\n"
            + action_section + "\n\n"
            "Rispondi SOLO con JSON:\n"
            "{\n"
            '  "screen_state": "descrizione breve di cosa vedi",\n'
            '  "task_relevant": "elementi rilevanti per il task",\n'
            '  "suggested_action": {\n'
            '    "tool": "mouse_click|keyboard_type|keyboard_hotkey|sys_exec",\n'
            '    "params": {"x": 0, "y": 0},\n'
            '    "reason": "perché questa azione"\n'
            "  },\n"
            '  "confidence": 0.9,\n'
            '  "found_elements": ["lista elementi UI trovati"]\n'
            "}"
        )

    # ─── find_element ─────────────────────────────────────────────────────────

    def find_element(self, description: str, region: str = "full") -> dict:
        """
        Trova un elemento UI nello schermo per descrizione testuale.
        Ritorna: {"found": bool, "coordinates": {"x":0,"y":0}, "confidence": 0.9}
        """
        snap = self.screenshot(region=region, save=False)
        if "error" in snap:
            return snap

        if not self._gemini:
            return {"error": "❌ Gemini non disponibile"}

        try:
            import google.generativeai as genai
            import json, re

            prompt = (
                'Trova l\'elemento UI: "' + description + '"\n\n'
                "Rispondi SOLO con JSON:\n"
                '{"found": true, "element_type": "button", '
                '"coordinates": {"x": 450, "y": 320}, "confidence": 0.95, '
                '"description": "cosa vedi"}\n'
                'Se non trovato: {"found": false, "reason": "perché"}'
            )

            image_part = {"mime_type": "image/png", "data": snap["base64"]}
            resp = self._gemini.generate_content([prompt, image_part])
            clean = re.sub(r"```json\s*|```\s*", "", resp.text.strip()).strip()

            try:
                return json.loads(clean)
            except json.JSONDecodeError:
                return {"found": False, "reason": "Parse error: " + resp.text[:100]}

        except Exception as e:
            return {"found": False, "reason": "❌ " + str(e)}
