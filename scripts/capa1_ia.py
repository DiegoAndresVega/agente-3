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
    "colors_extended": ["#HEX1", "#HEX2", "...hasta 6 colores de la paleta completa de marca"],
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
    "font_style_category": "burbuja|redondeado|geometrico|humanista|corporativo|condensado|serif_moderno|serif_clasico|display",
    "google_fonts_name": "nombre EXACTO en Google Fonts del equivalente más cercano visualmente.",
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
- Si recibes "EXTRACCIÓN AUTOMÁTICA DEL BRANDBOOK", esos colores HEX son los colores REALES del brandbook — úsalos DIRECTAMENTE en primary, secondary, accent. NO los ignores ni los sustituyas por tu propia estimación.
- "COLORES HEX DEL BRANDBOOK" lista colores por frecuencia: el primero es casi siempre primary, el segundo secondary, el tercero puede ser accent.
- "COLORES DETECTADOS EN GRÁFICOS" son colores usados en bloques visuales del PDF — también son colores de marca reales.
- primary: el color corporativo principal (el más prominente/frecuente en la lista extraída del brandbook).
- secondary: el segundo color de marca más diferenciado del primario. Busca en toda la lista, no solo los primeros dos.
- accent: color de acento o de sub-marcas si existe. Puede estar en los colores gráficos aunque no en el texto.
- colors_extended: lista de todos los colores de marca detectados (máx. 6 HEX), para que el diseñador tenga la paleta completa.
- primary_tint: mezcla primario con blanco (35%). Calcula el HEX.
- primary_shade: mezcla primario con negro (30%). Calcula el HEX.
- Si no hay brandbook ni web, deduce todo del logo.
- typography.font_name: nombre exacto mencionado en el brandbook. null si no hay mención explícita.
- typography.font_style_category + typography.google_fonts_name: analiza el logotipo con estos criterios:

  INSPECCIÓN VISUAL (aplica al logotipo o tipografía visible en el brandbook):
    1. TERMINALES: ¿Las letras terminan en corte recto (geométrico) o en remate circular/burbuja?
    2. CONTRAFORMAS: ¿El interior de 'o','a','d','g' es casi circular (burbuja) o rectangular (corporativo)?
    3. PROPORCIÓN: ¿Letras anchas y circulares (playful) o compactas y estrechas (condensado)?
    4. TRAZO: ¿Grosor uniforme monolinear (geométrico/rounded) o contraste grueso-fino (humanista/serif)?
    5. PERSONALIDAD: ¿Juvenil/friendly/orgánico o sobrio/profesional/neutro?

  CATEGORÍAS → escribe en font_style_category + elige google_fonts_name de la lista:
    "burbuja"      → terminales muy redondeados, letras casi circulares, tono friendly/playful
                     "Fredoka One" (circular compacta), "Comfortaa" (geométrica redondeada),
                     "Nunito" (redondeada elegante), "Pacifico" (script amigable),
                     "Righteous" (geométrica display redondeada)

    "redondeado"   → sans-serif moderno con esquinas suavizadas — más neutro que burbuja
                     "Varela Round", "Quicksand", "Nunito Sans", "DM Sans", "Jost"

    "geometrico"   → trazos limpios y uniformes, esquinas angulosas, neutral y moderno
                     "Inter", "Outfit", "Barlow", "Urbanist", "Plus Jakarta Sans"

    "humanista"    → proporciones orgánicas, trazos con algo de contraste, cálido y legible
                     "Lato", "Source Sans 3", "Open Sans", "Raleway", "Mulish"

    "corporativo"  → sans-serif neutro profesional, institucional
                     "Montserrat", "Roboto", "IBM Plex Sans", "Work Sans", "Figtree"

    "condensado"   → estrecho y alto, tipografía de impacto para titulares
                     "Barlow Condensed", "Oswald", "Exo 2", "Rajdhani", "Bebas Neue"

    "serif_moderno" → serifa con contraste, actual y editorial
                     "Playfair Display", "DM Serif Display", "Cormorant Garamond"

    "serif_clasico" → serifa tradicional, institucional o académica
                     "Lora", "Merriweather", "Libre Baskerville", "Noto Serif"

    "display"      → tipografía con fuerte personalidad propia, experimental
                     "Josefin Sans", "Space Grotesk", "Syne", "Bebas Neue"

  EJEMPLO: smöoy usa terminales circulares, letras anchas y amigables → "burbuja" → "Fredoka One"
  EJEMPLO: Helvetica/Arial → "corporativo" → "Inter" o "IBM Plex Sans"
  EJEMPLO: Futura → "geometrico" → "Jost" o "Outfit"

