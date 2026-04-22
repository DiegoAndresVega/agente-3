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

import numpy as np
from PIL import Image, ImageDraw

# Coste orientativo: quality="low" ~$0.011/imagen
#                    quality="medium" ~$0.042/imagen
CALIDAD_IMAGEN = "medium"

# ─── Switch global ────────────────────────────────────────────────────────────
# True  → usa gpt-image-1 para generar imágenes (requiere OPENAI_API_KEY)
# False → fondo creativo generado en PIL, sin llamadas a OpenAI
USE_DALLE = True


# ─── Fondo artístico ──────────────────────────────────────────────────────────

def generar_fondo(prompt: str, ancho: int, alto: int,
                  color_fallback: str = "#1A1A2E",
                  concepto: dict | None = None) -> Image.Image:
    """
    Genera un fondo artístico con gpt-image-1.
    Si prompt vacío o USE_DALLE=False → fondo creativo por concepto (PIL).
    """
    if not USE_DALLE or not prompt or not prompt.strip():
        return _fondo_concepto(color_fallback, ancho, alto, concepto)

    try:
        client = _cliente()
        size   = "1024x1536" if alto > ancho else "1024x1024"
        img    = _llamar_api(client, prompt, size)
        print(f"  [DALLE-FONDO] ✓ Imagen recibida ({size}, quality={CALIDAD_IMAGEN})")
        return _resize_and_crop(img, ancho, alto)
    except Exception as e:
        print(f"  [DALLE-FONDO] Error: {e} → usando fallback creativo")
        return _fondo_concepto(color_fallback, ancho, alto, concepto)


# ─── Capa de texto tipográfico ────────────────────────────────────────────────

