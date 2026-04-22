"""
font_manager.py — Descargador y caché de Google Fonts
Sustain Awards

Descarga fuentes de Google Fonts (endpoint CSS público, sin API key)
y las cachea en assets/fonts/ como archivos .ttf para PIL.

Uso:
    from scripts.font_manager import get_font_path, warmup

    path = get_font_path("Montserrat", weight=700)
    font = ImageFont.truetype(str(path), size=80) if path else fallback
"""

import re
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR    = PROJECT_ROOT / "assets" / "fonts"

# User-Agent antiguo → Google devuelve format('truetype') con URLs .ttf
# UAs modernos reciben woff2, que PIL no puede abrir directamente.
_USER_AGENT = "Mozilla/5.0 (compatible; Python/3.11; SustainAwards-Fonts/1.0)"

# Familias genéricas CSS — Claude podría alucionarlas como nombre de fuente
_GENERIC = {"sans-serif", "serif", "monospace", "display", "cursive", "fantasy"}

# Sufijos de peso que Claude puede añadir al nombre de la familia (se limpian)
_WEIGHT_SUFFIXES = [
    " Bold", " Regular", " Light", " Medium",
    " Italic", " Thin", " Black", " ExtraBold", " SemiBold",
]


def _normalize(family: str) -> str:
    """Elimina sufijos de peso del nombre de la familia."""
    for suffix in _WEIGHT_SUFFIXES:
        if family.endswith(suffix):
            family = family[: -len(suffix)]
    return family.strip()


def _cache_path(family: str, weight: int) -> Path:
    safe = family.replace(" ", "_")
    return FONTS_DIR / f"{safe}_{weight}.ttf"


def find_local_font(family: str, weight: int = 700) -> Path | None:
    """Busca en FONTS_DIR por nombre de familia (con y sin peso, .ttf y .otf)."""
    safe = family.replace(" ", "_")
    for name in [f"{safe}_{weight}", f"{safe}", family.replace(" ", "-")]:
        for ext in ["ttf", "otf"]:
            p = FONTS_DIR / f"{name}.{ext}"
            if p.exists():
                print(f"  [fonts] Fuente local: {p.name}")
                return p
    return None


def register_local_font(family_name: str, data: bytes, ext: str = "ttf") -> Path | None:
    """Guarda bytes de fuente en assets/fonts/. Valida que no esté vacío (>10 KB)."""
    if not data or len(data) < 10_000:
        return None
    # Limpiar prefijo de subset PDF (ej: "ABCDEF+FuturaPT-Bold" → "FuturaPT-Bold")
    clean = family_name.split("+")[-1].strip().replace(" ", "_")
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = FONTS_DIR / f"{clean}.{ext}"
    dest.write_bytes(data)
    print(f"  [fonts] Registrada fuente local: {dest.name} ({len(data)//1024} KB)")
    return dest


# Caché en memoria de familias que fallaron en Google Fonts — evita reintentos
_failed_google: set[str] = set()

# ─── Catálogo tipográfico por categoría visual ────────────────────────────────
# Fuentes ordenadas de más a menos fiel al estilo visual.
# Usadas como fallback cuando la fuente principal no está en Google Fonts.
FONT_CATALOG: dict[str, list[str]] = {
    # Terminales circulares, letras casi redondas, tono friendly/playful
    "burbuja":       ["Fredoka One", "Comfortaa", "Nunito", "Pacifico", "Righteous",
                      "Varela Round"],
    # Sans-serif moderno con esquinas suavizadas — más neutro que burbuja
    "redondeado":    ["Nunito Sans", "Quicksand", "Varela Round", "DM Sans",
                      "Jost", "Outfit"],
    # Trazos limpios y uniformes, neutral y moderno
    "geometrico":    ["Jost", "Outfit", "Barlow", "Inter", "Urbanist",
                      "Plus Jakarta Sans", "Figtree"],
    # Proporciones orgánicas, cálido y legible
    "humanista":     ["Lato", "Source Sans 3", "Open Sans", "Raleway", "Mulish",
                      "Nunito Sans"],
    # Sans-serif neutro profesional, institucional
    "corporativo":   ["Montserrat", "IBM Plex Sans", "Work Sans", "Figtree",
                      "Roboto", "Inter"],
    # Estrecho y alto, para titulares de impacto
    "condensado":    ["Barlow Condensed", "Oswald", "Exo 2", "Rajdhani",
                      "Bebas Neue", "Kanit"],
    # Serifa con contraste, editorial y actual
    "serif_moderno": ["Playfair Display", "DM Serif Display", "Cormorant Garamond",
                      "Lora"],
    # Serifa tradicional o académica
    "serif_clasico": ["Lora", "Merriweather", "Libre Baskerville", "Noto Serif",
                      "Playfair Display"],
    # Personalidad propia, experimental o muy expresiva
    "display":       ["Josefin Sans", "Space Grotesk", "Syne", "Bebas Neue",
                      "Raleway", "Barlow Condensed"],
}


