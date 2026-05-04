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
import math
import os
import tempfile
from io import BytesIO

import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Caché de perfiles de máscara — se calcula una vez por forma/tamaño y se reutiliza
_MASK_PROFILE_CACHE: dict = {}


def _obtener_perfil_mascara(zona: dict, w: int, h: int) -> list | None:
    """
    Devuelve una lista de (zone_l, zone_r) para cada fila del bounding box.
    Permite saber el ancho imprimible exacto a cualquier altura del canvas.
    Usa caché en memoria para no releer el PNG en cada render.
    """
    mascara_path = zona.get("mascara")
    if not mascara_path:
        return None
    cache_key = (str(mascara_path), zona.get("x"), zona.get("y"), w, h)
    if cache_key in _MASK_PROFILE_CACHE:
        return _MASK_PROFILE_CACHE[cache_key]
    try:
        BUFFER = 4
        ruta = PROJECT_ROOT / mascara_path
        mask = Image.open(ruta).convert("L")
        bb_x, bb_y = zona["x"], zona["y"]
        crop = mask.crop((bb_x, bb_y, bb_x + w, bb_y + h))
        arr  = np.array(crop)
        profile = []
        for row in arr:
            nz = np.where(row > 128)[0]
            if len(nz) >= 2:
                lx  = int(nz[0])
                rx  = int(nz[-1])
                zl  = max(0, lx + BUFFER)
                zr  = max(0, (w - rx) + BUFFER)
            else:
                zl, zr = w // 2, w // 2   # fila fuera de la máscara
            profile.append((zl, zr))
        _MASK_PROFILE_CACHE[cache_key] = profile
        return profile
    except Exception as e:
        print(f"  [perfil máscara] {e}")
        return None


def _zona_en_y(profile: list | None, y_px: int) -> tuple | None:
    """Devuelve (zone_l, zone_r) para una posición Y en píxeles del canvas."""
    if not profile:
        return None
    idx = max(0, min(len(profile) - 1, int(y_px)))
    return profile[idx]


def _tw_en_y(profile: list | None, y_px: int, w: int,
             fallback_zl: int = 0, fallback_zr: int = 0) -> tuple[int, int, int]:
    """Devuelve (zone_l, zone_r, text_width) para un Y dado."""
    z = _zona_en_y(profile, y_px)
    if z is None:
        return fallback_zl, fallback_zr, max(20, w - fallback_zl - fallback_zr)
    zl, zr = z
    return zl, zr, max(20, w - zl - zr)