def generar_texto_dalle(textos: dict, concepto: dict) -> tuple[Image.Image, str] | tuple[None, None]:
    """
    Genera tipografía artística sobre fondo sólido puro (#000000 o #FFFFFF).
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


# ─── Generadores de fondos creativos (PIL) ───────────────────────────────────

def _fondo_concepto(color_fallback: str, w: int, h: int, concepto: dict | None) -> Image.Image:
    """Elige el generador adecuado según concepto y tono de fondo."""
    if concepto is None:
        return _fondo_solido(color_fallback, w, h)

    pid     = concepto.get("proposal_id", 1)
    i6      = (pid - 1) % 6
    bg_tone = concepto.get("bg_tone", "dark")
    sec     = (concepto.get("_secondary") or "").strip()
    acc     = (concepto.get("_accent") or "").strip()

    if bg_tone == "light":
        return _fondo_editorial(color_fallback, w, h, is_minimal=(i6 == 4))

    if i6 == 5:   # P6 — MARCA PURA
        return _fondo_marca_pura(color_fallback, sec or acc, w, h)
    elif i6 == 0: # P1 — PREMIUM OSCURO (fallback si DALLE falla)
        return _fondo_oscuro_cinematico(color_fallback, sec or acc, w, h)
    elif i6 == 2: # P3 — GRÁFICO AUDAZ (fallback)
        return _fondo_geometrico_bold(color_fallback, sec or acc, w, h)
    elif i6 == 3: # P4 — BILLBOARD IMPACTO (fallback)
        return _fondo_radial_impacto(color_fallback, sec or acc, w, h)
    else:
        return _fondo_solido(color_fallback, w, h)


def _fondo_editorial(brand_hex: str, w: int, h: int, is_minimal: bool = False) -> Image.Image:
    """
    P2 / P5: fondo editorial blanco.
    P2 → papel premium con toque de color de marca en esquina superior.
    P5 → papel limpio con dot-grid ultrasuave del color de marca.
    """
    r, g, b = _hex_rgb(brand_hex)

    base = np.full((h, w, 4), 255, dtype=np.uint8)

    # Grano de papel sutil (±4 valores, seed fijo para reproducibilidad)
    rng = np.random.default_rng(42)
    grain = rng.integers(-4, 5, (h, w), dtype=np.int16)
    for c in range(3):
        base[:, :, c] = np.clip(base[:, :, c].astype(np.int16) + grain, 249, 255).astype(np.uint8)

    if not is_minimal:
        # P2: tono muy sutil de marca en la esquina superior derecha (máx 5%)
        ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
        xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
        dist = np.sqrt((1.0 - xs[None, :]) ** 2 + ys[:, None] ** 2) / 1.42
        mask = np.clip((1.0 - dist * 2.2), 0.0, 1.0) * 0.055
        for ci, cv in enumerate([r, g, b]):
            base[:, :, ci] = np.clip(
                base[:, :, ci].astype(np.float32) * (1 - mask) + cv * mask, 0, 255
            ).astype(np.uint8)
    else:
        # P5: dot-grid minimalista — un punto por cada 36px, 6% del color de marca
        ym = np.arange(h) % 36 == 18
        xm = np.arange(w) % 36 == 18
        grid = ym[:, None] & xm[None, :]
        for ci, cv in enumerate([r, g, b]):
            col = base[:, :, ci].astype(np.float32)
            col[grid] = col[grid] * 0.94 + cv * 0.06
            base[:, :, ci] = np.clip(col, 0, 255).astype(np.uint8)

    return Image.fromarray(base, "RGBA")


def _fondo_marca_pura(primary_hex: str, secondary_hex: str, w: int, h: int) -> Image.Image:
    """
    P6 — MARCA PURA: gradiente radial del primario + banda diagonal del secundario
    + arco watermark blanco. Transforma un color plano en un backdrop de evento.
    """
    r, g, b = _hex_rgb(primary_hex)

    # Gradiente radial: centro 25% más claro, esquinas 25% más oscuras
    ys = np.linspace(-1.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(-1.0, 1.0, w, dtype=np.float32)
    dist = np.sqrt(ys[:, None] ** 2 + xs[None, :] ** 2) / 1.42  # 0=centro 1=esquina
    factor = 1.25 - dist * 0.50  # 1.25 en centro → 0.75 en esquina

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(r * factor, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(g * factor, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(b * factor, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    img = Image.fromarray(arr, "RGBA")

    # Banda diagonal del secundario o tint del primario
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
    else:
        sr = min(255, int(r + (255 - r) * 0.38))
        sg = min(255, int(g + (255 - g) * 0.38))
        sb = min(255, int(b + (255 - b) * 0.38))

    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    slant = int(h * 0.38)
    bw    = int(w * 0.14)
    cx    = int(w * 0.62)
    pts = [(cx, 0), (cx + bw, 0), (cx + bw - slant, h), (cx - slant, h)]
    od.polygon(pts, fill=(sr, sg, sb, 42))  # ~16% opacity
    img = Image.alpha_composite(img, ov)

    # Arco watermark grande en blanco (esquina inferior derecha, parcialmente fuera)
    circ_d = int(min(w, h) * 1.05)
    cov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cov)
    ccx, ccy = int(w * 0.82), int(h * 0.78)
    cd.ellipse([ccx - circ_d // 2, ccy - circ_d // 2,
                ccx + circ_d // 2, ccy + circ_d // 2],
               outline=(255, 255, 255, 22), width=3)
    img = Image.alpha_composite(img, cov)

    return img


def _fondo_oscuro_cinematico(primary_hex: str, secondary_hex: str, w: int, h: int) -> Image.Image:
    """
    P1 fallback — PREMIUM OSCURO: base casi negra con tinte de marca
    + barrido de luz diagonal desde esquina superior izquierda
    + glow sutil del secundario en la parte superior.
    """
    r, g, b = _hex_rgb(primary_hex)

    # Base muy oscura: 8–12% del color de marca
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)

    # Barrido diagonal de luz: más brillante en esquina sup-izq
    sweep = (1.0 - ys[:, None] * 0.75) * (1.0 - xs[None, :] * 0.65)
    sweep = np.clip(sweep, 0.0, 1.0)
    factor = np.clip(0.06 + sweep * 0.30, 0.0, 1.0)

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(r * factor, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(g * factor, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(b * factor, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    img = Image.fromarray(arr, "RGBA")

    # Glow del secundario desde parte superior central
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
    else:
        sr = min(255, int(r + (255 - r) * 0.45))
        sg = min(255, int(g + (255 - g) * 0.45))
        sb = min(255, int(b + (255 - b) * 0.45))

    gys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    gxs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    gd  = np.sqrt(((gxs[None, :] - 0.5) * 1.6) ** 2 + (gys[:, None] * 1.4) ** 2)
    glow = np.clip(1.0 - gd, 0.0, 1.0) ** 2.2 * 0.20

    garr = np.zeros((h, w, 4), dtype=np.uint8)
    garr[:, :, 0] = np.clip(sr * glow, 0, 255).astype(np.uint8)
    garr[:, :, 1] = np.clip(sg * glow, 0, 255).astype(np.uint8)
    garr[:, :, 2] = np.clip(sb * glow, 0, 255).astype(np.uint8)
    garr[:, :, 3] = np.clip(glow * 255, 0, 255).astype(np.uint8)

    img = Image.alpha_composite(img, Image.fromarray(garr, "RGBA"))
    return img


def _fondo_geometrico_bold(primary_hex: str, secondary_hex: str, w: int, h: int) -> Image.Image:
    """
    P3 fallback — GRÁFICO AUDAZ: base casi negra + gran forma diagonal del secundario
    + línea de corte horizontal. Estética póster/campaña.
    """
    r, g, b = _hex_rgb(primary_hex)
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
    else:
        sr = min(255, int(r + (255 - r) * 0.60))
        sg = min(255, int(g + (255 - g) * 0.60))
        sb = min(255, int(b + (255 - b) * 0.60))

    # Base muy oscura con tinte de marca
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = int(r * 0.07)
    arr[:, :, 1] = int(g * 0.07)
    arr[:, :, 2] = int(b * 0.07)
    arr[:, :, 3] = 255

    # Gradiente vertical sutil: ligeramente más claro en la parte superior
    ys = np.linspace(1.0, 0.7, h, dtype=np.float32)
    for ci, cv in enumerate([r, g, b]):
        arr[:, :, ci] = np.clip(arr[:, :, ci].astype(np.float32) * ys[:, None], 0, 255).astype(np.uint8)

    img = Image.fromarray(arr, "RGBA")

    # Gran forma diagonal del secundario (más visible, ~22% opacity)
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    slant = int(h * 0.45)
    pts = [
        (int(w * 0.28), 0),
        (w + int(w * 0.15), 0),
        (w + int(w * 0.15) - slant, h),
        (int(w * 0.28) - slant, h),
    ]
    od.polygon(pts, fill=(sr, sg, sb, 56))  # ~22%
    img = Image.alpha_composite(img, ov)

    # Línea de corte horizontal fina en blanco (refuerza la tensión gráfica)
    cut_ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cut_ov)
    cut_y = int(h * 0.46)
    cd.line([(0, cut_y), (w, cut_y)], fill=(255, 255, 255, 28), width=2)
    img = Image.alpha_composite(img, cut_ov)

    return img


def _fondo_radial_impacto(primary_hex: str, secondary_hex: str, w: int, h: int) -> Image.Image:
    """
    P4 fallback — BILLBOARD: gradiente radial explosivo desde el centro del primario
    + corona del secundario en los bordes. Energía máxima.
    """
    r, g, b = _hex_rgb(primary_hex)
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
    else:
        sr = max(0, int(r * 0.55))
        sg = max(0, int(g * 0.55))
        sb = max(0, int(b * 0.55))

    ys = np.linspace(-1.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(-1.0, 1.0, w, dtype=np.float32)
    dist = np.sqrt(ys[:, None] ** 2 + xs[None, :] ** 2) / 1.42  # 0=centro 1=esquina

    # Centro vivo del primario → bordes del secundario más oscuro
    t = dist  # 0=primary, 1=secondary
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(r * (1 - t) + sr * t, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(g * (1 - t) + sg * t, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(b * (1 - t) + sb * t, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255

    return Image.fromarray(arr, "RGBA")


def _fondo_solido(hex_color: str, w: int, h: int) -> Image.Image:
    """Gradiente diagonal sutil — fallback genérico."""
    r, g, b = _hex_rgb(hex_color)
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    strength = 0.04 if lum > 0.70 else 0.18

    ys = np.linspace(0, 1, h, dtype=np.float32)
    xs = np.linspace(0, 1, w, dtype=np.float32)
    grad = ys[:, None] * 0.5 + xs[None, :] * 0.5
    factor = 1.0 + strength - grad * (strength * 2)

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(r * factor, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(g * factor, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(b * factor, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


# ─── Utilidades privadas ──────────────────────────────────────────────────────

def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    h = (hex_color or "#888888").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return (136, 136, 136)


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
