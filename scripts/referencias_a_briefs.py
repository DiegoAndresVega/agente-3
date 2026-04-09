"""
Convierte imágenes y PDFs de referencia en design briefs JSON para el sistema de aprendizaje.

Lee imágenes (.jpg, .png, .webp) y PDFs de assets/referencias/ (o cualquier carpeta),
le pide a Claude que analice el diseño de cada página/imagen y genere el brief JSON,
y guarda el resultado en assets/aprendizaje/ listo para ser usado como ejemplo.

Los PDFs se procesan página a página — cada página con contenido visual genera su propio brief.

Uso:
    python scripts/referencias_a_briefs.py
    python scripts/referencias_a_briefs.py --carpeta assets/mis_referencias
    python scripts/referencias_a_briefs.py --imagen ruta/imagen.jpg
    python scripts/referencias_a_briefs.py --pdf ruta/catalogo.pdf
    python scripts/referencias_a_briefs.py --forzar
"""

import os
import re
import json
import base64
import argparse
import sys
import io
from pathlib import Path

import anthropic

try:
    import fitz  # PyMuPDF
    PYMUPDF_OK = True
except ImportError:
    PYMUPDF_OK = False

PROJECT_ROOT    = Path(__file__).resolve().parent.parent
REFERENCIAS_DIR = PROJECT_ROOT / "assets" / "referencias"
APRENDIZAJE_DIR = PROJECT_ROOT / "assets" / "aprendizaje"

MODELO = "claude-sonnet-4-6"

PROMPT_ANALISIS = """\
Eres un diseñador gráfico senior analizando una imagen de referencia para extraer \
sus especificaciones técnicas de diseño en formato JSON.

La imagen puede mostrar un trofeo físico (en diagonal, con perspectiva), pero debes \
centrarte en el ÁREA IMPRIMIBLE — la zona plana donde está el diseño gráfico: \
colores, tipografía, logotipo, elementos geométricos, composición.

ESQUEMA DE SALIDA (design brief):
Genera un JSON con EXACTAMENTE esta estructura, completando los campos con los \
valores que observas en la imagen:

{
  "pattern_name": "nombre descriptivo del estilo que ves (2-3 palabras)",
  "design_rationale": "qué hace especial o efectivo este diseño (1 frase)",
  "background": {
    "type": "solid|gradient",
    "color_1": "#HEX del color principal de fondo",
    "color_2": "#HEX del segundo color si hay gradiente, o null",
    "direction": "vertical|horizontal"
  },
  "logo_watermark": {
    "active": false,
    "opacity": 0.06, "scale": 0.85, "position": "center"
  },
  "color_split": {
    "active": true/false,
    "direction": "vertical|horizontal",
    "ratio": 0.35,
    "color_zone_1": "#HEX zona superior o izquierda",
    "color_zone_2": "#HEX zona inferior o derecha"
  },
  "geometric_blocks": {
    "active": true/false,
    "blocks": [
      { "x_ratio": 0.0, "y_ratio": 0.85, "w_ratio": 1.0, "h_ratio": 0.15,
        "color": "#HEX", "opacity": 1.0 }
    ]
  },
  "floating_shapes": {
    "active": true/false,
    "shape": "circle|ellipse",
    "count": 8, "size_min": 0.05, "size_max": 0.22, "opacity": 0.12,
    "color": "#HEX"
  },
  "corner_accent": {
    "active": true/false,
    "corner": "top_right|top_left|bottom_right|bottom_left",
    "size_ratio": 0.25, "color": "#HEX", "opacity": 0.9
  },
  "decorative_lines": {
    "active": true/false,
    "lines": [
      { "x1_ratio": 0.08, "y1_ratio": 0.50, "x2_ratio": 0.92, "y2_ratio": 0.50,
        "color": "#HEX", "opacity": 0.5, "width": 1 }
    ]
  },
  "logo": {
    "treatment": "blanco|color",
    "position": "top_center|top_left|top_right|bottom_center|center",
    "scale": 0.60
  },
  "text": {
    "color": "#HEX del color del texto principal",
    "font_style": "display|editorial|modern|bold",
    "alignment": "center|left",
    "headline_size_ratio": 0.08,
    "margin_h": 0.07,
    "layout": "stacked|logo_bottom",
    "separator_lines": false
  },
  "award_text": {
    "headline": "texto del título que ves o placeholder genérico",
    "recipient": "nombre visible o 'Nombre del Premiado'",
    "subtitle": "subtítulo visible o 'Por su excelencia y dedicación'"
  }
}

INSTRUCCIONES:
- color_split y geometric_blocks NO pueden estar ambos active:true
- floating_shapes y geometric_blocks NO pueden estar ambos active:true
- Si no ves un elemento claramente, ponlo como active:false
- Estima los HEX de color lo más precisamente posible desde la imagen
- Devuelve SOLO el JSON, sin texto adicional, sin markdown\
"""


