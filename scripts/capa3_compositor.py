"""
CAPA 3 — Compositor
Sustain Awards

Proyecta la imagen del diseño (generada por Capa 2) sobre la fotografía
real del trofeo en las coordenadas calibradas.
"""

import json
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR     = PROJECT_ROOT / "data"


def cargar_modelo_trofeo(id_modelo: str) -> dict:
    """Carga la especificación del modelo de trofeo desde el catálogo."""
    with open(DATA_DIR / "trophy_catalog.json", encoding="utf-8") as f:
        catalogo = json.load(f)
    for modelo in catalogo["modelos"]:
        if modelo["id"] == id_modelo:
            return modelo
    raise ValueError(f"Modelo de trofeo '{id_modelo}' no encontrado en el catálogo")


def componer(diseno_rgba: Image.Image,
             trofeo_path: str,
             zona: dict) -> Image.Image:
    """
    Pega el diseño RGBA sobre la foto del trofeo en las coordenadas calibradas.

    Parámetros:
        diseno_rgba – imagen RGBA del diseño (Capa 2 output)
        trofeo_path – ruta relativa a la foto base del trofeo
        zona        – dict con x, y, ancho, alto (de trophy_catalog.json)

    Devuelve imagen RGB lista para guardar como JPG.
    """
    trofeo = Image.open(trofeo_path).convert("RGBA")

    # Redimensionar el diseño exactamente al tamaño de la zona imprimible
    diseno_final = diseno_rgba.resize(
        (zona["ancho"], zona["alto"]), Image.LANCZOS
    )

    if diseno_final.mode != "RGBA":
        diseno_final = diseno_final.convert("RGBA")
    trofeo.paste(diseno_final, (zona["x"], zona["y"]), diseno_final)
    return trofeo.convert("RGB")
