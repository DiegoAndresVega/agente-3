"""
CAPA 1 — Agente Diseñador Gráfico IA
Sustain Awards

Pipeline de 2 llamadas a Claude:
  Llamada A: Brand Analysis  → vocabulario visual de la marca
  Llamada B: Design Concepts → 3 conceptos con prompts para gpt-image-1

Modelos usados:
  Claude claude-sonnet-4-6 (coste medio) — ~1-2 céntimos por generación
"""

import os
import re
import json
import sys
from pathlib import Path
import base64

import anthropic


PROJECT_ROOT    = Path(__file__).resolve().parent.parent
DATA_DIR        = PROJECT_ROOT / "data"
SPECS_DIR       = PROJECT_ROOT / "outputs" / "design_specs"
APRENDIZAJE_DIR = PROJECT_ROOT / "assets" / "aprendizaje"
REFERENCIAS_DIR = PROJECT_ROOT / "assets" / "referencias"

MODELO_CLAUDE = "claude-sonnet-4-6"


# ─── Prompts ──────────────────────────────────────────────────────────────────

PROMPT_A_BRAND_ANALYSIS = """\
Eres un analista senior de identidad visual. Analiza todos los assets proporcionados \
(logotipo, manual de marca y/o datos web) y extrae el vocabulario visual completo.

Devuelve EXCLUSIVAMENTE un JSON válido, sin texto adicional, sin markdown:

{
  "brand_name": "nombre de la marca",
  "brand_tone": "formal|sostenible|tecnologico|deportivo|cultural|institucional|moderno|lujo",
  "visual_density": "limpia|media|rica",
  "colors": {
    "primary": "#HEX",
    "secondary": "#HEX",
    "accent": "#HEX o null",
    "background_light": "#HEX (tono claro para fondos)",
    "background_dark": "#HEX (tono oscuro premium)",
    "text_on_dark": "#HEX (contraste sobre fondos oscuros)",
    "text_on_light": "#HEX (contraste sobre fondos claros)",
    "primary_tint": "#HEX (primario + 35% blanco)",
    "primary_shade": "#HEX (primario + 30% negro)",
    "neutral": "#HEX (gris neutro o #6B6B6B)"
  },
  "typography": {
    "style": "sans-serif|serif|display|monospace",
    "brand_name_length": "corto|medio|largo",
    "font_name": "nombre exacto de la fuente principal del brandbook (ej: Futura PT, DIN Pro, FF Clan). null si no identificable.",
    "google_fonts_name": "nombre EXACTO en Google Fonts si la fuente está disponible o tiene equivalente cercano (ej: Montserrat, Raleway, Roboto). null si no hay equivalente razonable.",
    "google_fonts_weights": [400, 700]
  },
  "graphic_resources": {
    "uses_gradients": false,
    "uses_geometric_patterns": false,
    "bold_color_usage": false,
    "minimalist_tendency": false
  }
}

Reglas:
- PRIORIDAD DE FUENTES: brandbook PDF > logo > web corporativa. Si hay brandbook, úsalo como verdad absoluta.
- Si recibes "FUENTE CORPORATIVA DISPONIBLE LOCALMENTE: 'X'", escribe X exactamente en typography.font_name Y en typography.google_fonts_name. No uses equivalente ni busques alternativa.
- Si recibes "EXTRACCIÓN AUTOMÁTICA DEL BRANDBOOK", esos colores HEX son los colores REALES del brandbook — úsalos directamente en primary, secondary, accent. No los ignores.
- primary: el color corporativo principal (el más prominente/frecuente en el brandbook).
- secondary: el segundo color más corporativo. Si el brandbook tiene varios secundarios, elige el más diferenciado del primario.
- accent: color de acento o de líneas especializadas (sub-marcas, categorías) si existe. null si no hay.
- primary_tint: mezcla primario con blanco (35%). Calcula el HEX.
- primary_shade: mezcla primario con negro (30%). Calcula el HEX.
- Si no hay brandbook ni web, deduce todo del logo.
- typography.font_name: extrae el nombre exacto de la fuente principal mencionada en el brandbook. null si no hay mención explícita.
- typography.google_fonts_name: si esa fuente está en Google Fonts o tiene equivalente cercano, escribe el nombre exacto como aparece en fonts.google.com (mayúsculas exactas). null si no hay equivalente razonable.
- typography.google_fonts_weights: siempre [400, 700] como mínimo.
- Responde SOLO con el JSON.\
"""

