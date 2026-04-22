"""
CAPA 2 — Compositor de Diseño
Sustain Awards

Combina el fondo generado por gpt-image-1 con el logo exacto de la marca
y los textos del galardón, produciendo el diseño final del trofeo.

Pipeline por propuesta:
  1. gpt-image-1 genera el fondo artístico (capa_dalle.py)
  2. Overlay semitransparente de color de marca (coherencia cromática)
  3. Logo exacto en la posición definida
  4. Texto del galardón con contraste garantizado
"""

import base64
import os
import tempfile
from io import BytesIO

import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ─── Utilidades de color ──────────────────────────────────────────────────────

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    r, g, b = hex_to_rgb(hex_color)
    return (r, g, b, alpha)


def _luminancia(rgb: tuple) -> float:
    def canal(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def _ratio_contraste(hex1: str, hex2: str) -> float:
    try:
        l1 = _luminancia(hex_to_rgb(hex1))
        l2 = _luminancia(hex_to_rgb(hex2))
        if l1 < l2:
            l1, l2 = l2, l1
        return (l1 + 0.05) / (l2 + 0.05)
    except Exception:
        return 1.0


def color_texto_seguro(texto_hex: str, bg_tone: str) -> str:
    """
    Valida que el color de texto tenga contraste sobre el tono de fondo.
    bg_tone: "dark" | "light" | "mid"
    Si no hay contraste suficiente, elige blanco o negro.
    """
    bg_ref = {"dark": "#0A0A0A", "light": "#F5F5F5", "mid": "#888888"}.get(bg_tone, "#888888")
    if _ratio_contraste(texto_hex, bg_ref) >= 3.0:
        return texto_hex
    return "#FFFFFF" if bg_tone == "dark" else "#1A1A1A"


def _tint(hex_color: str, factor: float) -> str:
    """Mezcla el color con blanco (factor 0=original, 1=blanco)."""
    r, g, b = hex_to_rgb(hex_color)
    return "#{:02x}{:02x}{:02x}".format(
        int(r + (255 - r) * factor),
        int(g + (255 - g) * factor),
        int(b + (255 - b) * factor),
    )


def _shade(hex_color: str, factor: float) -> str:
    """Mezcla el color con negro (factor 0=original, 1=negro)."""
    r, g, b = hex_to_rgb(hex_color)
    return "#{:02x}{:02x}{:02x}".format(
        int(r * (1 - factor)),
        int(g * (1 - factor)),
        int(b * (1 - factor)),
    )


def _color_sobre_region(img: Image.Image, texto_hex: str,
                         x: int, y: int, ancho: int, alto: int) -> str:
    """
    Verifica el contraste del color de texto contra los píxeles reales del fondo.
    Si no hay contraste suficiente (WCAG AA: ratio >= 4.5), ajusta progresivamente
    el color de marca aclarándolo u oscureciéndolo hasta lograr contraste,
    manteniendo la coherencia cromática con la identidad de la empresa.
    """
    try:
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(img.width,  x + ancho)
        y2 = min(img.height, y + alto)
        if x2 <= x1 or y2 <= y1:
            return texto_hex

        region = img.crop((x1, y1, x2, y2)).convert("RGB")
        arr    = np.array(region)
        med_r  = int(np.median(arr[:, :, 0]))
        med_g  = int(np.median(arr[:, :, 1]))
        med_b  = int(np.median(arr[:, :, 2]))
        bg_hex = "#{:02x}{:02x}{:02x}".format(med_r, med_g, med_b)

        if _ratio_contraste(texto_hex, bg_hex) >= 4.5:
            return texto_hex

        # Fondo oscuro → aclarar el color de marca progresivamente
        # Fondo claro  → oscurecer el color de marca progresivamente
        bg_lum = _luminancia((med_r, med_g, med_b))
        if bg_lum < 0.4:
            for f in [0.35, 0.55, 0.72, 0.88, 1.0]:
                candidate = _tint(texto_hex, f)
                if _ratio_contraste(candidate, bg_hex) >= 4.5:
                    return candidate
            return "#F0F0F0"
        else:
            for f in [0.35, 0.55, 0.72, 0.88, 1.0]:
                candidate = _shade(texto_hex, f)
                if _ratio_contraste(candidate, bg_hex) >= 4.5:
                    return candidate
            return "#1A1A1A"

    except Exception:
        return texto_hex


# ─── Fuentes ──────────────────────────────────────────────────────────────────

_FONT_STYLES: dict[str, list[str]] = {
    "display": [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/verdanab.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "editorial": [
        "C:/Windows/Fonts/georgiab.ttf",
        "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/cambriab.ttf",
        "C:/Windows/Fonts/timesbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ],
    "modern": [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ],
    "bold": [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}


def _cargar_fuente(size: int, style: str = "bold") -> ImageFont.ImageFont:
    rutas = _FONT_STYLES.get(style, _FONT_STYLES["bold"])
    for ruta in rutas + _FONT_STYLES["bold"]:
        try:
            return ImageFont.truetype(ruta, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _cargar_fuente_marca(size: int, font_family: str | None,
                          weight: int = 700, style_fallback: str = "bold",
                          style_category: str = "") -> ImageFont.ImageFont:
    """
    Carga la fuente de marca con fallback inteligente por categoría visual.
    Orden de prioridad:
      1. font_family exacta (local o Google Fonts)
      2. Alternativas del mismo style_category (FONT_CATALOG)
      3. Fuente del sistema (_cargar_fuente)
    Nunca lanza excepción.
    """
    if font_family:
        try:
            from scripts.font_manager import get_font_path_with_fallback
            path = get_font_path_with_fallback(font_family, style_category or None, weight)
            if path and path.exists():
                print(f"  [renderer] Fuente: {path.name} (size={size})")
                return ImageFont.truetype(str(path), size)
        except Exception as e:
            print(f"  [renderer] Fuente marca no disponible ({font_family} w{weight}): {e}")
    return _cargar_fuente(size, style_fallback)


def cargar_fuentes(size_lg=18, size_md=14, size_sm=12, size_xs=10) -> dict:
    return {
        "bold_lg": _cargar_fuente(size_lg, "bold"),
        "bold_md": _cargar_fuente(size_md, "bold"),
        "regular": _cargar_fuente(size_sm, "modern"),
        "small":   _cargar_fuente(size_xs, "modern"),
    }


# ─── Texto: wrap y renderizado ────────────────────────────────────────────────

def _tw(draw: ImageDraw.Draw, texto: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), texto, font=font)
    return bbox[2] - bbox[0]


def _wrap_sin_partir(draw, texto, font, max_width) -> list[str]:
    """Divide en líneas sin partir palabras."""
    if not texto:
        return []
    lineas, linea_actual, ancho_actual = [], [], 0
    espacio = _tw(draw, " ", font)
    for palabra in texto.split():
        w = _tw(draw, palabra, font)
        if not linea_actual:
            linea_actual.append(palabra)
            ancho_actual = w
        elif ancho_actual + espacio + w <= max_width:
            linea_actual.append(palabra)
            ancho_actual += espacio + w
        else:
            lineas.append(" ".join(linea_actual))
            linea_actual = [palabra]
            ancho_actual = w
    if linea_actual:
        lineas.append(" ".join(linea_actual))
    return lineas


def _fuente_optima(draw, bloques, size_inicial, max_width, max_height, style="bold"):
    """Devuelve la fuente más grande donde todos los bloques caben."""
    size = size_inicial
    while size >= 7:
        font = _cargar_fuente(size, style)
        h_linea = font.getbbox("A")[3] + 6
        espaciado = max(4, int(size * 0.4))
        altura_total = 0
        cabe = True
        for texto in bloques:
            if not texto:
                continue
            lineas = _wrap_sin_partir(draw, texto, font, max_width)
            for linea in lineas:
                if _tw(draw, linea, font) > max_width:
                    cabe = False
                    break
            altura_total += len(lineas) * h_linea + espaciado
            if not cabe:
                break
        if cabe and altura_total <= max_height:
            return font
        size -= 1
    return _cargar_fuente(7, style)


def _dibujar_bloque(draw, texto, y, font, color, x_start, text_width, alineacion) -> int:
    """Dibuja un bloque de texto. Devuelve Y final."""
    if not texto:
        return y
    lineas  = _wrap_sin_partir(draw, texto, font, text_width)
    h_linea = font.getbbox("A")[3] + 6
    for i, linea in enumerate(lineas):
        tw = _tw(draw, linea, font)
        if alineacion == "center":
            x = x_start + max(0, (text_width - tw) // 2)
        elif alineacion == "right":
            x = x_start + max(0, text_width - tw)
        else:  # left
            x = x_start
        draw.text((x, y + i * h_linea), linea, fill=color, font=font)
    return y + len(lineas) * h_linea


# ─── Logo ─────────────────────────────────────────────────────────────────────

def _preparar_logo(logo_path: str, treatment: str,
                   opacity: float = 1.0, band_color: str | None = None) -> Image.Image:
    """
    treatment:
      "blanco"     — remapea a rango 200-255 preservando luminancia (claro sobre oscuro)
      "negro"      — remapea a rango 0-60 preservando luminancia (oscuro sobre claro)
      "color"      — colores originales (elimina solo el fondo blanco si no tiene alfa)
      "watermark"  — colores originales con opacidad reducida (usa opacity)
      "banda"      — blanco sobre rectángulo de color de marca (band_color)
    """
    logo_orig = Image.open(logo_path)
    has_alpha = logo_orig.mode in ("RGBA", "LA", "PA")
    logo = logo_orig.convert("RGBA")
    arr  = np.array(logo, dtype=np.float32)

    # Solo eliminar fondo blanco si el logo NO tiene canal alfa propio
    # (evita borrar elementos blancos intencionales de logos con transparencia)
    if not has_alpha:
        white = (arr[:, :, 0] > 228) & (arr[:, :, 1] > 228) & (arr[:, :, 2] > 228)
        arr[white, 3] = 0.0

    opaque = arr[:, :, 3] > 30

    if treatment == "blanco":
        # Preservar luminancia: píxeles oscuros → blanco brillante, claros → blanco suave
        # Resultado: internos del logo distinguibles (no rectangulo uniforme)
        lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        light = np.clip(200.0 + (255.0 - lum) * (55.0 / 255.0), 200.0, 255.0)
        arr[opaque, 0] = light[opaque]
        arr[opaque, 1] = light[opaque]
        arr[opaque, 2] = light[opaque]
        arr[opaque, 3] = 255.0

    elif treatment == "negro":
        # Preservar luminancia: píxeles claros → gris oscuro, oscuros → casi negro
        lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        dark = np.clip(lum * (60.0 / 255.0), 0.0, 60.0)
        arr[opaque, 0] = dark[opaque]
        arr[opaque, 1] = dark[opaque]
        arr[opaque, 2] = dark[opaque]
        arr[opaque, 3] = 255.0

    elif treatment == "watermark":
        alpha_val = float(max(20, min(255, int(opacity * 255))))
        arr[opaque, 3] = alpha_val
    # "color" y "banda": se usan los colores originales

    return Image.fromarray(arr.astype(np.uint8))


def _render_logo(concepto: dict, img: Image.Image,
                 logo_path: str, w: int, h: int) -> tuple[Image.Image, int]:
    if not logo_path:
        return img, int(h * 0.30)

    logo_cfg   = concepto.get("logo", {})
    treatment  = logo_cfg.get("treatment", "blanco")
    position   = logo_cfg.get("position", "top_center")
    scale      = float(logo_cfg.get("scale", 0.60))
    opacity    = float(logo_cfg.get("opacity", 0.18 if treatment == "watermark" else 1.0))
    band_color = logo_cfg.get("band_color")  # "#HEX" solo para treatment="banda"

    try:
        logo = _preparar_logo(logo_path, treatment, opacity, band_color)
    except Exception:
        return img, int(h * 0.30)

    # ── Watermark grande centrado — se pega ANTES del texto y no bloquea logo_bottom ──
    if treatment == "watermark":
        max_w = int(w * min(scale, 0.90))
        max_h = int(h * 0.70)
        ratio = min(max_w / logo.width, max_h / logo.height)
        logo  = logo.resize((max(1, int(logo.width * ratio)),
                             max(1, int(logo.height * ratio))), Image.LANCZOS)
        lx = (w - logo.width) // 2
        ly = (h - logo.height) // 2
        img.paste(logo, (lx, ly), logo)
        # El watermark no define logo_bottom; devolvemos zona superior libre
        return img, int(h * 0.08)

    max_w = int(w * scale)
    max_h = int(h * 0.22)
    ratio = min(max_w / logo.width, max_h / logo.height)
    logo  = logo.resize((max(1, int(logo.width * ratio)),
                         max(1, int(logo.height * ratio))), Image.LANCZOS)

    mg = int(h * 0.04)

    if position == "top_center":
        lx, ly = (w - logo.width) // 2, mg
    elif position == "top_left":
        lx, ly = mg, mg
    elif position == "top_right":
        lx, ly = w - logo.width - mg, mg
    elif position == "center":
        lx, ly = (w - logo.width) // 2, (h - logo.height) // 2
    elif position == "bottom_center":
        lx, ly = (w - logo.width) // 2, h - logo.height - mg
    else:
        lx, ly = (w - logo.width) // 2, mg

    # ── Auto-corrección universal: medir fondo real y garantizar contraste ────
    # Claude asigna el tratamiento sin ver el fondo DALLE; medimos aquí y corregimos.
    # Cubre: blanco/negro (threshold incorrecto) y color (incompatibilidad cromática).
    if treatment != "watermark":
        x1 = max(0, lx); y1 = max(0, ly)
        x2 = min(w, lx + logo.width); y2 = min(h, ly + logo.height)
        if x2 > x1 and y2 > y1:
            region = np.array(img.crop((x1, y1, x2, y2)).convert("RGB"))
            bg_r = int(np.median(region[:, :, 0]))
            bg_g = int(np.median(region[:, :, 1]))
            bg_b = int(np.median(region[:, :, 2]))
            lum  = _luminancia((bg_r, bg_g, bg_b))

            # Tratamiento óptimo por luminancia real del fondo
            # 0.45 es el punto de equilibrio: por debajo → logo blanco, por encima → negro
            optimal = "blanco" if lum < 0.45 else "negro"

            new_treatment = None

            if treatment in ("blanco", "negro") and treatment != optimal:
                new_treatment = optimal

            elif treatment == "color":
                # Verificar distancia cromática logo–fondo
                logo_arr = np.array(logo)
                opaque   = logo_arr[:, :, 3] > 30
                if opaque.any():
                    lr = int(np.median(logo_arr[opaque, 0]))
                    lg = int(np.median(logo_arr[opaque, 1]))
                    lb = int(np.median(logo_arr[opaque, 2]))
                    # Distancia euclidiana RGB (max posible ≈ 441)
                    dist = ((lr - bg_r) ** 2 + (lg - bg_g) ** 2 + (lb - bg_b) ** 2) ** 0.5
                    if dist < 75:   # colores demasiado similares → logo se funde con fondo
                        new_treatment = optimal

            if new_treatment:
                try:
                    logo2  = _preparar_logo(logo_path, new_treatment)
                    ratio2 = min(max_w / logo2.width, max_h / logo2.height)
                    logo   = logo2.resize(
                        (max(1, int(logo2.width  * ratio2)),
                         max(1, int(logo2.height * ratio2))), Image.LANCZOS)
                    print(f"  [logo] Auto-corrección: {treatment} → {new_treatment} "
                          f"(lum={lum:.2f})")
                    treatment = new_treatment
                except Exception:
                    pass

    # ── treatment="banda": rectángulo de color de marca detrás del logo ──
    if treatment == "banda" and band_color:
        try:
            pad_x = int(w * 0.06)
            pad_y = int(h * 0.018)
            br, bg, bb = hex_to_rgb(band_color)
            draw_tmp = ImageDraw.Draw(img)
            draw_tmp.rectangle(
                [(0, ly - pad_y), (w, ly + logo.height + pad_y)],
                fill=(br, bg, bb, 230)
            )
            # Logo en blanco sobre la banda
            logo_b = _preparar_logo(logo_path, "blanco")
            ratio2 = min(max_w / logo_b.width, max_h / logo_b.height)
            logo_b = logo_b.resize((max(1, int(logo_b.width * ratio2)),
                                    max(1, int(logo_b.height * ratio2))), Image.LANCZOS)
            lx = (w - logo_b.width) // 2
            img.paste(logo_b, (lx, ly), logo_b)
            return img, ly + logo_b.height
        except Exception:
            pass

    img.paste(logo, (lx, ly), logo)
    return img, ly + logo.height


# ─── Texto ────────────────────────────────────────────────────────────────────

def _render_texto(concepto: dict, img: Image.Image, award: dict,
                  w: int, h: int, logo_bottom: int) -> Image.Image:
    draw = ImageDraw.Draw(img)
    tc   = concepto.get("text") or concepto.get("text_style", {})

    # ── Configuración base ────────────────────────────────────────────
    color_hex      = tc.get("color", "#FFFFFF")
    alineacion     = tc.get("alignment", "center")
    font_style     = tc.get("font_style", "bold")
    font_family    = tc.get("font_family")  # Google Fonts name o None
    font_style_cat = tc.get("font_style_category", "")  # categoría visual para fallback
    margin_h       = int(w * float(tc.get("margin_h", 0.07)))
    layout         = tc.get("layout", "stacked")
    sep_lines      = tc.get("separator_lines", False)
    spacing_scale  = max(0.2, float(tc.get("spacing_scale", 1.0)))
    text_anchor    = tc.get("text_anchor", "center")

    # ── Colores y alineaciones por elemento ──────────────────────────
    hl_color  = tc.get("headline_color")  or color_hex
    rec_color = tc.get("recipient_color") or color_hex
    sub_color = tc.get("subtitle_color")  or color_hex
    hl_align  = tc.get("headline_alignment")  or alineacion
    rec_align = tc.get("recipient_alignment") or alineacion
    sub_align = tc.get("subtitle_alignment")  or alineacion
    rec_block = tc.get("recipient_block_color")  # "#HEX" o None

    x_start    = margin_h
    text_width = max(60, w - 2 * margin_h)

    # ── Zona horizontal por concepto (P1=izquierda, P5=derecha) ─────
    _pid_zone = concepto.get("proposal_id", 1)
    _i6_zone  = (_pid_zone - 1) % 6
    if _i6_zone == 0:        # P1 — zona izquierda (74% del ancho)
        text_width = max(60, int(w * 0.74) - margin_h)
        # alineación forzada izquierda
        if hl_align  == "center": hl_align  = "left"
        if rec_align == "center": rec_align = "left"
        if sub_align == "center": sub_align = "left"
    elif _i6_zone == 4:      # P5 — zona derecha (empieza en 32%)
        x_start    = max(margin_h, int(w * 0.32))
        text_width = max(60, w - x_start - margin_h)
        if hl_align  == "center": hl_align  = "right"
        if rec_align == "center": rec_align = "right"
        if sub_align == "center": sub_align = "right"

    # ── Geometría vertical ───────────────────────────────────────────
    # Layouts de canvas completo: elementos distribuidos por toda la altura
    # (headline arriba, recipient al centro, subtitle abajo — sin zona fija bajo el logo)
    _FULL_CANVAS = {"spread", "staggered", "billboard", "vertical"}
    if layout in _FULL_CANVAS:
        # y_start respeta logo_bottom — headline nunca entra en la zona del logo
        y_start = max(int(h * 0.04), logo_bottom + int(h * 0.018))
        y_end   = int(h * 0.96)
        sep_y   = None
    elif layout == "logo_bottom":
        y_start = int(h * 0.06)
        y_end   = int(h * 0.72)
        sep_y   = None
    else:  # stacked
        sep_y   = int(logo_bottom + (h - logo_bottom) * 0.10)
        y_start = sep_y + int(h * 0.03)
        y_end   = int(h * 0.97)

    # ── Contraste real sobre píxeles del fondo ───────────────────────
    zone_h   = max(1, y_end - y_start)
    bg_tone  = concepto.get("bg_tone", "dark")

    # Acento de marca para el PIL renderer (misma lógica que _build_html)
    _pil_ov_col = ((concepto.get("color_overlay") or {}).get("color") or "").strip()
    _pil_accent = _pil_ov_col if _is_vivid(_pil_ov_col) else (
                      hl_color if _is_vivid(hl_color) else (
                          rec_color if _is_vivid(rec_color) else hl_color))
    _pil_acc_rgb = hex_to_rgb(_pil_accent)
    # Color estructural: secundario si vívido, si no acento principal
    _pil_sec = (concepto.get("_secondary") or "").strip()
    _pil_struct = _pil_sec if _is_vivid(_pil_sec) else _pil_accent
    _pil_struct_rgb = hex_to_rgb(_pil_struct)
    # En fondos oscuros: aclarar el color estructural para que las barras/bandas
    # sean claramente visibles incluso en paletas monocromáticas (ej: azul-sobre-azul).
    if bg_tone == "dark":
        _sr, _sg, _sb = _pil_struct_rgb
        _pil_struct_rgb = (
            min(255, int(_sr + (255 - _sr) * 0.42)),
            min(255, int(_sg + (255 - _sg) * 0.42)),
            min(255, int(_sb + (255 - _sb) * 0.42)),
        )

    # En fondos claros forzamos colores oscuros de partida para evitar texto invisible
    if bg_tone == "light":
        color_hex = color_hex if _ratio_contraste(color_hex, "#F5F5F5") >= 3.0 else "#1A1A1A"
        hl_color  = hl_color  if _ratio_contraste(hl_color,  "#F5F5F5") >= 3.0 else "#1A1A1A"
        # P2/P5: permitir color secundario/acento para recipient si contraste suficiente
        _pid_pil  = concepto.get("proposal_id", 1)
        _i6_pil   = (_pid_pil - 1) % 6
        _p_color  = _pil_struct if _is_vivid(_pil_struct) and _ratio_contraste(_pil_struct, "#F5F5F5") >= 2.8 else (
                    _pil_accent if _is_vivid(_pil_accent) and _ratio_contraste(_pil_accent, "#F5F5F5") >= 2.8 else "")
        if _i6_pil in (1, 4) and _p_color:
            rec_color = _p_color
        elif _ratio_contraste(rec_color, "#F5F5F5") < 4.5:
            rec_color = "#0A0A0A"
        sub_color = sub_color if _ratio_contraste(sub_color, "#F5F5F5") >= 3.0 else "#444444"
    else:
        _pid_pil = concepto.get("proposal_id", 1)
        _i6_pil  = (_pid_pil - 1) % 6

    color_hex = _color_sobre_region(img, color_hex, x_start, y_start, text_width, zone_h)
    hl_color  = _color_sobre_region(img, hl_color,  x_start, y_start, text_width, zone_h // 3)
    rec_color = _color_sobre_region(img, rec_color, x_start, y_start + zone_h // 3, text_width, zone_h // 3)
    sub_color = _color_sobre_region(img, sub_color, x_start, y_end - zone_h // 3,   text_width, zone_h // 3)

    if sep_y is not None:
        draw.line([(x_start, sep_y), (x_start + text_width, sep_y)],
                  fill=(*hex_to_rgb(color_hex), 100), width=1)

    # ── Textos del galardón ──────────────────────────────────────────
    headline  = award.get("headline", "")
    recipient = award.get("recipient", "")
    subtitle  = award.get("subtitle", "")
    fecha     = str(award.get("fecha", "")) if award.get("fecha") else ""

    # Mayúsculas si Claude lo especifica (impacto geométrico en marcas modernas)
    if tc.get("recipient_uppercase") and recipient:
        recipient = recipient.upper()

    # ── Tamaños de fuente ────────────────────────────────────────────
    # Canvas estrecho (247×793): text_width ≈ 209px. Ratios basados en h producen
    # fuentes de 150px+ que nunca caben. Cap inicial agresivo por text_width.
    sz_hl  = max(8, min(int(h * float(tc.get("headline_size_ratio",  0.065))), int(text_width * 0.35)))
    sz_rec = max(8, min(int(h * float(tc.get("recipient_size_ratio", 0.16))),  int(text_width * 0.45)))
    sz_sub = max(7, min(int(h * float(tc.get("subtitle_size_ratio",  0.040))), int(text_width * 0.25)))

    n_seps     = (1 if sep_lines and headline else 0) + (1 if sep_lines and recipient else 0)
    max_text_h = max(20, zone_h - n_seps * int(h * 0.025))

    def _h_bloque(texto, size):
        if not texto: return 0
        f = _cargar_fuente(size, font_style)
        return len(_wrap_sin_partir(draw, texto, f, text_width)) * (f.getbbox("A")[3] + 6)

    n_blocks = sum(1 for t in [headline, recipient, subtitle, fecha] if t)
    esp_base = max(4, int(sz_rec * 0.45 * spacing_scale))
    total_h  = (_h_bloque(headline, sz_hl) + _h_bloque(recipient, sz_rec)
                + _h_bloque(subtitle, sz_sub) + _h_bloque(fecha, sz_sub)
                + esp_base * max(0, n_blocks - 1))

    # Escalar por altura si no caben verticalmente
    if total_h > max_text_h and total_h > 0:
        factor = max_text_h / total_h
        sz_hl  = max(8, int(sz_hl  * factor))
        sz_rec = max(8, int(sz_rec * factor))
        sz_sub = max(7, int(sz_sub * factor))
        esp_base = max(4, int(sz_rec * 0.45 * spacing_scale))
        total_h  = (_h_bloque(headline, sz_hl) + _h_bloque(recipient, sz_rec)
                    + _h_bloque(subtitle, sz_sub) + _h_bloque(fecha, sz_sub)
                    + esp_base * max(0, n_blocks - 1))

    # Cargar fuentes reales y ajustar por anchura con ellas (no con fuente del sistema)
    # La fuente de marca puede ser más ancha que el fallback — medir con la fuente exacta.
    font_hl  = _cargar_fuente_marca(sz_hl,  font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
    font_rec = _cargar_fuente_marca(sz_rec, font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
    font_sub = _cargar_fuente_marca(sz_sub, font_family, weight=400, style_fallback=font_style, style_category=font_style_cat)

    def _max_palabra(texto, font):
        if not texto:
            return 0
        return max((_tw(draw, p, font) for p in texto.split()), default=0)

    # Reducir con paso geométrico (12% por iteración) — converge en ~25 pasos
    # desde cualquier tamaño inicial hasta el que quepa en text_width.
    limite = int(text_width * 0.97)
    for _ in range(30):
        changed = False
        if _max_palabra(headline,  font_hl)  > limite:
            sz_hl  = max(8, int(sz_hl  * 0.88))
            font_hl  = _cargar_fuente_marca(sz_hl,  font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
            changed = True
        if _max_palabra(recipient, font_rec) > limite:
            sz_rec = max(8, int(sz_rec * 0.88))
            font_rec = _cargar_fuente_marca(sz_rec, font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
            changed = True
        if _max_palabra(subtitle,  font_sub) > limite:
            sz_sub = max(7, int(sz_sub * 0.88))
            font_sub = _cargar_fuente_marca(sz_sub, font_family, weight=400, style_fallback=font_style, style_category=font_style_cat)
            changed = True
        if not changed:
            break

    # ── Decoraciones por concepto (PIL) — capa de fondo antes del texto ──
    # Equivalente a las decoraciones CSS del HTML renderer.
    if _i6_pil == 0:
        # P1: Círculo watermark esquina inferior derecha en color estructural de marca
        cs  = int(min(w, h) * 0.72)
        cx  = int(w * 0.80)
        cy  = int(h * 0.74)
        draw.ellipse([cx - cs//2, cy - cs//2, cx + cs//2, cy + cs//2],
                     outline=(*_pil_struct_rgb, 41), width=2)
        # P1: headline en color estructural de marca
        if _is_vivid(_pil_struct):
            hl_color = _pil_struct

    elif _i6_pil == 2:
        # P3: Barra vertical gruesa + barra horizontal cruzada en color secundario
        bar_w   = max(14, int(w * 0.040))
        bar_x   = max(2, margin_h - bar_w - 6)
        bar_top_d = int(h * 0.06)
        bar_h_d   = int(h * 0.88)
        draw.rectangle([bar_x, bar_top_d, bar_x + bar_w, bar_top_d + bar_h_d],
                       fill=(*_pil_struct_rgb, 242))
        cross_y_d = int(h * 0.47)
        cross_w_d = int(w * 0.28)
        draw.rectangle([bar_x + bar_w + 2, cross_y_d,
                        bar_x + bar_w + 2 + cross_w_d, cross_y_d + 2],
                       fill=(*_pil_struct_rgb, 115))

    elif _i6_pil == 5:
        # P6: Círculo watermark centrado en blanco
        cs  = int(min(w, h) * 0.70)
        cx  = w // 2
        cy  = int(h * 0.52)
        draw.ellipse([cx - cs//2, cy - cs//2, cx + cs//2, cy + cs//2],
                     outline=(255, 255, 255, 31), width=3)

    # ── Layouts de canvas completo ───────────────────────────────────

    if layout == "spread":
        # Headline: bajo el logo · Recipient: centro exacto del canvas · Subtitle: muy abajo
        # y_start ya incorpora logo_bottom — nunca entra en la zona del logo
        rec_h = _h_bloque(recipient, sz_rec)

        y_hl  = y_start                       # respeta logo_bottom
        y_rec = h // 2 - rec_h // 2          # centro absoluto del canvas
        y_sub = int(h * 0.85)
        y_fec = int(h * 0.91)

        # P5: triple punto de acento entre headline y recipient
        if _i6_pil == 4:
            gap_av = max(0, y_rec - (y_hl + sz_hl + 6))
            dot_y5 = y_hl + sz_hl + max(10, gap_av // 2 - 4)
            dot_y5 = min(dot_y5, y_rec - 20)
            dot_c  = _pil_struct_rgb if _is_vivid(_pil_struct) else (_pil_acc_rgb if _is_vivid(_pil_accent) else hex_to_rgb(rec_color))
            for di, (dx_off, ds) in enumerate([(-14, 5), (0, 7), (14, 5)]):
                cx_d = w // 2 + dx_off
                alpha = 153 if ds == 5 else 230
                draw.ellipse([cx_d - ds//2, dot_y5 - ds//2,
                              cx_d + ds//2, dot_y5 + ds//2],
                             fill=(*dot_c, alpha))

        if headline:
            _dibujar_bloque(draw, headline, y_hl, font_hl,
                            hex_to_rgba(hl_color, 220), x_start, text_width, hl_align)
        if recipient:
            if rec_block:
                try:
                    rb  = hex_to_rgb(rec_block)
                    pad = int(h * 0.018)
                    draw.rectangle([(0, y_rec - pad), (w, y_rec + rec_h + pad)],
                                   fill=(*rb, 220))
                    rec_color = _color_sobre_region(img, rec_color, 0, y_rec - pad,
                                                    w, rec_h + 2 * pad)
                except Exception:
                    pass
            _dibujar_bloque(draw, recipient, y_rec, font_rec,
                            hex_to_rgba(rec_color, 255), x_start, text_width, rec_align)
        if subtitle:
            _dibujar_bloque(draw, subtitle, y_sub, font_sub,
                            hex_to_rgba(sub_color, 190), x_start, text_width, sub_align)
        if fecha:
            _dibujar_bloque(draw, fecha, y_fec, font_sub,
                            hex_to_rgba(sub_color, 160), x_start, text_width, sub_align)
        return img

    if layout == "staggered":
        # Headline: arriba derecha (bajo logo) · Recipient: ENORME izquierda, centro
        # Subtitle: abajo derecha — composición diagonal / asimétrica extrema
        # Inspirado en: PepsiCo BAM — tensión visual por asimetría deliberada
        rec_h = _h_bloque(recipient, sz_rec)

        y_hl  = y_start                       # respeta logo_bottom
        y_rec = h // 2 - rec_h // 2          # centro absoluto del canvas
        y_sub = int(h * 0.87)
        y_fec = int(h * 0.92)

        if headline:
            _dibujar_bloque(draw, headline, y_hl, font_hl,
                            hex_to_rgba(hl_color, 200), x_start, text_width, "right")
        if recipient:
            _dibujar_bloque(draw, recipient, y_rec, font_rec,
                            hex_to_rgba(rec_color, 255), x_start, text_width, "left")
        if subtitle:
            _dibujar_bloque(draw, subtitle, y_sub, font_sub,
                            hex_to_rgba(sub_color, 190), x_start, text_width, "right")
        if fecha:
            _dibujar_bloque(draw, fecha, y_fec, font_sub,
                            hex_to_rgba(sub_color, 160), x_start, text_width, "right")
        return img

    if layout == "vertical":
        # Recipient girado 90° CCW ocupa toda la altura del lado derecho
        # Headline y subtitle quedan en el lado izquierdo (debajo del logo / muy abajo)
        # Inspirado en: Enter Der Open Access Award
        mg     = int(h * 0.04)
        band_w = int(w * 0.28)         # banda más estrecha → más espacio al lado izquierdo
        v_avail = h - 2 * mg

        # Imagen temporal landscape para dibujar el recipient horizontalmente
        tmp      = Image.new("RGBA", (v_avail, band_w), (0, 0, 0, 0))
        tmp_draw = ImageDraw.Draw(tmp)

        font_v = _fuente_optima(tmp_draw, [recipient] if recipient else ["X"],
                                band_w - 4, v_avail, band_w - 4, font_style)

        if recipient:
            lines = _wrap_sin_partir(tmp_draw, recipient, font_v, v_avail)
            lh    = font_v.getbbox("A")[3] + 6
            tot_h = len(lines) * lh
            ty    = max(0, (band_w - tot_h) // 2)
            for i, line in enumerate(lines):
                tw = _tw(tmp_draw, line, font_v)
                tx = max(0, (v_avail - tw) // 2)
                tmp_draw.text((tx, ty + i * lh), line,
                              fill=hex_to_rgba(rec_color, 255), font=font_v)

        # Rotar 90° CCW → el texto se lee de abajo hacia arriba (efecto lateral)
        rotated = tmp.rotate(90, expand=True)
        rx = w - rotated.width - int(w * 0.03)
        img.paste(rotated, (rx, mg), rotated)

        # Lado izquierdo: ancho real disponible entre margen y la banda vertical
        left_w = max(40, rx - x_start - int(w * 0.03))

        # Headline: empieza DEBAJO del logo para no solaparse con él
        hl_top = max(mg, logo_bottom + int(h * 0.025))
        if headline:
            # Auto-tamaño: garantiza que ninguna palabra desborde left_w
            font_hl_v = _fuente_optima(draw, [headline], sz_hl,
                                       left_w, int(h * 0.20), font_style)
            _dibujar_bloque(draw, headline, hl_top, font_hl_v,
                            hex_to_rgba(hl_color, 220), x_start, left_w, "left")

        if subtitle:
            # Auto-tamaño subtitle también
            font_sub_v = _fuente_optima(draw, [subtitle], sz_sub,
                                        left_w, int(h * 0.10), font_style)
            _dibujar_bloque(draw, subtitle, int(h * 0.85), font_sub_v,
                            hex_to_rgba(sub_color, 190), x_start, left_w, "left")
        if fecha:
            _dibujar_bloque(draw, fecha, int(h * 0.91), font_sub,
                            hex_to_rgba(sub_color, 160), x_start, left_w, "left")
        return img

    if layout == "billboard":
        # Recipient llena prácticamente todo el canvas — headline y subtitle son micro-captions
        # Inspirado en: Premios Carpa, Booking — el nombre lo es TODO
        sz_hl_b  = max(6, int(h * 0.036))
        sz_sub_b = max(5, int(h * 0.028))
        font_hl_b  = _cargar_fuente(sz_hl_b,  font_style)
        font_sub_b = _cargar_fuente(sz_sub_b, font_style)
        # Headline respeta logo_bottom — nunca entra en la zona del logo
        mg_top = max(int(h * 0.04), logo_bottom + int(h * 0.018))
        # P4: banda en color secundario (efecto Booking: color 2 sobre fondo primario)
        if _i6_pil == 3 and bg_tone in ("dark", "mid"):
            band_top_b = int(h * 0.20)
            band_h_b   = int(h * 0.52)
            _b4_rgb = _pil_struct_rgb if _is_vivid(_pil_struct) else _pil_acc_rgb
            draw.rectangle([0, band_top_b, w, band_top_b + band_h_b],
                           fill=(*_b4_rgb, 71))  # ~28% opacity

        hl_h_px  = _h_bloque(headline, sz_hl_b)  if headline else 0
        sub_h_px = _h_bloque(subtitle, sz_sub_b) if subtitle else 0

        # Zona del recipient: desde bajo el headline hasta sobre el subtitle
        rec_top  = mg_top + hl_h_px + int(h * 0.02) if headline else mg_top
        rec_bot  = int(h * 0.87) if subtitle else int(h * 0.92)
        rec_zone = max(20, rec_bot - rec_top)

        font_rec_b = _fuente_optima(draw, [recipient] if recipient else ["X"],
                                    int(h * 0.34), text_width, rec_zone, font_style)
        if recipient:
            lineas_rec = _wrap_sin_partir(draw, recipient, font_rec_b, text_width)
            rec_h_px   = len(lineas_rec) * (font_rec_b.getbbox("A")[3] + 6)
            y_rec      = rec_top + max(0, (rec_zone - rec_h_px) // 2)
        else:
            y_rec = rec_top

        if headline:
            _dibujar_bloque(draw, headline, mg_top, font_hl_b,
                            hex_to_rgba(hl_color, 180), x_start, text_width, "center")
        if recipient:
            _dibujar_bloque(draw, recipient, y_rec, font_rec_b,
                            hex_to_rgba(rec_color, 255), x_start, text_width, "center")
        if subtitle:
            _dibujar_bloque(draw, subtitle, int(h * 0.88), font_sub_b,
                            hex_to_rgba(sub_color, 160), x_start, text_width, "center")
        if fecha:
            _dibujar_bloque(draw, fecha, int(h * 0.93), font_sub_b,
                            hex_to_rgba(sub_color, 130), x_start, text_width, "center")
        return img

    # ── Ancla vertical ───────────────────────────────────────────────
    if text_anchor == "top":
        y = y_start
    elif text_anchor == "bottom":
        y = max(y_start, y_end - total_h)
    else:
        y = y_start + max(0, (zone_h - total_h) // 2)

    # ── Helper separador ─────────────────────────────────────────────
    def _sep(y_pos):
        draw.line([(x_start, y_pos), (x_start + text_width, y_pos)],
                  fill=(*hex_to_rgb(color_hex), 80), width=1)
        return y_pos + int(h * 0.025)

    # ── Renderizado ──────────────────────────────────────────────────
    if headline:
        esp = max(4, int(font_hl.getbbox("A")[3] * 0.4 * spacing_scale))
        y = _dibujar_bloque(draw, headline, y, font_hl,
                            hex_to_rgba(hl_color, 255),
                            x_start, text_width, hl_align) + esp
        if sep_lines:
            y = _sep(y)
        # P1: punto de acento tras el headline en color secundario/acento
        elif _i6_pil == 0 and (_is_vivid(_pil_struct) or _is_vivid(_pil_accent)):
            dot_r = 4
            dot_cx = w // 2
            draw.ellipse([dot_cx - dot_r, y - dot_r, dot_cx + dot_r, y + dot_r],
                         fill=(*_pil_struct_rgb, 224))
            y += dot_r * 2 + esp
        # P6: regla gruesa tras el headline en color secundario si disponible
        elif _i6_pil == 5:
            rule_w6 = int(text_width * 0.78)
            rule_x6 = x_start + (text_width - rule_w6) // 2
            _r6_rgb = _pil_struct_rgb if _is_vivid(_pil_struct) else (255, 255, 255)
            _r6_alpha = 217 if _is_vivid(_pil_struct) else 107
            draw.rectangle([rule_x6, y, rule_x6 + rule_w6, y + 3],
                           fill=(*_r6_rgb, _r6_alpha))
            y += 3 + esp

    if recipient:
        esp  = max(4, int(font_rec.getbbox("A")[3] * 0.5 * spacing_scale))
        rh   = _h_bloque(recipient, sz_rec)
        pad  = int(h * 0.018)
        if rec_block:
            try:
                rb = hex_to_rgb(rec_block)
                draw.rectangle([(0, y - pad), (w, y + rh + pad)], fill=(*rb, 220))
                # Revalidar color del texto sobre el bloque recién dibujado
                rec_color = _color_sobre_region(img, rec_color, 0, y - pad, w, rh + 2 * pad)
            except Exception:
                pass
        y = _dibujar_bloque(draw, recipient, y, font_rec,
                            hex_to_rgba(rec_color, 255),
                            x_start, text_width, rec_align) + esp
        if sep_lines:
            y = _sep(y)

    if subtitle:
        esp = max(4, int(font_sub.getbbox("A")[3] * 0.4 * spacing_scale))
        y = _dibujar_bloque(draw, subtitle, y, font_sub,
                            hex_to_rgba(sub_color, 190),
                            x_start, text_width, sub_align) + esp

    if fecha:
        _dibujar_bloque(draw, fecha, y, font_sub,
                        hex_to_rgba(sub_color, 160),
                        x_start, text_width, sub_align)

    return img


# ─── Chroma key y composición de texto DALLE ─────────────────────────────────

def _extraer_texto_chroma(texto_img: Image.Image, bg_hex: str,
                           threshold: int = 35) -> Image.Image:
    """
    Extrae píxeles de texto usando distancia euclidiana al color de fondo sólido.

    Para cada píxel:
      dist = sqrt((R-bg_R)^2 + (G-bg_G)^2 + (B-bg_B)^2)   [0..441]
      dist <= threshold  → alpha=0   (fondo, transparentar)
      dist >  threshold  → alpha proporcional, saturado a 255 en zona de texto

    threshold=35 tolera variaciones de fondo puro de hasta ±35 por canal.
    Factor 180: satura el alpha a 255 rápido (texto completamente opaco en su interior).
    """
    rgba = texto_img.convert("RGBA")
    arr  = np.array(rgba, dtype=np.float32)

    bg_r, bg_g, bg_b = hex_to_rgb(bg_hex)
    diff = arr[:, :, :3] - np.array([bg_r, bg_g, bg_b], dtype=np.float32)
    dist = np.sqrt(np.sum(diff ** 2, axis=2))  # shape: (H, W)

    alpha = np.clip((dist - threshold) / (180.0 - threshold) * 255.0, 0, 255)
    alpha = np.where(dist <= threshold, 0.0, alpha)

    resultado = arr.copy().astype(np.uint8)
    resultado[:, :, 3] = alpha.astype(np.uint8)
    return Image.fromarray(resultado, "RGBA")


def _componer_capa_texto(texto_rgba: Image.Image, img: Image.Image,
                          y_start: int, y_end: int, margin_h: int,
                          text_anchor: str, w: int) -> Image.Image:
    """
    1. Autocrop: elimina filas/columnas con alpha total < 8 (halos de anti-aliasing)
    2. Escala: fit en (w - 2*margin_h) × (y_end - y_start), manteniendo aspect ratio
    3. Posiciona: centrado horizontal, vertical según text_anchor (top/center/bottom)
    4. Pega sobre img con canal alpha como máscara
    """
    arr   = np.array(texto_rgba)
    alpha = arr[:, :, 3]

    ALPHA_MIN = 8
    filas_con_texto = np.any(alpha > ALPHA_MIN, axis=1)
    cols_con_texto  = np.any(alpha > ALPHA_MIN, axis=0)

    if not np.any(filas_con_texto) or not np.any(cols_con_texto):
        return img  # imagen vacía: no hay texto que componer

    row_min = int(np.argmax(filas_con_texto))
    row_max = int(len(filas_con_texto) - np.argmax(filas_con_texto[::-1]))
    col_min = int(np.argmax(cols_con_texto))
    col_max = int(len(cols_con_texto) - np.argmax(cols_con_texto[::-1]))

    cropped = texto_rgba.crop((col_min, row_min, col_max, row_max))

    zona_w = max(1, w - 2 * margin_h)
    zona_h = max(1, y_end - y_start)
    ratio  = min(zona_w / cropped.width, zona_h / cropped.height)
    new_w  = max(1, int(cropped.width  * ratio))
    new_h  = max(1, int(cropped.height * ratio))
    scaled = cropped.resize((new_w, new_h), Image.LANCZOS)

    x_paste = margin_h + (zona_w - new_w) // 2
    if text_anchor == "top":
        y_paste = y_start
    elif text_anchor == "bottom":
        y_paste = max(y_start, y_end - new_h)
    else:
        y_paste = y_start + (zona_h - new_h) // 2

    img.paste(scaled, (x_paste, y_paste), scaled)
    return img


# ─── Overlay de color de marca ────────────────────────────────────────────────

def _apply_overlay(img: Image.Image, overlay_cfg: dict, w: int, h: int) -> Image.Image:
    if not overlay_cfg.get("active"):
        return img
    try:
        color   = hex_to_rgb(overlay_cfg.get("color", "#000000"))
        # Cap opacity: máx 0.28 — evita que una tinta de marca destruya el fondo DALLE
        raw_op  = float(overlay_cfg.get("opacity", 0.15))
        opacity = int(min(raw_op, 0.28) * 255)
        overlay = Image.new("RGBA", (w, h), (*color, opacity))
        return Image.alpha_composite(img, overlay)
    except Exception:
        return img


# ─── HTML/CSS Renderer (Playwright) ──────────────────────────────────────────

_pw_instance = None
_pw_browser  = None


def _get_browser():
    """Singleton Chromium headless — se lanza una vez por proceso Flask."""
    global _pw_instance, _pw_browser
    # Comprobar cache ANTES de importar (permite uso desde threads Flask sin re-importar)
    if _pw_browser is not None:
        try:
            if _pw_browser.is_connected():
                return _pw_browser
        except Exception:
            pass
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        print(f"  [HTML] Playwright no instalado: {e}")
        return None
    try:
        print("  [HTML] Lanzando Chromium...")
        _pw_instance = sync_playwright().start()
        _pw_browser  = _pw_instance.chromium.launch(headless=True)
        print(f"  [HTML] Chromium listo: v{_pw_browser.version}")
        return _pw_browser
    except Exception as e:
        import traceback
        print(f"  [HTML] ERROR Playwright ({type(e).__name__}): {e}")
        traceback.print_exc()
        return None


def _img_to_data_url(img: Image.Image, quality: int = 88) -> str:
    """Convierte PIL Image a data URL JPEG para inyectar como fondo HTML."""
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _build_font_css(font_family: str | None, style_category: str = "") -> tuple[str, str]:
    """
    Devuelve (css_declaration, font_family_css).
    Prioridad: fuente local (.ttf en assets/fonts/) → Google Fonts @import → system font.
    Usa get_font_path_with_fallback para aplicar el catálogo tipográfico por categoría visual.
    """
    if not font_family:
        return "", "'Segoe UI', Arial, sans-serif"

    try:
        from scripts.font_manager import get_font_path_with_fallback
        path_700 = get_font_path_with_fallback(font_family, style_category or None, 700)
        path_400 = get_font_path_with_fallback(font_family, style_category or None, 400)
    except Exception:
        path_700 = path_400 = None

    # Determinar la familia real resuelta (puede diferir del nombre pedido si hubo fallback)
    import re as _re
    resolved_family = font_family
    ref_path = path_700 or path_400
    if ref_path:
        # Extraer nombre limpio del filename: "Fredoka_One_700.ttf" → "Fredoka One"
        stem = _re.sub(r"_\d{3}$", "", ref_path.stem)
        resolved_family = stem.replace("_", " ")

    family_safe = resolved_family.replace("'", "").replace('"', "")

    if path_700 or path_400:
        # @font-face con archivos locales ya descargados — sin red
        blocks = []
        if path_400:
            url = str(path_400).replace("\\", "/")
            blocks.append(
                f"@font-face {{ font-family: '{family_safe}'; "
                f"src: url('file:///{url}'); font-weight: 400; }}"
            )
        if path_700:
            url = str(path_700).replace("\\", "/")
            blocks.append(
                f"@font-face {{ font-family: '{family_safe}'; "
                f"src: url('file:///{url}'); font-weight: 700; }}"
            )
        return "\n".join(blocks), f"'{family_safe}', sans-serif"
    else:
        # Google Fonts @import — requiere red; Playwright la carga via temp file
        family_url = font_family.replace(" ", "+")
        css = (f"@import url('https://fonts.googleapis.com/css2?"
               f"family={family_url}:wght@400;700&display=swap');")
        return css, f"'{font_family.replace(chr(39), '').replace(chr(34), '')}', sans-serif"


def _is_vivid(hex_color: str) -> bool:
    """True si el color tiene saturación significativa (no es gris/blanco/negro)."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
        mx, mn = max(r, g, b), min(r, g, b)
        return (mx - mn) / mx > 0.28 if mx > 0.08 else False
    except Exception:
        return False


def _build_html(concepto: dict, award: dict, bg_data_url: str,
                w: int, h: int, logo_bottom: int,
                hl_px: int = 0, rec_px: int = 0, sub_px: int = 0) -> str:
    """Construye el HTML completo con tratamiento tipográfico de diseñador por concepto.
    Cada uno de los 6 conceptos tiene su propio lenguaje visual: pesos, tracking,
    sombras, elementos decorativos (líneas, barras, puntos, bandas).
    Los tamaños en px vienen pre-calculados por PIL (métricas exactas de fuente).
    """
    tc = concepto.get("text_style", {})

    layout           = tc.get("layout", "stacked")
    anchor           = tc.get("text_anchor", "center")
    font_family      = tc.get("font_family")
    font_style_cat   = tc.get("font_style_category", "")
    spacing_scale    = max(0.3, float(tc.get("spacing_scale", 1.0)))
    bg_tone          = concepto.get("bg_tone", "dark")
    secondary_color  = concepto.get("_secondary", "") or ""
    accent_color     = concepto.get("_accent", "")    or ""

    margin_px = max(16, int(w * 0.08))

    # ── Zonas de composición horizontal por concepto ─────────────────
    # P1: texto en zona IZQUIERDA (60% del ancho) — deja espacio derecho para decoración
    # P5: texto en zona DERECHA (60% del ancho) — composición editorial asimétrica
    # Resto: ancho completo (margen simétrico estándar)
    pid_zone = concepto.get("proposal_id", 1)
    i6_zone  = (pid_zone - 1) % 6
    if i6_zone == 0:        # P1 — zona izquierda (deja 26% derecho libre)
        zone_l = margin_px
        zone_r = int(w * 0.26)
    elif i6_zone == 4:      # P5 — zona derecha
        zone_l = int(w * 0.32)
        zone_r = margin_px
    else:                   # resto — ancho completo
        zone_l = margin_px
        zone_r = margin_px

    # ── Colores con corrección de contraste ──────────────────────────
    hl_color  = tc.get("headline_color",  "#FFFFFF")
    rec_color = tc.get("recipient_color", "#FFFFFF")
    sub_color = tc.get("subtitle_color",  "#AAAAAA")

    if bg_tone == "light":
        if _ratio_contraste(hl_color,  "#F5F5F5") < 3.0: hl_color  = "#1A1A1A"
        if _ratio_contraste(rec_color, "#F5F5F5") < 4.5: rec_color = "#0A0A0A"
        if _ratio_contraste(sub_color, "#F5F5F5") < 2.5: sub_color = "#444444"
    elif bg_tone == "dark":
        if _ratio_contraste(hl_color,  "#0A0A0A") < 3.0: hl_color  = "#FFFFFF"
        if _ratio_contraste(rec_color, "#0A0A0A") < 4.5: rec_color = "#FFFFFF"
        if _ratio_contraste(sub_color, "#0A0A0A") < 2.5: sub_color = "#CCCCCC"

    # ── Tamaños en px ────────────────────────────────────────────────
    if not rec_px:
        rec_px = max(14, min(int(h * float(tc.get("recipient_size_ratio", 0.18))),
                             int((w - 2 * margin_px) * 0.42)))
    if not hl_px:
        hl_px  = max(10, min(int(h * float(tc.get("headline_size_ratio",  0.090))),
                             int((w - 2 * margin_px) * 0.30)))
    if not sub_px:
        sub_px = max(8,  min(int(h * float(tc.get("subtitle_size_ratio",  0.040))),
                             int((w - 2 * margin_px) * 0.20)))

    gap = max(6, int(rec_px * 0.22 * spacing_scale))

    # ── Alineaciones ─────────────────────────────────────────────────
    hl_align  = tc.get("headline_alignment",  "center")
    rec_align = tc.get("recipient_alignment", "center")
    sub_align = tc.get("subtitle_alignment",  "center")

    # ── Fuente ───────────────────────────────────────────────────────
    font_css, font_family_css = _build_font_css(font_family, font_style_cat)

    # ── Textos ───────────────────────────────────────────────────────
    import html as _h
    headline  = _h.escape(award.get("headline",  "") or "")
    recipient = _h.escape(award.get("recipient", "") or "")
    subtitle  = _h.escape(award.get("subtitle",  "") or "")
    fecha     = _h.escape(str(award.get("fecha", "") or ""))

    rec_upper = "uppercase" if tc.get("recipient_uppercase") else "none"

    # ══════════════════════════════════════════════════════════════════
    # TRATAMIENTO TIPOGRÁFICO POR CONCEPTO — lenguaje visual de diseñador
    # Cada concepto es un sistema gráfico distinto: pesos, tracking, color de
    # texto y elementos decorativos crean identidad visual diferenciada.
    # ══════════════════════════════════════════════════════════════════
    pid        = concepto.get("proposal_id", 1)
    i6         = (pid - 1) % 6

    # Acento de marca — color más saturado disponible en el concepto
    _overlay_color = ((concepto.get("color_overlay") or {}).get("color") or "").strip()
    accent_dec = _overlay_color if _is_vivid(_overlay_color) else (
        hl_color if _is_vivid(hl_color) else (
            rec_color if _is_vivid(rec_color) else hl_color
        )
    )
    # Color secundario estructural — se usa en barras/bandas para contraste máximo
    # Prioridad: secondary_color (si es vívido) > accent_dec
    struct_color = secondary_color if _is_vivid(secondary_color) else accent_dec
    # En fondos oscuros: aclarar el color estructural un 42% para visibilidad máxima
    # en paletas monocromáticas (azul-sobre-azul, verde-sobre-verde, etc.)
    if bg_tone == "dark":
        struct_color = _tint(struct_color, 0.42)

    # Valores por defecto
    hl_weight           = "700"
    hl_tracking         = "0.02em"
    rec_tracking        = "-0.01em"
    sub_tracking        = "0.15em"
    hl_line_height      = "1.18"
    rec_line_height     = "1.04"
    hl_extra_css        = ""
    rec_extra_css       = ""
    sub_extra_css       = ""
    decoracion_abs      = ""      # HTML decorativo posicionado absolutamente (detrás del texto)
    decoracion_after_hl = ""      # Elemento decorativo dentro del flujo stacked
    _p2_rule            = False
    _p5_dot             = False

    if i6 == 0:
        # ─── P1 PREMIUM OSCURO ───────────────────────────────────────
        # Sistema: headline en color de marca (no blanco) + separador punto +
        # recipient blanco con glow + círculo watermark esquina inferior.
        # Referencia: packaging premium, trofeos Cannes Lions.
        hl_weight    = "200"
        hl_tracking  = "0.22em"
        rec_tracking = "-0.03em"
        sub_tracking = "0.32em"
        hl_extra_css  = f"text-transform: uppercase; color: {struct_color}; opacity: 0.92;"
        rec_extra_css = "text-shadow: 0 4px 32px rgba(0,0,0,0.60);"
        sub_extra_css = "font-weight: 300; text-transform: uppercase; opacity: 0.50;"
        # Círculo watermark esquina inferior derecha — profundidad editorial
        cs = int(min(w, h) * 0.72)
        cx = int(w * 0.80)
        cy = int(h * 0.74)
        decoracion_abs = (
            f'<div style="position:absolute;left:{cx - cs//2}px;top:{cy - cs//2}px;'
            f'width:{cs}px;height:{cs}px;border:2px solid {struct_color};'
            f'opacity:0.16;border-radius:50%"></div>'
        )
        # Punto de acento entre headline y recipient
        decoracion_after_hl = (
            f'<div style="width:9px;height:9px;border-radius:50%;'
            f'background:{struct_color};opacity:0.88;align-self:center;margin:3px 0"></div>'
        )

    elif i6 == 1:
        # ─── P2 EDITORIAL BLANCO ─────────────────────────────────────
        # Sistema: recipient en color primario de marca (magenta/azul/etc. sobre blanco)
        # + headline ultra-thin casi invisible + regla editorial.
        # Referencia: editorial fashion magazine, AWS Awards, Dezeen.
        hl_weight    = "200"
        hl_tracking  = "0.28em"
        rec_tracking = "-0.04em"
        sub_tracking = "0.38em"
        hl_line_height = "1.22"
        hl_extra_css  = "text-transform: uppercase; opacity: 0.52;"
        sub_extra_css = "font-weight: 200; text-transform: uppercase; opacity: 0.40;"
        # Recipient en color secundario/acento si tiene contraste suficiente sobre fondo claro
        _p2_color = struct_color if _is_vivid(struct_color) and _ratio_contraste(struct_color, "#F5F5F5") >= 2.8 else (
            accent_dec if _is_vivid(accent_dec) and _ratio_contraste(accent_dec, "#F5F5F5") >= 2.8 else ""
        )
        if _p2_color:
            rec_extra_css = f"color: {_p2_color};"
        _p2_rule = True

    elif i6 == 2:
        # ─── P3 GRÁFICO AUDAZ ────────────────────────────────────────
        # Sistema: barra vertical GRUESA de marca (20px) + barra horizontal cruzada
        # + recipient ENORME tracking muy apretado. Tensión gráfica extrema.
        # Referencia: PepsiCo BAM, Nike campaign, Pentagram editorial.
        hl_tracking  = "0.07em"
        rec_tracking = "-0.05em"
        sub_tracking = "0.16em"
        hl_extra_css  = "text-transform: uppercase; opacity: 0.70;"
        rec_extra_css = "text-shadow: 0 8px 60px rgba(0,0,0,0.72);"
        sub_extra_css = "text-transform: uppercase; opacity: 0.65;"
        # Barra vertical gruesa — elemento gráfico principal
        bar_w   = max(14, int(w * 0.040))
        bar_x   = max(2, margin_px - bar_w - 6)
        bar_top = int(h * 0.06)
        bar_h   = int(h * 0.88)
        # Barra horizontal cruzada — tensión gráfica en la zona del recipient
        cross_y = int(h * 0.47)
        cross_w = int(w * 0.28)
        decoracion_abs = (
            f'<div style="position:absolute;left:{bar_x}px;top:{bar_top}px;'
            f'width:{bar_w}px;height:{bar_h}px;background:{struct_color};'
            f'opacity:0.95;border-radius:2px"></div>'
            f'<div style="position:absolute;left:{bar_x + bar_w + 2}px;top:{cross_y}px;'
            f'width:{cross_w}px;height:2px;background:{struct_color};opacity:0.45"></div>'
        )

    elif i6 == 3:
        # ─── P4 BILLBOARD IMPACTO ────────────────────────────────────
        # Sistema: banda de color de marca detrás del recipient (no gris oscuro) +
        # glow dramático en el nombre. Headline como micro-badge con tracking extremo.
        # Referencia: festival posters, Time magazine covers.
        hl_weight    = "700"
        hl_tracking  = "0.16em"
        rec_tracking = "-0.03em"
        sub_tracking = "0.26em"
        hl_extra_css  = "text-transform: uppercase; opacity: 0.78;"
        rec_extra_css = (
            f"text-shadow: 0 8px 65px rgba(0,0,0,0.80), "
            f"0 3px 22px rgba(0,0,0,0.45);"
        )
        sub_extra_css = "text-transform: uppercase; opacity: 0.70;"
        # Banda de color de marca (no gris oscuro) — da calidez y coherencia cromática
        band_top = int(h * 0.20)
        band_h   = int(h * 0.52)
        if bg_tone in ("dark", "mid"):
            # Usa el secundario si es vívido (efecto Booking: amarillo sobre azul)
            _band_col = struct_color if _is_vivid(struct_color) else accent_dec
            band_style = f"background:{_band_col};opacity:0.28"
        else:
            band_style = "background:rgba(0,0,0,0.14);opacity:1"
        decoracion_abs = (
            f'<div style="position:absolute;left:0;top:{band_top}px;'
            f'width:{w}px;height:{band_h}px;{band_style}"></div>'
        )

    elif i6 == 4:
        # ─── P5 MÍNIMO MODERNO ───────────────────────────────────────
        # Sistema: recipient en color de marca (si contraste OK) + headline casi
        # imperceptible + triple punto separador en acento de marca.
        # Referencia: Swiss design, Muji, Apple, trofeos Wired.
        hl_weight    = "200"
        hl_tracking  = "0.22em"
        rec_tracking = "0.01em"
        sub_tracking = "0.40em"
        hl_line_height = "1.25"
        hl_extra_css  = "text-transform: uppercase; opacity: 0.55;"
        sub_extra_css = "font-weight: 200; text-transform: uppercase; opacity: 0.36;"
        _p5_color = struct_color if _is_vivid(struct_color) and _ratio_contraste(struct_color, "#F5F5F5") >= 2.8 else (
            accent_dec if _is_vivid(accent_dec) and _ratio_contraste(accent_dec, "#F5F5F5") >= 2.8 else ""
        )
        if _p5_color:
            rec_extra_css = f"color: {_p5_color};"
        _p5_dot = True

    else:
        # ─── P6 MARCA PURA ───────────────────────────────────────────
        # Sistema: fondo sólido del primario + círculo watermark centrado +
        # regla gruesa de marca + recipient con glow suave.
        # Referencia: trofeos Apple Design Awards, GQ España.
        hl_weight    = "300"
        hl_tracking  = "0.18em"
        rec_tracking = "-0.02em"
        sub_tracking = "0.26em"
        hl_extra_css  = "text-transform: uppercase; opacity: 0.65;"
        rec_extra_css = "text-shadow: 0 4px 42px rgba(0,0,0,0.52);"
        sub_extra_css = "text-transform: uppercase; opacity: 0.60;"
        # Círculo watermark centrado — textura geométrica sobre el sólido de marca
        cs = int(min(w, h) * 0.70)
        cx = w // 2
        cy = int(h * 0.52)
        decoracion_abs = (
            f'<div style="position:absolute;left:{cx - cs//2}px;top:{cy - cs//2}px;'
            f'width:{cs}px;height:{cs}px;border:3px solid white;'
            f'opacity:0.12;border-radius:50%"></div>'
        )
        # Regla ancha y gruesa bajo el headline — usa secundario si vívido, si no blanco
        _p6_rule_color = struct_color if _is_vivid(struct_color) else "white"
        _p6_rule_op = "0.85" if _is_vivid(struct_color) else "0.42"
        decoracion_after_hl = (
            f'<div style="width:78%;height:3px;background:{_p6_rule_color};'
            f'opacity:{_p6_rule_op};align-self:center"></div>'
        )

    # ── CSS completo ─────────────────────────────────────────────────
    base_css = f"""
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        width: {w}px; height: {h}px;
        overflow: hidden; position: relative;
        background: url('{bg_data_url}') center/cover no-repeat;
    }}
    .hl {{
        font-family: {font_family_css};
        font-size: {hl_px}px; font-weight: {hl_weight};
        color: {hl_color}; text-align: {hl_align};
        line-height: {hl_line_height};
        letter-spacing: {hl_tracking};
        overflow-wrap: break-word; word-break: break-word;
        {hl_extra_css}
    }}
    .rec {{
        font-family: {font_family_css};
        font-size: {rec_px}px; font-weight: 700;
        color: {rec_color}; text-align: {rec_align};
        line-height: {rec_line_height};
        letter-spacing: {rec_tracking};
        overflow-wrap: break-word; word-break: break-word;
        text-transform: {rec_upper};
        {rec_extra_css}
    }}
    .sub {{
        font-family: {font_family_css};
        font-size: {sub_px}px; font-weight: 400;
        color: {sub_color}; text-align: {sub_align};
        line-height: 1.30; letter-spacing: {sub_tracking};
        overflow-wrap: break-word;
        {sub_extra_css}
    }}
    .fecha {{
        font-family: {font_family_css};
        font-size: {sub_px}px; font-weight: 300;
        color: {sub_color}; text-align: {sub_align};
        letter-spacing: {sub_tracking}; opacity: 0.70;
    }}
    """

    # ── Layouts ──────────────────────────────────────────────────────

    # Margen inferior y posición del headline respetando el logo
    _mg_bot = int(h * 0.04)  # margen para subtitle/fecha (abajo, no depende del logo)
    # El headline siempre empieza DEBAJO del logo — nunca antes
    _hl_top = max(int(h * 0.04), logo_bottom + int(h * 0.018))

    # P2: regla editorial bajo el headline
    if _p2_rule:
        rule_y  = _hl_top + hl_px + 12
        rule_w  = int((w - 2 * margin_px) * 0.45)
        rule_x  = margin_px if hl_align != "center" else (w - rule_w) // 2
        decoracion_abs = (
            f'<div style="position:absolute;top:{rule_y}px;'
            f'left:{rule_x}px;width:{rule_w}px;'
            f'height:1px;background:{rec_color};opacity:0.22"></div>'
        )
    # P5: triple punto de acento en color de marca
    if _p5_dot:
        gap_available = max(0, h // 2 - rec_px // 2 - _hl_top - hl_px)
        dot_y = _hl_top + hl_px + max(10, gap_available // 2 - 5)
        dot_y = min(dot_y, h // 2 - rec_px // 2 - 22)
        dot_color = struct_color if _is_vivid(struct_color) else (accent_dec if _is_vivid(accent_dec) else rec_color)
        decoracion_abs = (
            f'<div style="position:absolute;top:{dot_y}px;left:50%;'
            f'transform:translateX(-50%);display:flex;gap:9px;align-items:center;">'
            f'<div style="width:5px;height:5px;border-radius:50%;'
            f'background:{dot_color};opacity:0.60"></div>'
            f'<div style="width:7px;height:7px;border-radius:50%;'
            f'background:{dot_color};opacity:0.90"></div>'
            f'<div style="width:5px;height:5px;border-radius:50%;'
            f'background:{dot_color};opacity:0.60"></div>'
            f'</div>'
        )

    # Layout: spread (P2 editorial, P5 minimal)
    if layout == "spread":
        sub_bot = _mg_bot + sub_px + (int(h * 0.04) if fecha else 0)
        body = f"""
        {decoracion_abs}
        {f'<div class="hl" style="position:absolute;top:{_hl_top}px;left:{zone_l}px;right:{zone_r}px">{headline}</div>' if headline else ''}
        {f'<div class="rec" style="position:absolute;top:50%;transform:translateY(-50%);left:{zone_l}px;right:{zone_r}px">{recipient}</div>' if recipient else ''}
        {f'<div class="sub" style="position:absolute;bottom:{sub_bot}px;left:{zone_l}px;right:{zone_r}px">{subtitle}</div>' if subtitle else ''}
        {f'<div class="fecha" style="position:absolute;bottom:{_mg_bot}px;left:{zone_l}px;right:{zone_r}px">{fecha}</div>' if fecha else ''}
        """

    # Layout: staggered (P3 gráfico audaz)
    # Headline arriba a la DERECHA · Recipient ENORME a la IZQUIERDA · Subtitle DERECHA abajo
    # La tensión diagonal ES el concepto — no es un error de alineación
    elif layout == "staggered":
        sub_bot = _mg_bot + sub_px + (int(h * 0.04) if fecha else 0)
        body = f"""
        {decoracion_abs}
        {f'<div class="hl" style="position:absolute;top:{_hl_top}px;left:{zone_l}px;right:{zone_r}px;text-align:right">{headline}</div>' if headline else ''}
        {f'<div class="rec" style="position:absolute;top:50%;transform:translateY(-50%);left:{zone_l}px;right:{zone_r}px;text-align:left">{recipient}</div>' if recipient else ''}
        {f'<div class="sub" style="position:absolute;bottom:{sub_bot}px;left:{zone_l}px;right:{zone_r}px;text-align:right">{subtitle}</div>' if subtitle else ''}
        {f'<div class="fecha" style="position:absolute;bottom:{_mg_bot}px;left:{zone_l}px;right:{zone_r}px;text-align:right">{fecha}</div>' if fecha else ''}
        """

    # Layout: billboard (P4 — nombre como póster)
    # Headline: micro-caption justo bajo el logo
    # Recipient: inicio dinámico bajo el headline (nunca toca el logo)
    # Subtitle/fecha: anclados al fondo
    elif layout == "billboard":
        sub_bot  = _mg_bot + sub_px + (int(h * 0.035) if fecha else 0)
        rec_top  = _hl_top + hl_px + max(8, gap)   # recipient empieza bajo el headline
        body = f"""
        {decoracion_abs}
        {f'<div class="hl" style="position:absolute;top:{_hl_top}px;left:{zone_l}px;right:{zone_r}px">{headline}</div>' if headline else ''}
        {f'<div class="rec" style="position:absolute;top:{rec_top}px;left:{zone_l}px;right:{zone_r}px">{recipient}</div>' if recipient else ''}
        {f'<div class="sub" style="position:absolute;bottom:{sub_bot}px;left:{zone_l}px;right:{zone_r}px">{subtitle}</div>' if subtitle else ''}
        {f'<div class="fecha" style="position:absolute;bottom:{_mg_bot}px;left:{zone_l}px;right:{zone_r}px">{fecha}</div>' if fecha else ''}
        """

    # Layout: stacked (P1, P6 — y fallback)
    else:
        y_start = int(logo_bottom + (h - logo_bottom) * 0.10)
        y_end   = int(h * 0.97)
        mid     = (y_start + y_end) // 2

        if anchor == "top":
            pos = f"top:{y_start}px"
        elif anchor == "bottom":
            pos = f"bottom:{h - y_end}px"
        else:
            pos = f"top:{mid}px;transform:translateY(-50%)"

        flex_align = {"left": "flex-start", "right": "flex-end"}.get(rec_align, "center")

        items = []
        if headline:
            items.append(f'<div class="hl">{headline}</div>')
            if decoracion_after_hl:
                items.append(decoracion_after_hl)
        if recipient: items.append(f'<div class="rec">{recipient}</div>')
        if subtitle:  items.append(f'<div class="sub">{subtitle}</div>')
        if fecha:     items.append(f'<div class="fecha">{fecha}</div>')

        body = f"""
        {decoracion_abs}
        <div style="position:absolute;left:{zone_l}px;right:{zone_r}px;
                    {pos};display:flex;flex-direction:column;
                    align-items:{flex_align};gap:{gap}px;">
            {"".join(items)}
        </div>
        """

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
{font_css}
{base_css}
</style></head>
<body>{body}</body></html>"""


def _render_texto_html(concepto: dict, img: Image.Image, award: dict,
                       w: int, h: int, logo_bottom: int) -> Image.Image:
    """
    Renderiza el texto del galardón con HTML/CSS + Chromium headless.
    img: PIL Image con fondo + logo ya compuestos.
    Devuelve PIL Image con el texto superpuesto.
    """
    browser = _get_browser()
    if browser is None:
        print("  [HTML] ✗ Playwright no disponible — fallback PIL")
        return _render_texto(concepto, img, award, w, h, logo_bottom)
    print(f"  [HTML] ✓ Playwright activo (Chromium {browser.version})")

    # ── Calcular tamaños de fuente con PIL (métricas reales de la fuente) ──
    # CSS renderiza mejor, pero no puede reducir si la fuente es demasiado ancha.
    # PIL mide el ancho real de cada palabra con la fuente exacta y reduce hasta que encaje.
    tc             = concepto.get("text_style", {})
    font_family    = tc.get("font_family")
    font_style     = tc.get("font_style", "bold")
    font_style_cat = tc.get("font_style_category", "")
    margin_px      = max(16, int(w * 0.08))
    text_width     = max(60, w - 2 * margin_px)

    headline  = award.get("headline",  "") or ""
    recipient = award.get("recipient", "") or ""
    subtitle  = award.get("subtitle",  "") or ""

    # Aplicar uppercase ANTES de medir — CSS text-transform no reduce el font-size automáticamente
    # Las mayúsculas son ~15% más anchas que minúsculas en fuentes proporcionales
    if tc.get("recipient_uppercase") and recipient:
        recipient_medida = recipient.upper()
    else:
        recipient_medida = recipient

    sz_hl  = max(8, min(int(h * float(tc.get("headline_size_ratio",  0.090))),
                        int(text_width * 0.35)))
    sz_rec = max(8, min(int(h * float(tc.get("recipient_size_ratio", 0.18))),
                        int(text_width * 0.42)))
    sz_sub = max(7, min(int(h * float(tc.get("subtitle_size_ratio",  0.040))),
                        int(text_width * 0.22)))

    font_hl  = _cargar_fuente_marca(sz_hl,  font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
    font_rec = _cargar_fuente_marca(sz_rec, font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
    font_sub = _cargar_fuente_marca(sz_sub, font_family, weight=400, style_fallback=font_style, style_category=font_style_cat)

    _dummy_draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    def _mw(texto, font):
        if not texto: return 0
        return max((_tw(_dummy_draw, p, font) for p in texto.split()), default=0)

    limite = int(text_width * 0.96)
    for _ in range(30):
        changed = False
        if _mw(headline,        font_hl)  > limite:
            sz_hl  = max(8, int(sz_hl  * 0.88))
            font_hl  = _cargar_fuente_marca(sz_hl,  font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
            changed  = True
        if _mw(recipient_medida, font_rec) > limite:
            sz_rec = max(8, int(sz_rec * 0.88))
            font_rec = _cargar_fuente_marca(sz_rec, font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
            changed  = True
        if _mw(subtitle,        font_sub) > limite:
            sz_sub = max(7, int(sz_sub * 0.88))
            font_sub = _cargar_fuente_marca(sz_sub, font_family, weight=400, style_fallback=font_style, style_category=font_style_cat)
            changed  = True
        if not changed:
            break

    print(f"  [HTML] Tamaños: hl={sz_hl}px  rec={sz_rec}px  sub={sz_sub}px")

    bg_url = _img_to_data_url(img)
    html   = _build_html(concepto, award, bg_url, w, h, logo_bottom, sz_hl, sz_rec, sz_sub)

    # Escribir a fichero temporal para que Playwright pueda cargar Google Fonts
    tmp = tempfile.NamedTemporaryFile(
        suffix=".html", mode="w", encoding="utf-8", delete=False
    )
    tmp.write(html)
    tmp.close()
    file_url = "file:///" + tmp.name.replace("\\", "/")

    try:
        page = browser.new_page(viewport={"width": w, "height": h})
        # load → DOM + subrecursos locales cargados; más rápido y fiable que networkidle
        page.goto(file_url, wait_until="load", timeout=15000)
        page.wait_for_timeout(120)  # pequeño margen para fuentes @font-face
        png_bytes = page.screenshot(type="png", full_page=False)
        page.close()
    except Exception as e:
        print(f"  [HTML] Error en screenshot: {e} — fallback PIL")
        try: page.close()
        except Exception: pass
        try: os.unlink(tmp.name)
        except Exception: pass
        return _render_texto(concepto, img, award, w, h, logo_bottom)
    finally:
        try: os.unlink(tmp.name)
        except Exception: pass

    result = Image.open(BytesIO(png_bytes)).convert("RGB")
    print(f"  [HTML] Screenshot OK — {w}×{h}px")
    return result


# ─── Función principal ────────────────────────────────────────────────────────

def renderizar_diseno(concepto: dict, w: int, h: int,
                      logo_path: str, award: dict,
                      fuentes: dict | None = None,
                      seed: int = 42) -> Image.Image:
    """
    Renderiza un diseño completo:
      1. gpt-image-1 genera el fondo artístico (dalle_prompt — sin texto)
      2. Overlay ligero de color de marca (coherencia cromática)
      3. Logo exacto encima (PIL)
      4. Texto con PIL — tipografía dirigida por Claude (tamaños, colores, layout)
    """
    from scripts import capa_dalle

    dalle_prompt   = concepto.get("dalle_prompt", "")
    # Para fondos claros (P2/P5) el color_fallback es el color primario de la marca
    # (usado como tinte muy sutil), no como fondo — los generadores lo usarán correctamente.
    # Para oscuros el overlay.color = primario de marca = base del fondo.
    bg_tone_pre = concepto.get("bg_tone", "dark")
    ov_color    = (concepto.get("color_overlay") or {}).get("color", "") or ""
    _secondary  = (concepto.get("_secondary") or "")
    # Intentar sacar el primario: overlay.color si está seteado, si no el texto hl_color
    _hl_col     = (concepto.get("text_style") or {}).get("headline_color", "") or ""
    color_fallback = (ov_color or _secondary or _hl_col or
                      ("#F8F8F5" if bg_tone_pre == "light" else "#1A1A2E"))
    pid = concepto.get("proposal_id", "?")

    # ── Paso 1: Fondo artístico ───────────────────────────────────────
    print(f"    [DALLE-FONDO] Generando fondo para propuesta {pid}...")
    img = capa_dalle.generar_fondo(dalle_prompt, w, h, color_fallback, concepto=concepto)

    # ── Paso 2: Overlay de coherencia cromática ───────────────────────
    # P1 y P3 usan DALLE para el fondo — el overlay aplanaría su creatividad.
    # Solo aplicar overlay si la propuesta no es P1 ni P3.
    _i6_ov = (concepto.get("proposal_id", 1) - 1) % 6
    _ov_cfg = concepto.get("color_overlay", {})
    if _i6_ov in (0, 2) and dalle_prompt:  # P1/P3 con fondo DALLE: sin overlay
        _ov_cfg = {}
    img = _apply_overlay(img, _ov_cfg, w, h)

    # ── Paso 3: Logo (PIL) ────────────────────────────────────────────
    img, logo_bottom = _render_logo(concepto, img, logo_path, w, h)
    # Si el logo está abajo, el texto ocupa la parte superior del canvas
    if concepto.get("logo", {}).get("position") == "bottom_center":
        logo_bottom = int(h * 0.04)

    # ── Paso 4: Texto — HTML/CSS + Playwright (tipografía real de marca) ────
    tc_info = concepto.get("text_style", {})
    layout  = tc_info.get("layout", "stacked")
    anchor  = tc_info.get("text_anchor", "center")
    print(f"    [TEXTO-HTML] P{pid}: layout={layout}  anchor={anchor}  logo_treatment={concepto.get('logo',{}).get('treatment','?')}")
    img = _render_texto_html(concepto, img, award, w, h, logo_bottom)

    return img
