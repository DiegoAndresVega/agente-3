"""
CAPA 3 — Compositor
Agente 3 — Sustain Awards Custom

A diferencia del Agente 2, aquí NO hay foto de trofeo base.
La imagen del trofeo llega ya generada por capa_imagen.py.
Esta capa normaliza, encuadra y exporta al formato final.

También mantiene `cargar_modelo_material` como interfaz unificada
para que test_server.py pueda cargar specs del material.
"""

import json
from pathlib import Path

from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR     = PROJECT_ROOT / "data"


def cargar_modelo_material(id_material: str) -> dict:
    """Carga la especificación del material desde material_catalog.json."""
    catalog_path = DATA_DIR / "material_catalog.json"
    with open(catalog_path, encoding="utf-8") as f:
        catalogo = json.load(f)
    for material in catalogo["materiales"]:
        if material["id"] == id_material:
            return material
    raise ValueError(f"Material '{id_material}' no encontrado en material_catalog.json")


# Alias de compatibilidad — test_server puede llamar a cargar_modelo_trofeo en el futuro
def cargar_modelo_trofeo(id_modelo: str) -> dict:
    """Alias de compatibilidad con la interfaz del Agente 2."""
    return cargar_modelo_material(id_modelo)


def componer(
    trofeo_img: Image.Image,
    material_config: dict,
) -> Image.Image:
    """
    Normaliza la imagen del trofeo generada por capa_imagen y la devuelve lista para exportar.

    En el Agente 3 no hay compositing sobre foto: el trofeo ya es la imagen final.
    Esta función garantiza:
      - Tamaño de salida correcto (según material_config.dimensiones_output)
      - Modo RGB para exportación JPG
      - Encuadre limpio (centra el trofeo si tiene padding desigual)

    Args:
        trofeo_img:      Imagen PIL en RGB generada por capa_imagen.py
        material_config: Entrada del material_catalog.json

    Returns:
        Imagen PIL en RGB lista para .save() como JPG.
    """
    dims   = material_config.get("dimensiones_output", {"ancho": 1024, "alto": 1536})
    target = (dims["ancho"], dims["alto"])

    img = trofeo_img.convert("RGB")

    if img.size != target:
        img = _encuadrar_con_fondo(img, target)

    pid_log = "(sin pid)"
    print(f"  [Capa 3] Trofeo normalizado {img.size[0]}×{img.size[1]}px  {pid_log}")
    return img


def _encuadrar_con_fondo(
    img: Image.Image,
    target: tuple[int, int],
    fondo_color: tuple[int, int, int] = (248, 248, 246),
) -> Image.Image:
    """
    Redimensiona preservando aspecto y centra sobre fondo claro.
    Equivalente a "object-fit: contain" de CSS.
    """
    img_ratio    = img.width  / img.height
    target_ratio = target[0] / target[1]

    if img_ratio > target_ratio:
        nuevo_ancho = target[0]
        nuevo_alto  = int(target[0] / img_ratio)
    else:
        nuevo_alto  = target[1]
        nuevo_ancho = int(target[1] * img_ratio)

    img_resized = img.resize((nuevo_ancho, nuevo_alto), Image.LANCZOS)

    fondo = Image.new("RGB", target, fondo_color)
    offset_x = (target[0] - nuevo_ancho) // 2
    offset_y = (target[1] - nuevo_alto)  // 2
    fondo.paste(img_resized, (offset_x, offset_y))
    return fondo