PROMPT_B_DESIGN_CONCEPTS = """\
Eres el director creativo de una agencia premium de galardones corporativos.
Tu trabajo: generar 6 conceptos de diseño radicalmente distintos para un trofeo/galardón.

MANDATO CREATIVO:
No tienes plantillas. Inventas desde cero partiendo de la personalidad real de esta marca.
Cada concepto debe tener una IDENTIDAD VISUAL completamente diferente.

DIFERENCIACIÓN OBLIGATORIA entre los 6 conceptos:
  1. Tonos de fondo BIEN DISTRIBUIDOS: exactamente 2 oscuros, 2 claros, 2 medios/coloridos
     — NO hagas 3 o más oscuros seguidos, ni 2 conceptos con fondo casi idéntico
  2. Posición del logo diferente en cada uno
  3. Tratamiento tipográfico radicalmente diferente en cada uno:
     — Algunos: ultra-bold condensed, otros: serif editorial, otros: geométrico
     — Algunos: recipient enorme hero (ratio 0.18), otros: tamaño moderado (0.10)
  4. Colores de texto distintos: no repitas la misma combinación en dos conceptos
  5. text_style.text_anchor OBLIGATORIO variado: P1=top, P2=center, P3=bottom,
     P4=bottom, P5=center, P6=top — sin repetir el mismo anchor en propuestas consecutivas
  6. text_style.layout OBLIGATORIO variado — los 5 tipos deben repartirse:
     P1=stacked, P2=spread, P3=staggered, P4=billboard, P5=vertical, P6=stacked
     Este campo ES OBLIGATORIO en cada propuesta. No lo omitas nunca.
  7. En fondos CLAROS usa siempre texto oscuro (#1A1A1A, #002E3C, #333333)
     En fondos OSCUROS usa siempre texto claro (#FFFFFF, #FFD700, #E0E0E0)
  8. Uso del logo CREATIVO y variado — elige entre estas opciones:
     - "blanco"    → logo en blanco, para fondos oscuros (clásico)
     - "negro"     → logo en negro, para fondos claros o blancos
     - "color"     → logo en colores originales de marca, para fondos neutros/claros
     - "watermark" → logo grande semitransparente centrado en el fondo (opacity: 0.12–0.20),
                     crea profundidad y presencia de marca sin competir con el texto
     - "banda"     → franja horizontal del color primario de marca que cruza el trofeo,
                     el logo aparece en blanco sobre ella (band_color: "#HEX del primario")
     Cada propuesta debe usar un tratamiento diferente. No repitas el mismo en dos seguidas.

CAMPO dalle_prompt — SOLO EL FONDO ARTÍSTICO:
  - En INGLÉS, retrato vertical (portrait)
  - Describe ÚNICAMENTE el fondo: texturas, geometría, gradientes, iluminación, atmósfera
  - NO incluyas texto, tipografía, letras ni palabras
  - NO menciones logos, personas ni caras
  - Termina SIEMPRE con: "No text, no logos, no people. Premium award background."
  - Propuesta 6: dalle_prompt = "" (fondo sólido monocromo, sin generación IA)

  Ejemplos de dalle_prompt bien escritos:
    "Deep navy #1A237E background with subtle gold geometric lines radiating from center.
     Soft vignette edges, dramatic studio lighting, premium corporate texture.
     No text, no logos, no people. Premium award background."

    "Clean white #FFFFFF with bold horizontal band in brand color #2E7D32 at center.
     Editorial minimalist composition, soft shadows on the band edges.
     No text, no logos, no people. Premium award background."

CAMPO text_prompt — SOLO LA TIPOGRAFÍA DEL GALARDÓN:
  - En INGLÉS, describe ÚNICAMENTE el tratamiento tipográfico
  - Incluye los textos LITERALES del galardón con jerarquía visual explícita:
      → recipient (nombre del premiado): HERO SIZE, el elemento más grande
      → headline (nombre del premio): tamaño medio
      → subtitle (organización): pequeño, discreto
  - Especifica: peso tipográfico, familia (serif/sans-serif/display), tratamiento visual
    (embossed, glowing, metallic, engraved, editorial, reversed, outlined, etc.)
  - Especifica colores HEX exactos para cada nivel
  - NO menciones el fondo ni colores de fondo
  - Orientación vertical, texto centrado

  Ejemplos de text_prompt bien escritos:
    "Ultra-bold condensed sans-serif award typography. Recipient 'OFESAUTO' at massive hero
     scale, white #FFFFFF with subtle gold outer glow. Award title 'Empresa Comprometida
     con la Seguridad' at medium size, gold #FFD700. Organization 'Juaneda Hospitales'
     at small caption size, light gray #AAAAAA. Dramatic size contrast between levels."

    "Elegant serif editorial layout. Recipient 'EMPRESA EJEMPLO' at large italic hero scale,
     deep navy #1A237E bold. Award title 'Premio Sostenibilidad' at medium regular weight,
     dark gray #555555. Organization 'Nombre del Cliente' at small light caption, gray #888888.
     Refined institutional feel, generous spacing."

REGLA CRÍTICA — subtitle (organización):
  El subtitle SIEMPRE es el nombre del cliente/empresa premiada (brand_name del análisis).
  NUNCA escribas el nombre de la empresa organizadora del evento ni ninguna marca de premios.
  Si no sabes el nombre del cliente, usa el brand_name del análisis de marca.

REGLA CRÍTICA — contraste de texto:
  - Fondo OSCURO (bg_tone=dark): recipient y headline en colores MUY CLAROS (#FFFFFF, #FFD700, #E0E0E0).
    NUNCA uses gris medio o colores apagados sobre fondo oscuro.
  - Fondo CLARO (bg_tone=light): recipient y headline en colores MUY OSCUROS (#000000, #1A1A1A, primario de marca).
    NUNCA uses gris claro, blanco ni colores pálidos sobre fondo claro.
  - Fondo MEDIO (bg_tone=mid): usa el color primario de la marca si tiene suficiente contraste,
    o negro/blanco según la luminancia del fondo.
  El contraste mínimo aceptable es 4.5:1 (WCAG AA). Textos ilegibles arruinan el diseño.

CAMPO text_bg_dark — fondo para generación del texto:
  - true  → el texto es CLARO (blanco, dorado, plateado) → fondo negro para generación
  - false → el texto es OSCURO (azul, negro, gris oscuro) → fondo blanco para generación
  Regla: si el recipient en text_prompt es de color claro → true. Si es oscuro → false.

CAMPO text_style.font_family — fuente de marca para el renderizado:
  - Copia aquí el valor de typography.google_fonts_name del análisis de marca.
  - Si es null en el análisis, escribe null aquí. No inventes ni supongas fuentes.
  - Esta fuente se descarga de Google Fonts y se usa para el renderizado PIL (fallback).
  - También menciónala en text_prompt: añade "rendered in [FontName] typeface" al estilo.
  - Es IGUAL en los 6 conceptos — es la fuente corporativa, no varía por propuesta.

CAMPO text_style.text_anchor — posición vertical del bloque de texto en el canvas:
  OBLIGATORIO variar entre las 6 propuestas. Distribución sugerida:
  - Propuestas 1, 4: "top"    (texto en la parte alta, logo abajo o pequeño arriba)
  - Propuestas 2, 5: "center" (texto centrado verticalmente)
  - Propuestas 3, 6: "bottom" (texto en la parte baja, logo arriba)
  Esto garantiza que cada diseño tenga una composición diferente.

CAMPO text_style.layout — distribución espacial del texto en el canvas:
  Tienes 5 opciones. OBLIGATORIO variar entre los 6 conceptos:
  - "stacked"   → bloque compacto bajo el logo, posición controlada por text_anchor.
                  Uso en fondos cargados o cuando el logo domina la composición.
  - "spread"    → canvas completo: headline en lo alto del trofeo, recipient en el centro
                  exacto, subtitle/fecha en la parte baja. Gran espacio vacío entre zonas.
                  Efecto editorial premium (estilo Danone Institute, AWS).
  - "staggered" → canvas completo + asimetría extrema: headline pequeño alineado DERECHA
                  arriba, recipient ENORME alineado IZQUIERDA en el centro, subtitle DERECHA
                  abajo. Tensión visual diagonal. Para marcas atrevidas (estilo PepsiCo BAM).
  - "billboard" → canvas completo: recipient llena casi todo el trofeo, headline micro-caption
                  arriba, subtitle micro-caption abajo. El nombre del premiado lo es TODO.
                  Máximo impacto. Ideal para marcas minimalistas o de lujo.
  - "vertical"  → recipient girado 90° ocupa toda la altura del lado derecho del trofeo.
                  Headline y subtitle quedan en el lado izquierdo (arriba y abajo).
                  Efecto lateral dramático (estilo Enter Award). Para marcas vanguardistas.
  Distribución obligatoria: P1=stacked, P2=spread, P3=staggered, P4=billboard, P5=vertical, P6=stacked
  (billboard y vertical como máximo una vez cada uno)

JERARQUÍA FIJA: recipient > headline > subtitle (siempre, en todos los conceptos)

Devuelve EXCLUSIVAMENTE un JSON array de 6 conceptos, sin markdown:

[
  {
    "proposal_id": 1,
    "pattern_name": "nombre evocador 2-3 palabras",
    "design_rationale": "por qué este concepto encaja con la marca (1 frase)",
    "dalle_prompt": "English — ONLY artistic background, NO text, NO logos...",
    "text_prompt": "English — typography style + literal award texts + colors + hierarchy...",
    "text_bg_dark": true,
    "bg_tone": "dark|light|mid",
    "color_overlay": { "active": false, "color": "#HEX de marca", "opacity": 0.10 },
    "logo": { "treatment": "blanco|negro|color|watermark|banda", "position": "top_center|top_left|top_right|center|bottom_center", "scale": 0.55, "opacity": 0.15, "band_color": "#HEX o null" },
    "text_style": { "text_anchor": "top|center|bottom", "layout": "stacked|spread|staggered|billboard", "font_family": "Google Fonts name o null" },
    "award_text": { "headline": "nombre del premio", "recipient": "nombre del premiado", "subtitle": "nombre del cliente (brand_name) — NUNCA el nombre del organizador del evento" }
  },
  { "proposal_id": 2, ... },
  { "proposal_id": 3, ... },
  { "proposal_id": 4, ... },
  { "proposal_id": 5, ... },
  { "proposal_id": 6, "dalle_prompt": "", ... }
]

Responde SOLO con el JSON array.\
"""


