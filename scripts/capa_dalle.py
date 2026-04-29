"""
CAPA DALLE — Generación de fondos artísticos con OpenAI gpt-image-1
Sustain Awards

Funciones:
  generar_fondo()       – fondo artístico para el trofeo
  generar_texto_capa()  – tipografía premium con fondo transparente
"""

import os
import base64
import hashlib
import time
import urllib.request
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

from scripts.config import (
    USE_DALLE,
    IMAGE_QUALITY as CALIDAD_IMAGEN,
    IMAGE_PROVIDER,
    IMAGE_MODEL_OPENAI,
    REPLICATE_MODEL,
)


# ─── Helpers de logging ──────────────────────────────────────────────────────

def _nombre_generador(concepto: dict | None) -> str:
    """Devuelve el nombre del generador PIL que se usaría para este concepto."""
    if concepto is None:
        return "sólido"
    if concepto.get("bg_tone") == "light":
        return "fondo claro (metal)"
    return "PIL-aleatorio"


# ─── Fondo artístico ──────────────────────────────────────────────────────────

def _inyectar_colores_en_prompt(prompt: str, primary: str, secondary: str) -> str:
    """
    Añade los HEX de marca al inicio del dalle_prompt.
    DALL-E respeta los colores con más fidelidad cuando se dan como valores exactos
    al principio del prompt, antes de la descripción artística.
    """
    if not prompt:
        return prompt
    partes = []
    if primary and len(primary) == 7 and primary.startswith("#"):
        partes.append(f"primary brand color {primary}")
    if secondary and len(secondary) == 7 and secondary.startswith("#"):
        partes.append(f"accent color {secondary}")
    if not partes:
        return prompt
    prefijo = f"Use ONLY these exact brand colors: {', '.join(partes)}. "
    return prefijo + prompt


def generar_fondo(prompt: str, ancho: int, alto: int,
                  color_fallback: str = "#1A1A2E",
                  concepto: dict | None = None) -> Image.Image:
    """
    Genera un fondo artístico con gpt-image-1.
    Si prompt vacío o USE_DALLE=False → fondo creativo por concepto (PIL).
    """
    pid = concepto.get("proposal_id", "?") if concepto else "?"
    if not USE_DALLE or not prompt or not prompt.strip():
        gen_name = _nombre_generador(concepto)
        print(f"  [DALLE-FONDO] P{pid} → PIL ({gen_name})  [DALL·E desactivado o prompt vacío]")
        return _fondo_concepto(color_fallback, ancho, alto, concepto)

    try:
        client = _cliente()
        size   = "1024x1536" if alto > ancho else "1024x1024"
        # Inyectar HEX de marca al inicio del prompt — DALL-E respeta colores cuando se dan explícitamente
        primary_hex   = (concepto or {}).get("_primary", color_fallback)
        secondary_hex = (concepto or {}).get("_secondary", "")
        prompt = _inyectar_colores_en_prompt(prompt, primary_hex, secondary_hex)
        print(f"  [DALLE-FONDO] P{pid} → Llamando gpt-image-1  ({size}, quality={CALIDAD_IMAGEN}) ...")
        print(f"  [DALLE-FONDO] P{pid} Colores inyectados: primary={primary_hex} · accent={secondary_hex or '—'}")
        _t0 = time.time()
        img = _llamar_api(client, prompt, size)
        print(f"  [DALLE-FONDO] P{pid} ✓ Imagen recibida en {time.time()-_t0:.1f}s")
        return _resize_and_crop(img, ancho, alto)
    except Exception as e:
        print(f"  [DALLE-FONDO] P{pid} Error: {e} → fallback PIL")
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

def _derive_pil_seed(concepto: dict) -> int:
    """
    Seed único por run: combina run_id (por ejecución), propuesta y tiempo en 30s.
    run_id garantiza variedad entre marcas distintas; time//30 garantiza variedad
    entre ejecuciones sucesivas de la misma marca.
    """
    run_id = concepto.get("_run_id", "")
    hint = (
        f"{run_id}"
        f"{concepto.get('dalle_prompt', '')[:50]}"
        f"{concepto.get('proposal_id', 1)}"
        f"{int(time.time() // 30)}"
    )
    return int(hashlib.md5(hint.encode()).hexdigest()[:8], 16)