def get_font_path(family: str | None, weight: int = 700) -> Path | None:
    """
    Devuelve un Path local a un .ttf de Google Fonts (descargado y cacheado).

    - Si family es None, vacío o un nombre genérico CSS → retorna None.
    - Si el archivo ya está en caché → lo devuelve sin red.
    - Si no → descarga de Google Fonts y cachea en assets/fonts/.
    - Cualquier error → retorna None (el caller debe hacer fallback).

    Args:
        family: nombre de familia en Google Fonts (ej: "Montserrat", "Raleway").
                Case-sensitive, igual que en fonts.google.com.
        weight: peso numérico (400 = regular, 700 = bold).
    """
    if not family or not family.strip():
        return None

    family = _normalize(family.strip())

    if family.lower() in _GENERIC:
        return None

    # Prioridad 1: buscar fuente local (subida o extraída del PDF)
    local = find_local_font(family, weight)
    if local:
        return local

    dest = _cache_path(family, weight)
    if dest.exists():
        print(f"  [fonts] Usando caché: {dest.name}")
        return dest

    # Si esta familia ya falló en Google Fonts en esta sesión, no reintentar
    if family in _failed_google:
        return None

    FONTS_DIR.mkdir(parents=True, exist_ok=True)

    family_url = family.replace(" ", "+")
    css_url    = f"https://fonts.googleapis.com/css2?family={family_url}:wght@{weight}"

    try:
        resp = requests.get(
            css_url,
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        css = resp.text

        # Buscar URL del archivo de fuente en el CSS (@font-face → src: url(...))
        match = re.search(r"url\((https://[^)]+\.(?:ttf|woff2?))\)", css)
        if not match:
            print(f"  [fonts] No se encontró URL de fuente para '{family}' w{weight}")
            # Muchas fuentes display solo tienen peso 400 (ej: Fredoka One, Pacifico)
            # Si pedimos 700 y falla, intentar con 400 antes de abandonar
            if weight != 400:
                alt = get_font_path(family, 400)
                if alt:
                    # Enlazar como el peso solicitado para que los lookups futuros lo encuentren
                    import shutil
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(alt, dest)
                    print(f"  [fonts] '{family}' solo tiene w400 — usando como w{weight}")
                    return dest
            return None

        font_url  = match.group(1)
        font_data = requests.get(font_url, timeout=15).content
        dest.write_bytes(font_data)
        print(f"  [fonts] Descargada: {dest.name} ({len(font_data) // 1024} KB)")
        return dest

    except requests.RequestException as e:
        print(f"  [fonts] '{family}' no disponible en Google Fonts — usando fallback")
        _failed_google.add(family)
        return None
    except Exception as e:
        print(f"  [fonts] Error inesperado para '{family}' w{weight}: {e}")
        _failed_google.add(family)
        return None


def warmup(family: str | None, weights: list[int] | None = None) -> dict[int, Path | None]:
    """
    Pre-descarga todos los pesos de una familia en assets/fonts/.
    Llamar una vez al inicio del pipeline para evitar latencia durante el render.

    Returns:
        Dict mapping weight → Path (o None si falló para ese peso).
    """
    if not family:
        return {}
    weights = weights or [400, 700]
    result  = {}
    for w in weights:
        result[w] = get_font_path(family, w)
    return result


def get_font_path_with_fallback(
    family: str | None,
    style_category: str | None = None,
    weight: int = 700,
) -> Path | None:
    """
    Intenta descargar `family`. Si falla (no existe en Google Fonts),
    prueba en orden las alternativas del mismo `style_category` del catálogo.

    Esto garantiza que siempre se use la fuente visualmente más cercana
    aunque el nombre exacto no esté disponible en Google Fonts.

    Args:
        family:         nombre de familia (Google Fonts o local)
        style_category: categoría visual ("burbuja", "geometrico", etc.)
        weight:         peso numérico (400=regular, 700=bold)
    """
    # 1. Intentar la fuente principal
    path = get_font_path(family, weight)
    if path:
        return path

    # 2. Si falla y tenemos categoría, probar alternativas del catálogo
    if style_category and style_category in FONT_CATALOG:
        for alt in FONT_CATALOG[style_category]:
            if alt == family:
                continue
            path = get_font_path(alt, weight)
            if path:
                print(f"  [fonts] Fallback tipográfico: '{family}' → '{alt}' "
                      f"(categoría: {style_category})")
                return path

    return None
