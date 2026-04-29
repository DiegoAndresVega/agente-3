"""
CAPA 0 — Normalización de inputs
Sustain Awards

Recibe los datos crudos del pedido y los transforma en un brand_context
unificado y listo para que Capa 1 (IA) lo consuma.

Procesa:
  - Logo (PNG/SVG/JPG)  → base64 JPEG para enviar a Claude
  - Brandbook PDF       → base64 PDF para enviar a Claude (si existe)
  - URL corporativa     → fetch HTML → extrae colores, densidad visual, estilo
"""

import re
import base64
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR   = PROJECT_ROOT / "assets"


# ─── Resolución de rutas ──────────────────────────────────────────────────────

def resolver_asset(ruta_relativa: str) -> Path | None:
    """
    Resuelve ruta relativa al PROJECT_ROOT con fuzzy matching
    (normaliza espacios vs guiones bajos en el nombre de archivo).
    """
    if not ruta_relativa:
        return None
    ruta_exacta = PROJECT_ROOT / ruta_relativa
    if ruta_exacta.exists():
        return ruta_exacta
    directorio = ruta_exacta.parent
    nombre_buscado = ruta_exacta.name.replace("_", " ").lower()
    if directorio.exists():
        for candidato in directorio.iterdir():
            if candidato.name.replace("_", " ").lower() == nombre_buscado:
                return candidato
    return None


# ─── Codificación de assets ───────────────────────────────────────────────────

def codificar_imagen(fuente) -> tuple[str, str]:
    """
    Acepta ruta (Path/str) o bytes crudos.
    Convierte a JPEG y devuelve (base64_string, "image/jpeg").
    """
    if isinstance(fuente, (str, Path)):
        img = Image.open(fuente)
    else:
        img = Image.open(BytesIO(fuente))

    if img.mode in ("RGBA", "LA", "P"):
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
        fondo.paste(img, mask=mask)
        img = fondo
    elif img.mode != "RGB":
        img = img.convert("RGB")

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    return b64, "image/jpeg"


PDF_MAX_BYTES       = 4 * 1024 * 1024   # 4 MB — por encima se muestrea
PDF_PAGINAS_VISUAL  = 10                 # máximo de páginas visuales a enviar a Claude


