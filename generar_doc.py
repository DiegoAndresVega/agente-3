"""
Genera el PDF de documentación del Agente de Diseño Gráfico — Sustain Awards.
Uso: python generar_doc.py
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib import colors


# ─── Paleta ───────────────────────────────────────────────────────────────────
NEGRO       = HexColor("#1A1A1A")
GRIS_TEXTO  = HexColor("#3D3D3D")
GRIS_CLARO  = HexColor("#F4F4F4")
GRIS_LINEA  = HexColor("#DDDDDD")
ACENTO      = HexColor("#2E6BE6")   # azul corporativo suave
ACENTO_SOFT = HexColor("#E8EFFD")

W, H = A4
MARGEN = 2.2 * cm


# ─── Estilos ──────────────────────────────────────────────────────────────────
def estilos():
    base = getSampleStyleSheet()

    titulo = ParagraphStyle(
        "Titulo",
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=28,
        textColor=NEGRO,
        spaceAfter=6,
    )
    subtitulo = ParagraphStyle(
        "Subtitulo",
        fontName="Helvetica",
        fontSize=11,
        leading=16,
        textColor=HexColor("#555555"),
        spaceAfter=14,
    )
    h2 = ParagraphStyle(
        "H2",
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=18,
        textColor=NEGRO,
        spaceBefore=18,
        spaceAfter=4,
    )
    h3 = ParagraphStyle(
        "H3",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=14,
        textColor=ACENTO,
        spaceBefore=10,
        spaceAfter=2,
    )
    cuerpo = ParagraphStyle(
        "Cuerpo",
        fontName="Helvetica",
        fontSize=9.5,
        leading=15,
        textColor=GRIS_TEXTO,
        spaceAfter=5,
    )
    bullet = ParagraphStyle(
        "Bullet",
        fontName="Helvetica",
        fontSize=9.5,
        leading=15,
        textColor=GRIS_TEXTO,
        leftIndent=16,
        spaceAfter=3,
    )
    bullet2 = ParagraphStyle(
        "Bullet2",
        fontName="Helvetica",
        fontSize=9,
        leading=14,
        textColor=HexColor("#555555"),
        leftIndent=32,
        spaceAfter=2,
    )
    code = ParagraphStyle(
        "Code",
        fontName="Courier",
        fontSize=8.5,
        leading=13,
        textColor=HexColor("#2D2D2D"),
        backColor=GRIS_CLARO,
        leftIndent=12,
        rightIndent=12,
        spaceAfter=4,
        spaceBefore=4,
    )
    label = ParagraphStyle(
        "Label",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=white,
    )
    return {
        "titulo": titulo, "subtitulo": subtitulo,
        "h2": h2, "h3": h3,
        "cuerpo": cuerpo, "bullet": bullet, "bullet2": bullet2,
        "code": code, "label": label,
    }


def separador():
    return HRFlowable(width="100%", thickness=0.6, color=GRIS_LINEA,
                      spaceAfter=6, spaceBefore=2)


def badge(texto, color_fondo, color_texto=white):
    """Celda badge de color para tablas."""
    return Paragraph(
        f'<font color="white"><b>{texto}</b></font>',
        ParagraphStyle("badge", fontName="Helvetica-Bold", fontSize=8,
                       leading=10, textColor=color_texto)
    )


# ─── Contenido ────────────────────────────────────────────────────────────────
def construir_doc():
    E = estilos()

    elementos = []

    # ── CABECERA ──────────────────────────────────────────────────────────────
    elementos.append(Paragraph("AGENTE DE DISEÑO GRÁFICO", E["titulo"]))
    elementos.append(Paragraph(
        "Pipeline de propuestas automáticas para trofeos de colección · Sustain Awards",
        E["subtitulo"]
    ))
    elementos.append(separador())
    elementos.append(Spacer(1, 8))

    # ── RESUMEN ───────────────────────────────────────────────────────────────
    elementos.append(Paragraph("Resumen", E["h2"]))
    elementos.append(Paragraph(
        "Sistema de inteligencia artificial de 4 capas que genera automáticamente "
        "6 propuestas gráficas distintas para cualquier trofeo del catálogo de Sustain Awards. "
        "A partir de los assets de marca del cliente (logo, brandbook, URL corporativa) y el "
        "texto del galardón, el agente extrae el vocabulario visual de la marca, diseña 6 "
        "conceptos creativos diferenciados, renderiza las imágenes con tipografía real y las "
        "compone sobre la fotografía del trofeo, adaptándose a la geometría de cada modelo "
        "(rectangular, placa o superficie irregular con máscara).",
        E["cuerpo"]
    ))
    elementos.append(Paragraph(
        "La interfaz web permite subir los assets, elegir el modelo de trofeo y recibir "
        "los 6 mockups en segundos. El resultado puede enviarse por email al cliente como "
        "HTML o exportarse como archivos JPG de alta resolución.",
        E["cuerpo"]
    ))
    elementos.append(Spacer(1, 4))

    # ── INPUT ─────────────────────────────────────────────────────────────────
    elementos.append(separador())
    elementos.append(Paragraph("Input", E["h2"]))

    inputs = [
        ("Modelo de trofeo",
         "Selección del catálogo: Totem Basic (rectangular), Placa A5 (horizontal), "
         "Copetin (superficie irregular con máscara de polígono calibrada)."),
        ("Assets de marca",
         "Logo (PNG/SVG/JPG), Brandbook/Style Guide (PDF), y/o URL corporativa. "
         "El sistema acepta cualquier combinación — puede operar solo con el logo."),
        ("Texto del galardón",
         "Nombre del premiado (recipient), nombre del premio (headline), "
         "organización (subtitle) y fecha opcional."),
        ("Ejemplos aprobados (opcional)",
         "Imágenes de diseños previos validados por el usuario, usadas como "
         "few-shot learning para afinación del estilo creativo del agente."),
    ]
    for titulo_i, desc_i in inputs:
        elementos.append(Paragraph(f"— <b>{titulo_i}</b>", E["bullet"]))
        elementos.append(Paragraph(desc_i, E["bullet2"]))

    elementos.append(Spacer(1, 4))

    # ── OUTPUT ────────────────────────────────────────────────────────────────
    elementos.append(separador())
    elementos.append(Paragraph("Output", E["h2"]))
    outputs = [
        "6 propuestas gráficas con conceptos visuales radicalmente distintos.",
        "Por cada propuesta: mockup JPG del diseño compuesto sobre la fotografía real del trofeo.",
        "JSON de especificación de diseño: paleta, tipografía, layout, prompts DALL·E.",
        "Análisis de marca extraído: tono, colores HEX, fuente corporativa, densidad visual.",
    ]
    for o in outputs:
        elementos.append(Paragraph(f"— {o}", E["bullet"]))
    elementos.append(Spacer(1, 4))

    # ── ARQUITECTURA: 4 CAPAS ─────────────────────────────────────────────────
    elementos.append(separador())
    elementos.append(Paragraph("Arquitectura — Pipeline de 4 Capas", E["h2"]))

    capas = [
        ("CAPA 0", "Normalización", ACENTO,
         "capa0_normalizer.py",
         [
             "Recibe el pedido (assets + texto del galardón).",
             "Convierte logo a base64 JPEG para visión de Claude.",
             "Extrae colores HEX, Pantone y fuentes de PDFs mediante PyMuPDF.",
             "Renderiza páginas del brandbook como imágenes JPEG (visión por página).",
             "Fetch de URL corporativa: extrae colores CSS, descripción de estilo y captura de pantalla.",
             "Output: brand_context dict con todos los assets normalizados.",
         ]),
        ("CAPA 1", "Diseñador IA", HexColor("#5B4FCF"),
         "capa1_ia.py  ·  2 llamadas a Claude Sonnet 4.6",
         [
             "Llamada A — Brand Analysis: analiza logo + brandbook + web y extrae vocabulario visual "
             "estructurado en JSON (colores primario/secundario/acento, fuente corporativa, tono de marca).",
             "Llamada B — Design Concepts: genera 6 conceptos creativos diferenciados. Cada uno define "
             "layout, tipografía, paleta, fondo DALL·E y jerarquía de texto. Incluye semilla "
             "aleatoria por sesión para garantizar variedad entre ejecuciones.",
             "Few-shot learning: si existen ejemplos aprobados por el usuario, se incluyen como "
             "referencias visuales para alinear el estilo creativo.",
             "Validación automática: layouts permitidos por trofeo, contrastes mínimos, "
             "restricciones de impresión UV (sin metálicos reales, sin sólidos negros).",
             "Output: lista de 6 design_spec JSON + brand_analysis.",
         ]),
        ("CAPA 2", "Renderer", HexColor("#1A7A4A"),
         "capa2_renderer.py  ·  Playwright + PIL + fuentes Google",
         [
             "Genera el fondo artístico: DALL·E (gpt-image-1) o Flux vía Replicate según config.",
             "Aplica overlay de coherencia cromática (velo sutil del color de marca).",
             "Coloca el logo con tratamiento adaptado al fondo (blanco/negro/color/watermark/banda).",
             "Renderiza tipografía con Playwright/Chromium usando fuentes Google Fonts reales.",
             "Para trofeos con superficie irregular (máscara): calcula perfil de ancho por fila "
             "y posiciona cada elemento de texto en la zona más ancha disponible de esa franja "
             "vertical, evitando la zona más estrecha del trofeo.",
             "Corrección de contraste automática por píxeles reales del fondo generado.",
             "Output: imagen RGBA del diseño en las dimensiones del área imprimible.",
         ]),
        ("CAPA 3", "Compositor", HexColor("#B5451B"),
         "capa3_compositor.py",
         [
             "Escala el diseño al bounding box del área imprimible calibrada.",
             "Para trofeos rectangulares: paste directo en la posición calibrada.",
             "Para trofeos con máscara (Copetin): recorte por polígono irregular usando "
             "la máscara PNG generada con calibrar_trofeo.py — anti-aliasing con blur gaussiano.",
             "Output: mockup JPG del trofeo real con el diseño integrado.",
         ]),
    ]

    for cod, nombre, color, script, puntos in capas:
        # Fila de encabezado de capa
        data_h = [[
            Paragraph(f'<b>{cod}</b>', ParagraphStyle("cb", fontName="Helvetica-Bold",
                      fontSize=9, leading=11, textColor=white)),
            Paragraph(f'<b>{nombre}</b>', ParagraphStyle("cn", fontName="Helvetica-Bold",
                      fontSize=9, leading=11, textColor=white)),
            Paragraph(script, ParagraphStyle("cs", fontName="Courier",
                      fontSize=8, leading=11, textColor=HexColor("#DDEEFF"))),
        ]]
        t_h = Table(data_h, colWidths=[2.2*cm, 3.2*cm, 10*cm])
        t_h.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), color),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING", (0,0), (0,-1), 8),
            ("LEFTPADDING", (1,0), (-1,-1), 6),
            ("ROUNDEDCORNERS", [3, 3, 0, 0]),
        ]))
        elementos.append(t_h)

        # Puntos de la capa
        puntos_txt = "<br/>".join(f"· {p}" for p in puntos)
        data_b = [[Paragraph(puntos_txt,
                              ParagraphStyle("pb", fontName="Helvetica", fontSize=8.5,
                                             leading=14, textColor=GRIS_TEXTO))]]
        t_b = Table(data_b, colWidths=[15.4*cm])
        t_b.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), GRIS_CLARO),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING", (0,0), (-1,-1), 10),
            ("RIGHTPADDING", (0,0), (-1,-1), 10),
            ("LINEBELOW", (0,0), (-1,-1), 0.5, GRIS_LINEA),
        ]))
        elementos.append(t_b)
        elementos.append(Spacer(1, 10))

    # ── MECÁNICAS Y MODELOS ───────────────────────────────────────────────────
    elementos.append(separador())
    elementos.append(Paragraph("Mecánicas y Modelos de IA", E["h2"]))

    mecanicas = [
        ("Análisis de marca — Brand Analysis (Claude Sonnet 4.6, T=0.3)",
         "Visión multimodal sobre logo + páginas del brandbook + screenshot de la web. "
         "Extracción JSON estructurada: paleta completa (primary, secondary, accent, extended), "
         "tipografía (nombre exacto, equivalente Google Fonts, categoría visual), tono y densidad. "
         "Prioridad de fuentes: brandbook PDF > logo > web corporativa."),
        ("Generación de conceptos — Design Concepts (Claude Sonnet 4.6, T=1.0)",
         "Produce 6 conceptos con roles creativos distintos: P1 Primera Impresión, P2 Claridad "
         "Editorial, P3 Tensión Gráfica, P4 Billboard, P5 Minimalismo Premium, P6 Identidad Pura. "
         "Cada concepto incluye: layout tipográfico, tratamiento de logo, fondo DALL·E en inglés, "
         "overlay de color, decoración funcional (laurel_arc, diagonal_corners, rule_grid, etc.). "
         "Semilla aleatoria por sesión garantiza variedad entre ejecuciones del mismo pedido."),
        ("Generación de fondos — DALL·E / gpt-image-1 (OpenAI) o Flux Schnell (Replicate)",
         "Fondo artístico sin texto ni logos, en orientación retrato. Cada propuesta usa "
         "una técnica visualmente distinta: cinematográfico, geométrico audaz, acuarela, "
         "halftone, etc. Para P2/P5 (fondo blanco): no se genera imagen — el metal del "
         "trofeo actúa como fondo premium. Restricciones UV: sin metálicos reales, sin "
         "sólidos negros planos, sin fluorescentes."),
        ("Renderizado tipográfico — Playwright + Google Fonts",
         "Chromium headless renderiza el HTML/CSS con fuentes Google Fonts descargadas "
         "localmente o via @font-face. PIL pre-calcula los tamaños en píxeles para cada "
         "elemento usando las fuentes exactas (evita overflow en Chromium). "
         "Fallback automático a PIL puro si Playwright no está disponible."),
        ("Posicionamiento adaptativo para superficies irregulares",
         "Para trofeos con máscara (Copetin): se genera un perfil de ancho fila-a-fila "
         "desde el PNG de máscara. La función _mejor_zona_texto() encuentra la sub-zona "
         "más ancha en cada tercio vertical (head=0–28%, recipient=28–57%, sub=72–95%) "
         "usando una ventana deslizante de 18px. Cada elemento de texto se posiciona y "
         "dimensiona independientemente según el ancho real disponible en su franja, "
         "evitando la zona estrecha del trofeo. Funciona para cualquier forma con máscara."),
        ("Few-shot learning acumulativo",
         "Diseños aprobados por el usuario se almacenan en assets/aprendizaje/ como "
         "pares imagen+JSON. En ejecuciones posteriores se inyectan como ejemplos "
         "multimodales en la llamada B de Claude, guiando el estilo creativo sin "
         "sobreescribir las instrucciones del sistema. Límite configurable (MAX_FEW_SHOT=15)."),
    ]

    for titulo_m, desc_m in mecanicas:
        elementos.append(Paragraph(f"<b>{titulo_m}</b>", E["h3"]))
        elementos.append(Paragraph(desc_m, E["cuerpo"]))

    # ── TROFEOS SOPORTADOS ────────────────────────────────────────────────────
    elementos.append(separador())
    elementos.append(Paragraph("Catálogo de Trofeos Soportados", E["h2"]))

    trofeos_data = [
        ["Modelo", "Forma", "Área imprimible", "Layouts permitidos", "Notas"],
        ["Totem Basic", "Rectangular", "247 × 793 px\n(100 × 150 mm)", "Todos (6)", "Calibrado con Paint\nsobre foto 1200×1500px"],
        ["Placa A5", "Rectangular\nhorizontal", "380 × 280 px\n(148 × 105 mm)", "stacked, spread,\nbillboard", "Calibrado — pendiente\nfoto real"],
        ["Copetin", "Máscara\nirregular", "120 × 571 px\n(forma variable)", "stacked, spread", "Polígono 32 puntos\nPerfil fila-a-fila"],
    ]

    col_w = [2.8*cm, 2.5*cm, 3.2*cm, 3.5*cm, 3.4*cm]
    t_tr = Table(trofeos_data, colWidths=col_w, repeatRows=1)
    t_tr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), NEGRO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, GRIS_CLARO]),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, GRIS_LINEA),
    ]))
    elementos.append(t_tr)
    elementos.append(Spacer(1, 10))

    # ── CONFIGURACIÓN Y COSTES ────────────────────────────────────────────────
    elementos.append(separador())
    elementos.append(Paragraph("Configuración y Costes estimados", E["h2"]))

    config_data = [
        ["Variable de entorno", "Valor por defecto", "Descripción"],
        ["MODEL_BRAND_ANALYSIS",   "claude-sonnet-4-6",  "Modelo para extracción de marca"],
        ["MODEL_DESIGN_CONCEPTS",  "claude-sonnet-4-6",  "Modelo para generación de conceptos"],
        ["IMAGE_PROVIDER",         "openai",             "Proveedor de imágenes (openai | replicate)"],
        ["IMAGE_MODEL_OPENAI",     "gpt-image-1",        "Modelo de imagen de OpenAI"],
        ["IMAGE_QUALITY",          "medium",             "Calidad imagen (low | medium | high)"],
        ["RENDER_ENGINE",          "playwright",         "Motor tipográfico (playwright | pil)"],
        ["USE_DALLE",              "true",               "Activar generación IA de fondos"],
        ["USE_FEW_SHOT",           "true",               "Activar ejemplos de aprendizaje"],
    ]

    col_w2 = [5*cm, 4*cm, 6.4*cm]
    t_cfg = Table(config_data, colWidths=col_w2, repeatRows=1)
    t_cfg.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), NEGRO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTNAME",      (0, 1), (0, -1), "Courier"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, GRIS_CLARO]),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, GRIS_LINEA),
    ]))
    elementos.append(t_cfg)
    elementos.append(Spacer(1, 8))

    costes = [
        ("Demo / pruebas", "~$0.03 / pedido",
         "USE_DALLE=false — solo Claude Haiku, sin imágenes IA"),
        ("Producción estándar", "~$0.17–0.23 / pedido",
         "Config por defecto: Sonnet + gpt-image-1 quality=medium"),
        ("Producción económica", "~$0.05–0.08 / pedido",
         "IMAGE_PROVIDER=replicate (Flux Schnell, 10× más barato)"),
        ("Máxima calidad", "~$0.30–0.40 / pedido",
         "MODEL_DESIGN_CONCEPTS=claude-opus-4-7 + quality=high"),
    ]

    costes_data = [["Modo", "Coste estimado", "Descripción"]] + \
                  [[c[0], c[1], c[2]] for c in costes]
    t_costes = Table(costes_data, colWidths=[4*cm, 3.5*cm, 7.9*cm], repeatRows=1)
    t_costes.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), ACENTO),
        ("TEXTCOLOR",     (0, 0), (-1, 0), white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTNAME",      (1, 1), (1, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, ACENTO_SOFT]),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.4, GRIS_LINEA),
    ]))
    elementos.append(t_costes)
    elementos.append(Spacer(1, 10))

    # ── TEORÍA / RAZONAMIENTO ─────────────────────────────────────────────────
    elementos.append(separador())
    elementos.append(Paragraph("Razonamiento y Decisiones de Diseño", E["h2"]))

    razonamiento = [
        ("¿Por qué 2 llamadas a Claude en lugar de 1?",
         "La extracción de marca (Brand Analysis) requiere baja temperatura (T=0.3) "
         "para precisión en colores HEX y nombres de fuente. La generación creativa "
         "requiere alta temperatura (T=1.0) para diversidad. Separar las llamadas "
         "permite optimizar cada una para su objetivo."),
        ("¿Por qué 6 conceptos con roles fijos?",
         "Cada propuesta cumple una función de decisión: P1 impacto, P2 legibilidad, "
         "P3 energía, P4 protagonismo del nombre, P5 minimalismo, P6 identidad pura. "
         "Esto garantiza que el cliente siempre reciba al menos una propuesta "
         "conservadora y una arriesgada, sin duplicados visuales."),
        ("¿Por qué PIL para medir fuentes y Playwright para renderizar?",
         "Playwright/Chromium renderiza tipografía con kerning y hinting profesional, "
         "pero no puede auto-reducir fuentes que desbordan. PIL mide el ancho exacto "
         "de cada palabra con la fuente real y determina el tamaño máximo que cabe — "
         "Playwright solo recibe tamaños ya validados."),
        ("¿Por qué perfil fila-a-fila para superficies irregulares?",
         "Un único ancho mínimo global (solución anterior) forzaba todo el texto al "
         "punto más estrecho del trofeo, haciendo el texto ilegible. El perfil por "
         "fila permite a cada elemento de texto usar el ancho real disponible en su "
         "altura, colocando el texto en las zonas más anchas y legibles."),
        ("Restricciones de impresión UV incorporadas al prompt",
         "La impresión UV sobre metal tiene limitaciones físicas: fondos negros "
         "sólidos crean textura irregular, las tintas metálicas no existen en UV, "
         "los fluorescentes requieren conversión CMYK. Estas restricciones se "
         "inyectan como reglas obligatorias en el system prompt de Capa 1, haciendo "
         "que la IA diseñe directamente para el medio físico."),
    ]

    for titulo_r, desc_r in razonamiento:
        elementos.append(Paragraph(f"<b>{titulo_r}</b>", E["h3"]))
        elementos.append(Paragraph(desc_r, E["cuerpo"]))

    # ── PIE ───────────────────────────────────────────────────────────────────
    elementos.append(Spacer(1, 16))
    elementos.append(separador())
    elementos.append(Paragraph(
        "Sustain Awards · Agente de Diseño Gráfico · 2026 · "
        "Stack: Python 3.12 · Claude Sonnet 4.6 · gpt-image-1 · Playwright · PIL · Flask",
        ParagraphStyle("pie", fontName="Helvetica", fontSize=7.5,
                       leading=10, textColor=HexColor("#999999"), spaceAfter=4)
    ))

    return elementos


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    output = "Sustain_Awards_Agente_Diseño_Grafico.pdf"

    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=MARGEN,
        rightMargin=MARGEN,
        topMargin=MARGEN,
        bottomMargin=MARGEN,
        title="Agente de Diseño Gráfico — Sustain Awards",
        author="Sustain Awards",
    )
    doc.build(construir_doc())
    print(f"PDF generado: {output}")
