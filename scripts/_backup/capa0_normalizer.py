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
PDF_PAGINAS_VISUAL  = 16                 # máximo de páginas visuales a enviar a Claude


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

        for i in indices:
            pag = doc[i]
            mat = fitz.Matrix(1.5, 1.5)      # ~108 dpi — suficiente para análisis
            pix = pag.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=75)
            b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
            imagenes_b64.append(b64)
            kb_total += len(buf.getvalue()) // 1024

        doc.close()
        print(f"    [BrandBook] Páginas seleccionadas por relevancia: {indices}")
        print(f"    [BrandBook] Total enviado a Claude: {len(indices)} páginas ({kb_total} KB)")

    except Exception as e:
        print(f"    [BrandBook] Error procesando PDF ({e})")

    # ── Construir resumen de texto ────────────────────────────────────────────
    lineas = [f"[BRANDBOOK — {len(colores_hex)} colores HEX, {len(colores_pant)} Pantone, {len(fuentes)} fuentes]"]

    if colores_hex:
        top = sorted(colores_hex.items(), key=lambda x: -len(x[1]))[:20]
        lineas.append("COLORES HEX DEL BRANDBOOK (ordenados por frecuencia = importancia):")
        for h, pags in top:
            lineas.append(f"  {h} — aparece en páginas: {pags[:5]}")

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

        colores = set()

        # meta theme-color
        meta_color = soup.find("meta", {"name": "theme-color"})
        if meta_color and meta_color.get("content"):
            c = meta_color["content"].strip()
            if c.startswith("#"):
                colores.add(c.upper())

        # colores en atributos style inline (background-color, color, background)
        hex_pattern = re.compile(r'#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b')
        for tag in soup.find_all(style=True):
            estilo = tag.get("style", "")
            for match in hex_pattern.finditer(estilo):
                h = match.group(0).upper()
                # filtrar blanco puro y negro puro
                if h not in ("#FFFFFF", "#000000", "#FFF", "#000"):
                    colores.add(h)

        # colores en <style> embebido
        for style_tag in soup.find_all("style"):
            texto_css = style_tag.get_text()
            for match in hex_pattern.finditer(texto_css):
                h = match.group(0).upper()
                if h not in ("#FFFFFF", "#000000", "#FFF", "#000"):
                    colores.add(h)

        # Open Graph / Twitter card colors
        for meta in soup.find_all("meta"):
            content = meta.get("content", "")
            for match in hex_pattern.finditer(content):
                h = match.group(0).upper()
                colores.add(h)

        resultado["colores_detectados"] = list(colores)[:10]  # máx 10

        # Densidad visual
        num_imgs = len(soup.find_all("img"))
        texto_total = len(soup.get_text())
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

        # Detectar imágenes hero (sections grandes, divs con background-image)
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
        if len(colores) > 5:
            estilos.append("paleta de colores amplia")
        elif len(colores) <= 2:
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


# ─── Normalizador principal ───────────────────────────────────────────────────

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
        # logo_path queda vacío; el caller (web server) lo gestionará
    else:
        ruta_logo = resolver_asset(assets.get("logo_path", ""))
        if ruta_logo is None:
            raise FileNotFoundError(
                f"Logo no encontrado: {assets.get('logo_path')}\n"
                f"  Esperado en: {ASSETS_DIR / 'logos'}"
            )
        b64, tipo = codificar_imagen(ruta_logo)
        brand_context["logo_b64"]  = b64
        brand_context["logo_type"] = tipo
        brand_context["logo_path"] = str(ruta_logo.relative_to(PROJECT_ROOT))
        print(f"  → Logo     : {ruta_logo.name} ✓")

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
        url_data = fetch_url(url)
        brand_context["url_data"] = url_data
        if url_data["ok"]:
            print(f"    Colores detectados : {url_data['colores_detectados'][:5]}")
            print(f"    Densidad visual    : {url_data['densidad_visual']}")
            print(f"    Gradientes         : {'sí' if url_data['tiene_gradientes'] else 'no'}")
        else:
            print(f"    Aviso: {url_data['descripcion_estilo']}")
    else:
        print(f"  → URL      : no especificada")

    return brand_context