def _colores_dominantes_imagen(img_pil: "Image.Image", n: int = 6) -> list[str]:
    """
    Extrae los N colores más saturados/dominantes de una imagen PIL.
    Útil para capturar colores de marca que aparecen como bloques gráficos en el brandbook
    pero no como texto HEX (p.ej. franjas de color, logotipos, gráficos de paleta).

    Usa muestreo de píxeles + cuantización a paleta reducida para eficiencia.
    Filtra blancos, negros y grises sin saturación.
    """
    from collections import Counter
    img_small = img_pil.resize((80, 80))
    pixels = list(img_small.getdata())

    def cuantizar(r, g, b):
        return ((r // 32) * 32, (g // 32) * 32, (b // 32) * 32)

    conteo = Counter(cuantizar(*p[:3]) for p in pixels)
    resultado = []
    for (r, g, b), _ in conteo.most_common(100):
        lum = (r * 299 + g * 587 + b * 114) // 1000
        sat = max(r, g, b) - min(r, g, b)
        if lum < 20 or lum > 235:   # muy oscuro o muy claro
            continue
        if sat < 30:                 # gris sin saturación
            continue
        h = f"#{r:02X}{g:02X}{b:02X}"
        if h not in resultado:
            resultado.append(h)
        if len(resultado) >= n:
            break
    return resultado


def _indices_por_relevancia(total: int, n: int,
                             colores_hex: dict, colores_pant: dict) -> list[int]:
    """
    Selecciona hasta n páginas priorizando las que contienen identidad visual real:
      1. Primeras 2 páginas (portada + intro, suelen tener el logo principal)
      2. Páginas con más menciones de colores HEX o Pantone (paleta cromática)
      3. Relleno con distribución uniforme si quedan slots libres

    Esto garantiza que Claude vea las páginas de paleta, tipografía e identidad
    aunque estén al final del documento (ej: Juaneda, páginas 125-130).
    """
    if total <= n:
        return list(range(total))

    indices = set()

    # Portada e intro — casi siempre tienen el logo y la marca principal
    indices.update([0, min(1, total - 1)])

    # Páginas con menciones de colores (índice 0-based = página - 1)
    puntuacion = {}   # índice_pagina → puntuación de relevancia
    for pags in colores_hex.values():
        for p in pags:
            puntuacion[p - 1] = puntuacion.get(p - 1, 0) + 2   # HEX vale más
    for pags in colores_pant.values():
        for p in pags:
            puntuacion[p - 1] = puntuacion.get(p - 1, 0) + 1

    # Ordenar por puntuación descendente, añadir hasta llenar slots
    por_relevancia = sorted(puntuacion.items(), key=lambda x: -x[1])
    for idx, _ in por_relevancia:
        if len(indices) >= n:
            break
        if 0 <= idx < total:
            indices.add(idx)

    # Relleno uniforme si aún quedan slots
    if len(indices) < n:
        paso = max(1, total // (n - len(indices) + 1))
        for k in range(0, total, paso):
            if len(indices) >= n:
                break
            indices.add(k)

    return sorted(indices)[:n]


def _extraer_brandbook_completo(data: bytes) -> tuple[list[str], str, dict]:
    """
    Abre el PDF UNA SOLA VEZ y realiza:
      1. Extracción de texto de TODAS las páginas (colores HEX, Pantone, fuentes)
      2. Renderizado de páginas distribuidas como imágenes JPEG independientes

    Retorna (lista_de_b64_jpeg, resumen_texto, fuentes_extraidas).
    Cada JPEG se enviará a Claude como bloque image — sin wrapper PDF,
    evitando el bug de PyMuPDF 1.27 con fitz.open(filetype="jpg").
    """
    import fitz

    hex_re  = re.compile(r'#([0-9A-Fa-f]{6})\b')
    # RGB valores escritos como "R: 41 G: 128 B: 185" o "41 / 128 / 185" o "41, 128, 185" o "rgb(41,128,185)"
    rgb_re  = re.compile(
        r'(?:R(?:ed)?\s*[:\s]\s*(\d{1,3})\s*[,/\s]\s*G(?:reen)?\s*[:\s]\s*(\d{1,3})\s*[,/\s]\s*B(?:lue)?\s*[:\s]\s*(\d{1,3})'
        r'|rgb\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\))',
        re.IGNORECASE,
    )
    pant_re = re.compile(r'PANTONE\s+[\w\d]+', re.IGNORECASE)
    font_re = re.compile(
        r'(?:font(?:\s+family)?|typeface|tipograf[íi]a|fuente)\s*[:\-]?\s*'
        r'([A-Za-z][A-Za-z0-9 \-]{2,40})',
        re.IGNORECASE,
    )

    colores_hex      = {}
    colores_pant     = {}
    fuentes          = set()
    imagenes_b64     = []   # lista de JPEG base64, una por página seleccionada
    fuentes_extraidas = {}  # nombre_limpio → Path
    colores_graficos  = set()  # colores extraídos de píxeles de páginas renderizadas

    try:
        doc   = fitz.open(stream=bytearray(data), filetype="pdf")
        total = len(doc)

        # ── 1. Extracción de texto de TODAS las páginas ──────────────────────
        for i in range(total):
            texto = doc[i].get_text()
            for m in hex_re.finditer(texto):
                h = "#" + m.group(1).upper()
                if h not in ("#FFFFFF", "#000000"):
                    colores_hex.setdefault(h, []).append(i + 1)
            for m in rgb_re.finditer(texto):
                # grupo 1-3 → "R: G: B:" format; grupo 4-6 → "rgb()" format
                if m.group(1):
                    r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
                else:
                    r, g, b = int(m.group(4)), int(m.group(5)), int(m.group(6))
                if all(0 <= v <= 255 for v in (r, g, b)):
                    lum = (r * 299 + g * 587 + b * 114) // 1000
                    if 5 < lum < 250:   # excluir blanco puro y negro puro
                        h = f"#{r:02X}{g:02X}{b:02X}"
                        colores_hex.setdefault(h, []).append(i + 1)
            for m in pant_re.finditer(texto):
                colores_pant.setdefault(m.group(0).upper().strip(), []).append(i + 1)
            for m in font_re.finditer(texto):
                fuentes.add(m.group(1).strip())

        print(f"    [BrandBook] Escaneadas {total} páginas en busca de identidad visual")
        print(f"    [BrandBook] Colores HEX  : {len(colores_hex)}  →  {list(colores_hex.keys())[:8]}")
        print(f"    [BrandBook] Pantone       : {len(colores_pant)}")
        print(f"    [BrandBook] Tipografías   : {len(fuentes)}  →  {sorted(fuentes)[:5]}")

        # ── 1b. Extracción de fuentes embebidas del PDF ──────────────────────
        xrefs_vistos = set()
        for i in range(min(total, 20)):   # primeras 20 páginas — las fuentes se registran al principio
            for font_info in doc[i].get_fonts(full=True):
                xref      = font_info[0]   # xref del recurso
                font_name = font_info[3]   # basefont name (puede tener prefijo ABCDEF+)
                if xref in xrefs_vistos or not font_name:
                    continue
                xrefs_vistos.add(xref)
                try:
                    result = doc.extract_font(xref)
                    # PyMuPDF 1.27: extract_font devuelve (name, ext, type, buffer)
                    if not result or len(result) < 4:
                        continue
                    fext   = result[1] or "ttf"
                    buffer = result[3]
                    if fext not in ("ttf", "otf", "cff"):
                        continue
                    out_ext = "otf" if fext in ("otf", "cff") else "ttf"
                    from scripts.font_manager import register_local_font
                    path = register_local_font(font_name, buffer, out_ext)
                    if path:
                        clean = font_name.split("+")[-1].strip()
                        fuentes_extraidas[clean] = path
                except Exception:
                    pass

        if fuentes_extraidas:
            print(f"    [BrandBook] Fuentes extraídas del PDF: {list(fuentes_extraidas.keys())[:5]}")

        # ── 2. Renderizar páginas por relevancia como JPEG independientes ────
        indices  = _indices_por_relevancia(total, PDF_PAGINAS_VISUAL,
                                           colores_hex, colores_pant)
        kb_total = 0
        colores_graficos = set()   # colores extraídos de los píxeles de las páginas

        for i in indices:
            pag = doc[i]
            mat = fitz.Matrix(1.2, 1.2)      # ~86 dpi — análisis visual ok, payload menor
            pix = pag.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            # Extraer colores dominantes de la página renderizada
            for c in _colores_dominantes_imagen(img, n=6):
                colores_graficos.add(c)

            buf = BytesIO()
            img.save(buf, format="JPEG", quality=65)
            b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
            imagenes_b64.append(b64)
            kb_total += len(buf.getvalue()) // 1024

        doc.close()
        print(f"    [BrandBook] Páginas seleccionadas por relevancia: {indices}")
        print(f"    [BrandBook] Total enviado a Claude: {len(indices)} páginas ({kb_total} KB)")
        print(f"    [BrandBook] Colores gráficos (píxeles): {list(colores_graficos)[:10]}")

    except Exception as e:
        print(f"    [BrandBook] Error procesando PDF ({e})")

    # ── Construir resumen de texto ────────────────────────────────────────────
    lineas = [f"[BRANDBOOK — {len(colores_hex)} colores HEX, {len(colores_pant)} Pantone, {len(fuentes)} fuentes]"]

    if colores_hex:
        top = sorted(colores_hex.items(), key=lambda x: -len(x[1]))[:20]
        lineas.append("COLORES HEX DEL BRANDBOOK (ordenados por frecuencia = importancia):")
        for h, pags in top:
            lineas.append(f"  {h} — aparece en páginas: {pags[:5]}")

    if colores_graficos:
        lineas.append("COLORES DETECTADOS EN GRÁFICOS/BLOQUES DE LAS PÁGINAS (muestreo visual):")
        lineas.append("  Estos colores son los más usados en las ilustraciones y bloques de color del brandbook.")
        for c in sorted(colores_graficos)[:20]:
            lineas.append(f"  {c}")

    if colores_pant:
        lineas.append("REFERENCIAS PANTONE:")
        for p, pags in list(colores_pant.items())[:15]:
            lineas.append(f"  {p} — páginas: {pags[:3]}")

    if fuentes:
        lineas.append("TIPOGRAFÍAS MENCIONADAS:")
        for f in sorted(fuentes)[:10]:
            lineas.append(f"  {f}")

    resumen = "\n".join(lineas)
    return imagenes_b64, resumen, fuentes_extraidas


def codificar_pdf(fuente) -> tuple[list[str], str, dict]:
    """
    Acepta ruta (Path/str) o bytes crudos.
    Devuelve (lista_b64_jpeg, resumen_texto_colores, fuentes_extraidas).
    Las imágenes se enviarán a Claude como bloques image independientes.
    """
    if isinstance(fuente, (str, Path)):
        with open(fuente, "rb") as f:
            data = f.read()
    else:
        data = fuente

    tam_mb = len(data) / 1024 / 1024
    print(f"    PDF recibido: {tam_mb:.1f} MB — procesando con PyMuPDF...")
    return _extraer_brandbook_completo(data)


# ─── Análisis de URL corporativa ──────────────────────────────────────────────

def fetch_url(url: str) -> dict:
    """
    Hace fetch de la URL corporativa y extrae información visual:
    - Colores detectados (meta theme-color, backgrounds CSS inline, paleta)
    - Densidad visual (nº imágenes, cantidad de texto)
    - Descripción del estilo (inferida de las clases/estructura)

    Devuelve dict con todo el contexto, o dict vacío si falla.
    """
    resultado = {
        "url": url,
        "colores_detectados": [],
        "densidad_visual": "desconocida",
        "descripcion_estilo": "No se pudo acceder a la URL",
        "tiene_gradientes": False,
        "tiene_imagenes_hero": False,
        "num_imagenes": 0,
        "ok": False,
    }

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        def _lum(hex_c: str) -> float:
            h = hex_c.lstrip("#")
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            try:
                r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            except Exception:
                return 0.5
            return (0.299*r + 0.587*g + 0.114*b) / 255

        def _sat(hex_c: str) -> float:
            h = hex_c.lstrip("#")
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            try:
                r, g, b = int(h[0:2],16)/255, int(h[2:4],16)/255, int(h[4:6],16)/255
            except Exception:
                return 0
            mx, mn = max(r,g,b), min(r,g,b)
            return (mx - mn) / mx if mx > 0 else 0

        def _es_color_marca(hex_c: str) -> bool:
            """Filtra colores de UI genéricos y deja solo colores de marca sólidos."""
            l = _lum(hex_c)
            s = _sat(hex_c)
            # Excluir: casi-blanco (fondos), casi-negro (texto), grises (UI neutral)
            if l > 0.88 or l < 0.04:
                return False
            if s < 0.18:   # muy desaturado = gris/neutral
                return False
            return True

        colores_alta  = []   # tema y CSS variables → máxima prioridad
        colores_media = set()  # inline styles y <style> general

        hex_pattern = re.compile(r'#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b')

        # 1. meta theme-color — máxima confianza (la marca lo declara explícitamente)
        meta_color = soup.find("meta", {"name": "theme-color"})
        if meta_color and meta_color.get("content", "").strip().startswith("#"):
            h = meta_color["content"].strip().upper()
            if _es_color_marca(h):
                colores_alta.append(h)

        # 2. CSS custom properties con nombre de marca/color (--primary, --brand, etc.)
        css_var_re = re.compile(
            r'--[\w-]*(?:primary|secondary|accent|brand|color|main|key)[\w-]*\s*:\s*(#[0-9A-Fa-f]{6})',
            re.IGNORECASE,
        )
        for style_tag in soup.find_all("style"):
            for match in css_var_re.finditer(style_tag.get_text()):
                h = match.group(1).upper()
                if _es_color_marca(h) and h not in colores_alta:
                    colores_alta.append(h)

        # 3. Atributos style inline en elementos de alto nivel (header, nav, button, a)
        _BRAND_TAGS = {"header", "nav", "footer", "button", "a", "h1", "h2", "h3"}
        for tag in soup.find_all(_BRAND_TAGS, style=True):
            for match in hex_pattern.finditer(tag.get("style", "")):
                h = match.group(0).upper()
                if _es_color_marca(h):
                    colores_media.add(h)

        # 4. <style> embebido general — solo colores de marca (filtrando grises y near-white)
        for style_tag in soup.find_all("style"):
            for match in hex_pattern.finditer(style_tag.get_text()):
                h = match.group(0).upper()
                if _es_color_marca(h):
                    colores_media.add(h)

        # Descargar los primeros 3 CSS externos (donde están los colores de marca reales)
        for link_tag in soup.find_all("link", rel=lambda r: r and "stylesheet" in r)[:3]:
            href = link_tag.get("href", "")
            if not href or "font" in href.lower():
                continue
            try:
                css_url = urljoin(url, href)
                css_resp = requests.get(css_url, timeout=5, headers=headers)
                css_text = css_resp.text
                for match in css_var_re.finditer(css_text):
                    h = match.group(1).upper()
                    if _es_color_marca(h) and h not in colores_alta:
                        colores_alta.append(h)
                for match in hex_pattern.finditer(css_text):
                    h = match.group(0).upper()
                    if _es_color_marca(h):
                        colores_media.add(h)
            except Exception:
                pass

        # Construir lista final: prioridad alta primero, luego media, max 5 colores
        colores_final = colores_alta[:]
        for c in sorted(colores_media, key=lambda x: -_sat(x)):  # más saturados primero
            if c not in colores_final:
                colores_final.append(c)
            if len(colores_final) >= 5:
                break

        # Deduplicar preservando orden y filtrando colores muy similares entre sí
        colores_dedup = []
        for c in colores_final:
            # Evitar colores casi idénticos (diferencia < 15 en cada canal)
            similar = False
            for prev in colores_dedup:
                h1 = prev.lstrip("#"); h2 = c.lstrip("#")
                if len(h1) == 6 and len(h2) == 6:
                    try:
                        diff = max(abs(int(h1[i:i+2],16)-int(h2[i:i+2],16)) for i in (0,2,4))
                        if diff < 25:
                            similar = True; break
                    except Exception:
                        pass
            if not similar:
                colores_dedup.append(c)
        colores_final = colores_dedup[:5]
        resultado["colores_detectados"] = colores_final

        # Densidad visual
        num_imgs = len(soup.find_all("img"))
        resultado["num_imagenes"] = num_imgs

        if num_imgs > 15:
            resultado["densidad_visual"] = "rica"
        elif num_imgs > 5:
            resultado["densidad_visual"] = "media"
        else:
            resultado["densidad_visual"] = "limpia"

        # Detectar gradientes en CSS
        css_texto = " ".join(t.get_text() for t in soup.find_all("style"))
        resultado["tiene_gradientes"] = "gradient" in css_texto.lower()

        # Detectar imágenes hero
        hero_keywords = ["hero", "banner", "jumbotron", "header", "cover"]
        clases_texto = " ".join(
            " ".join(tag.get("class", [])) for tag in soup.find_all(class_=True)
        ).lower()
        resultado["tiene_imagenes_hero"] = any(k in clases_texto for k in hero_keywords)

        # Descripción del estilo
        estilos = []
        if resultado["tiene_gradientes"]:
            estilos.append("usa gradientes")
        if resultado["densidad_visual"] == "limpia":
            estilos.append("diseño limpio y espaciado")
        elif resultado["densidad_visual"] == "rica":
            estilos.append("diseño rico en contenido visual")
        if resultado["tiene_imagenes_hero"]:
            estilos.append("imágenes hero prominentes")
        if len(colores_final) > 3:
            estilos.append("paleta de colores amplia")
        elif len(colores_final) <= 1:
            estilos.append("identidad cromática restringida")

        resultado["descripcion_estilo"] = (
            "; ".join(estilos) if estilos else "estilo estándar corporativo"
        )
        resultado["ok"] = True

    except requests.exceptions.Timeout:
        resultado["descripcion_estilo"] = "Timeout al acceder a la URL"
    except requests.exceptions.RequestException as e:
        resultado["descripcion_estilo"] = f"Error de red: {str(e)[:80]}"
    except Exception as e:
        resultado["descripcion_estilo"] = f"Error inesperado: {str(e)[:80]}"

    return resultado


def screenshot_url(url: str) -> tuple[str | None, list[str]]:
    """
    Toma un screenshot de la URL usando Playwright.
    Devuelve (jpeg_base64, colores_hero) donde colores_hero son los colores dominantes
    de la franja superior (hero/banner) extraídos por píxeles — más fiables que CSS.
    """
    try:
        from scripts.capa2_renderer import _get_browser
        browser = _get_browser()
        if browser is None:
            return None, []
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        try:
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=12000)
            page.wait_for_timeout(1500)
            png_bytes = page.screenshot(type="png", full_page=False,
                                         clip={"x": 0, "y": 0, "width": 1280, "height": 800})
            page.close()
        finally:
            context.close()

        img = Image.open(BytesIO(png_bytes)).convert("RGB")
        img = img.resize((800, 500), Image.LANCZOS)

        # Extraer colores del HERO (40% superior) — zona más representativa de la marca
        hero_h = int(img.height * 0.40)
        hero   = img.crop((0, 0, img.width, hero_h))
        colores_hero = _colores_dominantes_imagen(hero, n=6)

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode(), colores_hero

    except Exception:
        return None, []


# ─── Normalizador principal ───────────────────────────────────────────────────

def _normalizar_color_hex(c) -> str | None:
    """
    Convierte cualquier formato de color a #RRGGBB.
    Acepta: #RGB, #RRGGBB, RRGGBB (sin #), rgb(r,g,b).
    Devuelve None si no se puede convertir.
    """
    if not c or not isinstance(c, str):
        return None
    c = c.strip()
    m = re.match(r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', c, re.IGNORECASE)
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if all(0 <= v <= 255 for v in (r, g, b)):
            return f"#{r:02X}{g:02X}{b:02X}"
        return None
    h = c.lstrip("#").upper()
    if len(h) == 3 and all(ch in "0123456789ABCDEF" for ch in h):
        h = h[0]*2 + h[1]*2 + h[2]*2
    if len(h) == 6 and all(ch in "0123456789ABCDEF" for ch in h):
        return f"#{h}"
    return None


def _llamar_firecrawl(url: str) -> dict | None:
    """
    Capa primaria de identificación de color: extrae primary/secondary/accent
    y tipografías de la web usando Firecrawl Extract + IA.

    Requiere FIRECRAWL_API_KEY en el entorno.
    Si la key no está configurada o falla, devuelve None silenciosamente
    y el pipeline continúa con el Color Oracle como fallback.
    """
    import os
    api_key = os.getenv("FIRECRAWL_API_KEY", "")
    if not api_key:
        print(f"  [Firecrawl] FIRECRAWL_API_KEY no configurada — saltando")
        return None
    try:
        import requests
    except ImportError:
        return None

    schema = {
        "type": "object",
        "properties": {
            "logo_color":      {"type": "string",
                                "description": "The exact color of the company LOGO or brand mark as hex (#RRGGBB). "
                                               "Look specifically at the logo icon, symbol, or wordmark in the header. "
                                               "This is the single most reliable signal for primary brand identity."},
            "primary_color":   {"type": "string",
                                "description": "Main brand identity color as hex (#RRGGBB). "
                                               "Derive from: (1) logo color, (2) main header/nav background. "
                                               "NOT from: financial gain/loss indicators, error alerts, "
                                               "success states, or any color used only for functional meaning. "
                                               "NOT white, NOT gray."},
            "secondary_color": {"type": "string",
                                "description": "Second distinct brand color as hex (#RRGGBB). "
                                               "A REAL brand color — NOT white (#ffffff), NOT near-white, "
                                               "NOT light gray. Look for colored elements consistent across the site. "
                                               "Return null if no clear second brand color exists."},
            "accent_color":    {"type": "string",
                                "description": "CTA/action button color as hex (#RRGGBB). "
                                               "Look for 'Search', 'Buy', 'Book Now', 'Sign up' button colors. "
                                               "Return null if same as primary/secondary or if only white/gray."},
            "font_heading":    {"type": "string",
                                "description": "Primary heading typeface name (e.g. 'Inter', 'Montserrat')."},
            "font_body":       {"type": "string",
                                "description": "Body text typeface name."},
        },
        "required": ["primary_color"],
    }
    print(f"  [Firecrawl] Llamando API para {url[:60]}...")
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            json={
                "url":     url,
                "formats": ["extract"],
                "extract": {
                    "schema": schema,
                    "prompt": (
                        "Extract brand IDENTITY colors only — not functional or semantic UI colors. "
                        "METHODOLOGY — follow this order strictly: "
                        "1. LOGO: Find the company logo in the header. The logo color IS the primary_color. "
                        "   Also return it in logo_color field. "
                        "2. HEADER BACKGROUND: If the nav/header has a non-white background color, "
                        "   that confirms the primary. "
                        "3. SECONDARY: Look for a second brand color used consistently in UI elements. "
                        "4. ACCENT: Look for CTA button colors (Search, Buy, Book, Sign up). "
                        "CRITICAL EXCLUSIONS — never return these as brand colors: "
                        "- Red or green used for financial data (price up/down, gains/losses, portfolio) "
                        "- Red for errors or alerts, green for success messages "
                        "- Colors only used in promotional/seasonal banners "
                        "- White, near-white, or light gray as secondary or accent "
                        "The primary_color must be the color OF the logo/brand mark itself."
                    ),
                },
            },
            timeout=30,
        )
        print(f"  [Firecrawl] HTTP {resp.status_code}")
        if resp.status_code == 200:
            body = resp.json()
            data = body.get("data", {}).get("extract", {})
            if data and (data.get("primary_color") or data.get("logo_color")):
                print(f"  [Firecrawl] Respuesta raw: {data}")
                # Si logo_color está disponible, usarlo como primario — es la señal más fiable
                logo_c = _normalizar_color_hex(data.get("logo_color", ""))
                if logo_c:
                    prim_original = data.get("primary_color", "")
                    data["primary_color"] = logo_c
                    if prim_original and prim_original.upper() != logo_c.upper():
                        print(f"  [Firecrawl] primary corregido por logo_color: {prim_original} → {logo_c}")
                    else:
                        print(f"  [Firecrawl] logo_color confirma primary: {logo_c}")
                return data
            else:
                print(f"  [Firecrawl] Respuesta sin colores — body keys: {list(body.keys())}, data: {data}")
        else:
            print(f"  [Firecrawl] Error HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  [Firecrawl] Error: {e} — continuando sin Firecrawl")
    return None


def _consolidar_colores_hsv(colores: list[str], max_grupos: int = 5) -> list[str]:
    """
    Agrupa colores por familia de tono HSV y devuelve el representante más saturado
    de cada grupo. Elimina near-duplicates (mismo azul en 5 variantes → 1 canónico).

    Umbral: distancia de tono circular < 0.08 (~29°) = misma familia cromática.
    Selección de representante: mayor saturación × valor (el color más vívido del grupo).
    """
    import colorsys

    def _hex_to_hsv(h: str) -> tuple[float, float, float]:
        h = h.lstrip("#")
        r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    def _dist_hue_circular(h1: float, h2: float) -> float:
        d = abs(h1 - h2)
        return min(d, 1.0 - d)

    validos = [c for c in colores if c and len(c.lstrip("#")) == 6]
    if not validos:
        return []

    datos = []
    for c in validos:
        try:
            hv, sv, vv = _hex_to_hsv(c)
            datos.append({"hex": c, "h": hv, "s": sv, "v": vv})
        except Exception:
            pass

    grupos: list[list[dict]] = []
    for item in datos:
        colocado = False
        for grupo in grupos:
            rep = max(grupo, key=lambda x: x["s"])
            if _dist_hue_circular(item["h"], rep["h"]) < 0.08:
                grupo.append(item)
                colocado = True
                break
        if not colocado:
            grupos.append([item])

    resultado = []
    for grupo in grupos:
        mejor = max(grupo, key=lambda x: x["s"] * x["v"])
        resultado.append(mejor["hex"])

    return resultado[:max_grupos]


def normalizar_pedido(pedido: dict,
                      logo_bytes: bytes | None = None,
                      pdf_bytes: bytes | None = None) -> dict:
    """
    Normaliza todos los assets de un pedido en un brand_context unificado.

    Acepta assets de dos formas:
      - Como bytes (flujo web: logo_bytes, pdf_bytes pasados directamente)
      - Como rutas en pedido["assets"] (flujo CLI: resuelve desde disco)

    Devuelve brand_context con:
      logo_b64, logo_type       ← para enviar a Claude como imagen
      pdf_imagenes              ← lista de JPEG b64 (páginas del brandbook), vacía si no hay PDF
      pdf_resumen               ← texto extraído del PDF (colores HEX, Pantone, fuentes)
      url_data                  ← resultado fetch_url (vacío si no hay URL)
      logo_path                 ← ruta al logo en disco (para Capa 2 renderer)
    """
    brand_context = {
        "logo_b64":      "",
        "logo_type":     "image/jpeg",
        "pdf_imagenes":  [],   # lista de JPEG b64, una por página seleccionada
        "pdf_resumen":   "",   # texto extraído del PDF (colores, fuentes, pantones)
        "fuentes_pdf":   {},   # fuentes extraídas del PDF (nombre → Path)
        "fuente_upload": "",   # nombre de fuente subida por el usuario
        "url_data":      {},
        "logo_path":     "",   # ruta en disco para capa2_renderer
    }

    assets = pedido.get("assets", {})

    # ── Logo ──────────────────────────────────────────────────────────────────
    if logo_bytes:
        b64, tipo = codificar_imagen(logo_bytes)
        brand_context["logo_b64"]  = b64
        brand_context["logo_type"] = tipo
        print(f"  → Logo     : recibido ✓")
    else:
        ruta_logo = resolver_asset(assets.get("logo_path", "") or "")
        if ruta_logo is not None:
            b64, tipo = codificar_imagen(ruta_logo)
            brand_context["logo_b64"]  = b64
            brand_context["logo_type"] = tipo
            brand_context["logo_path"] = str(ruta_logo.relative_to(PROJECT_ROOT))
            print(f"  → Logo     : {ruta_logo.name} ✓")
        else:
            print(f"  → Logo     : no proporcionado (continuando sin él)")

    # ── PDF Brandbook ─────────────────────────────────────────────────────────
    if pdf_bytes:
        print(f"  → Brandbook: recibido ({len(pdf_bytes)//1024} KB) — extrayendo identidad visual...")
        imagenes, resumen, fuentes_pdf = codificar_pdf(pdf_bytes)
        brand_context["pdf_imagenes"] = imagenes
        brand_context["pdf_resumen"]  = resumen
        brand_context["fuentes_pdf"]  = fuentes_pdf
        n_imgs = len(imagenes)
        print(f"  → Brandbook: ✓ ({n_imgs} páginas visuales + texto extraído)")
    else:
        ruta_pdf_raw = assets.get("brand_book_path", "")
        if ruta_pdf_raw:
            ruta_pdf = resolver_asset(ruta_pdf_raw)
            if ruta_pdf:
                print(f"  → Brandbook: {ruta_pdf.name} — extrayendo identidad visual...")
                imagenes, resumen, fuentes_pdf = codificar_pdf(ruta_pdf)
                brand_context["pdf_imagenes"] = imagenes
                brand_context["pdf_resumen"]  = resumen
                brand_context["fuentes_pdf"]  = fuentes_pdf
                n_imgs = len(imagenes)
                print(f"  → Brandbook: ✓ ({n_imgs} páginas visuales + texto extraído)")
            else:
                print(f"  → Brandbook: no encontrado ({ruta_pdf_raw}) — sin brandbook")
        else:
            print(f"  → Brandbook: no especificado")

    # ── URL corporativa ───────────────────────────────────────────────────────
    url = assets.get("url_corporativa", "") or pedido.get("url_corporativa", "")
    if url:
        print(f"  → URL      : {url} — analizando...")

        # Firecrawl: capa primaria de identificación de color y tipografía.
        # Si devuelve 2+ colores válidos → establece canonical_palette directamente,
        # saltando el Color Oracle en capa1. Sin key → silencioso, pipeline normal.
        print(f"  → Firecrawl   : intentando extracción de identidad...")
        _fc = _llamar_firecrawl(url)
        if _fc:
            _raw_fc_cols = [_fc.get("primary_color"), _fc.get("secondary_color"), _fc.get("accent_color")]
            _fc_cols_all = [norm for c in _raw_fc_cols if (norm := _normalizar_color_hex(c))]

            # Separar saturados de blancos/casi-blancos.
            # Los blancos pueden ser parte legítima de la marca (Parodontax: rojo + blanco),
            # pero los ponemos al final para que los colores saturados tengan prioridad.
            # Si Firecrawl solo devuelve saturados, los blancos se ignoran.
            def _es_casi_blanco(h: str) -> bool:
                try:
                    r, g, b = int(h[1:3],16), int(h[3:5],16), int(h[5:7],16)
                    return (r*299 + g*587 + b*114) / (255*1000) > 0.88
                except Exception:
                    return False

            _fc_saturados = [c for c in _fc_cols_all if not _es_casi_blanco(c)]
            _fc_blancos   = [c for c in _fc_cols_all if _es_casi_blanco(c)]

            # Deduplicar saturados por familia HSV — elimina near-duplicates (ej: #FFBA00 y #FFBA00)
            _fc_saturados = _consolidar_colores_hsv(_fc_saturados, max_grupos=3)

            # Palette: saturados primero, blancos al final solo si hay pocos saturados
            _fc_cols = _fc_saturados + (_fc_blancos if len(_fc_saturados) < 2 else [])
            _n_saturados = len(_fc_saturados)

            if _fc_blancos and len(_fc_saturados) >= 2:
                print(f"    Blancos omitidos (ya hay {_n_saturados} colores saturados): {_fc_blancos}")
            elif _fc_blancos:
                print(f"    Blancos incluidos (pocos saturados — pueden ser parte de la marca): {_fc_blancos}")

            if _fc_cols:
                brand_context["canonical_palette"]         = _fc_cols
                brand_context["_fc_saturated_count"]       = _n_saturados
                brand_context["firecrawl_fonts"]           = {
                    "heading": _fc.get("font_heading", ""),
                    "body":    _fc.get("font_body", ""),
                }
                print(f"    Colores canónicos : {_fc_cols}  (saturados: {_n_saturados})")
                if _fc.get("font_heading"):
                    print(f"    Tipografía heading: {_fc['font_heading']}")
            else:
                print(f"    Resultado insuficiente — raw: {_raw_fc_cols}")
                print(f"    Pipeline estándar (Color Oracle)")
        else:
            print(f"    Sin key o error — pipeline estándar (Color Oracle)")

        # CSS/HTML analysis — siempre útil para estilo, densidad visual y colores secundarios
        url_data = fetch_url(url)
        brand_context["url_data"] = url_data
        if url_data["ok"]:
            print(f"    CSS colores        : {url_data['colores_detectados'][:5]}")
            print(f"    Densidad visual    : {url_data['densidad_visual']}")
            print(f"    Gradientes         : {'sí' if url_data['tiene_gradientes'] else 'no'}")
        else:
            print(f"    Aviso: {url_data['descripcion_estilo']}")

        # Screenshot: se omite solo si Firecrawl encontró 2+ colores saturados (paleta completa).
        # Si Firecrawl solo encontró 1 saturado + blanco, tomamos screenshot igualmente
        # para que el hero pixel extraction encuentre colores adicionales (ej: amarillo CTA).
        _fc_saturated_count = brand_context.get("_fc_saturated_count", 0)
        _fc_ok = bool(brand_context.get("canonical_palette")) and _fc_saturated_count >= 2
        if _fc_ok:
            print(f"  → Screenshot web: omitido (Firecrawl identificó {_fc_saturated_count} colores saturados)")
        else:
            _razon = f"Firecrawl solo encontró {_fc_saturated_count} color(es) saturado(s) — buscando más" if brand_context.get("canonical_palette") else "sin Firecrawl"
            print(f"  → Screenshot web: capturando ({_razon})...")
            screenshot_b64, hero_colors = screenshot_url(url)
            if screenshot_b64:
                brand_context["url_screenshot_b64"] = screenshot_b64
                brand_context["url_hero_colors"]    = hero_colors
                print(f"    Screenshot OK ({len(screenshot_b64)//1000}KB)")
                if hero_colors:
                    print(f"    Colores hero (píxeles): {hero_colors}")
            else:
                print(f"    Screenshot: no disponible (continuando sin él)")
    else:
        print(f"  → URL      : no especificada")

    # ── Pre-paleta consolidada (input para el Color Oracle) ───────────────────
    # Une colores del hero (píxeles) + CSS y agrupa near-duplicates por tono HSV.
    # Resultado: 4-5 colores verdaderamente distintos en lugar del listado ruidoso.
    _raw_colors = (
        list(brand_context.get("url_hero_colors", [])) +
        list(brand_context.get("url_data", {}).get("colores_detectados", []))
    )
    if _raw_colors:
        brand_context["pre_palette"] = _consolidar_colores_hsv(_raw_colors, max_grupos=5)
        print(f"  → Pre-paleta HSV  : {brand_context['pre_palette']}")
    else:
        brand_context["pre_palette"] = []

    return brand_context
