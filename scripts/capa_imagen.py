"""
CAPA IMAGEN — Generación completa del trofeo con gpt-image-1
Agente 3 — Sustain Awards Custom

A diferencia del Agente 2 (que genera fondos para overlay),
esta capa genera el trofeo completo: forma + material + texto integrado.

La IA crea la visualización del objeto físico de una vez.
"""

import os
import base64
import time
from io import BytesIO

from PIL import Image, ImageEnhance, ImageFilter

from scripts.config import (
    USE_DALLE,
    IMAGE_QUALITY as CALIDAD_IMAGEN,
    IMAGE_PROVIDER,
    IMAGE_MODEL_OPENAI,
)


# ─── Cliente OpenAI ──────────────────────────────────────────────────────────

def _cliente():
    import openai
    return openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


# ─── Helpers de prompt ───────────────────────────────────────────────────────

def _construir_prompt_hormigon_acero(
    forma: dict,
    colores_marca: list[str],
    texto_premiado: str,
    texto_award: str,
    nombre_empresa: str,
) -> str:
    """
    Construye el prompt completo para generar un trofeo de Hormigón y Acero.
    Integra forma escultórica, colores de marca y texto del premiado.
    """
    color_principal = colores_marca[0] if colores_marca else "#4A4A4A"
    color_acento    = colores_marca[1] if len(colores_marca) > 1 else "#A0A0A0"

    texto_bloque = ""
    if texto_premiado or texto_award:
        partes = []
        if texto_award:
            partes.append(f'"{texto_award}"')
        if texto_premiado:
            partes.append(f'"{texto_premiado}"')
        if nombre_empresa:
            partes.append(f'"{nombre_empresa}"')
        texto_bloque = (
            f"The trophy surface has engraved or embossed text: {' / '.join(partes)}. "
            "Text is cleanly integrated into the concrete or steel surface. "
        )

    return (
        f"{forma['descripcion_prompt']}. "
        f"Award trophy made of concrete and steel. "
        f"Brand accent color {color_principal} appears as painted steel elements, "
        f"colored inlays, or industrial coating on metal parts. "
        f"Secondary accent {color_acento} used for contrast details. "
        f"{texto_bloque}"
        "Studio product photography, pure white background, "
        "soft directional lighting with subtle shadow at base. "
        "Professional award photography, sharp focus, photorealistic render. "
        "Portrait orientation, trophy centered in frame with breathing room. "
        "No text or logos floating outside the trophy object itself."
    )


# ─── Fallback PIL ────────────────────────────────────────────────────────────

