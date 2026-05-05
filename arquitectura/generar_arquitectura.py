"""
Genera el PDF de arquitectura de Sustain Awards.
Uso: python arquitectura/generar_arquitectura.py
"""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import Flowable

# ── Paleta Sustain Awards ──────────────────────────────────────────────────────
SA_BLACK      = colors.HexColor("#000000")
SA_LIMA       = colors.HexColor("#DBFF0A")
SA_GRAY_DARK  = colors.HexColor("#575452")
SA_GRAY_MID   = colors.HexColor("#A0A0A0")
SA_GRAY_LIGHT = colors.HexColor("#DEDEDE")
SA_OFF_WHITE  = colors.HexColor("#F4F4F2")
SA_WHITE      = colors.white

OUTPUT = Path(__file__).parent / "Sustain_Awards_Arquitectura.pdf"

PAGE_W, PAGE_H = A4
MARGIN     = 2 * cm
CONTENT_W  = PAGE_W - 2 * MARGIN   # ~453 pt

# ── Estilos ────────────────────────────────────────────────────────────────────
def build_styles():
    base = getSampleStyleSheet()
    s = {}

    def ps(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=base[parent], **kw)

    s["cover_title"] = ps("cover_title", fontName="Helvetica-Bold", fontSize=34,
        textColor=SA_WHITE, leading=40, alignment=TA_LEFT, spaceAfter=4)
    s["cover_sub"]   = ps("cover_sub",   fontName="Helvetica", fontSize=13,
        textColor=SA_LIMA, leading=18, alignment=TA_LEFT, spaceAfter=4)
    s["cover_meta"]  = ps("cover_meta",  fontName="Helvetica", fontSize=9.5,
        textColor=SA_GRAY_MID, leading=15, alignment=TA_LEFT)

    s["section_title"] = ps("section_title", fontName="Helvetica-Bold", fontSize=19,
        textColor=SA_BLACK, leading=24, alignment=TA_LEFT, spaceAfter=8)
    s["subsection"]    = ps("subsection",    fontName="Helvetica-Bold", fontSize=12,
        textColor=SA_BLACK, leading=17, alignment=TA_LEFT, spaceBefore=14, spaceAfter=5)

    s["body"]      = ps("body",      fontName="Helvetica", fontSize=9.5,
        textColor=SA_GRAY_DARK, leading=15, alignment=TA_JUSTIFY, spaceAfter=7)
    s["body_left"] = ps("body_left", fontName="Helvetica", fontSize=9.5,
        textColor=SA_GRAY_DARK, leading=15, alignment=TA_LEFT, spaceAfter=7)
    s["body_bold"] = ps("body_bold", fontName="Helvetica-Bold", fontSize=9.5,
        textColor=SA_BLACK, leading=15, alignment=TA_LEFT, spaceAfter=4)

    # Estilo para celdas de tabla — sin indent extra, left-align
    s["cell"]      = ps("cell",      fontName="Helvetica", fontSize=8.5,
        textColor=SA_GRAY_DARK, leading=13, alignment=TA_LEFT)
    s["cell_bold"] = ps("cell_bold", fontName="Helvetica-Bold", fontSize=8.5,
        textColor=SA_BLACK, leading=13, alignment=TA_LEFT)
    s["cell_hdr"]  = ps("cell_hdr",  fontName="Helvetica-Bold", fontSize=8.5,
        textColor=SA_WHITE, leading=13, alignment=TA_LEFT)
    s["cell_code"] = ps("cell_code", fontName="Courier", fontSize=7.5,
        textColor=SA_GRAY_DARK, leading=12, alignment=TA_LEFT)

    s["bullet"] = ps("bullet", fontName="Helvetica", fontSize=9.5,
        textColor=SA_GRAY_DARK, leading=15, leftIndent=12, spaceAfter=4)
    s["label"]  = ps("label",  fontName="Helvetica-Bold", fontSize=7.5,
        textColor=SA_GRAY_DARK, leading=11, alignment=TA_LEFT)

    s["toc_title"] = ps("toc_title", fontName="Helvetica-Bold", fontSize=9.5,
        textColor=SA_BLACK, leading=14, alignment=TA_LEFT)
    s["toc_desc"]  = ps("toc_desc",  fontName="Helvetica", fontSize=8.5,
        textColor=SA_GRAY_DARK, leading=13, alignment=TA_LEFT)
    s["toc_num"]   = ps("toc_num",   fontName="Helvetica-Bold", fontSize=9.5,
        textColor=SA_LIMA, leading=14, alignment=TA_CENTER)

    return s


# ── Flowables personalizados ───────────────────────────────────────────────────

class SectionHeader(Flowable):
    def __init__(self, number, title, width=None):
        super().__init__()
        self.number = number
        self.title  = title
        self.width  = width or CONTENT_W
        self.height = 1.3 * cm

    def draw(self):
        c = self.canv
        w = self.width
        c.setStrokeColor(SA_GRAY_LIGHT)
        c.setLineWidth(0.5)
        c.line(0, 0, w, 0)
        if self.number:
            c.setFillColor(SA_LIMA)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(0, self.height - 0.25 * cm, self.number)
        c.setFillColor(SA_BLACK)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(0, self.height - 0.95 * cm, self.title)


