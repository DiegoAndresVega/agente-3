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


PDF_MAX_BYTES  = 4 * 1024 * 1024   # 4 MB — por encima se extrae por páginas
PDF_MAX_PAGES  = 4                  # máximo de páginas a extraer si el PDF es grande


def _extraer_paginas_como_imagenes(data: bytes) -> tuple[str, str]:
    """
    Cuando el PDF es demasiado grande, extrae las primeras páginas
    como imágenes JPEG concatenadas en un PDF ligero.
    Requiere PyMuPDF (fitz).
    """
    try:
        import fitz  # PyMuPDF
        doc   = fitz.open(stream=data, filetype="pdf")
        n     = min(PDF_MAX_PAGES, len(doc))
        buf   = BytesIO()

        # Crear PDF nuevo con las páginas renderizadas como imágenes
        nuevo = fitz.open()
        for i in range(n):
            pag  = doc[i]
            mat  = fitz.Matrix(1.5, 1.5)          # 108 dpi — suficiente para análisis
            pix  = pag.get_pixmap(matrix=mat)
            img  = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img_buf = BytesIO()
            img.save(img_buf, format="JPEG", quality=75)
            img_buf.seek(0)
            img_doc = fitz.open(stream=img_buf.read(), filetype="jpg")
            rect    = img_doc[0].rect
            pagina  = nuevo.new_page(width=rect.width, height=rect.height)
            pagina.show_pdf_page(rect, img_doc, 0)

        nuevo.save(buf)
        b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
        print(f"    PDF reducido a {n} páginas ({len(buf.getvalue())//1024} KB)")
        return b64, "application/pdf"

    except Exception as e:
        print(f"    Aviso: no se pudo reducir el PDF ({e}) — se omite brandbook")
        return "", "application/pdf"


def codificar_pdf(fuente) -> tuple[str, str]:
    """
    Acepta ruta (Path/str) o bytes crudos.
    Si el PDF supera PDF_MAX_BYTES, extrae solo las primeras páginas.
    Devuelve (base64_string, "application/pdf").
    """
    if isinstance(fuente, (str, Path)):
        with open(fuente, "rb") as f:
            data = f.read()
    else:
        data = fuente

    if len(data) > PDF_MAX_BYTES:
        print(f"    PDF grande ({len(data)//1024//1024} MB) — extrayendo primeras {PDF_MAX_PAGES} páginas...")
        return _extraer_paginas_como_imagenes(data)

    b64 = base64.standard_b64encode(data).decode("utf-8")
    return b64, "application/pdf"


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
      logo_b64, logo_type       ← para enviar a Claude
      pdf_b64, pdf_type         ← para enviar a Claude (vacío si no hay)
      url_data                  ← resultado fetch_url (vacío si no hay URL)
      logo_path                 ← ruta al logo en disco (para Capa 2 renderer)
    """
    brand_context = {
        "logo_b64":   "",
        "logo_type":  "image/jpeg",
        "pdf_b64":    "",
        "pdf_type":   "application/pdf",
        "url_data":   {},
        "logo_path":  "",   # ruta en disco para capa2_renderer
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
        b64, tipo = codificar_pdf(pdf_bytes)
        brand_context["pdf_b64"]  = b64
        brand_context["pdf_type"] = tipo
    else:
        ruta_pdf_raw = assets.get("brand_book_path", "")
        if ruta_pdf_raw:
            ruta_pdf = resolver_asset(ruta_pdf_raw)
            if ruta_pdf:
                b64, tipo = codificar_pdf(ruta_pdf)
                brand_context["pdf_b64"]  = b64
                brand_context["pdf_type"] = tipo
                print(f"  → Brandbook: {ruta_pdf.name} ✓")
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