def _mejor_zona_texto(profile: list | None, y0_frac: float, y1_frac: float,
                      h: int, w: int, window: int = 18) -> int:
    """
    Encuentra el Y central de la sub-zona más ancha en [y0_frac*h, y1_frac*h].
    Usa media móvil para elegir una región estable, no un píxel aislado.
    Sirve para colocar cada elemento de texto en la parte más ancha del trofeo.
    """
    if not profile:
        return int((y0_frac + y1_frac) / 2 * h)
    y0   = max(0, int(y0_frac * h))
    y1   = min(len(profile), int(y1_frac * h))
    if y0 >= y1:
        return (y0 + y1) // 2
    hw       = window // 2
    best_y   = (y0 + y1) // 2
    best_avg = -1.0
    for y in range(y0, y1):
        yi0 = max(y0, y - hw)
        yi1 = min(y1, y + hw + 1)
        avg = sum(max(0, w - profile[yy][0] - profile[yy][1])
                  for yy in range(yi0, yi1)) / max(1, yi1 - yi0)
        if avg > best_avg:
            best_avg = avg
            best_y   = y
    return best_y


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
                pass  # silencioso — demasiado verboso por tamaño
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

    # Eliminación de fondo por corner sampling.
    # No depende de has_alpha: un PNG puede declarar canal alpha pero tener fondo opaco.
    # Comprobamos si las ESQUINAS ya son transparentes (logo con alpha correcto → skip).
    s = max(3, min(8, logo.width // 20, logo.height // 20))
    _ca = np.concatenate([
        arr[:s, :s, 3].flatten(), arr[:s, -s:, 3].flatten(),
        arr[-s:, :s, 3].flatten(), arr[-s:, -s:, 3].flatten(),
    ])
    _corners_opaque = np.median(_ca) > 10   # esquinas transparentes → logo ya tiene alpha correcto

    if _corners_opaque:
        # Esquinas opacas → hay fondo visible. Detectar color y eliminar.
        _cr = np.concatenate([
            arr[:s, :s, :3].reshape(-1, 3), arr[:s, -s:, :3].reshape(-1, 3),
            arr[-s:, :s, :3].reshape(-1, 3), arr[-s:, -s:, :3].reshape(-1, 3),
        ], axis=0)
        bg_r = np.median(_cr[:, 0])
        bg_g = np.median(_cr[:, 1])
        bg_b = np.median(_cr[:, 2])
        bg_lum = (0.299 * bg_r + 0.587 * bg_g + 0.114 * bg_b) / 255
        # Solo eliminar fondos claros (lum > 0.40): no tocar logos blancos sobre fondo oscuro
        if bg_lum > 0.40:
            dist = np.sqrt(
                (arr[:, :, 0] - bg_r) ** 2 +
                (arr[:, :, 1] - bg_g) ** 2 +
                (arr[:, :, 2] - bg_b) ** 2
            )
            # Transición suave en el borde (anti-aliasing natural)
            arr[:, :, 3] = np.where(
                dist < 30, 0.0,
                np.where(dist < 55, arr[:, :, 3] * ((dist - 30) / 25.0), arr[:, :, 3])
            )

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

    # ── Zona horizontal: máscara irregular vs. rectangular estándar ────
    _zone_l_px = tc.get("_zone_l_px")
    _zone_r_px = tc.get("_zone_r_px")
    _eff_w     = tc.get("_effective_width_px")
    _base_w    = _eff_w if _eff_w else w

    _pid_zone = concepto.get("proposal_id", 1)
    _i6_zone  = (_pid_zone - 1) % 6

    if _zone_l_px is not None:
        # Trofeo con máscara irregular: posicionar texto en la zona real imprimible.
        # Las zonas ya incluyen el buffer de seguridad — no añadir margin_h adicional.
        x_start    = _zone_l_px
        text_width = max(20, w - _zone_l_px - (_zone_r_px or 0))
        # No aplicar zonas asimétricas P1/P5 — la zona ya es la correcta para la forma
    else:
        # Trofeo rectangular: aplicar márgenes estándar y zonas P1/P5
        _min_tw    = max(20, int(_base_w * 0.25))
        text_width = max(_min_tw, _base_w - 2 * margin_h)
        x_start    = margin_h
        if _i6_zone == 0:        # P1 — zona izquierda (74% del ancho)
            text_width = max(60, int(w * 0.74) - margin_h)
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

    # ── Segunda validación post-loop: recalcular esp_base y total_h con fuentes reales ──
    # Tras la reducción por anchura, sz_rec puede haber bajado → esp_base y total_h quedan
    # desactualizados. Este segundo pase garantiza que el bloque cabe verticalmente.
    esp_base = max(4, int(sz_rec * 0.45 * spacing_scale))
    total_h = (_h_bloque(headline, sz_hl) + _h_bloque(recipient, sz_rec)
               + _h_bloque(subtitle, sz_sub) + _h_bloque(fecha, sz_sub)
               + esp_base * max(0, n_blocks - 1))
    if total_h > max_text_h and total_h > 0:
        factor2 = max_text_h / total_h
        sz_hl  = max(8, int(sz_hl  * factor2))
        sz_rec = max(8, int(sz_rec * factor2))
        sz_sub = max(7, int(sz_sub * factor2))
        font_hl  = _cargar_fuente_marca(sz_hl,  font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
        font_rec = _cargar_fuente_marca(sz_rec, font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
        font_sub = _cargar_fuente_marca(sz_sub, font_family, weight=400, style_fallback=font_style, style_category=font_style_cat)
        esp_base = max(4, int(sz_rec * 0.45 * spacing_scale))

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
        # Headline: zona ancha superior · Recipient: zona ancha media · Subtitle: zona ancha inferior
        # Para trofeos con máscara irregular, se busca activamente las zonas más anchas.
        _profile = tc.get("_mask_profile")
        _fb_zl   = x_start
        _fb_zr   = w - x_start - text_width

        if _profile:
            # Buscar las Y más anchas en cada tercio — evita la zona estrecha del trofeo
            _hl_y_frac = max(0.04, y_start / h)
            y_hl  = _mejor_zona_texto(_profile, _hl_y_frac, 0.28, h, w)
            y_rec = _mejor_zona_texto(_profile, 0.28,       0.57, h, w)
            y_sub = _mejor_zona_texto(_profile, 0.72,       0.95, h, w)
            y_fec = min(y_sub + int(h * 0.06), int(h * 0.97))
        else:
            y_hl  = y_start
            y_rec = h // 2
            y_sub = int(h * 0.85)
            y_fec = int(h * 0.91)

        if _profile:
            _zl_hl,  _zr_hl,  _tw_hl  = _tw_en_y(_profile, y_hl,  w, _fb_zl, _fb_zr)
            _zl_rec, _zr_rec, _tw_rec  = _tw_en_y(_profile, y_rec, w, _fb_zl, _fb_zr)
            _zl_sub, _zr_sub, _tw_sub  = _tw_en_y(_profile, y_sub, w, _fb_zl, _fb_zr)
            # Fuente óptima para cada zona (más ancha = fuente más grande)
            sz_hl_e  = max(8, min(int(h * float(tc.get("headline_size_ratio",  0.065))), int(_tw_hl  * 0.35)))
            sz_rec_e = max(8, min(int(h * float(tc.get("recipient_size_ratio", 0.16))),  int(_tw_rec * 0.45)))
            sz_sub_e = max(7, min(int(h * float(tc.get("subtitle_size_ratio",  0.040))), int(_tw_sub * 0.25)))
            font_hl_e  = _cargar_fuente_marca(sz_hl_e,  font_family, 700, font_style, font_style_cat)
            font_rec_e = _cargar_fuente_marca(sz_rec_e, font_family, 700, font_style, font_style_cat)
            font_sub_e = _cargar_fuente_marca(sz_sub_e, font_family, 400, font_style, font_style_cat)
            for _ in range(30):
                ch = False
                if _max_palabra(headline,  font_hl_e)  > _tw_hl  - 2: sz_hl_e  = max(8, int(sz_hl_e  * 0.88)); font_hl_e  = _cargar_fuente_marca(sz_hl_e,  font_family, 700, font_style, font_style_cat); ch = True
                if _max_palabra(recipient, font_rec_e) > _tw_rec - 2: sz_rec_e = max(8, int(sz_rec_e * 0.88)); font_rec_e = _cargar_fuente_marca(sz_rec_e, font_family, 700, font_style, font_style_cat); ch = True
                if _max_palabra(subtitle,  font_sub_e) > _tw_sub - 2: sz_sub_e = max(7, int(sz_sub_e * 0.88)); font_sub_e = _cargar_fuente_marca(sz_sub_e, font_family, 400, font_style, font_style_cat); ch = True
                if not ch: break
        else:
            _zl_hl = _zl_rec = _zl_sub = x_start
            _tw_hl = _tw_rec = _tw_sub = text_width
            font_hl_e = font_hl; font_rec_e = font_rec; font_sub_e = font_sub

        rec_h = _h_bloque(recipient, sz_rec_e if _profile else sz_rec)
        # Centrar verticalmente el recipient en su zona óptima
        y_rec = y_rec - rec_h // 2 if _profile else h // 2 - rec_h // 2

        # Contraste en la zona real (no en la zona global del canvas)
        hl_color  = _color_sobre_region(img, hl_color,  _zl_hl,  y_hl,  _tw_hl,  max(1, int(h * 0.15)))
        rec_color = _color_sobre_region(img, rec_color, _zl_rec, y_rec, _tw_rec,  max(1, int(h * 0.20)))
        sub_color = _color_sobre_region(img, sub_color, _zl_sub, y_sub, _tw_sub,  max(1, int(h * 0.12)))

        # P5: triple punto de acento entre headline y recipient
        if _i6_pil == 4:
            gap_av = max(0, y_rec - (y_hl + sz_hl + 6))
            dot_y5 = y_hl + sz_hl + max(10, gap_av // 2 - 4)
            dot_y5 = min(dot_y5, y_rec - 20)
            dot_c  = _pil_struct_rgb if _is_vivid(_pil_struct) else (_pil_acc_rgb if _is_vivid(_pil_accent) else hex_to_rgb(rec_color))
            for di, (dx_off, ds) in enumerate([(-14, 5), (0, 7), (14, 5)]):
                cx_d = (_zl_hl + w - _zl_hl) // 2 + dx_off
                alpha = 153 if ds == 5 else 230
                draw.ellipse([cx_d - ds//2, dot_y5 - ds//2,
                              cx_d + ds//2, dot_y5 + ds//2],
                             fill=(*dot_c, alpha))

        _fn_hl  = font_hl_e  if _profile else font_hl
        _fn_rec = font_rec_e if _profile else font_rec
        _fn_sub = font_sub_e if _profile else font_sub

        if headline:
            _dibujar_bloque(draw, headline, y_hl, _fn_hl,
                            hex_to_rgba(hl_color, 220), _zl_hl, _tw_hl, hl_align)
        if recipient:
            if rec_block:
                try:
                    rb  = hex_to_rgb(rec_block)
                    pad = int(h * 0.018)
                    draw.rectangle([(_zl_rec, y_rec - pad),
                                    (w - (_zr_rec if _profile else 0), y_rec + rec_h + pad)],
                                   fill=(*rb, 220))
                    rec_color = _color_sobre_region(img, rec_color, _zl_rec, y_rec - pad,
                                                    _tw_rec, rec_h + 2 * pad)
                except Exception:
                    pass
            _dibujar_bloque(draw, recipient, y_rec, _fn_rec,
                            hex_to_rgba(rec_color, 255), _zl_rec, _tw_rec, rec_align)
        if subtitle:
            _dibujar_bloque(draw, subtitle, y_sub, _fn_sub,
                            hex_to_rgba(sub_color, 190), _zl_sub, _tw_sub, sub_align)
        if fecha:
            _dibujar_bloque(draw, fecha, y_fec, _fn_sub,
                            hex_to_rgba(sub_color, 160), _zl_sub, _tw_sub, sub_align)
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
    # Para formas con máscara irregular: centrar el bloque en la zona más ancha
    _pil_stacked_profile = tc.get("_mask_profile")
    if _pil_stacked_profile and text_anchor == "center":
        _hl_frac_st = max(0.04, y_start / h)
        _opt_y_st   = _mejor_zona_texto(_pil_stacked_profile, _hl_frac_st, 0.90, h, w)
        y = max(y_start, _opt_y_st - total_h // 2)
        # Usar la zona en ese Y óptimo
        _zl_st, _zr_st, _tw_st = _tw_en_y(_pil_stacked_profile, _opt_y_st, w, x_start, w - x_start - text_width)
        x_start    = _zl_st
        text_width = _tw_st
    elif text_anchor == "top":
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

    # ── Motif decorativo adicional (decoration_hint del concepto) ──
    motif_hint = concepto.get("decoration_hint", "none")
    if motif_hint and motif_hint != "none":
        motif_layer = _dibujar_motif_pil(motif_hint, w, h,
                                          _pil_struct_rgb, _pil_acc_rgb, bg_tone)
        if motif_layer:
            img = Image.alpha_composite(img, motif_layer)

    return img


# ─── Sistema de motifs decorativos PIL ───────────────────────────────────────

def _dibujar_motif_pil(motif: str, w: int, h: int,
                        struct_rgb: tuple, accent_rgb: tuple,
                        bg_tone: str) -> Image.Image | None:
    """
    Dibuja un elemento decorativo adicional sobre el canvas.
    Devuelve una imagen RGBA con el motif, para compositar sobre el diseño final.
    """
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    if motif == "laurel_arc":
        # Corona de laurel simplificada: arco de elipses en la parte inferior
        cx, cy = w // 2, int(h * 0.88)
        for angle_deg in range(-60, 61, 8):
            angle = math.radians(angle_deg)
            rx, ry = int(w * 0.38), int(h * 0.08)
            px = cx + int(rx * math.sin(angle))
            py = cy - int(ry * math.cos(angle))
            r_dot = max(3, int(w * 0.018))
            d.ellipse([px - r_dot, py - r_dot, px + r_dot, py + r_dot],
                      fill=(*struct_rgb, 160))

    elif motif == "diagonal_corners":
        # Líneas diagonales en esquinas superior-izquierda e inferior-derecha (Renault style)
        lw = max(2, int(w * 0.022))
        col = (*accent_rgb, 200)
        n_lines = 3
        gap = int(w * 0.048)
        for i in range(n_lines):
            off = i * gap
            d.line([(0, off + gap), (off + gap, 0)], fill=col, width=lw)
            d.line([(w, h - off - gap), (w - off - gap, h)], fill=col, width=lw)

    elif motif == "section_header":
        # Banda de color en el top 22% (Booking.com style)
        band_h = int(h * 0.22)
        if bg_tone == "light":
            d.rectangle([0, 0, w, band_h], fill=(*accent_rgb, 230))
        else:
            d.rectangle([0, 0, w, band_h], fill=(*struct_rgb, 180))

    elif motif == "badge_frame":
        # Marco circular centrado en la zona de texto
        cx, cy = w // 2, int(h * 0.50)
        r_badge = int(min(w, h) * 0.42)
        lw = max(2, int(w * 0.018))
        d.ellipse([cx - r_badge, cy - r_badge, cx + r_badge, cy + r_badge],
                  outline=(*struct_rgb, 75), width=lw)

    elif motif == "corner_brackets":
        # Corchetes editoriales en las 4 esquinas
        blen = int(min(w, h) * 0.055)
        lw = max(2, int(w * 0.012))
        col = (*struct_rgb, 180)
        margin = int(w * 0.06)
        for (x0, y0, sx, sy) in [(margin, margin, 1, 1),
                                   (w - margin, margin, -1, 1),
                                   (margin, h - margin, 1, -1),
                                   (w - margin, h - margin, -1, -1)]:
            d.line([(x0, y0), (x0 + sx * blen, y0)], fill=col, width=lw)
            d.line([(x0, y0), (x0, y0 + sy * blen)], fill=col, width=lw)

    elif motif == "dot_arc":
        # Arco de puntos punteados (Booking.com style) en zona media-baja
        cx, cy = w // 2, int(h * 0.74)
        for angle_deg in range(-50, 51, 12):
            angle = math.radians(angle_deg)
            rx, ry = int(w * 0.40), int(h * 0.065)
            px = cx + int(rx * math.sin(angle))
            py = cy - int(ry * math.cos(angle))
            r_dot = max(2, int(w * 0.011))
            d.ellipse([px - r_dot, py - r_dot, px + r_dot, py + r_dot],
                      fill=(*struct_rgb, 140))

    elif motif == "starburst":
        # Radiación de líneas desde el centro (energía)
        cx, cy = w // 2, int(h * 0.50)
        n_rays = 16
        ray_len = int(min(w, h) * 0.44)
        col = (*struct_rgb, 45)
        lw = max(1, int(w * 0.008))
        for i in range(n_rays):
            angle = math.radians(i * 360 / n_rays)
            ex = cx + int(ray_len * math.cos(angle))
            ey = cy + int(ray_len * math.sin(angle))
            d.line([(cx, cy), (ex, ey)], fill=col, width=lw)

    elif motif == "rule_grid":
        # Sistema de líneas editoriales horizontales sutiles
        col = (*struct_rgb, 35)
        lw = 1
        for y_pos in range(int(h * 0.12), int(h * 0.92), int(h * 0.08)):
            d.line([(int(w * 0.07), y_pos), (int(w * 0.93), y_pos)], fill=col, width=lw)

    else:
        return None

    return layer


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

    # ── Zonas de composición horizontal ──────────────────────────────
    # Para trofeos con máscara irregular: usar las zonas calculadas de la máscara.
    # Para trofeos rectangulares: zonas P1/P5 asimétricas estándar.
    _tc_zone_l = tc.get("_zone_l_px")
    _tc_zone_r = tc.get("_zone_r_px")
    pid_zone = concepto.get("proposal_id", 1)
    i6_zone  = (pid_zone - 1) % 6
    if _tc_zone_l is not None:
        # Máscara irregular: zona fija que garantiza el texto dentro de la forma
        zone_l = _tc_zone_l
        zone_r = _tc_zone_r if _tc_zone_r is not None else 0
    elif i6_zone == 0:      # P1 — zona izquierda (deja 26% derecho libre)
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

    # Corrección de contraste para motifs con banda oscura sobre fondo claro.
    # section_header pone una banda del color de marca en el top 22% del canvas —
    # si el headline cae sobre esa banda, necesita texto claro independientemente del bg_tone.
    decoration_hint = concepto.get("decoration_hint", "none")
    if decoration_hint == "section_header":
        band_bottom = int(h * 0.22)
        hl_top_approx = max(int(h * 0.04), logo_bottom + int(h * 0.018))
        if hl_top_approx < band_bottom:
            if _ratio_contraste(hl_color, "#1A1A1A") < 3.5:
                hl_color = "#FFFFFF"

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
    # Decoraciones por slot: activas solo si decoration_hint=="auto" o "none"(default del slot)
    # Si Claude especificó un motif distinto → el slot no fuerza su decoración
    _hint = concepto.get("decoration_hint", "none")
    _use_slot_deco = (_hint in ("none", "auto"))  # slot decoration only when hint is none/auto
    _p2_rule = (_hint == "rule_grid") or (_use_slot_deco and i6 == 1)
    _p5_dot  = (_hint == "dot_arc")  or (_use_slot_deco and i6 == 4)

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
        if _use_slot_deco:
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
        if _use_slot_deco:
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
        if _use_slot_deco:
            # Banda de color de marca — da calidez y coherencia cromática
            band_top = int(h * 0.20)
            band_h   = int(h * 0.52)
            if bg_tone in ("dark", "mid"):
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
        if _use_slot_deco:
            # Círculo watermark centrado — textura geométrica sobre el sólido de marca
            cs = int(min(w, h) * 0.70)
            cx = w // 2
            cy = int(h * 0.52)
            decoracion_abs = (
                f'<div style="position:absolute;left:{cx - cs//2}px;top:{cy - cs//2}px;'
                f'width:{cs}px;height:{cs}px;border:3px solid white;'
                f'opacity:0.12;border-radius:50%"></div>'
            )
            # Regla ancha y gruesa bajo el headline
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
        overflow-wrap: normal; word-break: normal;
        {hl_extra_css}
    }}
    .rec {{
        font-family: {font_family_css};
        font-size: {rec_px}px; font-weight: 700;
        color: {rec_color}; text-align: {rec_align};
        line-height: {rec_line_height};
        letter-spacing: {rec_tracking};
        overflow-wrap: normal; word-break: normal;
        text-transform: {rec_upper};
        {rec_extra_css}
    }}
    .sub {{
        font-family: {font_family_css};
        font-size: {sub_px}px; font-weight: 400;
        color: {sub_color}; text-align: {sub_align};
        line-height: 1.30; letter-spacing: {sub_tracking};
        overflow-wrap: normal; word-break: normal;
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

    # ── Motif decorativo adicional (decoration_hint) ──
    motif_hint = concepto.get("decoration_hint", "none")
    if motif_hint and motif_hint != "none":
        _mc = struct_color  # color del motif
        _ac = accent_dec or struct_color
        if motif_hint == "laurel_arc":
            # Arco de puntos en la parte inferior
            _dots_html = ""
            for _ang in range(-60, 61, 8):
                _rad = math.radians(_ang)
                _rx, _ry = int(w * 0.38), int(h * 0.08)
                _px = w // 2 + int(_rx * math.sin(_rad))
                _py = int(h * 0.88) - int(_ry * math.cos(_rad))
                _r_d = max(3, int(w * 0.018))
                _dots_html += (f'<div style="position:absolute;'
                               f'left:{_px - _r_d}px;top:{_py - _r_d}px;'
                               f'width:{_r_d*2}px;height:{_r_d*2}px;'
                               f'border-radius:50%;background:{_mc};opacity:0.63;"></div>')
            decoracion_abs += f'<div style="position:absolute;top:0;left:0;width:100%;height:100%;">{_dots_html}</div>'
        elif motif_hint == "diagonal_corners":
            _lw = max(2, int(w * 0.022))
            _gap = int(w * 0.048)
            _corner_lines = ""
            for _i in range(3):
                _off = _i * _gap
                _corner_lines += (f'<div style="position:absolute;top:{_off}px;left:0;'
                                  f'width:{_off + _gap}px;height:{_lw}px;'
                                  f'background:{_ac};opacity:0.78;'
                                  f'transform-origin:0 0;transform:rotate(45deg);"></div>')
                _corner_lines += (f'<div style="position:absolute;bottom:{_off}px;right:0;'
                                  f'width:{_off + _gap}px;height:{_lw}px;'
                                  f'background:{_ac};opacity:0.78;'
                                  f'transform-origin:100% 100%;transform:rotate(45deg);"></div>')
            decoracion_abs += f'<div style="position:absolute;top:0;left:0;width:100%;height:100%;overflow:hidden;">{_corner_lines}</div>'
        elif motif_hint == "section_header":
            _bh = int(h * 0.22)
            _bc = _ac if bg_tone == "light" else _mc
            decoracion_abs += (f'<div style="position:absolute;top:0;left:0;width:100%;'
                               f'height:{_bh}px;background:{_bc};opacity:0.90;"></div>')
        elif motif_hint == "badge_frame":
            _r_b = int(min(w, h) * 0.42)
            _cx, _cy = w // 2 - _r_b, int(h * 0.50) - _r_b
            _lw_b = max(2, int(w * 0.018))
            decoracion_abs += (f'<div style="position:absolute;'
                               f'left:{_cx}px;top:{_cy}px;'
                               f'width:{_r_b*2}px;height:{_r_b*2}px;'
                               f'border-radius:50%;border:{_lw_b}px solid {_mc};opacity:0.30;"></div>')
        elif motif_hint == "corner_brackets":
            _blen = int(min(w, h) * 0.055)
            _lw_c = max(2, int(w * 0.012))
            _marg = int(w * 0.06)
            _bk = ""
            for (_x0, _y0, _sx, _sy) in [(_marg, _marg, 1, 1),
                                           (w - _marg - _blen, _marg, -1, 1),
                                           (_marg, h - _marg - _blen, 1, -1),
                                           (w - _marg - _blen, h - _marg - _blen, -1, -1)]:
                _bk += (f'<div style="position:absolute;left:{_x0}px;top:{_y0}px;'
                        f'width:{_blen}px;height:{_lw_c}px;background:{_mc};opacity:0.70;"></div>'
                        f'<div style="position:absolute;left:{_x0}px;top:{_y0}px;'
                        f'width:{_lw_c}px;height:{_blen}px;background:{_mc};opacity:0.70;"></div>')
            decoracion_abs += f'<div style="position:absolute;top:0;left:0;width:100%;height:100%;">{_bk}</div>'
        elif motif_hint == "dot_arc":
            _dots2 = ""
            for _ang in range(-50, 51, 12):
                _rad = math.radians(_ang)
                _rx2, _ry2 = int(w * 0.40), int(h * 0.065)
                _px2 = w // 2 + int(_rx2 * math.sin(_rad))
                _py2 = int(h * 0.74) - int(_ry2 * math.cos(_rad))
                _rd2 = max(2, int(w * 0.011))
                _dots2 += (f'<div style="position:absolute;'
                           f'left:{_px2 - _rd2}px;top:{_py2 - _rd2}px;'
                           f'width:{_rd2*2}px;height:{_rd2*2}px;'
                           f'border-radius:50%;background:{_mc};opacity:0.55;"></div>')
            decoracion_abs += f'<div style="position:absolute;top:0;left:0;width:100%;height:100%;">{_dots2}</div>'

    # Perfil de máscara para zonas por-elemento (formas irregulares)
    _html_profile = tc.get("_mask_profile")

    def _html_zone(y_px):
        """Devuelve (zl, zr, w_text) para un Y dado en el canvas HTML."""
        if _html_profile:
            zl, zr, wt = _tw_en_y(_html_profile, y_px, w, zone_l, zone_r)
            return zl, zr, wt
        return zone_l, zone_r, max(20, w - zone_l - zone_r)

    # Layout: spread (P2 editorial, P5 minimal)
    if layout == "spread":
        sub_bot = _mg_bot + sub_px + (int(h * 0.04) if fecha else 0)
        _sp_hl_max_h = max(40, int(h * 0.18))

        if _html_profile:
            # Posicionar cada elemento en la zona más ancha disponible de esa franja vertical
            _hl_frac  = max(0.04, logo_bottom / h)
            _y_hl_h   = _mejor_zona_texto(_html_profile, _hl_frac, 0.28, h, w)
            _y_rec_h  = _mejor_zona_texto(_html_profile, 0.28,     0.57, h, w)
            _y_sub_h  = _mejor_zona_texto(_html_profile, 0.72,     0.95, h, w)
            _sp_rec_max_h = max(40, _y_sub_h - _y_rec_h - int(h * 0.04))
        else:
            _y_hl_h  = _hl_top
            _y_rec_h = max(_hl_top + _sp_hl_max_h + int(h * 0.04), int(h * 0.36))
            _y_sub_h = h - sub_bot - sub_px
            _sp_rec_max_h = max(40, _y_sub_h - _y_rec_h - int(h * 0.04))

        _zl_hl_h,  _zr_hl_h,  _sp_w_hl  = _html_zone(_y_hl_h)
        _zl_rec_h, _zr_rec_h, _sp_w_rec  = _html_zone(_y_rec_h)
        _zl_sub_h, _zr_sub_h, _sp_w_sub  = _html_zone(_y_sub_h)
        body = f"""
        {decoracion_abs}
        {f'<div class="hl" style="position:absolute;top:{_y_hl_h}px;left:{_zl_hl_h}px;width:{_sp_w_hl}px;max-height:{_sp_hl_max_h}px;overflow-x:visible;overflow-y:hidden">{headline}</div>' if headline else ''}
        {f'<div class="rec" style="position:absolute;top:{_y_rec_h}px;left:{_zl_rec_h}px;width:{_sp_w_rec}px;max-height:{_sp_rec_max_h}px;overflow-x:visible;overflow-y:hidden">{recipient}</div>' if recipient else ''}
        {f'<div class="sub" style="position:absolute;top:{_y_sub_h}px;left:{_zl_sub_h}px;width:{_sp_w_sub}px">{subtitle}</div>' if subtitle else ''}
        {f'<div class="fecha" style="position:absolute;top:{min(_y_sub_h + sub_px + 6, int(h*0.97))}px;left:{_zl_sub_h}px;width:{_sp_w_sub}px">{fecha}</div>' if fecha else ''}
        """

    # Layout: staggered (P3 gráfico audaz)
    # Headline arriba a la DERECHA · Recipient ENORME a la IZQUIERDA · Subtitle DERECHA abajo
    # La tensión diagonal ES el concepto — no es un error de alineación
    elif layout == "staggered":
        sub_bot = _mg_bot + sub_px + (int(h * 0.04) if fecha else 0)
        _sg_w         = w - zone_l - zone_r
        _sg_hl_bottom = _hl_top + hl_px * 3   # estimación conservadora (3 líneas máx)
        _sg_rec_top   = max(_sg_hl_bottom + int(h * 0.04), int(h * 0.30))
        _sg_sub_top   = h - sub_bot - sub_px
        _sg_rec_max_h = max(40, _sg_sub_top - _sg_rec_top - int(h * 0.03))
        body = f"""
        {decoracion_abs}
        {f'<div class="hl" style="position:absolute;top:{_hl_top}px;left:{zone_l}px;width:{_sg_w}px;text-align:right;max-height:{int(h*0.26)}px;overflow-x:visible;overflow-y:hidden">{headline}</div>' if headline else ''}
        {f'<div class="rec" style="position:absolute;top:{_sg_rec_top}px;left:{zone_l}px;width:{_sg_w}px;text-align:left;max-height:{_sg_rec_max_h}px;overflow-x:visible;overflow-y:hidden">{recipient}</div>' if recipient else ''}
        {f'<div class="sub" style="position:absolute;bottom:{sub_bot}px;left:{zone_l}px;width:{_sg_w}px;text-align:right">{subtitle}</div>' if subtitle else ''}
        {f'<div class="fecha" style="position:absolute;bottom:{_mg_bot}px;left:{zone_l}px;width:{_sg_w}px;text-align:right">{fecha}</div>' if fecha else ''}
        """

    # Layout: billboard (P4 — nombre como póster)
    elif layout == "billboard":
        sub_bot       = _mg_bot + sub_px + (int(h * 0.035) if fecha else 0)
        _bb_w         = w - zone_l - zone_r
        rec_top       = _hl_top + hl_px * 2 + max(8, gap)
        _bb_sub_top   = h - sub_bot - sub_px
        _bb_rec_max_h = max(40, _bb_sub_top - rec_top - int(h * 0.02))
        body = f"""
        {decoracion_abs}
        {f'<div class="hl" style="position:absolute;top:{_hl_top}px;left:{zone_l}px;width:{_bb_w}px;max-height:{int(h*0.18)}px;overflow-x:visible;overflow-y:hidden">{headline}</div>' if headline else ''}
        {f'<div class="rec" style="position:absolute;top:{rec_top}px;left:{zone_l}px;width:{_bb_w}px;max-height:{_bb_rec_max_h}px;overflow-x:visible;overflow-y:hidden">{recipient}</div>' if recipient else ''}
        {f'<div class="sub" style="position:absolute;bottom:{sub_bot}px;left:{zone_l}px;width:{_bb_w}px">{subtitle}</div>' if subtitle else ''}
        {f'<div class="fecha" style="position:absolute;bottom:{_mg_bot}px;left:{zone_l}px;width:{_bb_w}px">{fecha}</div>' if fecha else ''}
        """

    # Layout: stacked (P1, P6 — y fallback)
    else:
        y_start = int(logo_bottom + (h - logo_bottom) * 0.10)
        y_end   = int(h * 0.97)

        if _html_profile:
            # Para formas irregulares: centrar el bloque en la zona más ancha disponible
            _hl_frac = max(0.04, logo_bottom / h)
            _st_opt_y = _mejor_zona_texto(_html_profile, _hl_frac, 0.90, h, w)
            _st_zl, _st_zr, _st_w = _html_zone(_st_opt_y)
            mid = _st_opt_y
        else:
            mid = (y_start + y_end) // 2
            _st_zl, _st_zr, _st_w = _html_zone(mid)

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
        <div style="position:absolute;left:{_st_zl}px;width:{_st_w}px;
                    {pos};display:flex;flex-direction:column;overflow:visible;
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
    margin_px  = max(10, int(w * float(tc.get("margin_h", 0.08))))
    _zone_l_px = tc.get("_zone_l_px")
    _zone_r_px = tc.get("_zone_r_px")
    _eff_w_h   = tc.get("_effective_width_px")
    _base_w    = _eff_w_h if _eff_w_h else w
    i6_z       = (concepto.get("proposal_id", 1) - 1) % 6  # siempre definido

    _mask_profile = tc.get("_mask_profile")
    if _zone_l_px is not None:
        text_width = max(20, w - _zone_l_px - (_zone_r_px or 0))
    else:
        _min_tw_h  = max(20, int(_base_w * 0.25))
        _use_full_w = (_base_w < 100)
        if not _use_full_w and i6_z == 0:
            text_width = max(_min_tw_h, _base_w - margin_px - int(_base_w * 0.26))
        elif not _use_full_w and i6_z == 4:
            text_width = max(_min_tw_h, _base_w - int(_base_w * 0.32) - margin_px)
        else:
            text_width = max(_min_tw_h, _base_w - 2 * margin_px)

    headline  = award.get("headline",  "") or ""
    recipient = award.get("recipient", "") or ""
    subtitle  = award.get("subtitle",  "") or ""

    if tc.get("recipient_uppercase") and recipient:
        recipient_medida = recipient.upper()
    else:
        recipient_medida = recipient

    # Per-element text widths usando las zonas más anchas del trofeo.
    # Para trofeos con máscara irregular, headline/subtitle se ubican en las partes
    # más anchas — el recipient también evita la zona más estrecha.
    layout_html = tc.get("layout", "stacked")
    if _mask_profile and layout_html in ("spread", "staggered", "billboard"):
        _logo_bot_h = logo_bottom   # logo_bottom pasado a _render_texto_html
        _hl_y_frac  = max(0.04, _logo_bot_h / h)
        _y_hl_est   = _mejor_zona_texto(_mask_profile, _hl_y_frac, 0.28, h, w)
        _y_rec_est  = _mejor_zona_texto(_mask_profile, 0.28,       0.57, h, w)
        _y_sub_est  = _mejor_zona_texto(_mask_profile, 0.72,       0.95, h, w)
        _, _, _tw_hl_h  = _tw_en_y(_mask_profile, _y_hl_est,  w, _zone_l_px or 0, _zone_r_px or 0)
        _, _, _tw_rec_h = _tw_en_y(_mask_profile, _y_rec_est, w, _zone_l_px or 0, _zone_r_px or 0)
        _, _, _tw_sub_h = _tw_en_y(_mask_profile, _y_sub_est, w, _zone_l_px or 0, _zone_r_px or 0)
    else:
        _y_hl_est = _y_rec_est = _y_sub_est = None
        _tw_hl_h = _tw_rec_h = _tw_sub_h = text_width

    sz_hl  = max(8, min(int(h * float(tc.get("headline_size_ratio",  0.090))),
                        int(_tw_hl_h  * 0.32)))
    sz_rec = max(8, min(int(h * float(tc.get("recipient_size_ratio", 0.18))),
                        int(_tw_rec_h * 0.40)))
    sz_sub = max(7, min(int(h * float(tc.get("subtitle_size_ratio",  0.040))),
                        int(_tw_sub_h * 0.18)))

    font_hl  = _cargar_fuente_marca(sz_hl,  font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
    font_rec = _cargar_fuente_marca(sz_rec, font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
    font_sub = _cargar_fuente_marca(sz_sub, font_family, weight=400, style_fallback=font_style, style_category=font_style_cat)

    _dummy_draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    _HL_TRACKING  = [0.22, 0.28, 0.07, 0.16, 0.22, 0.18]
    _SUB_TRACKING = [0.32, 0.38, 0.16, 0.26, 0.40, 0.26]
    _REC_TRACKING = [0.00, 0.00, 0.00, 0.00, 0.01, 0.00]
    _hl_ls  = _HL_TRACKING[i6_z]
    _sub_ls = _SUB_TRACKING[i6_z]
    _rec_ls = _REC_TRACKING[i6_z]

    headline_medida = headline.upper() if headline else headline
    subtitle_medida = subtitle.upper() if subtitle else subtitle

    def _mw_css(texto, font, sz, tracking_em):
        if not texto:
            return 0
        return max(
            _tw(_dummy_draw, p, font) + len(p) * tracking_em * sz
            for p in texto.split()
        )

    # Reducción per-elemento: cada fuente se reduce contra su propio límite de ancho
    lim_hl  = _tw_hl_h  - 4
    lim_rec = _tw_rec_h - 4
    lim_sub = _tw_sub_h - 4
    for _ in range(30):
        changed = False
        if _mw_css(headline_medida, font_hl, sz_hl, _hl_ls) > lim_hl:
            sz_hl  = max(8, int(sz_hl  * 0.88))
            font_hl  = _cargar_fuente_marca(sz_hl,  font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
            changed  = True
        if _mw_css(recipient_medida, font_rec, sz_rec, _rec_ls) > lim_rec:
            sz_rec = max(8, int(sz_rec * 0.88))
            font_rec = _cargar_fuente_marca(sz_rec, font_family, weight=700, style_fallback=font_style, style_category=font_style_cat)
            changed  = True
        if _mw_css(subtitle_medida, font_sub, sz_sub, _sub_ls) > lim_sub:
            sz_sub = max(7, int(sz_sub * 0.88))
            font_sub = _cargar_fuente_marca(sz_sub, font_family, weight=400, style_fallback=font_style, style_category=font_style_cat)
            changed  = True
        if not changed:
            break

    print(f"  [HTML] Tamaños: hl={sz_hl}px(tw={_tw_hl_h})  rec={sz_rec}px(tw={_tw_rec_h})  sub={sz_sub}px(tw={_tw_sub_h})")
    # Segunda validación post-loop: misma garantía vertical que el path PIL

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


# ─── Cálculo automático de ancho efectivo desde máscara ──────────────────────

def _calcular_ancho_efectivo_mascara(zona: dict, w: int, h: int) -> tuple:
    """
    Lee la máscara PNG del trofeo y calcula el área de texto segura.
    Escanea la zona central (20-85% del alto) y encuentra el punto más estrecho.

    Devuelve (effective_width, zone_l, zone_r) o (None, None, None) si falla.
      - effective_width: ancho mínimo del área imprimible (con buffer de seguridad)
      - zone_l: margen izquierdo desde el borde del bounding box hasta el texto
      - zone_r: margen derecho desde el borde derecho del bounding box hasta el texto
    """
    mascara_path = zona.get("mascara")
    if not mascara_path:
        return None, None, None
    try:
        ruta = PROJECT_ROOT / mascara_path
        mask = Image.open(ruta).convert("L")
        bb_x, bb_y = zona["x"], zona["y"]
        crop = mask.crop((bb_x, bb_y, bb_x + w, bb_y + h))
        arr = np.array(crop)
        y0, y1 = int(h * 0.20), int(h * 0.85)
        BUFFER = 4  # píxeles de seguridad a cada lado
        min_span = w
        best_left = 0
        best_right = w
        for row in arr[y0:y1]:
            nz = np.where(row > 128)[0]
            if len(nz) >= 2:
                left_x  = int(nz[0])
                right_x = int(nz[-1])
                span = right_x - left_x
                if span < min_span:
                    min_span  = span
                    best_left  = left_x
                    best_right = right_x
        zone_l         = max(0, best_left  + BUFFER)
        zone_r         = max(0, (w - best_right) + BUFFER)
        effective_width = max(20, best_right - best_left - 2 * BUFFER)
        print(f"  [trofeo] Zona texto: x={zone_l}..{w - zone_r}px "
              f"(ancho efectivo={effective_width}px, bbox={w}px)")
        return effective_width, zone_l, zone_r
    except Exception as e:
        print(f"  [trofeo] No se pudo calcular zona de máscara: {e}")
        return None, None, None


# ─── Función principal ────────────────────────────────────────────────────────

def renderizar_diseno(concepto: dict, w: int, h: int,
                      logo_path: str, award: dict,
                      fuentes: dict | None = None,
                      seed: int = 42,
                      trophy_margin_h: float | None = None,
                      trophy_effective_width: int | None = None,
                      trophy_zone_l: int | None = None,
                      trophy_zone_r: int | None = None,
                      trophy_zona: dict | None = None) -> Image.Image:
    """
    Renderiza un diseño completo:
      1. gpt-image-1 genera el fondo artístico (dalle_prompt — sin texto)
      2. Overlay ligero de color de marca (coherencia cromática)
      3. Logo exacto encima (PIL)
      4. Texto con PIL — tipografía dirigida por Claude (tamaños, colores, layout)
    """
    from scripts import capa_dalle

    # Para trofeos con máscara irregular: calcular zona de texto desde la máscara.
    _mask_profile = None
    if trophy_zona and trophy_zona.get("mascara"):
        _mask_profile = _obtener_perfil_mascara(trophy_zona, w, h)
        if trophy_effective_width is None or trophy_zone_l is None:
            _eff_w, _zl, _zr = _calcular_ancho_efectivo_mascara(trophy_zona, w, h)
            if trophy_effective_width is None:
                trophy_effective_width = _eff_w
            if trophy_zone_l is None and _zl is not None:
                trophy_zone_l = _zl
                trophy_zone_r = _zr

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

    import time as _t
    _t_prop = _t.time()
    patron  = concepto.get("pattern_name", "—")
    bg_tone = concepto.get("bg_tone", "?")
    print(f"\n  ┌─ P{pid} · {patron}  [{bg_tone}] ─────────────────────────")
    _usa_dalle = bool(dalle_prompt and dalle_prompt.strip())
    print(f"  │  Colores: overlay={color_fallback}  fondo={'DALL·E' if _usa_dalle else 'PIL'}")

    # ── Paso 1: Fondo artístico ───────────────────────────────────────
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
    # Inyectar restricciones del trofeo en text_style para que los renderers las usen.
    # effective_width_px: ancho mínimo real de la forma (para formas irregulares que
    # son más estrechas en algún punto que su bounding box completo).
    if any(v is not None for v in (trophy_margin_h, trophy_effective_width,
                                   trophy_zone_l, trophy_zone_r, _mask_profile)):
        tc = concepto.setdefault("text_style", {})
        if trophy_margin_h is not None:
            tc["margin_h"] = max(trophy_margin_h, float(tc.get("margin_h", 0.07)))
        if trophy_effective_width is not None:
            tc["_effective_width_px"] = trophy_effective_width
        if trophy_zone_l is not None:
            tc["_zone_l_px"] = trophy_zone_l
            tc["_zone_r_px"] = trophy_zone_r if trophy_zone_r is not None else 0
        if _mask_profile is not None:
            tc["_mask_profile"] = _mask_profile
    tc_info = concepto.get("text_style", {})
    layout  = tc_info.get("layout", "stacked")
    anchor  = tc_info.get("text_anchor", "center")
    print(f"  │  Texto: layout={layout}  anchor={anchor}  logo={concepto.get('logo',{}).get('treatment','?')}")
    img = _render_texto_html(concepto, img, award, w, h, logo_bottom)
    print(f"  └─ P{pid} renderizado en {_t.time()-_t_prop:.1f}s")

    return img