def _trofeo_pil_fallback(
    ancho: int,
    alto: int,
    color_principal: str,
    concepto: dict,
) -> Image.Image:
    """
    Genera una imagen de placeholder cuando USE_DALLE=False o falla la API.
    Útil para modo demo sin coste de API.
    """
    from PIL import ImageDraw, ImageFont

    img = Image.new("RGB", (ancho, alto), "#F5F5F3")
    draw = ImageDraw.Draw(img)

    # Forma simplificada: rectángulo con color de marca
    cx = ancho // 2
    base_y = int(alto * 0.75)
    top_y  = int(alto * 0.15)
    w_trofeo = int(ancho * 0.35)

    try:
        r, g, b = int(color_principal[1:3], 16), int(color_principal[3:5], 16), int(color_principal[5:7], 16)
        color_rgb = (r, g, b)
        color_acero = (min(r + 40, 255), min(g + 40, 255), min(b + 40, 255))
    except Exception:
        color_rgb  = (74, 74, 74)
        color_acero = (120, 120, 120)

    # Columna principal (hormigón simulado)
    draw.rectangle(
        [cx - w_trofeo // 2, top_y, cx + w_trofeo // 2, base_y],
        fill=(210, 205, 198),
    )
    # Franja de acero con color de marca
    franja_h = int((base_y - top_y) * 0.15)
    draw.rectangle(
        [cx - w_trofeo // 2, top_y + franja_h, cx + w_trofeo // 2, top_y + franja_h * 2],
        fill=color_rgb,
    )
    # Base de acero
    draw.rectangle(
        [cx - int(w_trofeo * 0.7), base_y, cx + int(w_trofeo * 0.7), base_y + 30],
        fill=color_acero,
    )

    # Texto de concepto
    pid = concepto.get("proposal_id", "?")
    forma_nombre = concepto.get("forma_escultorica", "")
    draw.text(
        (cx, int(alto * 0.88)),
        f"[Demo] P{pid} — {forma_nombre}",
        fill=(100, 100, 100),
        anchor="mm",
    )

    return img


# ─── Función principal ────────────────────────────────────────────────────────

def generar_trofeo(
    concepto: dict,
    material_config: dict,
    brand_context: dict,
    award: dict,
) -> Image.Image:
    """
    Genera la imagen completa del trofeo para un concepto dado.

    Args:
        concepto:        Brief de diseño de capa1_ia (incluye forma_escultorica, colores)
        material_config: Entrada del material_catalog.json para este material
        brand_context:   Contexto de marca de capa0 (colores canónicos, nombre)
        award:           Texto del premiado (headline, recipient, subtitle)

    Returns:
        Imagen PIL en RGB del trofeo completo.
    """
    pid = concepto.get("proposal_id", "?")
    dims = material_config.get("dimensiones_output", {"ancho": 1024, "alto": 1536})
    ancho, alto = dims["ancho"], dims["alto"]

    # Colores de marca
    canonical = brand_context.get("canonical_palette") or []
    if not canonical:
        analysis = brand_context.get("brand_analysis", {}).get("colors", {})
        canonical = [
            c for c in [analysis.get("primary"), analysis.get("secondary"), analysis.get("accent")]
            if c and c.startswith("#") and len(c) == 7
        ]
    color_principal = canonical[0] if canonical else "#4A4A4A"

    # Forma escultórica asignada por capa1
    forma_id = concepto.get("forma_escultorica", "columnar")
    formas   = {f["id"]: f for f in material_config.get("formas_esculturicas", [])}
    forma    = formas.get(forma_id, {"id": forma_id, "nombre": forma_id, "descripcion_prompt": "abstract trophy form"})

    # Textos del premiado
    texto_premiado = award.get("recipient", "")
    texto_award    = award.get("headline", "")
    nombre_empresa = brand_context.get("brand_analysis", {}).get("brand_name", "")

    if not USE_DALLE:
        print(f"  [Capa-Imagen] P{pid} → PIL fallback (USE_DALLE=False)")
        return _trofeo_pil_fallback(ancho, alto, color_principal, concepto)

    prompt = _construir_prompt_hormigon_acero(
        forma=forma,
        colores_marca=canonical,
        texto_premiado=texto_premiado,
        texto_award=texto_award,
        nombre_empresa=nombre_empresa,
    )

    print(f"  [Capa-Imagen] P{pid} · forma={forma_id} · gpt-image-1 ({CALIDAD_IMAGEN})")
    print(f"    prompt[:120]: {prompt[:120]}...")

    for intento in range(3):
        try:
            client = _cliente()
            size   = "1024x1536" if alto > ancho else "1024x1024"

            respuesta = client.images.generate(
                model=IMAGE_MODEL_OPENAI,
                prompt=prompt,
                n=1,
                size=size,
                quality=CALIDAD_IMAGEN,
                output_format="png",
                response_format="b64_json",
            )

            datos_b64 = respuesta.data[0].b64_json
            img_bytes = base64.b64decode(datos_b64)
            img = Image.open(BytesIO(img_bytes)).convert("RGB")

            # Normalizar al tamaño de salida si la API devuelve diferente
            if img.size != (ancho, alto):
                img = img.resize((ancho, alto), Image.LANCZOS)

            print(f"  [Capa-Imagen] P{pid} ✓ generado ({img.size[0]}×{img.size[1]}px)")
            return img

        except Exception as e:
            if intento < 2:
                print(f"  [Capa-Imagen] P{pid} · intento {intento+1} fallido: {e} — reintentando...")
                time.sleep(2 ** intento)
            else:
                print(f"  [Capa-Imagen] P{pid} · error persistente: {e} — usando PIL fallback")
                return _trofeo_pil_fallback(ancho, alto, color_principal, concepto)