# ─── Carga de ejemplos de aprendizaje ────────────────────────────────────────

def _cargar_ejemplos_aprendizaje() -> list[dict]:
    """
    Carga ejemplos validados por el usuario.
    - Ejemplos con dalle_prompt: imagen + JSON completo (nuevos)
    - Ejemplos sin dalle_prompt: solo imagen (referencias visuales)

    Límite recomendado: 15 imágenes máximo para controlar coste.
    Cada imagen añade ~2.000 tokens al contexto (~$0.006 extra en Sonnet).
    """
    MAX_EJEMPLOS = 15  # sweet spot: 8-12. Más de 15 no mejora y sube el coste.
    if not APRENDIZAJE_DIR.exists():
        return []

    jsons = sorted(
        APRENDIZAJE_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )[:MAX_EJEMPLOS]

    if not jsons:
        return []

    bloques = []
    for json_path in jsons:
        try:
            with open(json_path, encoding="utf-8") as f:
                brief = json.load(f)

            img_path = json_path.with_suffix(".jpg")
            if not img_path.exists():
                img_path = json_path.with_suffix(".png")

            if img_path.exists():
                ext = img_path.suffix.lower()
                mt  = "image/png" if ext == ".png" else "image/jpeg"
                b64 = base64.standard_b64encode(img_path.read_bytes()).decode()
                bloques.append({"type": "image",
                                "source": {"type": "base64", "media_type": mt, "data": b64}})

            # Solo incluir el JSON si es del nuevo formato (tiene dalle_prompt)
            if "dalle_prompt" in brief:
                bloques.append({
                    "type": "text",
                    "text": f"Brief validado:\n{json.dumps(brief, ensure_ascii=False, indent=2)}"
                })

        except Exception:
            pass

    return bloques