- typography.google_fonts_name: SIEMPRE proporciona un nombre utilizable (nunca null salvo sin assets).
  Si la fuente está en Google Fonts → escríbela exactamente tal como aparece en fonts.google.com.
- typography.google_fonts_weights: siempre [400, 700] como mínimo.
- Responde SOLO con el JSON.\
"""

PROMPT_B_DESIGN_CONCEPTS = """\
Eres el director creativo de una agencia premium de galardones corporativos.
Tu trabajo: generar 6 conceptos de diseño radicalmente distintos para un trofeo/galardón.

MANDATO CREATIVO:
Cada propuesta es un CONCEPTO VISUAL DISTINTO — no una variación de paleta, sino un lenguaje
visual diferente. Piensa como si fueran 6 agencias distintas respondiendo al mismo brief.
La jerarquía es siempre: Logo → Título → NOMBRE DEL PREMIADO (héroe) → Organización.
El nombre del premiado es SIEMPRE el elemento tipográfico más grande y con mayor contraste.

USO DE LA PALETA COMPLETA — colores primario, secundario Y acento:
  El secundario (secondary) y el acento (accent) son tan importantes como el primario.
  Úsalos como elementos ESTRUCTURALES: banda de color, bloque de fondo, franja horizontal.
  NO los uses solo para pequeños detalles — crea zonas visuales de color contrastante.
  EJEMPLO Booking.com: primary=azul, secondary=amarillo → banda amarilla en el top es el diseño.
  EJEMPLO Nike: primary=negro, accent=naranja → bloque naranja como elemento central.

  - color_overlay.color: pon SIEMPRE el secundario o acento aquí (no el primario — ya es el fondo).
  - Para el logo treatment "banda": usa secondary como band_color cuando el primario es el fondo.
  - headline_color / recipient_color: varía entre primary, secondary y accent en los 6 conceptos.

POSICIONAMIENTO COMPOSITIVO — el texto debe estar en zonas distintas por concepto:
  P1: texto en zona IZQUIERDA (el sistema lo anclará a la izquierda — tú pon contenido interesante)
  P2: texto CENTRADO — editorial y equilibrado
  P3: texto STAGGERED — ya lo maneja el layout, pon colores y tamaños dramáticos
  P4: texto CENTRADO — el nombre lo llena todo
  P5: texto en zona DERECHA — el sistema lo anclará a la derecha
  P6: texto CENTRADO — identidad simétrica de marca

  IMPORTANTE: esta variedad de posición (izquierda/centro/derecha) la gestiona el sistema.
  Tu trabajo es crear CONTENIDO y COLORES distintos para cada zona.