def analizar_imagen(ruta: Path, client: anthropic.Anthropic) -> dict:
    """Envía una imagen a Claude y obtiene el design brief JSON."""
    datos_b64 = base64.standard_b64encode(ruta.read_bytes()).decode("utf-8")
    media_type = "image/png" if ruta.suffix.lower() == ".png" else "image/jpeg"

    respuesta = client.messages.create(
        model=MODELO,
        max_tokens=2048,
        temperature=0.2,   # baja temperatura para análisis preciso
        system=PROMPT_ANALISIS,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": datos_b64}
                },
                {
                    "type": "text",
                    "text": "Analiza el diseño de esta imagen y genera el design brief JSON."
                }
            ]
        }]
    )

    texto = respuesta.content[0].text.strip()

    # Limpiar markdown si Claude lo incluye
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    if match:
        texto = match.group(1)
    else:
        match = re.search(r"(\{.*\})", texto, re.DOTALL)
        if match:
            texto = match.group(1)

    return json.loads(texto)


def extraer_paginas_pdf(pdf_path: Path) -> list[tuple[int, bytes]]:
    """
    Extrae las páginas de un PDF como imágenes PNG.
    Devuelve lista de (numero_pagina, bytes_png).
    Requiere PyMuPDF (fitz).
    """
    if not PYMUPDF_OK:
        raise ImportError(
            "PyMuPDF no está instalado. Instálalo con: pip install pymupdf"
        )
    doc = fitz.open(str(pdf_path))
    paginas = []
    for i, pagina in enumerate(doc):
        # Renderizar a 150 DPI — suficiente para análisis visual
        mat  = fitz.Matrix(150 / 72, 150 / 72)
        pix  = pagina.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        paginas.append((i + 1, pix.tobytes("png")))
    doc.close()
    return paginas


def analizar_bytes_imagen(img_bytes: bytes, media_type: str,
                           client: anthropic.Anthropic) -> dict:
    """Versión de analizar_imagen que acepta bytes directamente."""
    datos_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

    respuesta = client.messages.create(
        model=MODELO,
        max_tokens=2048,
        temperature=0.2,
        system=PROMPT_ANALISIS,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": datos_b64}
                },
                {
                    "type": "text",
                    "text": "Analiza el diseño de esta imagen y genera el design brief JSON."
                }
            ]
        }]
    )

    texto = respuesta.content[0].text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.DOTALL)
    if match:
        texto = match.group(1)
    else:
        match = re.search(r"(\{.*\})", texto, re.DOTALL)
        if match:
            texto = match.group(1)

    return json.loads(texto)


def procesar_pdf(pdf_path: Path, client: anthropic.Anthropic,
                 forzar: bool = False) -> tuple[int, int]:
    """
    Procesa un PDF página a página.
    Devuelve (procesadas, omitidas).
    """
    import shutil

    print(f"\n  PDF: {pdf_path.name}")
    try:
        paginas = extraer_paginas_pdf(pdf_path)
    except ImportError as e:
        print(f"  ✗ {e}")
        return 0, 0

    procesadas = 0
    omitidas   = 0

    for num_pag, img_bytes in paginas:
        nombre_base = f"ref_{pdf_path.stem}_p{num_pag:02d}"
        json_dst    = APRENDIZAJE_DIR / f"{nombre_base}.json"
        img_dst     = APRENDIZAJE_DIR / f"{nombre_base}.png"

        if json_dst.exists() and not forzar:
            print(f"    [omitido] página {num_pag} — ya existe")
            omitidas += 1
            continue

        print(f"    [analizando] página {num_pag}/{len(paginas)} ...", end="", flush=True)
        try:
            brief = analizar_bytes_imagen(img_bytes, "image/png", client)

            with open(json_dst, "w", encoding="utf-8") as f:
                json.dump(brief, f, ensure_ascii=False, indent=2)

            # Guardar la imagen de la página junto al JSON
            img_dst.write_bytes(img_bytes)

            print(f" ✓  →  {brief.get('pattern_name', '?')}")
            procesadas += 1

        except json.JSONDecodeError as e:
            print(f" ✗  JSON inválido: {e}")
        except Exception as e:
            print(f" ✗  Error: {e}")

    return procesadas, omitidas