# ─── Llamada genérica a Claude ────────────────────────────────────────────────

def _reparar_json_strings(texto: str) -> str:
    """
    Elimina saltos de línea literales dentro de valores de cadena JSON.
    Claude a veces genera strings multilínea que rompen json.loads.
    """
    resultado = []
    dentro_string = False
    escape_next = False
    for ch in texto:
        if escape_next:
            resultado.append(ch)
            escape_next = False
        elif ch == "\\":
            resultado.append(ch)
            escape_next = True
        elif ch == '"':
            resultado.append(ch)
            dentro_string = not dentro_string
        elif dentro_string and ch in ("\n", "\r"):
            resultado.append(" ")  # reemplaza salto de línea por espacio
        else:
            resultado.append(ch)
    return "".join(resultado)


def _llamar_claude(mensajes: list[dict], system_prompt: str,
                   etiqueta: str, temperatura: float = 1.0) -> dict | list:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY no encontrada.\n"
            "  Configúrala con: set ANTHROPIC_API_KEY=sk-ant-..."
        )

    client = anthropic.Anthropic(api_key=api_key)
    respuesta = client.messages.create(
        model=MODELO_CLAUDE,
        max_tokens=6000,
        temperature=temperatura,
        system=system_prompt,
        messages=mensajes,
    )

    texto = respuesta.content[0].text.strip()

    match = re.search(r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```", texto, re.DOTALL)
    if match:
        texto = match.group(1)
    else:
        match = re.search(r"([\[\{].*[\]\}])", texto, re.DOTALL)
        if match:
            texto = match.group(1)

    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        # Reparar: saltos de línea literales dentro de cadenas JSON (error frecuente)
        texto_reparado = _reparar_json_strings(texto)
        try:
            return json.loads(texto_reparado)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"[{etiqueta}] Respuesta no es JSON válido: {e}\n\nRespuesta:\n{texto[:500]}"
            )


# ─── Llamada A — Brand Analysis ───────────────────────────────────────────────

def _llamada_brand_analysis(pedido: dict, brand_context: dict) -> dict:
    content = []

    tiene_logo    = bool(brand_context.get("logo_b64"))
    pdf_imagenes  = brand_context.get("pdf_imagenes", [])
    tiene_pdf     = len(pdf_imagenes) > 0
    tiene_resumen = bool(brand_context.get("pdf_resumen"))
    tiene_url     = bool(brand_context.get("url_data", {}).get("ok"))

    print(f"  [ClaudeA] Fuentes de identidad visual disponibles:")
    print(f"    Logo              : {'✓' if tiene_logo else '✗'}")
    print(f"    Brandbook (visual): {'✓ (' + str(len(pdf_imagenes)) + ' páginas como imágenes)' if tiene_pdf else '✗'}")
    print(f"    Brandbook (texto) : {'✓ (colores/fuentes de todas las páginas)' if tiene_resumen else '✗'}")
    print(f"    Web corporativa   : {'✓' if tiene_url else '✗'}")

    if tiene_logo:
        content.append({"type": "image", "source": {
            "type": "base64",
            "media_type": brand_context["logo_type"],
            "data": brand_context["logo_b64"],
        }})

    # Páginas del brandbook como imágenes JPEG independientes
    if tiene_pdf:
        for idx, img_b64 in enumerate(pdf_imagenes):
            content.append({"type": "image", "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": img_b64,
            }})

    # Resumen de texto extraído del PDF (colores HEX, Pantone, fuentes de TODAS las páginas)
    # Esto garantiza que Claude vea la paleta aunque esté en páginas no incluidas visualmente
    if tiene_resumen:
        content.append({"type": "text", "text": (
            "EXTRACCIÓN AUTOMÁTICA DEL BRANDBOOK (texto de TODAS las páginas del PDF):\n"
            "Usa estos colores y fuentes como la fuente de verdad principal para el análisis.\n\n"
            + brand_context["pdf_resumen"]
        )})

    # Si hay fuente local disponible (subida o extraída del PDF), informar a Claude
    fuente_local = (
        brand_context.get("fuente_upload") or
        next(iter(brand_context.get("fuentes_pdf", {})), None)
    )
    if fuente_local:
        content.append({"type": "text", "text": (
            f"FUENTE CORPORATIVA DISPONIBLE LOCALMENTE: '{fuente_local}'\n"
            "Esta fuente ya está instalada en el sistema. Úsala EXACTAMENTE tal como aparece "
            "en typography.font_name y typography.google_fonts_name. No busques equivalente."
        )})
        print(f"  [ClaudeA] Fuente local disponible: '{fuente_local}'")

    url_data = brand_context.get("url_data", {})
    url_texto = ""
    if url_data.get("ok"):
        url_texto = (
            f"\nWEB CORPORATIVA ({url_data.get('url', '')}):\n"
            f"- Colores: {', '.join(url_data.get('colores_detectados', [])[:6])}\n"
            f"- Estilo: {url_data.get('descripcion_estilo', '—')}\n"
            "(Nota: la web tiene menor prioridad que el brandbook PDF)\n"
        )

    award  = pedido.get("award", {})
    evento = pedido.get("evento", {})
    content.append({"type": "text", "text": (
        f"DATOS:\n- Empresa: {pedido.get('id_cliente', '—')}\n"
        f"- Evento: {evento.get('nombre', '—')}\n"
        f"- Premio: {award.get('headline', '—')}\n{url_texto}"
        "PRIORIDAD: brandbook PDF > logo > web corporativa.\n"
        "Analiza los assets y extrae el vocabulario visual completo."
    )})

    resultado = _llamar_claude(
        [{"role": "user", "content": content}],
        PROMPT_A_BRAND_ANALYSIS,
        "BrandAnalysis",
        temperatura=0.3,  # análisis preciso → temperatura baja
    )

    if isinstance(resultado, dict):
        colores = resultado.get("colors", {})
        typo    = resultado.get("typography", {})
        print(f"  [ClaudeA] Resultado brand analysis:")
        print(f"    Marca     : {resultado.get('brand_name', '—')}")
        print(f"    Primario  : {colores.get('primary', '—')}")
        print(f"    Secundario: {colores.get('secondary', '—')}")
        print(f"    Acento    : {colores.get('accent', '—')}")
        print(f"    Fuente    : {typo.get('font_name', '—')} → Google Fonts: {typo.get('google_fonts_name', '—')}")

    return resultado if isinstance(resultado, dict) else {}


# ─── Llamada B — Design Concepts ─────────────────────────────────────────────

def _llamada_design_concepts(pedido: dict, brand_analysis: dict) -> list:
    award  = pedido.get("award", {})
    evento = pedido.get("evento", {})

    ejemplos = _cargar_ejemplos_aprendizaje()
    content  = []

    n_ejemplos = sum(1 for b in ejemplos if b.get("type") == "text")
    n_imagenes = sum(1 for b in ejemplos if b.get("type") == "image")

    if ejemplos:
        print(f"  → {n_imagenes} imagen(es) de referencia, {n_ejemplos} brief(s) validado(s)")
        content.append({"type": "text", "text": (
            f"EJEMPLOS VALIDADOS POR EL USUARIO ({n_imagenes} referencias visuales):\n"
            "Analiza estos diseños que han funcionado bien. Extrae patrones concretos:\n"
            "  - Qué recurso visual define cada uno\n"
            "  - Cómo se relacionan logo y texto\n"
            "  - Qué makes them feel premium and professional\n"
            "Aplica esos patrones (adaptados a la nueva marca) en tus propuestas.\n"
            "Menciona en design_rationale qué aprendiste de estas referencias."
        )})
        content.extend(ejemplos)
    else:
        print("  → Sin ejemplos previos (primera generación)")

    recipient_txt = award.get('recipient') or 'Nombre del Premiado'
    headline_txt  = award.get('headline')  or 'Excellence Award'
    subtitle_txt  = award.get('subtitle')  or 'Sustain Awards'
    fecha_line = f"\n- Fecha/Año   : {award.get('fecha', '')}" if award.get("fecha") else ""
    typo      = brand_analysis.get("typography", {})
    font_name = typo.get("google_fonts_name") or typo.get("font_name") or "sin datos"
    content.append({"type": "text", "text": (
        f"ANÁLISIS DE MARCA:\n{json.dumps(brand_analysis, ensure_ascii=False, indent=2)}\n\n"
        f"TEXTO EXACTO DEL GALARDÓN (úsalo literalmente en award_text y text_prompt):\n"
        f"- Nombre del premiado : {recipient_txt}\n"
        f"- Nombre del premio   : {headline_txt}\n"
        f"- Organización        : {subtitle_txt}\n"
        f"{fecha_line}\n"
        f"- Evento              : {evento.get('nombre', '')}\n\n"
        f"FUENTE DE MARCA (para text_style.font_family): {font_name}\n\n"
        "Genera los 6 conceptos. Incluye estos textos literalmente en award_text y text_prompt."
    )})

    resultado = _llamar_claude(
        [{"role": "user", "content": content}],
        PROMPT_B_DESIGN_CONCEPTS,
        "DesignConcepts",
        temperatura=1.0,  # máxima creatividad
    )
    return resultado if isinstance(resultado, list) else []


# ─── Validación ───────────────────────────────────────────────────────────────

def _validar_concepto(c: dict, idx: int) -> dict:
    # text_anchor rota entre top/center/bottom para garantizar variedad entre propuestas
    _anchors = ["top", "center", "bottom", "top", "center", "bottom"]
    defaults = {
        "proposal_id":      idx + 1,
        "pattern_name":     f"Concepto {idx + 1}",
        "design_rationale": "Diseño corporativo premium.",
        "dalle_prompt":     "Deep navy abstract corporate background, geometric shapes, premium. No text, no logos, no people. Premium award background.",
        "text_prompt":      "Bold corporate sans-serif award typography. Recipient name at massive hero scale, white #FFFFFF. Award title at medium size, gold #FFD700. Organization at small caption size, light gray #BBBBBB. Dramatic size contrast between levels.",
        "text_bg_dark":     True,
        "bg_tone":          "dark",
        "color_overlay":    {"active": False, "color": "#1A1A1A", "opacity": 0.15},
        "logo":             {"treatment": "blanco", "position": "top_center", "scale": 0.55},
        "text_style":       {
            "text_anchor":     _anchors[idx % 6],
            "layout":          ["stacked", "spread", "staggered", "billboard", "vertical", "stacked"][idx % 6],
            "font_family":     None,
            "margin_h":        0.07,
            "recipient_color": "#FFFFFF",
            "headline_color":  "#FFD700",
            "subtitle_color":  "#BBBBBB",
        },
        "award_text":       {"headline": "Excellence Award", "recipient": "Nombre Apellido", "subtitle": "Organización"},
    }
    for k, v in defaults.items():
        if k not in c or c[k] is None:
            c[k] = v
        elif isinstance(v, dict):
            for sk, sv in v.items():
                if sk not in c[k] or c[k][sk] is None:
                    c[k][sk] = sv
    return c


# ─── Guardado ─────────────────────────────────────────────────────────────────

def guardar_spec(spec: dict, id_pedido: str) -> Path:
    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    ruta = SPECS_DIR / f"{id_pedido}_design_spec.json"
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    return ruta


# ─── Pipeline principal ───────────────────────────────────────────────────────

def diseñar_desde_contexto(pedido: dict, brand_context: dict) -> tuple[list, dict]:
    """
    Pipeline de Capa 1: 2 llamadas a Claude.
    Devuelve (conceptos[6], spec_completo).
    """
    id_pedido = pedido.get("id_pedido", "TEST")

    print(f"\n{'─'*50}")
    print(f"  CAPA 1 · Agente Diseñador IA  [{MODELO_CLAUDE}]")
    print(f"  Pedido: {id_pedido}")
    print(f"{'─'*50}")

    print("\n[A] Brand Analysis...")
    brand_analysis = _llamada_brand_analysis(pedido, brand_context)
    colores = brand_analysis.get("colors", {})
    print(f"  → Tono   : {brand_analysis.get('brand_tone', '—')}")
    print(f"  → Primary: {colores.get('primary', '—')}")

    n_aprendizaje = len(list(APRENDIZAJE_DIR.glob("*.json"))) if APRENDIZAJE_DIR.exists() else 0
    print(f"\n[B] Design Concepts (ejemplos acumulados: {n_aprendizaje})...")
    conceptos = _llamada_design_concepts(pedido, brand_analysis)
    conceptos = [_validar_concepto(c, i) for i, c in enumerate(conceptos[:6])]
    while len(conceptos) < 6:
        conceptos.append(_validar_concepto({}, len(conceptos)))

    for c in conceptos:
        print(f"  → P{c['proposal_id']}: {c['pattern_name']} [{c.get('bg_tone','?')}]")

    spec = {
        "id_pedido":      id_pedido,
        "brand_analysis": brand_analysis,
        "design_concepts": conceptos,
    }
    ruta = guardar_spec(spec, id_pedido)
    print(f"  → Spec: {ruta.name}")

    return conceptos, spec