class PipelineStep(Flowable):
    def __init__(self, number, title, subtitle, color, width=None):
        super().__init__()
        self.number   = number
        self.title    = title
        self.subtitle = subtitle
        self.color    = color
        self.width    = width or CONTENT_W
        self.height   = 1.5 * cm

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        c.setFillColor(SA_OFF_WHITE)
        c.roundRect(0, 0, w, h, 5, fill=1, stroke=0)
        c.setFillColor(self.color)
        c.roundRect(0, 0, 0.45 * cm, h, 4, fill=1, stroke=0)
        c.rect(0.22 * cm, 0, 0.23 * cm, h, fill=1, stroke=0)
        c.setFillColor(self.color)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(0.62 * cm, h / 2 - 0.22 * cm, self.number)
        c.setFillColor(SA_BLACK)
        c.setFont("Helvetica-Bold", 10.5)
        c.drawString(1.6 * cm, h / 2 + 0.04 * cm, self.title)
        c.setFillColor(SA_GRAY_DARK)
        c.setFont("Helvetica", 8)
        c.drawString(1.6 * cm, h / 2 - 0.36 * cm, self.subtitle)


class ArrowConnector(Flowable):
    def __init__(self, width=None):
        super().__init__()
        self.width  = width or CONTENT_W
        self.height = 0.45 * cm

    def draw(self):
        c   = self.canv
        cx  = self.width / 2
        c.setStrokeColor(SA_GRAY_LIGHT)
        c.setFillColor(SA_GRAY_LIGHT)
        c.setLineWidth(1.2)
        c.line(cx, self.height, cx, 4)
        p = c.beginPath()
        p.moveTo(cx - 3.5, 4)
        p.lineTo(cx + 3.5, 4)
        p.lineTo(cx, 0)
        p.close()
        c.drawPath(p, fill=1, stroke=0)


# ── Helpers ────────────────────────────────────────────────────────────────────

def P(text, style):
    return Paragraph(text, style)

def bullet(text, s):
    return P(f"<b>·</b>  {text}", s["bullet"])

def sp(n=1):
    return Spacer(1, n * 0.22 * cm)

def hr():
    return HRFlowable(width="100%", thickness=0.4, color=SA_GRAY_LIGHT, spaceAfter=6)

def _tbl(data, col_w, style_cmds):
    """Crea una tabla con estilos base + comandos adicionales."""
    base = [
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.25, SA_GRAY_LIGHT),
    ]
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle(base + style_cmds))
    return t


def tech_table(rows, s):
    """Tabla 2 columnas: Tecnología | Descripción. Todas las celdas son Paragraph."""
    cw = [CONTENT_W * 0.30, CONTENT_W * 0.70]
    hdr = [P("<b>Tecnología / Librería</b>", s["cell_hdr"]),
           P("<b>Rol en el sistema</b>",      s["cell_hdr"])]
    data = [hdr] + [
        [P(f"<b>{r[0]}</b>", s["cell_bold"]), P(r[1], s["cell"])]
        for r in rows
    ]
    return _tbl(data, cw, [
        ("BACKGROUND",    (0, 0), (-1, 0),  SA_BLACK),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [SA_WHITE, SA_OFF_WHITE]),
    ])


def info_box(title, paragraphs, s):
    inner = [P(f"<b>{title}</b>", s["body_bold"])] + [P(p, s["body"]) for p in paragraphs]
    cw    = [0.22 * cm, CONTENT_W - 0.22 * cm - 0.5 * cm]
    data  = [["", inner]]
    t = Table(data, colWidths=cw)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), SA_LIMA),
        ("BACKGROUND",    (1, 0), (1, -1), SA_OFF_WHITE),
        ("TOPPADDING",    (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING",   (1, 0), (1, -1), 11),
        ("RIGHTPADDING",  (1, 0), (1, -1), 11),
        ("LEFTPADDING",   (0, 0), (0, -1), 0),
        ("RIGHTPADDING",  (0, 0), (0, -1), 0),
    ]))
    return [t, sp()]


# ══════════════════════════════════════════════════════
# CONSTRUCCIÓN DEL DOCUMENTO
# ══════════════════════════════════════════════════════

