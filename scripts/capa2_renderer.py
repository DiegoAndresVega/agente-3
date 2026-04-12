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
                          weight: int = 700, style_fallback: str = "bold") -> ImageFont.ImageFont:
    """
    Carga la fuente de marca desde caché local o Google Fonts.
    Si font_family es None o la descarga falla → fallback a _cargar_fuente(size, style_fallback).
    Nunca lanza excepción.
    """
    if font_family:
        try:
            from scripts.font_manager import get_font_path
            path = get_font_path(font_family, weight)
            if path and path.exists():
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
        else:
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
    color_hex     = tc.get("color", "#FFFFFF")
    alineacion    = tc.get("alignment", "center")
    font_style    = tc.get("font_style", "bold")
    font_family   = tc.get("font_family")  # Google Fonts name o None
    margin_h      = int(w * float(tc.get("margin_h", 0.07)))
    layout        = tc.get("layout", "stacked")
    sep_lines     = tc.get("separator_lines", False)
    spacing_scale = max(0.2, float(tc.get("spacing_scale", 1.0)))
    text_anchor   = tc.get("text_anchor", "center")

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

    # ── Geometría vertical ───────────────────────────────────────────
    if layout == "logo_bottom":
        y_start = int(h * 0.06)
        y_end   = int(h * 0.72)
        sep_y   = None
    else:
        sep_y   = int(logo_bottom + (h - logo_bottom) * 0.10)
        y_start = sep_y + int(h * 0.03)
        y_end   = int(h * 0.97)

    # ── Contraste real sobre píxeles del fondo ───────────────────────
    zone_h   = max(1, y_end - y_start)
    bg_tone  = concepto.get("bg_tone", "dark")

    # En fondos claros forzamos colores oscuros de partida para evitar texto invisible
    if bg_tone == "light":
        color_hex = color_hex if _ratio_contraste(color_hex, "#F5F5F5") >= 3.0 else "#1A1A1A"
        hl_color  = hl_color  if _ratio_contraste(hl_color,  "#F5F5F5") >= 3.0 else "#1A1A1A"
        rec_color = rec_color if _ratio_contraste(rec_color, "#F5F5F5") >= 4.5 else "#0A0A0A"
        sub_color = sub_color if _ratio_contraste(sub_color, "#F5F5F5") >= 3.0 else "#444444"

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

    # ── Tamaños de fuente ────────────────────────────────────────────
    sz_hl  = max(8, int(h * float(tc.get("headline_size_ratio",  0.065))))
    sz_rec = max(8, int(h * float(tc.get("recipient_size_ratio", 0.16))))
    sz_sub = max(7, int(h * float(tc.get("subtitle_size_ratio",  0.040))))

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

    # Escalar si no caben
    if total_h > max_text_h and total_h > 0:
        factor = max_text_h / total_h
        sz_hl  = max(8, int(sz_hl  * factor))
        sz_rec = max(8, int(sz_rec * factor))
        sz_sub = max(7, int(sz_sub * factor))
        # Recalcular total con nuevos tamaños
        esp_base = max(4, int(sz_rec * 0.45 * spacing_scale))
        total_h  = (_h_bloque(headline, sz_hl) + _h_bloque(recipient, sz_rec)
                    + _h_bloque(subtitle, sz_sub) + _h_bloque(fecha, sz_sub)
                    + esp_base * max(0, n_blocks - 1))

    font_hl  = _cargar_fuente_marca(sz_hl,  font_family, weight=700, style_fallback=font_style)
    font_rec = _cargar_fuente_marca(sz_rec, font_family, weight=700, style_fallback=font_style)
    font_sub = _cargar_fuente_marca(sz_sub, font_family, weight=400, style_fallback=font_style)

    # ── Layouts especiales: spread, staggered, billboard ────────────
    if layout == "spread":
        # recipient centrado en la zona, headline arriba, subtitle abajo
        rec_h   = _h_bloque(recipient, sz_rec)
        hl_h    = _h_bloque(headline,  sz_hl)
        sub_h   = _h_bloque(subtitle,  sz_sub)
        gap     = max(8, int(h * 0.022))

        y_rec = y_start + max(0, (zone_h - rec_h) // 2)
        y_hl  = max(y_start, y_rec - hl_h - gap)
        y_sub = min(y_end - sub_h, y_rec + rec_h + gap)
        y_fec = min(y_end, y_sub + sub_h + max(2, gap // 2))

        if headline:
            _dibujar_bloque(draw, headline, y_hl, font_hl,
                            hex_to_rgba(hl_color, 255), x_start, text_width, "center")
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
                            hex_to_rgba(rec_color, 255), x_start, text_width, "center")
        if subtitle:
            _dibujar_bloque(draw, subtitle, y_sub, font_sub,
                            hex_to_rgba(sub_color, 190), x_start, text_width, "center")
        if fecha:
            _dibujar_bloque(draw, fecha, y_fec, font_sub,
                            hex_to_rgba(sub_color, 160), x_start, text_width, "center")
        return img

    if layout == "staggered":
        # headline centrado pequeño — recipient ENORME left — subtitle right
        rec_h   = _h_bloque(recipient, sz_rec)
        hl_h    = _h_bloque(headline,  sz_hl)
        sub_h   = _h_bloque(subtitle,  sz_sub)
        gap     = max(8, int(h * 0.022))

        y_rec = y_start + max(0, (zone_h - rec_h) // 2)
        y_hl  = max(y_start, y_rec - hl_h - gap)
        y_sub = min(y_end - sub_h, y_rec + rec_h + gap)
        y_fec = min(y_end, y_sub + sub_h + max(2, gap // 2))

        if headline:
            _dibujar_bloque(draw, headline, y_hl, font_hl,
                            hex_to_rgba(hl_color, 200), x_start, text_width, "center")
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

    if layout == "billboard":
        # recipient llena la zona — headline y subtitle son elementos secundarios mínimos
        sz_hl_b  = max(6, int(h * 0.038))
        sz_sub_b = max(5, int(h * 0.030))
        font_hl_b  = _cargar_fuente(sz_hl_b,  font_style)
        font_sub_b = _cargar_fuente(sz_sub_b, font_style)
        gap = max(6, int(h * 0.018))

        hl_h_px  = _h_bloque(headline, sz_hl_b)  if headline else 0
        sub_h_px = _h_bloque(subtitle, sz_sub_b) if subtitle else 0
        rec_zone = max(20, zone_h - hl_h_px - sub_h_px - gap * 2)

        # Fuente máxima que cabe en la zona del recipient
        font_rec_b = _fuente_optima(draw, [recipient] if recipient else ["X"],
                                    int(h * 0.32), text_width, rec_zone, font_style)
        if recipient:
            lineas_rec = _wrap_sin_partir(draw, recipient, font_rec_b, text_width)
            rec_h_px   = len(lineas_rec) * (font_rec_b.getbbox("A")[3] + 6)
        else:
            rec_h_px = 0

        y_hl  = y_start
        y_rec = (y_start + hl_h_px + gap) if headline else (y_start + max(0, (zone_h - rec_h_px) // 2))
        y_sub = y_end - sub_h_px

        if headline:
            _dibujar_bloque(draw, headline, y_hl, font_hl_b,
                            hex_to_rgba(hl_color, 175), x_start, text_width, "center")
        if recipient:
            _dibujar_bloque(draw, recipient, y_rec, font_rec_b,
                            hex_to_rgba(rec_color, 255), x_start, text_width, "center")
        if subtitle:
            _dibujar_bloque(draw, subtitle, y_sub, font_sub_b,
                            hex_to_rgba(sub_color, 155), x_start, text_width, "center")
        if fecha:
            y_fec = min(y_end, y_sub + sub_h_px + max(2, gap // 2))
            _dibujar_bloque(draw, fecha, y_fec, font_sub_b,
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
        opacity = int(float(overlay_cfg.get("opacity", 0.15)) * 255)
        overlay = Image.new("RGBA", (w, h), (*color, opacity))
        return Image.alpha_composite(img, overlay)
    except Exception:
        return img


# ─── Función principal ────────────────────────────────────────────────────────

def renderizar_diseno(concepto: dict, w: int, h: int,
                      logo_path: str, award: dict,
                      fuentes: dict | None = None,
                      seed: int = 42) -> Image.Image:
    """
    Renderiza un diseño completo con pipeline dual OpenAI:
      1. gpt-image-1 genera el fondo artístico (dalle_prompt — sin texto)
      2. Overlay ligero de color de marca (coherencia cromática)
      3. Logo exacto encima (PIL) — la marca la gestiona Claude, no OpenAI
      4. gpt-image-1 genera la tipografía sobre fondo sólido (text_prompt)
         PIL extrae el texto con chroma key y lo compone sobre el fondo
      Fallback: _render_texto (PIL) si DALLE falla o USE_DALLE=False
    """
    from scripts import capa_dalle

    dalle_prompt   = concepto.get("dalle_prompt", "")
    text_prompt    = concepto.get("text_prompt",  "")
    color_fallback = concepto.get("color_overlay", {}).get("color", "#1A1A2E")
    pid = concepto.get("proposal_id", "?")

    # ── Paso 1: Fondo artístico ───────────────────────────────────────
    print(f"    [DALLE-FONDO] Generando fondo para propuesta {pid}...")
    img = capa_dalle.generar_fondo(dalle_prompt, w, h, color_fallback)

    # ── Paso 2: Overlay de coherencia cromática ───────────────────────
    img = _apply_overlay(img, concepto.get("color_overlay", {}), w, h)

    # ── Paso 3: Logo (PIL) ────────────────────────────────────────────
    img, logo_bottom = _render_logo(concepto, img, logo_path, w, h)
    # Si el logo está abajo, el texto ocupa la parte superior del canvas
    if concepto.get("logo", {}).get("position") == "bottom_center":
        logo_bottom = int(h * 0.04)

    # ── Paso 4: Texto del galardón ────────────────────────────────────
    tc_info  = concepto.get("text_style", {})
    layout   = tc_info.get("layout", "stacked")
    anchor   = tc_info.get("text_anchor", "center")
    print(f"    [LAYOUT] P{pid}: layout={layout}  anchor={anchor}  logo_treatment={concepto.get('logo',{}).get('treatment','?')}")
    if capa_dalle.USE_DALLE and text_prompt:
        print(f"    [DALLE-TEXTO] Generando tipografía para propuesta {pid} (layout={layout})...")
        texto_img, bg_hex = capa_dalle.generar_texto_dalle(award, concepto)
        print(f"    [DEBUG] texto_img={texto_img is not None} bg_hex={bg_hex}")

        if texto_img is not None and bg_hex is not None:
            print(f"    [CHROMA]      Extrayendo texto (bg={bg_hex})...")
            texto_rgba = _extraer_texto_chroma(texto_img, bg_hex, threshold=40)
            arr_t  = np.array(texto_rgba)
            opaque = int((arr_t[:, :, 3] > 30).sum())
            print(f"    [DEBUG] píxeles opacos tras chroma key: {opaque}")
            if opaque > 500:
                tc       = concepto.get("text_style", {})
                margin_h = int(w * float(tc.get("margin_h", 0.07)))
                anchor   = tc.get("text_anchor", "center")
                sep_y    = int(logo_bottom + (h - logo_bottom) * 0.10)
                y_start  = sep_y + int(h * 0.03)
                y_end    = int(h * 0.97)
                print(f"    [CHROMA OK] composición en y={y_start}..{y_end}")
                img = _componer_capa_texto(texto_rgba, img, y_start, y_end, margin_h, anchor, w)
            else:
                print(f"    [FALLBACK] chroma vacío ({opaque} px) → PIL para propuesta {pid}")
                img = _render_texto(concepto, img, award, w, h, logo_bottom)
        else:
            print(f"    [FALLBACK] DALLE-texto falló → PIL para propuesta {pid}")
            img = _render_texto(concepto, img, award, w, h, logo_bottom)
    else:
        print(f"    [FALLBACK] PIL (USE_DALLE=False o sin text_prompt) para propuesta {pid}")
        img = _render_texto(concepto, img, award, w, h, logo_bottom)

    return img