def procesar_carpeta(carpeta: Path, forzar: bool = False) -> None:
    """Procesa todas las imágenes y PDFs de una carpeta."""
    import shutil

    ext_imagen = {".jpg", ".jpeg", ".png", ".webp"}
    archivos   = sorted(carpeta.iterdir())
    imagenes   = [p for p in archivos if p.suffix.lower() in ext_imagen]
    pdfs       = [p for p in archivos if p.suffix.lower() == ".pdf"]

    if not imagenes and not pdfs:
        print(f"  No se encontraron imágenes ni PDFs en {carpeta}")
        return

    print(f"  Encontrados: {len(imagenes)} imagen(es), {len(pdfs)} PDF(s)")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n  [ERROR] Falta ANTHROPIC_API_KEY")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    APRENDIZAJE_DIR.mkdir(parents=True, exist_ok=True)

    procesadas = 0
    omitidas   = 0

    # ── Imágenes ──
    for img_path in imagenes:
        nombre_base = f"ref_{img_path.stem}"
        json_dst    = APRENDIZAJE_DIR / f"{nombre_base}.json"
        img_dst     = APRENDIZAJE_DIR / f"{nombre_base}{img_path.suffix}"

        if json_dst.exists() and not forzar:
            print(f"  [omitido] {img_path.name}")
            omitidas += 1
            continue

        print(f"  [analizando] {img_path.name} ...", end="", flush=True)
        try:
            brief = analizar_imagen(img_path, client)
            with open(json_dst, "w", encoding="utf-8") as f:
                json.dump(brief, f, ensure_ascii=False, indent=2)
            shutil.copy2(img_path, img_dst)
            print(f" ✓  →  {brief.get('pattern_name', '?')}")
            procesadas += 1
        except json.JSONDecodeError as e:
            print(f" ✗  JSON inválido: {e}")
        except Exception as e:
            print(f" ✗  Error: {e}")

    # ── PDFs ──
    for pdf_path in pdfs:
        p, o = procesar_pdf(pdf_path, client, forzar=forzar)
        procesadas += p
        omitidas   += o

    print(f"\n  Procesadas: {procesadas}  |  Omitidas: {omitidas}")
    print(f"  Ejemplos en assets/aprendizaje/: {len(list(APRENDIZAJE_DIR.glob('*.json')))}")


def procesar_imagen_individual(ruta: Path) -> None:
    """Procesa una sola imagen."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n  [ERROR] Falta ANTHROPIC_API_KEY")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    APRENDIZAJE_DIR.mkdir(parents=True, exist_ok=True)

    nombre_base = f"ref_{ruta.stem}"
    json_dst    = APRENDIZAJE_DIR / f"{nombre_base}.json"
    img_dst     = APRENDIZAJE_DIR / f"{nombre_base}{ruta.suffix}"

    print(f"  Analizando: {ruta.name} ...", end="", flush=True)
    try:
        brief = analizar_imagen(ruta, client)
        with open(json_dst, "w", encoding="utf-8") as f:
            json.dump(brief, f, ensure_ascii=False, indent=2)
        import shutil
        shutil.copy2(ruta, img_dst)
        print(f" ✓")
        print(f"  Patrón detectado: {brief.get('pattern_name', '?')}")
        print(f"  Guardado en: {json_dst}")
    except Exception as e:
        print(f" ✗  Error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convierte imágenes y PDFs de referencia en design briefs JSON"
    )
    parser.add_argument("--carpeta", type=str, default=None,
                        help="Carpeta con imágenes/PDFs (por defecto: assets/referencias/)")
    parser.add_argument("--imagen", type=str, default=None,
                        help="Procesar una sola imagen")
    parser.add_argument("--pdf", type=str, default=None,
                        help="Procesar un PDF (genera un brief por página)")
    parser.add_argument("--forzar", action="store_true",
                        help="Regenerar aunque el JSON ya exista")
    args = parser.parse_args()

    print("\n" + "="*50)
    print("  SUSTAIN AWARDS - Referencias a Briefs")
    print("="*50 + "\n")

    if not PYMUPDF_OK:
        print("  ⚠  PyMuPDF no instalado — los PDFs no se procesarán.")
        print("     Instálalo con: pip install pymupdf\n")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [ERROR] Falta ANTHROPIC_API_KEY")
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)
    APRENDIZAJE_DIR.mkdir(parents=True, exist_ok=True)

    if args.imagen:
        ruta = Path(args.imagen)
        if not ruta.exists():
            print(f"  [ERROR] No existe: {ruta}")
            sys.exit(1)
        procesar_imagen_individual(ruta)

    elif args.pdf:
        ruta = Path(args.pdf)
        if not ruta.exists():
            print(f"  [ERROR] No existe: {ruta}")
            sys.exit(1)
        p, o = procesar_pdf(ruta, client, forzar=args.forzar)
        print(f"\n  Procesadas: {p}  |  Omitidas: {o}")
        print(f"  Ejemplos en assets/aprendizaje/: {len(list(APRENDIZAJE_DIR.glob('*.json')))}")

    else:
        carpeta = Path(args.carpeta) if args.carpeta else REFERENCIAS_DIR
        if not carpeta.exists():
            print(f"  [ERROR] Carpeta no encontrada: {carpeta}")
            sys.exit(1)
        print(f"  Carpeta: {carpeta}")
        print(f"  Destino: {APRENDIZAJE_DIR}\n")
        procesar_carpeta(carpeta, forzar=args.forzar)

    print("\n  Listo. Los ejemplos se usarán automáticamente en la próxima generación.\n")
