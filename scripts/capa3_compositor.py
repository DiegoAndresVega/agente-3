"""
CAPA 3 — Compositor
Sustain Awards

Proyecta la imagen del diseño (generada por Capa 2) sobre la fotografía
real del trofeo en las coordenadas calibradas.

Soporta dos modos según zona_imprimible.forma:
  - rectangular (default) : paste simple en bounding box
  - mascara               : recorte por polígono irregular via máscara PNG
"""

import json
from pathlib import Path

from PIL import Image, ImageFilter


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
    Pega el diseño sobre la foto del trofeo según el modo de la zona imprimible.

    - forma='mascara'     → recorte por polígono irregular (copetin, etc.)
    - forma=rectangular   → paste directo en bounding box (totem, placa, etc.)
    """
    forma = zona.get("forma", "rectangular")
    print(f"  [Capa 3] Compositing → {forma}  ({zona.get('ancho','?')}×{zona.get('alto','?')}px)")
    if forma == "mascara":
        return _componer_mascara(diseno_rgba, trofeo_path, zona)
    return _componer_rectangular(diseno_rgba, trofeo_path, zona)


def _componer_rectangular(diseno_rgba: Image.Image,
                           trofeo_path: str,
                           zona: dict) -> Image.Image:
    """Modo clásico: escala el diseño al bounding box y lo pega directamente."""
    trofeo = Image.open(trofeo_path).convert("RGBA")
    diseno_final = diseno_rgba.resize((zona["ancho"], zona["alto"]), Image.LANCZOS)
    if diseno_final.mode != "RGBA":
        diseno_final = diseno_final.convert("RGBA")
    trofeo.paste(diseno_final, (zona["x"], zona["y"]), diseno_final)
    return trofeo.convert("RGB")


def _componer_mascara(diseno_rgba: Image.Image,
                      trofeo_path: str,
                      zona: dict) -> Image.Image:
    """
    Modo máscara: el diseño se escala al bounding box y se recorta
    con la máscara de polígono irregular antes de pegarlo sobre el trofeo.
    """
    trofeo = Image.open(trofeo_path).convert("RGBA")
    tw, th = trofeo.size

    # 1. Escalar el diseño al bounding box de la zona imprimible
    bb_x, bb_y = zona["x"], zona["y"]
    bb_w, bb_h = zona["ancho"], zona["alto"]
    diseno = diseno_rgba.resize((bb_w, bb_h), Image.LANCZOS).convert("RGBA")

    # 2. Cargar la máscara completa y recortar al bounding box
    mascara_path = PROJECT_ROOT / zona["mascara"]
    mascara_full = Image.open(mascara_path).convert("L")   # escala de grises
    mascara_crop = mascara_full.crop((bb_x, bb_y, bb_x + bb_w, bb_y + bb_h))

    # 3. Aplicar la máscara como canal alpha del diseño
    #    Blanco (255) en la máscara = visible | Negro (0) = transparente
    # Anti-aliasing: blur suaviza los dientes de sierra en contornos curvos
    mascara_crop = mascara_crop.filter(ImageFilter.GaussianBlur(radius=3))
    diseno.putalpha(mascara_crop)

    # 4. Pegar el diseño recortado sobre el trofeo en la posición correcta
    trofeo.paste(diseno, (bb_x, bb_y), diseno)

    return trofeo.convert("RGB")
