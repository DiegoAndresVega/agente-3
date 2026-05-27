"""
prompts_manager.py — Gestión dinámica de prompts del Agente 3

Los prompts se almacenan en prompts.json (sobreescritura de los defaults del código).
Si prompts.json no existe, se usan los defaults hardcodeados.
Los cambios en prompts.json surten efecto inmediatamente sin reiniciar el servidor.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_FILE = PROJECT_ROOT / "prompts.json"
HISTORY_DIR  = PROJECT_ROOT / "outputs" / "prompts_history"


# ─── Nombres y descripciones de cada prompt ──────────────────────────────────

PROMPT_KEYS = {
    "prompt_b_hormigon_acero": {
        "label":       "1. Conceptos de diseño — Claude Sonnet",
        "descripcion": "Controla la geometría y silueta del trofeo. "
                       "Para forzar cambios visibles, especifica proporciones numéricas concretas "
                       "(altura, anchura, grosor) y geometrías exactas. "
                       "No controla iluminación, fondo, ángulo de cámara ni textura.",
    },
    "prompt_base_trofeo_lora": {
        "label":       "2. Iluminación y fondo — LoRA (Replicate)",
        "descripcion": "Controla el color y tono del fondo, y la iluminación de la imagen "
                       "(dirección, intensidad, temperatura de color cálido/frío). "
                       "No controla ángulo de cámara, escala, encuadre ni textura — "
                       "esos aspectos están fijados por el modelo entrenado.",
    },
    "prompt_textura_hormigon": {
        "label":       "3. Textura y material — gpt-image-1 (OpenAI)",
        "descripcion": "Controla el material y acabado superficial del trofeo. "
                       "Puede cambiar a cualquier material (hormigón, mármol, metal oxidado, madera, lava...), "
                       "su textura, color y acabado (mate, pulido, rugoso). "
                       "Es la sección de mayor impacto visual.",
    },
}


# ─── Cargar prompts ───────────────────────────────────────────────────────────

def cargar_prompts() -> dict:
    """
    Devuelve los prompts activos.
    Si prompts.json existe, sus valores sobreescriben los defaults del código.
    """
    if PROMPTS_FILE.exists():
        try:
            with open(PROMPTS_FILE, encoding="utf-8") as f:
                guardados = json.load(f)
            return guardados.get("prompts", {})
        except Exception:
            pass
    return {}


def guardar_prompts(nuevos_prompts: dict, motivo: str = "") -> None:
    """
    Guarda prompts en prompts.json y crea una copia en el historial.
    Solo guarda las claves que difieren del valor por defecto.
    """
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # Backup del estado anterior
    if PROMPTS_FILE.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(PROMPTS_FILE, HISTORY_DIR / f"prompts_{ts}.json")

    datos = {
        "ultima_modificacion": datetime.now().isoformat(),
        "motivo":              motivo,
        "prompts":             nuevos_prompts,
    }
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def cargar_historial() -> list:
    """Devuelve los últimos 10 cambios guardados."""
    if not HISTORY_DIR.exists():
        return []
    archivos = sorted(HISTORY_DIR.glob("prompts_*.json"), reverse=True)[:10]
    historial = []
    for p in archivos:
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            historial.append({
                "archivo":  p.name,
                "fecha":    d.get("ultima_modificacion", ""),
                "motivo":   d.get("motivo", ""),
            })
        except Exception:
            pass
    return historial


def revertir_ultimo() -> tuple[bool, str]:
    """
    Restaura el estado anterior de los prompts.
    - Si hay historial: restaura el backup más reciente.
    - Si no hay historial pero existe prompts.json: lo elimina (vuelve a defaults del código).
    - Si no hay nada: nada que revertir.
    Devuelve (ok, mensaje).
    """
    archivos = sorted(HISTORY_DIR.glob("prompts_*.json"), reverse=True) if HISTORY_DIR.exists() else []

    if archivos:
        shutil.copy(archivos[0], PROMPTS_FILE)
        archivos[0].unlink()
        return True, "Revertido al estado anterior del historial."

    if PROMPTS_FILE.exists():
        PROMPTS_FILE.unlink()
        return True, "Revertido a los valores por defecto del programa (prompts del código fuente)."

    return False, "No hay cambios que revertir — el programa ya usa los valores por defecto."
