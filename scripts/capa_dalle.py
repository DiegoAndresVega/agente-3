"""
CAPA DALLE — Generación de fondos artísticos con OpenAI gpt-image-1
Sustain Awards

Funciones:
  generar_fondo()       – fondo artístico para el trofeo
  generar_texto_capa()  – tipografía premium con fondo transparente
"""

import os
import base64
import urllib.request
from io import BytesIO

from PIL import Image

# Coste orientativo: quality="low" ~$0.011/imagen
#                    quality="medium" ~$0.042/imagen
CALIDAD_IMAGEN = "low"

# ─── Switch global ────────────────────────────────────────────────────────────
# True  → usa gpt-image-1 para generar imágenes (requiere OPENAI_API_KEY)
# False → fondo sólido de color de marca, sin llamadas a OpenAI
USE_DALLE = True


# ─── Fondo artístico ──────────────────────────────────────────────────────────

def generar_fondo(prompt: str, ancho: int, alto: int,
                  color_fallback: str = "#1A1A2E") -> Image.Image:
    """
    Genera un fondo artístico con gpt-image-1.
    Si prompt vacío → fondo sólido monocromo (sin llamar a la API).
    """
    if not USE_DALLE or not prompt or not prompt.strip():
        return _fondo_solido(color_fallback, ancho, alto)

    try:
        client = _cliente()
        size   = "1024x1536" if alto > ancho else "1024x1024"
        img    = _llamar_api(client, prompt, size)
        return _resize_and_crop(img, ancho, alto)
    except Exception as e:
        print(f"  [DALLE-FONDO] Error: {e} → usando fallback")
        return _fondo_solido(color_fallback, ancho, alto)


# ─── Capa de texto tipográfico ────────────────────────────────────────────────

def generar_texto_dalle(textos: dict, concepto: dict) -> tuple[Image.Image, str] | tuple[None, None]:
    """
    Genera tipografía artística sobre fondo sólido puro (#000000 o #FFFFFF).

    El fondo sólido puro permite a PIL extraer los píxeles de texto mediante
    distancia euclidiana de color (chroma key), sin ambigüedades de anti-alias.

    Parámetros:
        textos   – {"headline": "...", "recipient": "...", "subtitle": "...", "fecha": "..."}
        concepto – concepto JSON con campos "text_prompt" y "text_bg_dark"

    Retorna (Image RGBA 1024x1536, bg_hex) o (None, None) si falla o USE_DALLE=False.
    NO hace resize/crop — la imagen sale en 1024x1536 para que el chroma key
    trabaje a máxima resolución antes de escalar.
    """
    if not USE_DALLE:
        return None, None

    text_prompt  = concepto.get("text_prompt", "").strip()
    text_bg_dark = concepto.get("text_bg_dark", True)

    if not text_prompt:
        return None, None

    headline  = textos.get("headline",  "")
    recipient = textos.get("recipient", "")
    subtitle  = textos.get("subtitle",  "")
    fecha     = textos.get("fecha",     "")

    bg_hex  = "#000000" if text_bg_dark else "#FFFFFF"
    bg_name = "pure solid black #000000" if text_bg_dark else "pure solid white #FFFFFF"

    layout = concepto.get("text_style", {}).get("layout", "stacked")

    _layout_instructions = {
        "spread": (
            "SPREAD LAYOUT — elements are SPATIALLY SEPARATED with wide vertical gaps: "
            "award title in the UPPER ZONE of the image (top quarter). "
            "Recipient name placed EXACTLY IN THE CENTER of the image with generous empty space above and below. "
            "Organization name in the LOWER ZONE (bottom quarter). "
            "Do NOT stack elements close together — each floats independently with breathing room."
        ),
        "staggered": (
            "STAGGERED ASYMMETRIC LAYOUT — intentional asymmetry: "
            "award title small and centered horizontally, placed in the upper area. "
            "Recipient name MASSIVE and LEFT-ALIGNED (flush to the left of the center zone). "
            "Organization name small and RIGHT-ALIGNED (flush to the right of the center zone). "
            "This asymmetry is intentional — it is the design."
        ),
        "billboard": (
            "BILLBOARD LAYOUT — the recipient name IS THE ENTIRE DESIGN: "
            "recipient name fills the MAXIMUM possible space at enormous scale, dominating the image. "
            "Award title in tiny caption size at the very top (almost invisible, very small). "
            "Organization name in tiny caption size at the very bottom (almost invisible, very small). "
            "The recipient name is the only visual focus — make it as large as possible."
        ),
        "stacked": (
            "STACKED LAYOUT — all elements grouped as a compact centered block "
            "with consistent tight spacing between them."
        ),
    }
    composicion  = _layout_instructions.get(layout, _layout_instructions["stacked"])
    font_family  = concepto.get("text_style", {}).get("font_family")
    font_instr   = f"Use {font_family} typeface throughout. " if font_family else ""

    partes = []
    if headline:
        partes.append(f"award title '{headline}' at medium size")
    if recipient:
        partes.append(f"recipient name '{recipient}' at HERO size (the largest element)")
    if subtitle:
        partes.append(f"organization '{subtitle}' at small size")
    if fecha:
        partes.append(f"date '{fecha}' at tiny caption size")

    if not partes:
        return None, None

    jerarquia = ", ".join(partes)

    prompt = (
        f"Award typography image on {bg_name} background. "
        f"Solid color background only — background is {bg_name} and nothing else. "
        "No gradients, no textures, no shapes, no decorations on the background. "
        "Vertical portrait orientation. "
        f"COMPOSITION: {composicion} "
        f"Text elements: {jerarquia}. "
        f"{font_instr}"
        f"Typography style: {text_prompt}. "
        "All text strictly within center 70% of image width — "
        "wide empty margins on left and right sides. "
        "No logos, no people, no decorative shapes. "
        "Pure typography on solid background only."
    )

    try:
        client = _cliente()
        img    = _llamar_api(client, prompt, "1024x1536")
        return img, bg_hex
    except Exception as e:
        print(f"  [DALLE-TEXTO] Error: {e} → PIL fallback")
        return None, None


# ─── Utilidades privadas ──────────────────────────────────────────────────────

def _cliente():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY no encontrada.\n"
            "  Configúrala con: set OPENAI_API_KEY=sk-proj-..."
        )
    from openai import OpenAI
    return OpenAI(api_key=api_key)


def _llamar_api(client, prompt: str, size: str) -> Image.Image:
    response = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=size,
        quality=CALIDAD_IMAGEN,
        n=1,
    )
    item = response.data[0]
    if hasattr(item, "b64_json") and item.b64_json:
        img_bytes = base64.b64decode(item.b64_json)
    else:
        with urllib.request.urlopen(item.url) as resp:
            img_bytes = resp.read()
    return Image.open(BytesIO(img_bytes)).convert("RGBA")


def _resize_and_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    """Escala para llenar el canvas y recorta centrado."""
    src_w, src_h = img.size
    ratio = max(w / src_w, h / src_h)
    new_w = int(src_w * ratio)
    new_h = int(src_h * ratio)
    img   = img.resize((new_w, new_h), Image.LANCZOS)
    left  = (new_w - w) // 2
    top   = (new_h - h) // 2
    return img.crop((left, top, left + w, top + h))


def _fondo_solido(hex_color: str, w: int, h: int) -> Image.Image:
    h_str = hex_color.lstrip("#")
    r = int(h_str[0:2], 16)
    g = int(h_str[2:4], 16)
    b = int(h_str[4:6], 16)
    return Image.new("RGBA", (w, h), (r, g, b, 255))