LOS 6 CONCEPTOS VISUALES (uno por propuesta — respétalos en ese orden):

  P1 — PREMIUM OSCURO
    Concepto: corporativo de alta gama, oscuro y elegante.
    Fondo oscuro (primario oscuro de marca o navy profundo). Logo arriba en blanco.
    Recipient en blanco o dorado. Texto compacto bajo el logo.
    bg_tone=dark, layout=stacked, logo arriba.

  P2 — EDITORIAL BLANCO
    Concepto: minimalismo editorial, espacio blanco generoso, como los trofeos de AWS o Danone.
    Fondo BLANCO (#FFFFFF) → dalle_prompt="" (fondo sólido, sin DALLE).
    Logo prominente arriba, en negro o color.
    recipient_color: USA EL COLOR PRIMARIO VIVIDO DE MARCA si tiene contraste ≥ 3:1 sobre blanco
      para texto grande — el nombre del premiado en magenta/rojo/azul sobre blanco puro es una
      elección editorial PODEROSA y de diseñador. Si no hay suficiente contraste, usa el oscuro.
    Mucho espacio vacío entre los elementos — el aire ES el diseño.
    bg_tone=light, layout=spread, logo arriba.

  P3 — GRÁFICO AUDAZ
    Concepto: impacto tipográfico extremo, como PepsiCo BAM. El nombre es un elemento gráfico.
    Fondo oscuro sólido o con textura mínima. Recipient en mayúsculas, enorme, alineado a la izquierda.
    Headline pequeño alineado a la derecha arriba. Tensión visual diagonal — es intencional.
    bg_tone=dark, layout=staggered, recipient uppercase=true.

  P4 — BILLBOARD IMPACTO
    Concepto: el nombre del premiado lo llena casi todo. Máximo impacto visual y cromático.
    Fondo con el COLOR DE MARCA como protagonista — puede ser vibrante, saturado, alegre.
    Para marcas coloridas: bg_tone=mid (no dark) para dejar que el color de marca brille.
    Para marcas corporativas/oscuras: bg_tone=dark con gradiente del primario.
    Recipient centra el canvas. Headline y subtitle como micro-captions arriba y abajo.
    layout=billboard.
    OBLIGATORIO: añade watermark del logo (opacity 0.12–0.16) o banda de color como anclaje.

  P5 — MÍNIMO MODERNO
    Concepto: espacio, geometría y limpieza. Fondo blanco o muy claro.
    Fondo MUY CLARO o blanco → dalle_prompt="" (fondo sólido).
    Layout spread: headline arriba pequeño, recipient grande en el centro, subtitle abajo.
    Logo en negro o color.
    recipient_color: igual que P2 — usa el primario vivido de marca si hay contraste suficiente.
      Una variación: usa el mismo color que P2 o experimenta con un tono ligeramente diferente.
    bg_tone=light, layout=spread, logo puede estar abajo.

  P6 — MARCA PURA
    Concepto: el color de marca como protagonista absoluto, identidad sin filtros.
    Fondo: color primario sólido → dalle_prompt="" (el sistema genera un gradiente radial
    con banda diagonal del secundario y watermark geométrico — no necesitas describir el fondo).
    Logo blanco arriba. Recipient en blanco (#FFFFFF) para máximo contraste.
    Para marcas VIVIDAS/ALEGRES: usa recipient en blanco o en secondary si hay contraste.
    Para marcas OSCURAS/CORPORATIVAS: recipient en blanco puro + headline con tracking amplio.
    bg_tone=dark, layout=stacked.

COLOR OVERLAY — tinta de coherencia cromática (USAR CON PRUDENCIA):
  Propósito: añadir un velo muy sutil del color de marca sobre el fondo DALLE para cohesión.
  - active=true SOLO si el fondo DALLE necesita anclarse cromáticamente a la marca.
  - opacity MÁXIMA: 0.18 — por encima de eso destruye la creatividad del fondo generado.
  - active=false en P2/P5 (fondos blancos — sin tinta) y en P1 si el fondo ya usa colores de marca.
  - NUNCA uses opacity > 0.20 — el sistema lo recortará igualmente a 0.28 por seguridad.

REGLAS DE COHERENCIA (aplicables a TODOS los conceptos):
  1. Fondos bien distribuidos: mínimo 2 oscuros (P1, P3 o P4, P6), mínimo 2 claros (P2, P5)
  2. Tratamiento de logo diferente en cada propuesta — no repitas el mismo en dos seguidas
  3. En fondos CLAROS (P2, P5): usa el primario vivido de marca para el recipient si contraste ≥ 3:1
     (texto grande). Para headline y subtitle: usa oscuro (#1A1A1A o equivalente).
     PROHIBIDO para headline/subtitle: texto gris claro, colores luminosos sin contraste
  4. En fondos OSCUROS (P1, P3, P4, P6): texto claro OBLIGATORIO (#FFFFFF, #FFD700, accent)
     PROHIBIDO: texto gris medio, colores apagados
  5. Recipient (nombre del premiado) = elemento tipográfico más grande en TODOS los conceptos
     NUNCA: headline más grande que recipient

CAMPO dalle_prompt — FONDO ARTÍSTICO CON PERSONALIDAD POR CONCEPTO:

  REGLAS UNIVERSALES:
  - En INGLÉS, retrato vertical (portrait)
  - Describe ÚNICAMENTE el fondo — sin texto, sin logos, sin personas
  - Termina SIEMPRE con: "No text, no logos, no people. Premium award background."
  - P2 y P5: dalle_prompt = "" (fondo sólido blanco/claro, sin generación IA)
  - P6: dalle_prompt = "" (fondo sólido del primario de marca, sin generación IA)
  - Los 3 prompts DALLE (P1, P3, P4) DEBEN ser visualmente radicalmente distintos entre sí.
    PROHIBIDO: repetir la misma técnica (ej. dos gradientes radiales, dos texturas de grano).

  PERSONALIDAD VISUAL POR CONCEPTO — OBLIGATORIO diferente técnica en cada uno:

  P1 (PREMIUM OSCURO) → Atmosférico, cinematográfico, casi táctil.
    Base MUY OSCURA (negro profundo o primario muy shade). Acento luminoso del secundario.
    Elige UNA técnica distinta según el tono de la marca:
      lujo/institucional → rayo de luz diagonal dorada, grano fotográfico, niebla specular
      tecnológico/moderno → glow neón muy sutil en el secundario, grid difuso, humo geométrico
      sostenible/cultural → textura orgánica oscura (piedra, corteza, agua negra), acento verde/tierra
      deportivo/creativo → fondo negro con splash de color bold en una esquina, energía contenida
    REGLA: el fondo de P1 debe verse como el packaging de un producto de alta gama.

  P3 (GRÁFICO AUDAZ) → Diseño gráfico puro — NOT fotografía, NOT gradientes suaves.
    Base muy oscura + UN elemento geométrico GRANDE y AUDAZ.
    Elige UNA técnica:
      marcas saturadas (rosa, naranja, verde) → arco enorme del color de marca cortando el canvas
      marcas corporativas (azul, gris) → franja diagonal SÓLIDA del primario, grid de líneas del secundario
      marcas con identidad fuerte → forma geométrica bold (triángulo, rectángulo) en el accent color
    El elemento geométrico ocupa 30-50% del canvas. Nada de texturas etéreas.

  P4 (BILLBOARD IMPACTO) → El fondo ES el color de marca. Energía máxima.
    Técnicas por tono de marca:
      lujo/premium → halftone dorado fino sobre el primario, gradiente oscuro-brillante
      moderno/tech → gradiente explosivo del primario al secundario, partículas geométricas
      colorido/lúdico (helados, moda) → el color de marca a PLENO VOLUMEN con textura bold:
        acuarela densa en los tonos de marca, manchas de color superpuestas, fondo tipo cartel pop
        ¡NO tengas miedo de fondos VIVOS y ALEGRES para marcas alegres!
      deportivo → explosión radial del color primario, como un estadio encendido
    RECUERDA: para marcas con colores VIBRANTES (rosa, amarillo, turquesa), un fondo saturado
    y alegre ES la elección correcta. No lo oscurezcas artificialmente.

  ESTRATEGIA DE COLOR ADAPTATIVA:
  Marca FORMAL / LUJO / INSTITUCIONAL (brand_tone = formal|lujo|institucional):
    P1 → negro profundo, acento dorado o gris platino, luz especular elegante
    P3 → geometría limpia y precisa, una sola forma contundente
    P4 → halftone refinado, gradiente oscuro-a-profundo con el primario como acento vibrante

  Marca TECNOLÓGICA / MODERNA / SOSTENIBLE (brand_tone = tecnologico|moderno|sostenible):
    P1 → oscuro con velo azul-verde del primario, glow neón muy contenido
    P3 → grid o circuito abstracto en el accent, forma geométrica del primario
    P4 → gradiente vibrante primario→secundario, energía digital

  Marca DEPORTIVA / CULTURAL / CREATIVA / LÚDICA (brand_tone = deportivo|cultural|creativo):
    P1 → oscuro fotográfico con destello del color de marca, textura rugosa
    P3 → forma ENORME del color de marca (no temas usar rosa, amarillo, verde lima aquí)
    P4 → color de marca A TOPE — acuarela, manchas, poster bold — ¡SÍ a los fondos alegres!

REGLA CRÍTICA — subtitle:
  El subtitle SIEMPRE es el nombre del cliente/empresa premiada (brand_name del análisis).
  NUNCA escribas el nombre del organizador del evento ni ninguna marca de premios.

REGLA CRÍTICA — contraste (INCUMPLIRLA hace el diseño ilegible):
  - bg_tone=dark: recipient y headline en #FFFFFF, #FFD700 o accent muy claro.
    NUNCA gris medio ni colores apagados sobre oscuro.
  - bg_tone=light: recipient y headline en #000000, #1A1A1A o primario MUY OSCURO de marca.
    PROHIBIDO en fondo claro: azul luminoso (#4FC3F7, #64B5F6), gris medio (#AAAAAA),
    cualquier color con luminancia > 40% — quedan invisibles sobre blanco.
  El contraste mínimo es 4.5:1 (WCAG AA).

USO DEL LOGO — elige entre estas opciones, varía en cada propuesta:
  - "blanco"    → logo remapeado a blanco, para fondos oscuros
  - "negro"     → logo remapeado a negro, para fondos claros
  - "color"     → colores originales, para fondos neutros/claros
  - "watermark" → logo semitransparente centrado (opacity 0.12–0.20), profundidad sin ruido
  - "banda"     → franja horizontal del primario, logo blanco sobre ella

DIRECCIÓN TIPOGRÁFICA:
  FUENTE: usa typography.google_fonts_name del análisis en los 6 conceptos.
    P3 puede usar fuente condensada creativa si lo requiere el concepto.

  JERARQUÍA (forzada por el sistema, solo orienta tus ratios):
    recipient_size_ratio : 0.15–0.22  (siempre el mayor)
    headline_size_ratio  : ~50% del recipient ratio elegido
    subtitle_size_ratio  : ~23% del recipient ratio elegido

  ALINEACIONES:
    P1, P2, P4, P5, P6: todo centrado ("center")
    P3 (staggered): headline="right", recipient="left", subtitle="right" — la asimetría es el diseño

  MAYÚSCULAS:
    recipient_uppercase: true → impacto (P3, P4 siempre; otros según marca)
    recipient_uppercase: false → elegancia (P1, P2, P5, P6 por defecto)

  ESPACIADO:
    spacing_scale: 0.5 (denso/impactante) | 1.0 (estándar) | 1.8 (aireado/lujoso)

CAMPO text_style.layout — distribución del texto en el canvas:
  - "stacked"   → bloque compacto bajo el logo. Posición por text_anchor (top/center/bottom).
  - "spread"    → headline arriba del canvas, recipient en el centro exacto, subtitle abajo.
                  Gran espacio vacío entre zonas — efecto editorial premium.
  - "staggered" → headline pequeño alineado DERECHA arriba, recipient ENORME alineado IZQUIERDA
                  centro, subtitle DERECHA abajo. Tensión diagonal deliberada. Solo para P3.
  - "billboard" → recipient domina el canvas, headline y subtitle como micro-captions. Solo P4.
  PROHIBIDO: "vertical" (texto girado 90° — ilegible en objeto físico)
  Distribución: P1=stacked, P2=spread, P3=staggered, P4=billboard, P5=spread, P6=stacked

JERARQUÍA FIJA: recipient > headline > subtitle (siempre, en todos los conceptos)

Devuelve EXCLUSIVAMENTE un JSON array de 6 conceptos, sin markdown:

[
  {
    "proposal_id": 1,
    "pattern_name": "nombre evocador 2-3 palabras",
    "design_rationale": "por qué este concepto encaja con la marca (1 frase)",
    "dalle_prompt": "English — ONLY artistic background, NO text, NO logos...",
    "bg_tone": "dark|light|mid",
    "color_overlay": { "active": false, "color": "#HEX de marca", "opacity": 0.10 },
    "logo": { "treatment": "blanco|negro|color|watermark|banda", "position": "top_center|top_left|top_right|center|bottom_center", "scale": 0.55, "opacity": 0.15, "band_color": "#HEX o null" },
    "text_style": {
      "text_anchor": "top|center|bottom",
      "layout": "stacked|spread|staggered|billboard|vertical",
      "font_family": "nombre exacto fuente de marca o null",
      "recipient_color": "#HEX",
      "headline_color": "#HEX",
      "subtitle_color": "#HEX",
      "recipient_size_ratio": 0.16,
      "headline_size_ratio": 0.065,
      "subtitle_size_ratio": 0.040,
      "recipient_alignment": "left|center|right",
      "headline_alignment": "left|center|right",
      "subtitle_alignment": "left|center|right",
      "recipient_uppercase": false,
      "spacing_scale": 1.0
    },
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

    # Retry hasta 2 veces para errores 500 transitorios de Anthropic
    ultimo_error = None
    for intento in range(2):
        try:
            respuesta = client.messages.create(
                model=MODELO_CLAUDE,
                max_tokens=6000,
                temperature=temperatura,
                system=system_prompt,
                messages=mensajes,
            )
            break
        except anthropic.APIStatusError as e:
            ultimo_error = e
            if e.status_code == 500 and intento == 0:
                print(f"  [{etiqueta}] Error 500 de Anthropic — reintentando...")
                import time; time.sleep(3)
            else:
                raise
    else:
        raise ultimo_error

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
    typo           = brand_analysis.get("typography", {})
    google_font = typo.get("google_fonts_name")   # solo fuentes descargables
    brand_tone  = brand_analysis.get("brand_tone", "institucional")

    if google_font:
        font_estrategia = (
            f"ESTRATEGIA DE FUENTES — varía obligatoriamente entre propuestas:\n"
            f"  P1: '{google_font}' — fuente de marca exacta, fidelidad total\n"
            f"  P2: '{google_font}' — fuente de marca exacta, variante de layout\n"
            f"  P3: fuente creativa/condensada que contraste con la marca — "
            f"elige según brand_tone '{brand_tone}': "
            f"institucional→'Barlow Condensed', moderno→'Exo 2', lujo→'Cormorant Garamond', "
            f"sostenible→'Josefin Sans', tech→'Rajdhani'\n"
            f"  P4: fuente display/impactante muy diferente — "
            f"institucional→'Oswald', moderno→'Bebas Neue', lujo→'Playfair Display', "
            f"sostenible→'Nunito', tech→'Orbitron'\n"
            f"  P5: fuente editorial o experimental — "
            f"institucional→'Libre Baskerville', moderno→'DM Serif Display', "
            f"lujo→'Cormorant', sostenible→'Lora', tech→'Space Grotesk'\n"
            f"  P6: '{google_font}' — vuelta a la marca con tratamiento distinto\n"
            f"Escribe el nombre EXACTO de Google Fonts en font_family de cada propuesta."
        )
    else:
        font_estrategia = (
            f"ESTRATEGIA DE FUENTES — fuente de marca no disponible en Google Fonts:\n"
            f"  P1, P2: null (usa fuente del sistema, fiel a la marca)\n"
            f"  P3: fuente condensada creativa según brand_tone '{brand_tone}': "
            f"institucional→'Barlow Condensed', moderno→'Exo 2', lujo→'Cormorant Garamond'\n"
            f"  P4: fuente display impactante: institucional→'Oswald', moderno→'Bebas Neue', lujo→'Playfair Display'\n"
            f"  P5: fuente editorial: institucional→'Libre Baskerville', moderno→'DM Serif Display', lujo→'Cormorant'\n"
            f"  P6: null (fiel a la marca)"
        )

    content.append({"type": "text", "text": (
        f"ANÁLISIS DE MARCA:\n{json.dumps(brand_analysis, ensure_ascii=False, indent=2)}\n\n"
        f"TEXTO EXACTO DEL GALARDÓN (úsalo literalmente en award_text):\n"
        f"- Nombre del premiado : {recipient_txt}\n"
        f"- Nombre del premio   : {headline_txt}\n"
        f"- Organización        : {subtitle_txt}\n"
        f"{fecha_line}\n"
        f"- Evento              : {evento.get('nombre', '')}\n\n"
        f"{font_estrategia}\n\n"
        "Genera los 6 conceptos. Incluye estos textos literalmente en award_text."
    )})

    resultado = _llamar_claude(
        [{"role": "user", "content": content}],
        PROMPT_B_DESIGN_CONCEPTS,
        "DesignConcepts",
        temperatura=1.0,  # máxima creatividad
    )
    return resultado if isinstance(resultado, list) else []


# ─── Validación ───────────────────────────────────────────────────────────────

def _validar_concepto(c: dict, idx: int, font_style_category: str = "",
                      secondary_color: str = "", accent_color: str = "") -> dict:
    # ── Parámetros FORZADOS — 6 arquetipos visuales distintos ──
    # Claude controla colores, dalle_prompt y award_text; el sistema controla estructura.
    # JERARQUÍA FIJA: recipient (100%) > headline (45-50%) > subtitle (22-25%)
    _anchors  = ["top",     "center",  "center",    "center",   "top",     "center"]
    _layouts  = ["stacked", "spread",  "staggered", "billboard","spread",  "stacked"]
    # P1 PREMIUM OSCURO:   stacked LEFT zone  — texto anclado izquierda
    # P2 EDITORIAL BLANCO: spread FULL WIDTH  — editorial centrado
    # P3 GRÁFICO AUDAZ:    staggered FULL     — barra izquierda + texto diagonal
    # P4 BILLBOARD:        billboard CENTER   — nombre domina el canvas
    # P5 MÍNIMO MODERNO:   spread RIGHT zone  — texto anclado derecha
    # P6 MARCA PURA:       stacked CENTER     — identidad simétrica
    _rec_sz   = [0.18,      0.22,      0.20,        0.22,       0.18,      0.16]
    _hl_sz    = [0.090,     0.100,     0.082,       0.090,      0.085,     0.080]
    _sub_sz   = [0.040,     0.048,     0.038,       0.042,      0.040,     0.037]
    _spacing  = [1.2,       0.8,       0.6,         0.8,        1.0,       1.6]
    _upper    = [False,     True,      True,        True,       False,     False]
    # Alineaciones: P1 izquierda, P3 diagonal, P5 derecha, resto centrado
    _hl_alns  = ["left",    "center",  "right",     "center",   "right",   "center"]
    _rec_alns = ["left",    "center",  "left",      "center",   "right",   "center"]
    _sub_alns = ["left",    "center",  "right",     "center",   "right",   "center"]

    # ── Defaults (solo se aplican si Claude no proporcionó el campo) ───────────
    _rec_cols = ["#FFFFFF", "#FFD700", "#FFFFFF", "#FFD700", "#FFFFFF", "#E0E0E0"]
    _hl_cols  = ["#FFD700", "#FFFFFF", "#FFFFFF", "#E0E0E0", "#FFD700", "#FFFFFF"]
    _sub_cols = ["#BBBBBB", "#AAAAAA", "#CCCCCC", "#999999", "#AAAAAA", "#BBBBBB"]

    i6 = idx % 6

    # Aplicar defaults para campos que Claude no generó
    defaults = {
        "proposal_id":      idx + 1,
        "pattern_name":     f"Concepto {idx + 1}",
        "design_rationale": "Diseño corporativo premium.",
        "dalle_prompt":     "Deep navy abstract corporate background, geometric shapes, premium. No text, no logos, no people. Premium award background.",
        "bg_tone":          "dark",
        "color_overlay":    {"active": False, "color": "#1A1A1A", "opacity": 0.15},
        "logo":             {"treatment": "blanco", "position": "top_center", "scale": 0.55},
        "text_style":       {
            "font_family":          None,
            "margin_h":             0.08,
            "recipient_color":      _rec_cols[i6],
            "headline_color":       _hl_cols[i6],
            "subtitle_color":       _sub_cols[i6],
        },
        "award_text": {"headline": "Excellence Award", "recipient": "Nombre Apellido", "subtitle": "Organización"},
    }
    for k, v in defaults.items():
        if k not in c or c[k] is None:
            c[k] = v
        elif isinstance(v, dict):
            for sk, sv in v.items():
                if sk not in c[k] or c[k][sk] is None:
                    c[k][sk] = sv

    # Forzar siempre la estructura tipográfica y layout del slot — garantía de variedad
    ts = c.setdefault("text_style", {})
    ts["layout"]               = _layouts[i6]
    ts["text_anchor"]          = _anchors[i6]
    ts["recipient_size_ratio"] = _rec_sz[i6]
    ts["headline_size_ratio"]  = _hl_sz[i6]
    ts["subtitle_size_ratio"]  = _sub_sz[i6]
    ts["spacing_scale"]        = _spacing[i6]
    ts["recipient_uppercase"]  = _upper[i6]
    ts["recipient_alignment"]  = _rec_alns[i6]
    ts["headline_alignment"]   = _hl_alns[i6]
    ts["subtitle_alignment"]   = _sub_alns[i6]
    # Propagar categoría de estilo tipográfico al renderer para fallback inteligente
    if font_style_category:
        ts["font_style_category"] = font_style_category

    # Propagar colores de marca secundario/acento — el renderer los usa como
    # color estructural en barras, bandas y elementos decorativos grandes.
    if secondary_color:
        c["_secondary"] = secondary_color
    if accent_color:
        c["_accent"] = accent_color

    # Forzar fondo sólido (sin DALLE) para P2, P5, P6
    if i6 in (1, 4, 5):
        c["dalle_prompt"] = ""

    # Garantía de no colisión logo–texto:
    # - "center" solo permitido para watermark (semi-transparente, intencional)
    # - cualquier logo opaco en "center" se mueve a top_center
    logo = c.setdefault("logo", {})
    if logo.get("position") == "center" and logo.get("treatment") != "watermark":
        logo["position"] = "top_center"

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
    typo = brand_analysis.get("typography", {})
    style_cat = typo.get("font_style_category", "")
    print(f"  → Fuente  : {typo.get('google_fonts_name', '—')} [{style_cat or '?'}]")

    secondary_col = colores.get("secondary", "") or ""
    accent_col    = colores.get("accent", "")    or ""

    print(f"\n[B] Design Concepts (ejemplos acumulados: {n_aprendizaje})...")
    conceptos = _llamada_design_concepts(pedido, brand_analysis)
    conceptos = [_validar_concepto(c, i, style_cat, secondary_col, accent_col)
                 for i, c in enumerate(conceptos[:6])]
    while len(conceptos) < 6:
        conceptos.append(_validar_concepto({}, len(conceptos), style_cat,
                                           secondary_col, accent_col))

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