def _fondo_concepto(color_fallback: str, w: int, h: int, concepto: dict | None) -> Image.Image:
    """
    Selecciona un generador PIL según bg_tone.
    - light: fondos claros con carácter de marca
    - mid:   colores de marca a PLENA saturación (sin oscurecer)
    - dark:  fondos de baja luminancia con tinte de marca
    Seed único por run+marca garantiza fondos distintos en cada ejecución.
    """
    if concepto is None:
        return _fondo_solido(color_fallback, w, h)

    bg_tone    = concepto.get("bg_tone", "dark")
    sec        = (concepto.get("_secondary") or "").strip()
    acc        = (concepto.get("_accent") or "").strip()
    ext_colors = concepto.get("_colors_extended", [])
    seed       = _derive_pil_seed(concepto)
    palette    = [c for c in [color_fallback, sec, acc] + list(ext_colors) if c]
    palette    = list(dict.fromkeys(palette))[:5]
    rng        = np.random.default_rng(seed)
    pid        = concepto.get("proposal_id", "?")

    if bg_tone == "light":
        generators = [
            lambda: _fondo_editorial(color_fallback, w, h, is_minimal=False, seed=seed),
            lambda: _fondo_editorial(color_fallback, w, h, is_minimal=True, seed=seed),
            lambda: _fondo_papel_bold(color_fallback, w, h, seed=seed),
            lambda: _fondo_secciones_bold(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_banda_light(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_tint_light(color_fallback, w, h, seed=seed),
            lambda: _fondo_lineas_marca(color_fallback, w, h, seed=seed),
        ]
    elif bg_tone == "mid":
        # Colores de marca a plena saturación — sin multiplicadores de oscurecimiento
        generators = [
            lambda: _fondo_gran_bloque_marca(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_gradiente_lineal(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_split_vertical(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_diagonal_brillante(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_arcos_concentric(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_chevron(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_franjas_marca(palette, w, h, seed=seed),
            lambda: _fondo_halftone(color_fallback, w, h, seed=seed),
            lambda: _fondo_blob_vibrante(color_fallback, sec, acc, w, h, seed=seed),
            lambda: _fondo_campos_color(palette, w, h, seed=seed),
            lambda: _fondo_marca_pura(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_secciones_bold(color_fallback, sec or acc, w, h, seed=seed),
        ]
    else:  # dark
        generators = [
            lambda: _fondo_oscuro_cinematico(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_marca_pura(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_geometrico_bold(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_radial_impacto(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_diagonal_marca(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_mesh_gradient(palette, w, h, seed=seed),
            lambda: _fondo_ondas(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_manchas(color_fallback, sec, acc, w, h, seed=seed),
            lambda: _fondo_constructivista(color_fallback, sec, acc, w, h, seed=seed),
            lambda: _fondo_duotono(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_espiral(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_neblina_capas(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_diagonal_multicolor(palette, w, h, seed=seed),
            lambda: _fondo_scan_lines(color_fallback, sec or acc, w, h, seed=seed),
            lambda: _fondo_angular_dark(color_fallback, sec or acc, w, h, seed=seed),
        ]

    idx = int(rng.integers(0, len(generators)))
    print(f"  [PIL] P{pid} bg={bg_tone} → gen#{idx}/{len(generators)}")
    try:
        return generators[idx]()
    except Exception as e:
        print(f"  [PIL] Generador {idx} falló: {e} → fallback sólido")
        return _fondo_solido(color_fallback, w, h)


def _fondo_editorial(brand_hex: str, w: int, h: int, is_minimal: bool = False, seed: int = 0) -> Image.Image:
    """
    P2 / P5: fondo editorial blanco.
    P2 → papel premium con toque de color de marca en esquina variable (seed).
    P5 → papel limpio con dot-grid ultrasuave del color de marca.
    """
    r, g, b = _hex_rgb(brand_hex)
    rng = np.random.default_rng(seed)

    base = np.full((h, w, 4), 255, dtype=np.uint8)

    # Grano de papel sutil (±4 valores, varía con seed)
    grain = rng.integers(-4, 5, (h, w), dtype=np.int16)
    for c in range(3):
        base[:, :, c] = np.clip(base[:, :, c].astype(np.int16) + grain, 249, 255).astype(np.uint8)

    if not is_minimal:
        # P2: toque de marca en esquina variable según seed (sup-der, sup-izq, inferior)
        corners = [(1.0, 0.0), (0.0, 0.0), (0.5, 1.0), (1.0, 0.5)]
        cx, cy = corners[seed % len(corners)]
        ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
        xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
        dist = np.sqrt((cx - xs[None, :]) ** 2 + (cy - ys[:, None]) ** 2) / 1.42
        mask = np.clip((1.0 - dist * 2.2), 0.0, 1.0) * 0.055
        for ci, cv in enumerate([r, g, b]):
            base[:, :, ci] = np.clip(
                base[:, :, ci].astype(np.float32) * (1 - mask) + cv * mask, 0, 255
            ).astype(np.uint8)
    else:
        # P5: dot-grid minimalista con espacio variable (30-42px según seed)
        spacing = 30 + (seed % 4) * 4
        ym = np.arange(h) % spacing == spacing // 2
        xm = np.arange(w) % spacing == spacing // 2
        grid = ym[:, None] & xm[None, :]
        for ci, cv in enumerate([r, g, b]):
            col = base[:, :, ci].astype(np.float32)
            col[grid] = col[grid] * 0.94 + cv * 0.06
            base[:, :, ci] = np.clip(col, 0, 255).astype(np.uint8)

    return Image.fromarray(base, "RGBA")


def _fondo_marca_pura(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
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

    # Banda diagonal del secundario o tint del primario (posición varía con seed)
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
    else:
        sr = min(255, int(r + (255 - r) * 0.38))
        sg = min(255, int(g + (255 - g) * 0.38))
        sb = min(255, int(b + (255 - b) * 0.38))

    rng = np.random.default_rng(seed)
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    slant = int(h * rng.uniform(0.30, 0.46))
    bw    = int(w * rng.uniform(0.11, 0.17))
    cx    = int(w * rng.uniform(0.55, 0.70))
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


def _fondo_oscuro_cinematico(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    P1 fallback — PREMIUM OSCURO: base casi negra con tinte de marca
    + barrido de luz diagonal desde esquina variable (seed)
    + glow sutil del secundario.
    """
    r, g, b = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)

    # Base muy oscura: 8–12% del color de marca
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)

    # Barrido diagonal de luz: ángulo varía con seed (4 esquinas posibles)
    sweep_combos = [(0.75, 0.65), (0.65, 0.80), (0.80, 0.55), (0.70, 0.70)]
    sy, sx = sweep_combos[seed % len(sweep_combos)]
    sweep = (1.0 - ys[:, None] * sy) * (1.0 - xs[None, :] * sx)
    sweep = np.clip(sweep, 0.0, 1.0)
    intensity = rng.uniform(0.24, 0.36)
    factor = np.clip(0.06 + sweep * intensity, 0.0, 1.0)

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


def _fondo_geometrico_bold(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    P3 fallback — GRÁFICO AUDAZ: base casi negra + gran forma diagonal del secundario
    + línea de corte. Ángulo y posición varían con seed.
    """
    r, g, b = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
    else:
        sr = min(255, int(r + (255 - r) * 0.60))
        sg = min(255, int(g + (255 - g) * 0.60))
        sb = min(255, int(b + (255 - b) * 0.60))

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = int(r * 0.07)
    arr[:, :, 1] = int(g * 0.07)
    arr[:, :, 2] = int(b * 0.07)
    arr[:, :, 3] = 255

    ys = np.linspace(1.0, 0.7, h, dtype=np.float32)
    for ci, cv in enumerate([r, g, b]):
        arr[:, :, ci] = np.clip(arr[:, :, ci].astype(np.float32) * ys[:, None], 0, 255).astype(np.uint8)

    img = Image.fromarray(arr, "RGBA")

    # Gran forma diagonal con ángulo variable
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    slant = int(h * rng.uniform(0.35, 0.55))
    x_start = rng.uniform(0.20, 0.38)
    pts = [
        (int(w * x_start), 0),
        (w + int(w * 0.15), 0),
        (w + int(w * 0.15) - slant, h),
        (int(w * x_start) - slant, h),
    ]
    od.polygon(pts, fill=(sr, sg, sb, 56))
    img = Image.alpha_composite(img, ov)

    cut_ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cut_ov)
    cut_y = int(h * rng.uniform(0.38, 0.54))
    cd.line([(0, cut_y), (w, cut_y)], fill=(255, 255, 255, 28), width=2)
    img = Image.alpha_composite(img, cut_ov)

    return img


def _fondo_radial_impacto(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    P4 fallback — BILLBOARD: gradiente radial explosivo desde el centro del primario
    + corona del secundario en los bordes. Energía máxima.
    """
    r, g, b = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
    else:
        sr = max(0, int(r * 0.55))
        sg = max(0, int(g * 0.55))
        sb = max(0, int(b * 0.55))

    # Centro del radial varía ligeramente con seed
    cy_offset = rng.uniform(-0.20, 0.20)
    cx_offset = rng.uniform(-0.15, 0.15)
    ys = np.linspace(-1.0 + cy_offset, 1.0 + cy_offset, h, dtype=np.float32)
    xs = np.linspace(-1.0 + cx_offset, 1.0 + cx_offset, w, dtype=np.float32)
    dist = np.sqrt(ys[:, None] ** 2 + xs[None, :] ** 2) / 1.42  # 0=centro 1=esquina

    # Centro vivo del primario → bordes del secundario más oscuro
    t = dist  # 0=primary, 1=secondary
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(r * (1 - t) + sr * t, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(g * (1 - t) + sg * t, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(b * (1 - t) + sb * t, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255

    return Image.fromarray(arr, "RGBA")


def _fondo_secciones_bold(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Fondo de dos secciones: banda superior del color primario, zona inferior blanca/muy clara.
    Inspirado en Booking.com. La proporción de la banda varía con seed (20-32% del alto).
    """
    rng = np.random.default_rng(seed)
    band_ratio = rng.uniform(0.20, 0.32)
    band_h = int(h * band_ratio)

    r, g, b = _hex_rgb(primary_hex)
    arr = np.full((h, w, 4), 255, dtype=np.uint8)

    # Banda superior del color primario
    arr[:band_h, :, 0] = r
    arr[:band_h, :, 1] = g
    arr[:band_h, :, 2] = b

    # Zona inferior muy clara con sutil tinte del primario
    tint = 0.03 + rng.uniform(0.0, 0.025)
    for ci, cv in enumerate([r, g, b]):
        col = arr[band_h:, :, ci].astype(np.float32)
        arr[band_h:, :, ci] = np.clip(col * (1 - tint) + cv * tint, 0, 255).astype(np.uint8)

    return Image.fromarray(arr, "RGBA")


def _fondo_diagonal_marca(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Fondo oscuro con gran franja diagonal del secundario, ángulo variable.
    Inspirado en Renault Trucks — acento diagonal estructural bold.
    """
    r, g, b = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
    else:
        sr = min(255, int(r + (255 - r) * 0.55))
        sg = min(255, int(g + (255 - g) * 0.55))
        sb = min(255, int(b + (255 - b) * 0.55))

    # Base oscura sólida con tinte de marca
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = int(r * 0.09)
    arr[:, :, 1] = int(g * 0.09)
    arr[:, :, 2] = int(b * 0.09)
    arr[:, :, 3] = 255
    img = Image.fromarray(arr, "RGBA")

    # Franja diagonal ancha (35-50% del ancho)
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    angle_ratio = rng.uniform(0.55, 0.75)   # inclinación
    band_w = int(w * rng.uniform(0.28, 0.42))
    x0 = int(w * rng.uniform(0.12, 0.35))
    pts = [
        (x0, 0),
        (x0 + band_w, 0),
        (x0 + band_w - int(h * angle_ratio), h),
        (x0 - int(h * angle_ratio), h),
    ]
    od.polygon(pts, fill=(sr, sg, sb, 55))  # ~22% opacity
    img = Image.alpha_composite(img, ov)

    return img


def _fondo_papel_bold(brand_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Fondo claro con grain de papel más intenso que _fondo_editorial.
    Para fondos light con mayor textura y carácter artesanal.
    """
    r, g, b = _hex_rgb(brand_hex)
    rng = np.random.default_rng(seed)

    # Base crema-blanca (no puro blanco)
    base_val = int(rng.uniform(245, 255))
    arr = np.full((h, w, 4), base_val, dtype=np.uint8)
    arr[:, :, 3] = 255

    # Grain más intenso que editorial (±8 valores)
    grain_intensity = int(rng.uniform(5, 9))
    grain = rng.integers(-grain_intensity, grain_intensity + 1, (h, w), dtype=np.int16)
    for c in range(3):
        arr[:, :, c] = np.clip(arr[:, :, c].astype(np.int16) + grain, 230, 255).astype(np.uint8)

    img = Image.fromarray(arr, "RGBA")

    # Vignette muy sutil del color de marca en los bordes
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    dist_center = np.sqrt((xs[None, :] - 0.5) ** 2 + (ys[:, None] - 0.5) ** 2) / 0.71
    vignette = np.clip(dist_center - 0.5, 0.0, 1.0) * rng.uniform(0.04, 0.09)

    ov = np.zeros((h, w, 4), dtype=np.uint8)
    ov[:, :, 0] = np.clip(r * vignette, 0, 255).astype(np.uint8)
    ov[:, :, 1] = np.clip(g * vignette, 0, 255).astype(np.uint8)
    ov[:, :, 2] = np.clip(b * vignette, 0, 255).astype(np.uint8)
    ov[:, :, 3] = np.clip(vignette * 255, 0, 255).astype(np.uint8)
    img = Image.alpha_composite(img, Image.fromarray(ov, "RGBA"))

    return img


def _fondo_mesh_gradient(colors: list[str], w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Gradiente mesh multi-punto: interpolación por distancia inversa entre N puntos de color.
    Resultado oscurecido al 35% para mantener fondo apto para texto claro.
    """
    rng = np.random.default_rng(seed)
    valid = [c for c in colors if c]
    if not valid:
        valid = ["#333333"]
    n = max(3, min(6, len(valid)))
    rgb_list = [_hex_rgb(c) for c in valid[:n]]

    pts_y = rng.uniform(0.0, 1.0, n).astype(np.float32)
    pts_x = rng.uniform(0.0, 1.0, n).astype(np.float32)

    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")

    r_acc = np.zeros((h, w), dtype=np.float32)
    g_acc = np.zeros((h, w), dtype=np.float32)
    b_acc = np.zeros((h, w), dtype=np.float32)
    w_acc = np.zeros((h, w), dtype=np.float32)

    for i, (pr, pg, pb) in enumerate(rgb_list):
        dist2 = (yy - pts_y[i]) ** 2 + (xx - pts_x[i]) ** 2
        weight = 1.0 / (dist2 + 1e-6)
        r_acc += weight * pr
        g_acc += weight * pg
        b_acc += weight * pb
        w_acc += weight

    # Oscurecer al 35% para que el texto claro sea legible
    darkening = 0.35
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(r_acc / w_acc * darkening, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(g_acc / w_acc * darkening, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(b_acc / w_acc * darkening, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


def _fondo_ondas(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Bandas sinusoidales de color — franjas onduladas diagonales en colores de marca.
    Base muy oscura + ondas sutiles del secundario.
    """
    rng = np.random.default_rng(seed)
    r1, g1, b1 = _hex_rgb(primary_hex)
    if secondary_hex:
        r2, g2, b2 = _hex_rgb(secondary_hex)
    else:
        r2 = min(255, int(r1 + (255 - r1) * 0.45))
        g2 = min(255, int(g1 + (255 - g1) * 0.45))
        b2 = min(255, int(b1 + (255 - b1) * 0.45))

    freq1  = rng.uniform(2.0, 4.5)
    freq2  = rng.uniform(1.2, 2.8)
    phase1 = rng.uniform(0, np.pi * 2)
    phase2 = rng.uniform(0, np.pi * 2)
    tilt   = rng.uniform(0.3, 0.7)

    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")

    wave_input = yy + xx * tilt
    wave = (np.sin(wave_input * freq1 * np.pi + phase1) * 0.5 +
            np.sin(wave_input * freq2 * np.pi + phase2) * 0.3)
    wave = (wave - wave.min()) / (wave.max() - wave.min() + 1e-8)

    # Blend entre primario y secundario muy oscurecidos
    dark = 0.10
    t    = wave * 0.25  # mezcla sutil — ondas como matiz, no como franjas duras
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(r1 * (dark + t * 0.15) + r2 * t * 0.10, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(g1 * (dark + t * 0.15) + g2 * t * 0.10, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(b1 * (dark + t * 0.15) + b2 * t * 0.10, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


def _fondo_manchas(primary_hex: str, secondary_hex: str, accent_hex: str,
                   w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Manchas abstractas — grandes elipses semitransparentes en colores de marca.
    Efecto acuarela / poster de color. Base muy oscura.
    """
    rng  = np.random.default_rng(seed)
    r1, g1, b1 = _hex_rgb(primary_hex)
    base_r = max(0, int(r1 * 0.06))
    base_g = max(0, int(g1 * 0.06))
    base_b = max(0, int(b1 * 0.06))
    img = Image.new("RGBA", (w, h), (base_r, base_g, base_b, 255))

    colors = [c for c in [primary_hex, secondary_hex, accent_hex] if c]
    n_blobs = int(rng.integers(5, 9))
    for _ in range(n_blobs):
        col_hex = colors[int(rng.integers(0, len(colors)))]
        cr, cg, cb = _hex_rgb(col_hex)
        cx = int(rng.uniform(-0.05, 1.05) * w)
        cy = int(rng.uniform(-0.05, 1.05) * h)
        rx = int(rng.uniform(0.18, 0.52) * w)
        ry = int(rng.uniform(0.22, 0.60) * h)
        opacity = int(rng.integers(30, 65))
        blob = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bd   = ImageDraw.Draw(blob)
        bd.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(cr, cg, cb, opacity))
        img = Image.alpha_composite(img, blob)
    return img


def _fondo_constructivista(primary_hex: str, secondary_hex: str, accent_hex: str,
                            w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Diseño constructivista / Bauhaus: formas geométricas bold en colores de marca.
    Base oscura + rectángulo diagonal grande + bloque secundario + línea accent.
    """
    rng = np.random.default_rng(seed)
    r1, g1, b1 = _hex_rgb(primary_hex)
    base = (max(0, int(r1 * 0.06)), max(0, int(g1 * 0.06)), max(0, int(b1 * 0.06)), 255)
    img  = Image.new("RGBA", (w, h), base)
    draw = ImageDraw.Draw(img)

    # Sección diagonal grande del primario
    x_split = int(rng.uniform(0.28, 0.62) * w)
    slant   = int(rng.uniform(0.20, 0.40) * h)
    pts = [(0, 0), (x_split, 0), (x_split + slant, h), (0, h)]
    draw.polygon(pts, fill=(r1, g1, b1, 60))

    # Bloque secundario (rectángulo bold)
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
        rect_x = int(rng.uniform(0.45, 0.75) * w)
        rect_y = int(rng.uniform(0.08, 0.28) * h)
        rect_w2 = int(rng.uniform(0.14, 0.28) * w)
        rect_h2 = int(rng.uniform(0.12, 0.26) * h)
        draw.rectangle([rect_x, rect_y, rect_x + rect_w2, rect_y + rect_h2],
                       fill=(sr, sg, sb, 90))

    # Línea horizontal fina del accent (o blanco)
    if accent_hex:
        ar, ag, ab = _hex_rgb(accent_hex)
    else:
        ar, ag, ab = 255, 255, 255
    line_y = int(rng.uniform(0.30, 0.68) * h)
    thick  = max(3, int(h * 0.010))
    draw.rectangle([0, line_y, w, line_y + thick], fill=(ar, ag, ab, 180))

    return img


def _fondo_duotono(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Duotono clásico: ruido suave mapeado entre primario oscuro y secundario oscuro.
    Aspecto de impresión dos colores — editorial y gráfico.
    """
    rng = np.random.default_rng(seed)
    r1, g1, b1 = _hex_rgb(primary_hex)
    if secondary_hex:
        r2, g2, b2 = _hex_rgb(secondary_hex)
    else:
        r2 = min(255, int(r1 + (255 - r1) * 0.50))
        g2 = min(255, int(g1 + (255 - g1) * 0.50))
        b2 = min(255, int(b1 + (255 - b1) * 0.50))

    # Ruido suave en baja resolución → upsample
    sh, sw = max(4, h // 6), max(4, w // 6)
    noise  = rng.uniform(0.0, 1.0, (sh, sw)).astype(np.float32)
    noise_img = Image.fromarray((noise * 255).astype(np.uint8), "L")
    noise_img = noise_img.resize((w, h), Image.BILINEAR)
    noise_arr = np.array(noise_img).astype(np.float32) / 255.0

    # Gradiente diagonal que guía la composición
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    grad = ys[:, None] * 0.55 + xs[None, :] * 0.45
    t    = np.clip(noise_arr * 0.65 + grad * 0.35, 0.0, 1.0)

    # Oscurecer ambos extremos para fondo de texto
    dark = 0.45
    dr1, dg1, db1 = int(r1 * dark), int(g1 * dark), int(b1 * dark)
    dr2, dg2, db2 = int(r2 * dark), int(g2 * dark), int(b2 * dark)

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(dr1 * (1 - t) + dr2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(dg1 * (1 - t) + dg2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(db1 * (1 - t) + db2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


def _fondo_espiral(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Vórtice suave basado en coordenadas polares: ángulo + distancia → color de marca.
    """
    rng = np.random.default_rng(seed)
    r1, g1, b1 = _hex_rgb(primary_hex)
    if secondary_hex:
        r2, g2, b2 = _hex_rgb(secondary_hex)
    else:
        r2 = min(255, int(r1 + (255 - r1) * 0.50))
        g2 = min(255, int(g1 + (255 - g1) * 0.50))
        b2 = min(255, int(b1 + (255 - b1) * 0.50))

    cy_off = rng.uniform(-0.12, 0.12)
    cx_off = rng.uniform(-0.12, 0.12)
    ys = np.linspace(-1.0 + cy_off, 1.0 + cy_off, h, dtype=np.float32)
    xs = np.linspace(-1.0 + cx_off, 1.0 + cx_off, w, dtype=np.float32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")

    angle  = np.arctan2(yy, xx)
    dist   = np.sqrt(yy ** 2 + xx ** 2) / 1.42
    twist  = rng.uniform(1.8, 3.8)
    spiral = (angle / (2 * np.pi) + dist * twist) % 1.0
    t      = (np.sin(spiral * np.pi * 2) + 1) / 2
    dark   = np.clip(1.0 - dist * 0.65, 0.15, 1.0) * 0.40  # max 40% luminancia

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip((r1 * (1 - t) + r2 * t) * dark, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip((g1 * (1 - t) + g2 * t) * dark, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip((b1 * (1 - t) + b2 * t) * dark, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


def _fondo_neblina_capas(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Glows radiales superpuestos en posiciones aleatorias — nebulosa / niebla iluminada.
    Profundidad máxima con base muy oscura.
    """
    rng = np.random.default_rng(seed)
    r1, g1, b1 = _hex_rgb(primary_hex)
    if secondary_hex:
        r2, g2, b2 = _hex_rgb(secondary_hex)
    else:
        r2, g2, b2 = min(255, int(r1 + (255 - r1) * 0.40)), \
                     min(255, int(g1 + (255 - g1) * 0.40)), \
                     min(255, int(b1 + (255 - b1) * 0.40))

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = max(0, int(r1 * 0.04))
    arr[:, :, 1] = max(0, int(g1 * 0.04))
    arr[:, :, 2] = max(0, int(b1 * 0.04))
    arr[:, :, 3] = 255
    img = Image.fromarray(arr, "RGBA")

    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")

    n_glows = int(rng.integers(3, 6))
    for i in range(n_glows):
        gx = rng.uniform(0.10, 0.90)
        gy = rng.uniform(0.05, 0.95)
        radius   = rng.uniform(0.28, 0.68)
        gr, gg, gb = (r1, g1, b1) if i % 2 == 0 else (r2, g2, b2)
        dist2    = np.sqrt(((xx - gx) * 1.3) ** 2 + (yy - gy) ** 2) / radius
        glow     = np.clip(1.0 - dist2, 0.0, 1.0) ** 2.5
        strength = rng.uniform(0.18, 0.38)
        ov = np.zeros((h, w, 4), dtype=np.uint8)
        ov[:, :, 0] = np.clip(gr * glow * strength, 0, 255).astype(np.uint8)
        ov[:, :, 1] = np.clip(gg * glow * strength, 0, 255).astype(np.uint8)
        ov[:, :, 2] = np.clip(gb * glow * strength, 0, 255).astype(np.uint8)
        ov[:, :, 3] = np.clip(glow * 255 * strength, 0, 255).astype(np.uint8)
        img = Image.alpha_composite(img, Image.fromarray(ov, "RGBA"))
    return img


def _fondo_diagonal_multicolor(colors: list[str], w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Franjas diagonales en los colores de marca al 25% de luminancia — inspiración Swiss.
    """
    rng = np.random.default_rng(seed)
    valid = [c for c in colors if c] or ["#333333"]

    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")

    tilt = rng.uniform(0.35, 0.75)
    proj = (yy + xx * tilt)
    proj = (proj - proj.min()) / (proj.max() - proj.min())

    n_reps   = int(rng.integers(2, 4))
    n_colors = len(valid)
    idx_map  = (proj * n_colors * n_reps).astype(np.int32) % n_colors

    # Oscurecer colores al 25% para mantener fondo oscuro legible
    rgb_list = [_hex_rgb(c) for c in valid]
    dark_rgb = [(max(5, int(r * 0.25)), max(5, int(g * 0.25)), max(5, int(b * 0.25)))
                for r, g, b in rgb_list]

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    for ci, (cr, cg, cb) in enumerate(dark_rgb):
        mask = idx_map == ci
        arr[mask, 0] = cr
        arr[mask, 1] = cg
        arr[mask, 2] = cb
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


# ─── Generadores MID — colores de marca a plena saturación ───────────────────

def _fondo_gran_bloque_marca(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Gran bloque del primario a plena saturación (sin oscurecer) sobre base blanca/crema.
    Modo varía con seed: banda superior, bloque izquierdo, diagonal.
    """
    r, g, b = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    cream = int(rng.uniform(246, 252))
    arr = np.full((h, w, 4), cream, dtype=np.uint8)
    arr[:, :, 3] = 255

    mode = seed % 3
    if mode == 0:
        split = int(h * rng.uniform(0.55, 0.70))
        arr[:split, :, 0] = r; arr[:split, :, 1] = g; arr[:split, :, 2] = b
    elif mode == 1:
        split = int(w * rng.uniform(0.50, 0.62))
        arr[:, :split, 0] = r; arr[:, :split, 1] = g; arr[:, :split, 2] = b
    else:
        ys_i = np.linspace(0.0, 1.0, h, dtype=np.float32)
        xs_i = np.linspace(0.0, 1.0, w, dtype=np.float32)
        yy_i, xx_i = np.meshgrid(ys_i, xs_i, indexing="ij")
        sy = rng.uniform(0.50, 0.70)
        sx = rng.uniform(0.50, 0.70)
        mask = (yy_i / sy + xx_i / sx) < 1.0
        arr[mask, 0] = r; arr[mask, 1] = g; arr[mask, 2] = b

    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
        img = Image.fromarray(arr, "RGBA")
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        thick = max(4, int(h * 0.012))
        ly = int(h * rng.uniform(0.72, 0.82))
        od.rectangle([int(w * 0.07), ly, int(w * 0.93), ly + thick], fill=(sr, sg, sb, 220))
        return Image.alpha_composite(img, ov)
    return Image.fromarray(arr, "RGBA")


def _fondo_gradiente_lineal(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Gradiente lineal entre primario y secundario a PLENA saturación.
    Dirección varía con seed: vertical, horizontal, diagonal.
    """
    r1, g1, b1 = _hex_rgb(primary_hex)
    if secondary_hex:
        r2, g2, b2 = _hex_rgb(secondary_hex)
    else:
        r2 = min(255, int(r1 + (255 - r1) * 0.50))
        g2 = min(255, int(g1 + (255 - g1) * 0.50))
        b2 = min(255, int(b1 + (255 - b1) * 0.50))

    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    mode = seed % 3
    if mode == 0:
        t = yy
    elif mode == 1:
        t = xx
    else:
        t = (yy + xx) / 2.0

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(r1 * (1 - t) + r2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(g1 * (1 - t) + g2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(b1 * (1 - t) + b2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


def _fondo_split_vertical(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Split vertical: izquierda = secundario o blanco, derecha = primario a plena saturación.
    Gradiente suave en la unión (6% de blend).
    """
    r1, g1, b1 = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    if secondary_hex:
        r2, g2, b2 = _hex_rgb(secondary_hex)
    else:
        r2, g2, b2 = 248, 248, 248

    split = rng.uniform(0.42, 0.58)
    blend_w = 0.06
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    t = np.clip((xs - split + blend_w / 2) / blend_w, 0.0, 1.0)

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(r2 * (1 - t) + r1 * t, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(g2 * (1 - t) + g1 * t, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(b2 * (1 - t) + b1 * t, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


def _fondo_diagonal_brillante(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Split diagonal limpio sin oscurecer — primario y secundario a plena saturación.
    Ángulo y posición de la diagonal varían con seed.
    """
    r1, g1, b1 = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    if secondary_hex:
        r2, g2, b2 = _hex_rgb(secondary_hex)
    else:
        r2, g2, b2 = 250, 250, 250

    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    tilt = rng.uniform(0.6, 1.4)
    offset = rng.uniform(0.35, 0.65)
    proj = (yy + xx * tilt) / (1 + tilt)
    blend_w = 0.04
    t = np.clip((proj - offset + blend_w / 2) / blend_w, 0.0, 1.0)

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(r1 * (1 - t) + r2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(g1 * (1 - t) + g2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(b1 * (1 - t) + b2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


def _fondo_arcos_concentric(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Arcos concéntricos desde una esquina — alterna primario y secundario a plena saturación.
    Origen varía entre las 4 esquinas según seed.
    """
    r1, g1, b1 = _hex_rgb(primary_hex)
    if secondary_hex:
        r2, g2, b2 = _hex_rgb(secondary_hex)
    else:
        r2, g2, b2 = 248, 248, 248

    corners = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]
    ox, oy = corners[seed % 4]

    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    dist = np.sqrt((xx - ox) ** 2 + (yy - oy) ** 2) / 1.42
    n_rings = 5 + (seed % 3)
    t = (dist * n_rings) % 1.0

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(r1 * (1 - t) + r2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(g1 * (1 - t) + g2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(b1 * (1 - t) + b2 * t, 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


def _fondo_chevron(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Gran cuña/flecha del secundario sobre base primaria — ambos a plena saturación.
    """
    r1, g1, b1 = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
    else:
        sr = min(255, r1 + 60); sg = min(255, g1 + 60); sb = min(255, b1 + 60)

    img = Image.new("RGBA", (w, h), (r1, g1, b1, 255))
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    tip_x = int(w * rng.uniform(0.45, 0.65))
    pts = [(0, 0), (tip_x, int(h * 0.50)), (0, h)]
    od.polygon(pts, fill=(sr, sg, sb, 210))
    tip2 = int(tip_x * rng.uniform(0.50, 0.72))
    pts2 = [(0, int(h * 0.18)), (tip2, int(h * 0.50)), (0, int(h * 0.82))]
    od.polygon(pts2, fill=(r1, g1, b1, 200))
    return Image.alpha_composite(img, ov)


def _fondo_franjas_marca(colors: list[str], w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Franjas horizontales de los colores de marca a plena saturación.
    Estilo cartel gráfico — alturas variables, intercaladas con blanco/crema si faltan colores.
    """
    rng = np.random.default_rng(seed)
    valid = [c for c in colors if c]
    if not valid:
        valid = ["#888888"]
    palette = (valid + ["#F2F2F0"])[:4]
    n_stripes = len(palette)
    weights = rng.dirichlet(np.ones(n_stripes) * 2.0)
    heights = (weights * h).astype(int)
    heights[-1] = h - heights[:-1].sum()

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 3] = 255
    y = 0
    for sh, col in zip(heights, palette):
        cr, cg, cb = _hex_rgb(col)
        arr[y:y + sh, :, 0] = cr
        arr[y:y + sh, :, 1] = cg
        arr[y:y + sh, :, 2] = cb
        y += sh
    return Image.fromarray(arr, "RGBA")


def _fondo_halftone(primary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Patrón halftone: puntos del color primario sobre base blanca.
    Radio decrece desde el centro hacia los bordes — efecto viñeta invertida.
    """
    r, g, b = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    base = Image.new("RGBA", (w, h), (252, 252, 250, 255))
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)
    spacing = max(18, int(min(w, h) * rng.uniform(0.032, 0.048)))
    max_radius = int(spacing * rng.uniform(0.38, 0.46))
    for gy in range(spacing // 2, h + spacing, spacing):
        for gx in range(spacing // 2, w + spacing, spacing):
            dist_c = np.sqrt(((gx / w) - 0.5) ** 2 + ((gy / h) - 0.5) ** 2) / 0.71
            radius = max(2, int(max_radius * (1.2 - dist_c * 0.7)))
            draw.ellipse([gx - radius, gy - radius, gx + radius, gy + radius],
                         fill=(r, g, b, 200))
    return Image.alpha_composite(base, ov)


def _fondo_blob_vibrante(primary_hex: str, secondary_hex: str, accent_hex: str,
                          w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Manchas/blobs orgánicas a PLENA saturación sobre base clara.
    A diferencia de _fondo_manchas, no oscurece los colores de marca.
    """
    rng = np.random.default_rng(seed)
    r1, g1, b1 = _hex_rgb(primary_hex)
    base_r = min(255, 244 + int(r1 * 0.04))
    base_g = min(255, 244 + int(g1 * 0.04))
    base_b = min(255, 244 + int(b1 * 0.04))
    img = Image.new("RGBA", (w, h), (base_r, base_g, base_b, 255))
    colors = [c for c in [primary_hex, secondary_hex, accent_hex] if c]
    n_blobs = int(rng.integers(4, 8))
    for i in range(n_blobs):
        col_hex = colors[i % len(colors)]
        cr, cg, cb = _hex_rgb(col_hex)
        cx = int(rng.uniform(-0.10, 1.10) * w)
        cy = int(rng.uniform(-0.10, 1.10) * h)
        rx = int(rng.uniform(0.15, 0.45) * w)
        ry = int(rng.uniform(0.18, 0.50) * h)
        opacity = int(rng.integers(85, 150))
        blob = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bd = ImageDraw.Draw(blob)
        bd.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(cr, cg, cb, opacity))
        img = Image.alpha_composite(img, blob)
    return img


def _fondo_campos_color(colors: list[str], w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Campos rectangulares de color estilo Mondrian/Rothko.
    Colores de marca puros en cada zona, zonas blancas como separación.
    """
    rng = np.random.default_rng(seed)
    valid = [c for c in colors if c]
    if not valid:
        valid = ["#888888"]
    palette = valid + ["#F2F2F0"]
    img = Image.new("RGBA", (w, h), (242, 242, 240, 255))
    draw = ImageDraw.Draw(img)
    n_rows = 2 + (seed % 2)
    row_splits = [0]
    step = h / n_rows
    for i in range(1, n_rows):
        row_splits.append(int(step * i + rng.uniform(-step * 0.15, step * 0.15)))
    row_splits.append(h)
    col_split = int(w * rng.uniform(0.38, 0.62))
    col_splits = [0, col_split, w]
    color_idx = 0
    for r_idx in range(len(row_splits) - 1):
        for c_idx in range(len(col_splits) - 1):
            col = palette[color_idx % len(palette)]
            cr, cg, cb = _hex_rgb(col)
            draw.rectangle(
                [col_splits[c_idx], row_splits[r_idx], col_splits[c_idx + 1], row_splits[r_idx + 1]],
                fill=(cr, cg, cb, 255)
            )
            color_idx += 1
    return img


# ─── Generadores LIGHT — base clara con carácter de marca ─────────────────────

def _fondo_banda_light(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Fondo blanco/crema con una banda ancha del color primario a plena saturación.
    La banda puede ser horizontal, diagonal o vertical — varía con seed.
    """
    r, g, b = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    base = int(rng.uniform(248, 254))
    arr = np.full((h, w, 4), base, dtype=np.uint8)
    arr[:, :, 3] = 255
    img = Image.fromarray(arr, "RGBA")
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    mode = seed % 3
    if mode == 0:
        band_start = int(h * rng.uniform(0.35, 0.55))
        band_end = int(band_start + h * rng.uniform(0.14, 0.24))
        od.rectangle([0, band_start, w, band_end], fill=(r, g, b, 255))
    elif mode == 1:
        slant = int(h * rng.uniform(0.25, 0.45))
        bw = int(w * rng.uniform(0.60, 0.80))
        x0 = int(w * rng.uniform(0.05, 0.20))
        pts = [(x0, 0), (x0 + bw, 0), (x0 + bw - slant, h), (x0 - slant, h)]
        od.polygon(pts, fill=(r, g, b, 255))
    else:
        band_start = int(w * rng.uniform(0.35, 0.55))
        band_end = int(band_start + w * rng.uniform(0.14, 0.24))
        od.rectangle([band_start, 0, band_end, h], fill=(r, g, b, 255))
    return Image.alpha_composite(img, ov)


def _fondo_tint_light(primary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Fondo blanco con gradiente muy suave de tinte del primario (8-15% de mezcla).
    Un lado ligeramente tintado, el otro casi blanco puro.
    """
    r, g, b = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)
    xs = np.linspace(0.0, 1.0, w, dtype=np.float32)
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    mode = seed % 4
    if mode == 0:
        t = yy
    elif mode == 1:
        t = 1 - yy
    elif mode == 2:
        t = xx
    else:
        t = (yy + xx) / 2.0
    max_tint = rng.uniform(0.08, 0.15)
    white = 252.0
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = np.clip(white * (1 - t * max_tint) + r * (t * max_tint), 0, 255).astype(np.uint8)
    arr[:, :, 1] = np.clip(white * (1 - t * max_tint) + g * (t * max_tint), 0, 255).astype(np.uint8)
    arr[:, :, 2] = np.clip(white * (1 - t * max_tint) + b * (t * max_tint), 0, 255).astype(np.uint8)
    arr[:, :, 3] = 255
    return Image.fromarray(arr, "RGBA")


def _fondo_lineas_marca(primary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Líneas finas diagonales en el color primario sobre fondo blanco.
    Espaciado, grosor y ángulo varían con seed.
    """
    r, g, b = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    img = Image.new("RGBA", (w, h), (252, 252, 250, 255))
    draw = ImageDraw.Draw(img)
    spacing = int(min(w, h) * rng.uniform(0.040, 0.065))
    thickness = max(1, int(spacing * 0.08))
    angle_tan = rng.uniform(0.5, 1.5)
    opacity = int(rng.uniform(35, 65))
    n_lines = int((w + h) / max(spacing, 1)) + 4
    for i in range(-2, n_lines):
        x0 = i * spacing
        x1 = x0 - int(h * angle_tan)
        draw.line([(x0, 0), (x1, h)], fill=(r, g, b, opacity), width=thickness)
    return img


# ─── Generadores DARK adicionales ─────────────────────────────────────────────

def _fondo_scan_lines(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Base muy oscura del primario con líneas horizontales finas del secundario.
    Efecto display/pantalla premium — fade vertical sutil.
    """
    r, g, b = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    dark = rng.uniform(0.08, 0.15)
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
    else:
        sr = min(255, int(r + (255 - r) * 0.50))
        sg = min(255, int(g + (255 - g) * 0.50))
        sb = min(255, int(b + (255 - b) * 0.50))

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = int(r * dark); arr[:, :, 1] = int(g * dark); arr[:, :, 2] = int(b * dark)
    arr[:, :, 3] = 255
    spacing = max(4, int(h * rng.uniform(0.015, 0.030)))
    line_bright = rng.uniform(0.20, 0.35)
    for y in range(0, h, spacing):
        arr[y, :, 0] = int(sr * line_bright)
        arr[y, :, 1] = int(sg * line_bright)
        arr[y, :, 2] = int(sb * line_bright)
    fade = np.linspace(1.0, 0.70, h, dtype=np.float32)
    for ci in range(3):
        arr[:, :, ci] = np.clip(arr[:, :, ci].astype(np.float32) * fade[:, None], 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def _fondo_angular_dark(primary_hex: str, secondary_hex: str, w: int, h: int, seed: int = 0) -> Image.Image:
    """
    Base muy oscura con 2-3 formas triangulares semitransparentes del secundario.
    Composición angular dinámica — posiciones aleatorias por seed.
    """
    r, g, b = _hex_rgb(primary_hex)
    rng = np.random.default_rng(seed)
    dark = rng.uniform(0.06, 0.11)
    if secondary_hex:
        sr, sg, sb = _hex_rgb(secondary_hex)
    else:
        sr = min(255, int(r + (255 - r) * 0.40))
        sg = min(255, int(g + (255 - g) * 0.40))
        sb = min(255, int(b + (255 - b) * 0.40))

    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :, 0] = int(r * dark); arr[:, :, 1] = int(g * dark); arr[:, :, 2] = int(b * dark)
    arr[:, :, 3] = 255
    img = Image.fromarray(arr, "RGBA")
    n_shapes = int(rng.integers(2, 4))
    for _ in range(n_shapes):
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        pts = [
            (int(rng.uniform(-0.1, 1.1) * w), int(rng.uniform(-0.1, 1.1) * h)),
            (int(rng.uniform(-0.1, 1.1) * w), int(rng.uniform(-0.1, 1.1) * h)),
            (int(rng.uniform(-0.1, 1.1) * w), int(rng.uniform(-0.1, 1.1) * h)),
        ]
        opacity = int(rng.integers(30, 65))
        od.polygon(pts, fill=(sr, sg, sb, opacity))
        img = Image.alpha_composite(img, ov)
    return img


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
    if IMAGE_PROVIDER == "replicate":
        return _llamar_replicate(prompt, size)
    # Proveedor por defecto: OpenAI
    response = client.images.generate(
        model=IMAGE_MODEL_OPENAI,
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


def _llamar_replicate(prompt: str, size: str) -> Image.Image:
    """Generación de imágenes vía Replicate (Flux). Requiere REPLICATE_API_TOKEN."""
    try:
        import replicate
    except ImportError:
        raise ImportError("Instala replicate: pip install replicate")

    aspect = "2:3" if "1536" in size else "1:1"
    output = replicate.run(
        REPLICATE_MODEL,
        input={"prompt": prompt, "aspect_ratio": aspect, "output_format": "png"},
    )
    url = str(output[0]) if isinstance(output, list) else str(output)
    with urllib.request.urlopen(url) as resp:
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