def build_document():
    s     = build_styles()
    story = []

    # ── PORTADA ────────────────────────────────────────
    story.append(Spacer(1, 5.5 * cm))
    story.append(P("ARQUITECTURA DEL SISTEMA", s["cover_sub"]))
    story.append(P("Agente de Diseño IA", s["cover_title"]))
    story.append(Spacer(1, 0.7 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=SA_GRAY_DARK))
    story.append(Spacer(1, 0.5 * cm))
    story.append(P(
        "Documento técnico y ejecutivo del sistema de generación automática "
        "de diseños para trofeos físicos con impresión UV.",
        s["cover_meta"]
    ))
    story.append(Spacer(1, 0.3 * cm))
    story.append(P("Versión 1.0  ·  Mayo 2026  ·  Confidencial", s["cover_meta"]))
    story.append(PageBreak())

    # ── ÍNDICE ─────────────────────────────────────────
    story.append(SectionHeader("", "Contenido", CONTENT_W))
    story.append(sp(2))

    toc_items = [
        ("01", "Cómo funciona paso a paso",       "El recorrido de una petición de principio a fin"),
        ("02", "Arquitectura técnica",            "Los módulos del pipeline y cómo se conectan"),
        ("03", "Tecnologías y librerías",         "Stack completo con roles específicos"),
        ("04", "Modelos de IA utilizados",        "Qué IA hace qué, temperatura y por qué"),
        ("05", "Estructura de archivos",          "Organización del repositorio"),
        ("06", "Flujo de datos detallado",        "Qué información viaja entre módulos"),
        ("07", "Restricciones y calidad",         "Reglas de impresión UV y garantías del sistema"),
    ]

    cw_toc = [1.1 * cm, CONTENT_W * 0.38, CONTENT_W - 1.1 * cm - CONTENT_W * 0.38]
    toc_data = [
        [P(f"<b>{n}</b>", s["toc_num"]),
         P(f"<b>{t}</b>", s["toc_title"]),
         P(d, s["toc_desc"])]
        for n, t, d in toc_items
    ]
    story.append(_tbl(toc_data, cw_toc, [
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [SA_WHITE, SA_OFF_WHITE]),
        ("TOPPADDING",     (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 7),
    ]))
    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 01. CÓMO FUNCIONA PASO A PASO
    # ══════════════════════════════════════════════════════
    story.append(SectionHeader("01", "Cómo funciona paso a paso", CONTENT_W))
    story.append(sp(2))
    story.append(P(
        "El recorrido completo de una petición, desde que el cliente pulsa "
        "'Generar diseño con IA' hasta que aparecen los seis mockups en pantalla.",
        s["body"]
    ))
    story.append(sp(2))

    pipeline_steps = [
        ("1", "El cliente rellena el formulario",
         "URL de marca, logo, brandbook, modelo de trofeo y texto del galardón",
         SA_LIMA),
        ("2", "El servidor recibe la petición",
         "Flask (Python) procesa los archivos subidos y construye el pedido estructurado",
         SA_BLACK),
        ("3", "Extracción de identidad de marca  —  Capa 0",
         "Se analiza la web, el logo y el PDF para extraer colores, tipografías y estilo visual",
         colors.HexColor("#1A6B3C")),
        ("4", "Análisis IA de la marca  —  Capa 1 (pasos 1 y 2)",
         "Claude Haiku extrae la paleta exacta; Claude Sonnet analiza tono y personalidad de marca",
         colors.HexColor("#5B4FCF")),
        ("5", "Generación de 6 conceptos de diseño  —  Capa 1 (paso 3)",
         "Claude Sonnet propone 6 composiciones distintas: colores, layout, estilo tipográfico",
         colors.HexColor("#5B4FCF")),
        ("6", "Generación del fondo artístico  —  Capa DALL·E",
         "DALL·E genera un fondo único por propuesta; 13 generadores PIL actúan como fallback",
         colors.HexColor("#E87C2A")),
        ("7", "Renderizado del diseño completo  —  Capa 2",
         "Playwright + PIL componen el diseño final: fondo + logo + texto con fuentes de marca",
         colors.HexColor("#C0392B")),
        ("8", "Composición sobre el trofeo  —  Capa 3",
         "El diseño se proyecta sobre la foto real del trofeo ajustándose a su forma exacta",
         colors.HexColor("#2C7BB6")),
        ("9", "Entrega al cliente",
         "Las 6 imágenes aparecen en la página de resultados y están disponibles para descarga",
         SA_LIMA),
    ]

    for i, (num, title, sub, col) in enumerate(pipeline_steps):
        story.append(PipelineStep(num, title, sub, col, CONTENT_W))
        if i < len(pipeline_steps) - 1:
            story.append(ArrowConnector(CONTENT_W))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 02. ARQUITECTURA TÉCNICA
    # ══════════════════════════════════════════════════════
    story.append(SectionHeader("02", "Arquitectura técnica", CONTENT_W))
    story.append(sp(2))
    story.append(P(
        "El sistema está organizado en capas independientes que se ejecutan secuencialmente. "
        "Cada capa tiene una única responsabilidad y recibe/entrega un objeto estandarizado, "
        "lo que permite mejorar o reemplazar cualquier capa sin afectar al resto.",
        s["body"]
    ))
    story.append(sp())

    # Tabla de capas — 3 columnas: Módulo + Archivo | Qué hace
    layers = [
        ("Entrada",     "Formulario web",       "form.html",
         "El cliente introduce datos y sube archivos. El formulario envía un POST multipart al servidor."),
        ("Servidor",    "Flask",                "test_server.py",
         "Recibe la petición HTTP, orquesta todas las capas en orden y devuelve el JSON de resultados al navegador."),
        ("Capa 0",      "Normalización",        "capa0_normalizer.py",
         "Convierte logo, PDF y URL en un brand_context unificado: paleta de colores, resumen del brandbook y screenshot de la web."),
        ("Capa 1",      "Inteligencia Artificial","capa1_ia.py",
         "Realiza tres llamadas Claude en cascada: Color Oracle → Brand Analysis → Design Concepts. Produce 6 especificaciones completas."),
        ("Capa DALL·E", "Fondos artísticos",    "capa_dalle.py",
         "Genera una imagen de fondo por propuesta vía DALL·E (OpenAI). Si no está disponible, usa uno de 13 generadores PIL creativos."),
        ("Capa 2",      "Renderizado gráfico",  "capa2_renderer.py",
         "Compone el diseño final: fondo + logo + texto con la tipografía real de marca. Usa Playwright (Chromium) para renderizar fuentes de Google Fonts con calidad de pantalla."),
        ("Capa 3",      "Compositor",           "capa3_compositor.py",
         "Proyecta el diseño sobre la fotografía real del trofeo físico, respetando la zona imprimible calibrada: rectangular o por máscara de forma irregular."),
        ("Salida",      "Resultados",           "results.html",
         "Muestra las 6 imágenes cargadas desde sessionStorage. El cliente puede descargar cada propuesta individualmente."),
    ]

    cw_layers = [CONTENT_W * 0.11, CONTENT_W * 0.19, CONTENT_W * 0.22, CONTENT_W * 0.48]
    hdr_layers = [
        P("<b>Módulo</b>",  s["cell_hdr"]),
        P("<b>Nombre</b>",  s["cell_hdr"]),
        P("<b>Archivo</b>", s["cell_hdr"]),
        P("<b>Qué hace</b>",s["cell_hdr"]),
    ]
    data_layers = [hdr_layers] + [
        [P(r[0], s["cell_bold"]), P(r[1], s["cell_bold"]),
         P(f"<font name='Courier' size='7.5'>{r[2]}</font>", s["cell"]),
         P(r[3], s["cell"])]
        for r in layers
    ]
    row_bgs = [("BACKGROUND", (0, i+1), (-1, i+1),
                SA_WHITE if i % 2 == 0 else SA_OFF_WHITE) for i in range(len(layers))]
    story.append(_tbl(data_layers, cw_layers, [
        ("BACKGROUND", (0, 0), (-1, 0), SA_BLACK),
    ] + row_bgs))
    story.append(sp(2))

    story.append(P("El objeto <b>brand_context</b> — resultado de Capa 0", s["subsection"]))
    story.append(P(
        "Capa 0 produce un diccionario Python llamado <b>brand_context</b> que fluye "
        "a través de todo el pipeline. Contiene toda la información de identidad extraída:",
        s["body"]
    ))
    story.append(sp())

    ctx_fields = [
        ("canonical_palette",  "Lista de colores HEX en orden de importancia: primario, secundario, acento"),
        ("logo_b64",           "Logo de la marca en base64 JPEG para enviarlo como imagen a Claude"),
        ("pdf_resumen",        "Resumen textual del brandbook extraído con PyMuPDF"),
        ("screenshot_b64",     "Captura de pantalla de la web corporativa"),
        ("brand_name",         "Nombre de la empresa detectado automáticamente"),
        ("fuente_upload",      "Nombre de la fuente corporativa subida por el cliente, si existe"),
    ]
    cw_ctx = [CONTENT_W * 0.30, CONTENT_W * 0.70]
    data_ctx = [
        [P(f"<font name='Courier' size='7.5'>{f[0]}</font>", s["cell_bold"]),
         P(f[1], s["cell"])]
        for f in ctx_fields
    ]
    story.append(_tbl(data_ctx, cw_ctx, [
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [SA_WHITE, SA_OFF_WHITE]),
    ]))
    story.append(sp(2))

    story.append(P("El objeto <b>concepto</b> — producido ×6 por Capa 1", s["subsection"]))
    story.append(P(
        "Capa 1 produce seis objetos <b>concepto</b>, uno por propuesta. "
        "Cada concepto es la especificación completa de un diseño:",
        s["body"]
    ))
    story.append(sp())

    concepto_fields = [
        ("proposal_id",           "Número de propuesta, del 1 al 6"),
        ("layout",                "Composición elegida: stacked, spread, staggered o billboard"),
        ("bg_tone",               "Tono del fondo: dark, mid o light"),
        ("dalle_prompt",          "Descripción textual del fondo para DALL·E"),
        ("award_text",            "Texto exacto del galardón: {headline, recipient, subtitle}"),
        ("_primary / _secondary / _accent", "Colores HEX de marca forzados desde canonical_palette"),
        ("text_style",            "Tamaños, alineaciones y colores de cada bloque de texto"),
        ("_run_id",               "Seed único por ejecución para garantizar variedad visual entre peticiones"),
    ]
    data_concepto = [
        [P(f"<font name='Courier' size='7.5'>{f[0]}</font>", s["cell_bold"]),
         P(f[1], s["cell"])]
        for f in concepto_fields
    ]
    story.append(_tbl(data_concepto, cw_ctx, [
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [SA_WHITE, SA_OFF_WHITE]),
    ]))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 03. TECNOLOGÍAS Y LIBRERÍAS
    # ══════════════════════════════════════════════════════
    story.append(SectionHeader("03", "Tecnologías y librerías", CONTENT_W))
    story.append(sp(2))

    story.append(P("Lenguaje y framework web", s["subsection"]))
    story.append(tech_table([
        ["Python 3.11+",
         "Lenguaje principal de todo el backend. Tipado estático opcional mediante type hints."],
        ["Flask 3.x",
         "Servidor web ligero. Gestiona rutas HTTP, recepción de archivos subidos y respuestas JSON."],
        ["HTML5 / CSS3",
         "Interfaz de usuario: formulario de entrada y página de resultados. Sin frameworks JS externos."],
        ["JavaScript (ES2022)",
         "Lógica de cliente: envío del formulario, almacenamiento en sessionStorage y descarga de imágenes."],
    ], s))
    story.append(sp(2))

    story.append(P("Inteligencia Artificial", s["subsection"]))
    story.append(tech_table([
        ["Anthropic Claude API",
         "Tres llamadas por petición: extracción de paleta de color, análisis de marca y generación de conceptos de diseño."],
        ["claude-haiku-4-5",
         "Modelo rápido y económico para el Color Oracle: extracción de paleta de color del logo y la web."],
        ["claude-sonnet-4-6",
         "Modelo principal para Brand Analysis y Design Concepts. Mejor balance entre calidad de razonamiento y velocidad."],
        ["OpenAI gpt-image-1 (DALL·E)",
         "Generación de fondos artísticos únicos por propuesta. Una llamada independiente por cada fondo que lo requiere."],
    ], s))
    story.append(sp(2))

    story.append(P("Procesamiento de imagen", s["subsection"]))
    story.append(tech_table([
        ["Pillow (PIL) 10+",
         "Librería principal de composición de imágenes: capas, gradientes, recorte, mezcla y aplicación de máscaras."],
        ["NumPy 1.24+",
         "Operaciones matriciales sobre píxeles: análisis de luminancia para detectar zonas de alta legibilidad tipográfica."],
        ["Playwright 1.40+",
         "Navegador Chromium en modo headless. Renderiza el diseño como HTML para obtener fuentes de Google Fonts con calidad tipográfica real."],
        ["PyMuPDF (fitz)",
         "Extracción de texto y metadatos de brandbooks y manuales de marca en formato PDF."],
    ], s))
    story.append(sp(2))

    story.append(P("Extracción de marca y red", s["subsection"]))
    story.append(tech_table([
        ["Firecrawl API",
         "Servicio externo que analiza el HTML de la web corporativa y extrae colores, tipografías y densidad visual de forma estructurada."],
        ["Requests",
         "Peticiones HTTP para descargar logos desde URL, acceder a webs corporativas y comunicarse con APIs externas."],
        ["BeautifulSoup 4",
         "Parsing de HTML como fallback cuando Firecrawl no está configurado. Extrae colores CSS inline de la web."],
    ], s))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 04. MODELOS DE IA
    # ══════════════════════════════════════════════════════
    story.append(SectionHeader("04", "Modelos de IA utilizados", CONTENT_W))
    story.append(sp(2))
    story.append(P(
        "Por cada petición el sistema realiza exactamente tres llamadas a la API de Anthropic "
        "(Claude) más llamadas a OpenAI por cada fondo generado con DALL·E. "
        "Cada llamada tiene una función muy específica y usa parámetros de temperatura distintos.",
        s["body"]
    ))
    story.append(sp(2))

    ia_blocks = [
        {
            "num":    "1ª llamada",
            "model":  "Claude Haiku  —  Color Oracle",
            "temp":   "Temperatura 0.0  (determinista)",
            "role":   "Extrae la paleta de colores exacta del logo y la web corporativa.",
            "why":    "Se usa temperatura 0 porque la paleta no debe ser creativa: debe ser siempre "
                      "la misma para la misma marca. Haiku es suficiente para esta tarea visual y es "
                      "diez veces más económico que Sonnet.",
            "output": "canonical_palette — lista de 2 a 3 colores HEX ordenados por peso visual.",
        },
        {
            "num":    "2ª llamada",
            "model":  "Claude Sonnet  —  Brand Analysis",
            "temp":   "Temperatura 0.3  (casi determinista)",
            "role":   "Analiza la personalidad, el tono y las restricciones de la marca.",
            "why":    "Temperatura baja para análisis consistente. Sonnet comprende mejor conceptos "
                      "abstractos como 'tono de marca' o 'densidad visual' que Haiku.",
            "output": "brand_name, brand_tone, visual_density, typography_style, design_restrictions.",
        },
        {
            "num":    "3ª llamada",
            "model":  "Claude Sonnet  —  Design Concepts",
            "temp":   "Temperatura 1.0  (máxima creatividad)",
            "role":   "Genera los 6 conceptos de diseño con su especificación completa.",
            "why":    "Alta temperatura para garantizar variedad entre las 6 propuestas. "
                      "Con temperatura baja, los 6 conceptos serían casi idénticos entre sí.",
            "output": "Array de 6 objetos concepto con layout, colores, tipografía, dalle_prompt y award_text.",
        },
        {
            "num":    "Llamadas DALL·E",
            "model":  "OpenAI gpt-image-1  —  Fondos artísticos",
            "temp":   "N/A (modelo de imagen)",
            "role":   "Genera la imagen de fondo única para cada propuesta que lo requiere.",
            "why":    "DALL·E produce fondos fotorrealistas y artísticos que los generadores PIL no "
                      "pueden igualar en calidad. Si no está disponible, 13 generadores PIL actúan "
                      "como fallback automático sin interrumpir el proceso.",
            "output": "Imagen PNG de alta resolución del fondo artístico generado.",
        },
    ]

    cw_ia = [CONTENT_W * 0.22, CONTENT_W * 0.78]

    for block in ia_blocks:
        rows_ia = [
            [P(f"<b>{block['num']}</b>",  s["cell_hdr"]),
             P(f"<b>{block['model']}</b>", s["cell_hdr"])],
            [P(block["temp"], s["cell"]),
             P(block["role"], s["cell"])],
            [P("<b>Por qué:</b>",  s["cell_bold"]),
             P(block["why"],       s["cell"])],
            [P("<b>Produce:</b>",  s["cell_bold"]),
             P(block["output"],    s["cell"])],
        ]
        t = _tbl(rows_ia, cw_ia, [
            ("BACKGROUND", (0, 0), (-1, 0), SA_BLACK),
            ("BACKGROUND", (0, 1), (-1, -1), SA_OFF_WHITE),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
        story.append(KeepTogether([t, sp()]))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 05. ESTRUCTURA DE ARCHIVOS
    # ══════════════════════════════════════════════════════
    story.append(SectionHeader("05", "Estructura de archivos", CONTENT_W))
    story.append(sp(2))
    story.append(P(
        "El proyecto sigue una estructura donde cada carpeta tiene una "
        "responsabilidad única y bien definida:",
        s["body"]
    ))
    story.append(sp())

    tree = [
        ("sustain-awards/",          True,  "Raíz del proyecto"),
        ("  test_server.py",         False, "Servidor Flask — punto de entrada del sistema"),
        ("  calibrar_trofeo.py",     False, "Herramienta para calibrar zonas imprimibles de nuevos modelos de trofeo"),
        ("  requirements.txt",       False, "Dependencias Python del proyecto"),
        ("  templates/",             True,  "Interfaz de usuario web"),
        ("    form.html",            False, "Formulario de entrada del cliente"),
        ("    results.html",         False, "Página de resultados con los 6 diseños generados"),
        ("  scripts/",               True,  "Módulos del pipeline de generación"),
        ("    config.py",            False, "Modelos, temperaturas y feature flags (DALL·E on/off, Firecrawl, etc.)"),
        ("    capa0_normalizer.py",  False, "Extracción de identidad de marca desde logo, web y PDF"),
        ("    capa1_ia.py",          False, "Orquestador de las tres llamadas a Claude"),
        ("    capa2_renderer.py",    False, "Compositor del diseño final con Playwright y PIL"),
        ("    capa3_compositor.py",  False, "Proyección del diseño sobre la fotografía del trofeo"),
        ("    capa_dalle.py",        False, "Generación de fondos artísticos con DALL·E y 13 fallbacks PIL"),
        ("    font_manager.py",      False, "Catálogo y carga de fuentes: Google Fonts y fuentes locales"),
        ("  data/",                  True,  "Datos del catálogo de productos"),
        ("    trophy_catalog.json",  False, "Especificación de cada modelo de trofeo: geometría, zonas y restricciones"),
        ("  assets/",                True,  "Recursos estáticos del sistema"),
        ("    trophies/",            True,  "Fotografías de los trofeos y sus máscaras de forma irregular"),
        ("    fonts/",               True,  "Fuentes tipográficas locales (fallback cuando no hay conexión a Internet)"),
        ("    referencias/",         True,  "Imágenes de referencia para el few-shot learning de la IA"),
        ("  arquitectura/",          True,  "Documentación técnica del sistema (este documento)"),
        ("  outputs/",               True,  "Imágenes generadas en tiempo de ejecución (se crean automáticamente)"),
    ]

    cw_tree = [CONTENT_W * 0.43, CONTENT_W * 0.57]
    for path, is_dir, desc in tree:
        indent = len(path) - len(path.lstrip(" "))
        fn    = "Helvetica-Bold" if is_dir else "Courier"
        fsz   = 9 if is_dir else 7.5
        fc    = "#000000" if is_dir else "#575452"
        bg    = SA_OFF_WHITE if is_dir else SA_WHITE
        row   = [
            [P(f'<font name="{fn}" size="{fsz}" color="{fc}">{path.rstrip()}</font>', s["cell"]),
             P(desc, s["cell"])]
        ]
        t = Table(row, colWidths=cw_tree)
        t.setStyle(TableStyle([
            ("LEFTPADDING",   (0, 0), (0, 0), 5 + indent * 2),
            ("LEFTPADDING",   (1, 0), (1, 0), 7),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("BACKGROUND",    (0, 0), (-1, -1), bg),
            ("LINEBELOW",     (0, 0), (-1, -1), 0.2, SA_GRAY_LIGHT),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(t)

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 06. FLUJO DE DATOS DETALLADO
    # ══════════════════════════════════════════════════════
    story.append(SectionHeader("06", "Flujo de datos detallado", CONTENT_W))
    story.append(sp(2))
    story.append(P(
        "Qué información exacta entra y sale de cada módulo del sistema, "
        "para entender con precisión dónde se procesa cada dato.",
        s["body"]
    ))
    story.append(sp(2))

    flow_stages = [
        {
            "from": "Cliente → Servidor Flask",
            "data": "Formulario multipart/form-data",
            "fields": [
                "url_corporativa — URL de la web de la marca",
                "logo — archivo PNG/JPG/SVG del logotipo",
                "brandbook — manual de marca en PDF",
                "font — fuente corporativa TTF/OTF",
                "modelo_trofeo — 'totem_basic' o 'copetin'",
                "headline / recipient / subtitle — texto exacto del galardón",
                "contacto_nombre / email / telefono / cantidad / fecha",
            ]
        },
        {
            "from": "Flask → Capa 0",
            "data": "pedido (dict) + logo_bytes + pdf_bytes",
            "fields": [
                "id_pedido — identificador único del job (ej. FORM-A1B2C3D4)",
                "modelo_trofeo — referencia al catálogo de trofeos",
                "evento: {nombre, fecha, lugar}",
                "award: {headline, recipient, subtitle, fecha}",
                "assets: {url_corporativa, logo_path}",
                "logo_bytes — contenido binario del archivo de logo subido",
                "pdf_bytes — contenido binario del brandbook subido",
            ]
        },
        {
            "from": "Capa 0 → Capa 1",
            "data": "brand_context (dict)",
            "fields": [
                "canonical_palette — lista de HEX ordenada por peso visual",
                "logo_b64 — logo en base64 para enviarlo como imagen a Claude",
                "pdf_resumen — texto extraído del brandbook con PyMuPDF",
                "screenshot_b64 — captura de pantalla de la web corporativa",
                "logo_path — ruta al archivo de logo en disco",
                "fuente_upload — nombre de la fuente corporativa subida, si existe",
            ]
        },
        {
            "from": "Capa 1 → Capa 2 + DALL·E",
            "data": "lista de 6 objetos concepto",
            "fields": [
                "proposal_id — número de propuesta, del 1 al 6",
                "layout — stacked | spread | staggered | billboard",
                "bg_tone — dark | mid | light",
                "dalle_prompt — descripción textual del fondo para DALL·E",
                "award_text: {headline, recipient, subtitle}",
                "_primary / _secondary / _accent — colores HEX de marca",
                "text_style — tamaños, colores y alineaciones tipográficas",
                "_run_id — seed único para garantizar variedad entre ejecuciones",
            ]
        },
        {
            "from": "DALL·E → Capa 2",
            "data": "imagen de fondo (PIL.Image)",
            "fields": [
                "Image RGBA de alta resolución — fondo artístico generado por DALL·E",
                "O: Image RGBA redimensionada — fondo generado por generador PIL (fallback automático)",
            ]
        },
        {
            "from": "Capa 2 → Capa 3",
            "data": "imagen de diseño completa (PIL.Image RGBA)",
            "fields": [
                "Imagen del diseño final compuesta: fondo + logo + texto tipográfico",
                "Dimensiones exactas de la zona imprimible del trofeo (ej. 247×793 px para Totem)",
            ]
        },
        {
            "from": "Capa 3 → Flask",
            "data": "mockup final (PIL.Image RGB)",
            "fields": [
                "Fotografía real del trofeo con el diseño proyectado sobre él",
                "Guardado en outputs/mockups/ como JPEG con calidad 95",
                "Devuelto como cadena base64 dentro del JSON de respuesta",
            ]
        },
        {
            "from": "Flask → Cliente (JSON)",
            "data": "Respuesta JSON de la API",
            "fields": [
                "job_id — identificador único del job procesado",
                "modelo_nombre — nombre del modelo de trofeo elegido",
                "award_headline — título del galardón usado en los diseños",
                "analisis_marca — descripción, tono, paleta y estilo detectados",
                "mockups — 6 objetos con: proposal_id, nombre, concepto, palette e imagen_b64",
            ]
        },
    ]

    cw_flow_hdr = [CONTENT_W * 0.37, CONTENT_W * 0.63]
    cw_flow_fld = [0.2 * cm, CONTENT_W - 0.2 * cm]

    for stage in flow_stages:
        hdr_row = [[
            P(f"<b>{stage['from']}</b>",  s["cell_hdr"]),
            P(f"<i>{stage['data']}</i>",  s["cell_hdr"]),
        ]]
        t_hdr = Table(hdr_row, colWidths=cw_flow_hdr)
        t_hdr.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), SA_BLACK),
            ("TOPPADDING",    (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ]))

        field_rows = [["", ""]] + [
            ["", P(f"<font name='Courier' size='7.5'>{f}</font>", s["cell"])]
            for f in stage["fields"]
        ]
        t_fld = Table(field_rows, colWidths=cw_flow_fld)
        t_fld.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), SA_LIMA),
            ("BACKGROUND",    (1, 0), (1, -1), SA_OFF_WHITE),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (1, 0), (1, -1), 8),
            ("RIGHTPADDING",  (1, 0), (1, -1), 8),
            ("LEFTPADDING",   (0, 0), (0, -1), 0),
            ("RIGHTPADDING",  (0, 0), (0, -1), 0),
            ("LINEBELOW",     (1, 1), (1, -1), 0.2, SA_GRAY_LIGHT),
        ]))
        story.append(KeepTogether([t_hdr, t_fld, sp()]))

    story.append(PageBreak())

    # ══════════════════════════════════════════════════════
    # 07. RESTRICCIONES Y CALIDAD
    # ══════════════════════════════════════════════════════
    story.append(SectionHeader("07", "Restricciones y calidad", CONTENT_W))
    story.append(sp(2))

    story.append(P("Restricciones de impresión UV", s["subsection"]))
    story.append(P(
        "El sistema conoce las restricciones técnicas de la impresión UV en trofeos y las "
        "aplica automáticamente durante la generación de diseños:",
        s["body"]
    ))
    story.append(sp())

    uv_rules = [
        ("Fondos sólidos oscuros",
         "Prohibidos. La tinta UV muestra variación de textura en superficies muy oscuras. "
         "El sistema aplica fade en los bordes de fondos oscuros y limita a un máximo de "
         "3 de las 6 propuestas con tono oscuro."),
        ("Tintas metálicas",
         "No existen como tal en impresión UV directa. El sistema simula el efecto dorado "
         "y plateado mediante gradientes cuidadosamente calibrados."),
        ("Margen mínimo",
         "Cada trofeo tiene un margen horizontal mínimo calibrado individualmente: 8% para "
         "Totem Basic y 20% para Copetin. El renderer lo aplica automáticamente al "
         "calcular el área disponible para el texto."),
        ("Zona imprimible exacta",
         "Las coordenadas de la zona imprimible de cada trofeo están calibradas manualmente "
         "en trophy_catalog.json. El compositor proyecta el diseño exactamente en esas "
         "coordenadas sobre la fotografía real."),
        ("Legibilidad de texto",
         "El sistema analiza la luminancia del fondo con NumPy y ajusta automáticamente la "
         "posición vertical del texto a la zona de mayor contraste disponible en la imagen."),
        ("Contraste mínimo WCAG",
         "El renderer verifica el ratio de contraste entre texto y fondo. Si no supera el "
         "mínimo recomendado (3:1 para texto grande), cambia el color del texto "
         "automáticamente para garantizar legibilidad."),
    ]

    cw_uv = [CONTENT_W * 0.27, CONTENT_W * 0.73]
    data_uv = [
        [P(f"<b>{r[0]}</b>", s["cell_bold"]), P(r[1], s["cell"])]
        for r in uv_rules
    ]
    row_bgs_uv = [("BACKGROUND", (0, i), (-1, i),
                   SA_OFF_WHITE if i % 2 == 0 else SA_WHITE) for i in range(len(uv_rules))]
    story.append(_tbl(data_uv, cw_uv, [
        ("BACKGROUND", (0, 0), (0, -1), SA_OFF_WHITE),
    ] + row_bgs_uv))
    story.append(sp(2))

    story.append(P("Garantías del sistema", s["subsection"]))
    guarantees = [
        "La canonical_palette de la marca se inyecta como 'verdad absoluta' en todos los prompts. "
        "La IA no puede cambiar los colores de marca por criterio creativo propio.",
        "Si el cliente proporciona texto exacto (headline, recipient, subtitle), el sistema lo fuerza "
        "en todos los conceptos tras la generación, sobreescribiendo cualquier variación de la IA.",
        "Los layouts con máscara irregular (Copetin) calculan el ancho real disponible fila a fila "
        "para garantizar que el texto nunca se salga de la zona imprimible.",
        "Si DALL·E falla o no está configurado, el sistema continúa con generadores PIL. "
        "El cliente recibe sus 6 diseños siempre, independientemente del estado de las APIs externas.",
        "Cada ejecución tiene un run_id único que garantiza variedad visual entre generaciones "
        "de la misma marca: los 6 diseños nunca son iguales entre distintas peticiones.",
    ]
    for g in guarantees:
        story.append(bullet(g, s))
    story.append(sp(2))

    for item in info_box(
        "Versión y estado del sistema",
        [
            "Documentación correspondiente al sistema en producción a mayo de 2026. "
            "Pipeline activo con los modelos claude-sonnet-4-6 (Brand Analysis y Design Concepts) "
            "y claude-haiku-4-5 (Color Oracle). DALL·E usa el modelo gpt-image-1 de OpenAI.",
            "Stack verificado: Python 3.12 · Flask 3.x · Pillow 10+ · NumPy 1.24+ · "
            "Playwright 1.40+ · PyMuPDF · Anthropic SDK · OpenAI SDK · Firecrawl API.",
        ],
        s
    ):
        story.append(item)

    # ── Renderizado final ──────────────────────────────────────────────────────
    def on_page(canvas, doc):
        canvas.saveState()
        pn = doc.page
        if pn == 1:
            canvas.setFillColor(SA_BLACK)
            canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
            canvas.setFillColor(SA_LIMA)
            canvas.rect(0, 0, PAGE_W, 1.1 * cm, fill=1, stroke=0)
            canvas.setFillColor(SA_LIMA)
            canvas.rect(0, 1.1 * cm, 0.55 * cm, PAGE_H - 1.1 * cm, fill=1, stroke=0)
        else:
            canvas.setFillColor(SA_GRAY_MID)
            canvas.setFont("Helvetica", 7.5)
            canvas.drawRightString(PAGE_W - MARGIN, 1.1 * cm, str(pn - 1))
            canvas.setStrokeColor(SA_GRAY_LIGHT)
            canvas.setLineWidth(0.4)
            canvas.line(MARGIN, 1.35 * cm, PAGE_W - MARGIN, 1.35 * cm)
            canvas.setFillColor(SA_GRAY_MID)
            canvas.setFont("Helvetica-Bold", 6.5)
            canvas.drawString(MARGIN, 1.1 * cm,
                              "SUSTAIN AWARDS  ·  Arquitectura del sistema  ·  Confidencial")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=2.1 * cm, bottomMargin=2.1 * cm,
        title="Sustain Awards — Arquitectura del sistema",
        author="Sustain Awards",
        subject="Arquitectura técnica y ejecutiva",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF generado: {OUTPUT}")
    return OUTPUT


if __name__ == "__main__":
    build_document()
