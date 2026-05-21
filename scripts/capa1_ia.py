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
import random
import hashlib
from pathlib import Path
import base64

import anthropic

from scripts.capa0_normalizer import _consolidar_colores_hsv as _consolidar_hsv
from scripts.config import (
    MODEL_BRAND_ANALYSIS, TEMP_BRAND_ANALYSIS,
    MODEL_DESIGN_CONCEPTS, TEMP_DESIGN_CONCEPTS,
    MODEL_COLOR_ORACLE, TEMP_COLOR_ORACLE,
)

PROJECT_ROOT    = Path(__file__).resolve().parent.parent
DATA_DIR        = PROJECT_ROOT / "data"
SPECS_DIR       = PROJECT_ROOT / "outputs" / "design_specs"
APRENDIZAJE_DIR = PROJECT_ROOT / "assets" / "aprendizaje"
REFERENCIAS_DIR = PROJECT_ROOT / "assets" / "referencias"


# ─── Prompts ──────────────────────────────────────────────────────────────────

PROMPT_COLOR_ORACLE = """\
You are a brand color specialist. Your ONLY task: identify the 2-3 canonical brand colors.

You will receive a logo image, optionally a web screenshot, and optionally a list of
algorithmically pre-filtered color candidates extracted from CSS and hero pixels.

Return EXCLUSIVELY valid JSON, no markdown, no explanation:

{"canonical_colors": ["#HEX_primary", "#HEX_secondary"], "confidence": "high|medium|low"}

RULES (non-negotiable):
1. Return EXACTLY 2 or 3 colors. Never 1, never more than 3.
2. First color = PRIMARY: the most prominent brand color. Usually the main header or CTA
   background color, the color that most defines the brand visually.
3. Second color = the most visually different secondary/accent. Must differ from primary
   by more than 30 degrees of hue OR belong to a clearly different lightness tier
   (e.g., dark navy + bright yellow = valid pair).
4. Third color ONLY if there is an unmistakably distinct third canonical brand color.
   When in doubt, omit it — 2 is better than 3 wrong.
5. NEVER include near-white (#F0F0F0 or lighter), near-black (#222222 or darker), or
   neutral grays (#707070 ± 25) in the canonical list.
6. If the web screenshot shows a clearly colored hero/header background — that color
   is almost certainly the PRIMARY (not the logo color on top of it).
7. IGNORE the logo wordmark text color. A logo may be rendered in white or black while
   the brand identity color is something entirely different.
8. If the extracted candidates list contains near-duplicate colors (same hue family),
   keep only the most saturated/vivid representative of each family.
9. Respond with ONLY the JSON object.\
"""

PROMPT_A_BRAND_ANALYSIS = """\
Eres un analista senior de identidad visual. Analiza todos los assets proporcionados \
(logotipo, manual de marca y/o datos web) y extrae el vocabulario visual completo.

Devuelve EXCLUSIVAMENTE un JSON válido, sin texto adicional, sin markdown:

{
  "brand_name": "nombre de la marca",
  "brand_tone": "formal|sostenible|tecnologico|deportivo|cultural|institucional|moderno|lujo|salud|farmacia",
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

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JERARQUÍA DE FUENTES PARA COLOR (síguela en orden estricto):
  1. "PALETA CANÓNICA VERIFICADA" → si aparece en el mensaje, es la verdad definitiva.
     Copia esos valores exactamente en primary, secondary, accent y colors_extended.
     No los valides, no los modifiques, no los fusiones con otras fuentes.
  2. Brandbook PDF → si no hay paleta canónica, el PDF es la fuente más fiable.
     Sus colores HEX son los colores reales de la marca.
  3. Web (CSS + colores hero) → si no hay PDF ni paleta canónica, usar colores de la web.
     El color del hero/banner refleja la identidad real que la marca muestra al mundo.
  4. Logo → SOLO para tipografía y forma del símbolo. NUNCA para colores de paleta.
     El logo puede ser negro, blanco o arbitrario — no representa la paleta de marca.
     Excepción: si solo hay logo y ninguna otra fuente, deducir colores del logo.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Si recibes "FUENTE CORPORATIVA DISPONIBLE LOCALMENTE: 'X'", escribe X exactamente en typography.font_name y google_fonts_name. No busques alternativa.
- Si recibes "EXTRACCIÓN AUTOMÁTICA DEL BRANDBOOK", esos HEX son colores reales del PDF — úsalos directamente en primary, secondary, accent.
- "COLORES HEX DEL BRANDBOOK" lista por frecuencia: el primero suele ser primary, el segundo secondary.
- primary: el color corporativo más prominente de la fuente más fiable disponible.
- secondary: el segundo color claramente diferenciado del primario.
- accent: busca colores de acento — amarillos, dorados, naranja, CTA. Muchas marcas combinan un azul principal con un amarillo o naranja de alta energía como acento. Null solo si no existe ningún color de contraste real.
- colors_extended: máx. 6 HEX únicos ordenados por importancia visual. Sin duplicados.
- primary_tint: primario + 35% blanco. primary_shade: primario + 30% negro.
- CUANDO HAY SCREENSHOT: identifica el color dominante del hero/banner. Ese color
  suele ser el PRIMARY, no el color del texto del logo. El logo puede ser blanco
  sobre un fondo de marca azul, rojo, verde, etc. — el fondo es el primary.
- Si no hay ninguna fuente salvo logo: deduce colores y fuente del logo.
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
                   etiqueta: str, temperatura: float = 1.0,
                   model: str | None = None) -> dict | list:
    import time as _time
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY no encontrada.\n"
            "  Configúrala con: set ANTHROPIC_API_KEY=sk-ant-..."
        )

    modelo = model or MODEL_DESIGN_CONCEPTS
    # Contar imágenes en el mensaje para dar contexto de lo que se envía
    _n_imgs = sum(1 for m in mensajes for b in (m.get("content") or [])
                  if isinstance(b, dict) and b.get("type") == "image")
    _temp_str = f"temp={temperatura}" if not modelo.startswith("claude-opus-4") else "temp=default"
    print(f"  [{etiqueta}] → Llamando {modelo}  ({_temp_str}"
          + (f", {_n_imgs} imágenes" if _n_imgs else "") + ") ...")
    _t0 = _time.time()

    client = anthropic.Anthropic(api_key=api_key)

    # Retry hasta 2 veces para errores 500 transitorios de Anthropic
    ultimo_error = None
    for intento in range(2):
        try:
            _params = dict(model=modelo, max_tokens=6000,
                           system=system_prompt, messages=mensajes)
            if not modelo.startswith("claude-opus-4"):
                _params["temperature"] = temperatura
            respuesta = client.messages.create(**_params)
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

    _elapsed = _time.time() - _t0
    _usage   = respuesta.usage
    print(f"  [{etiqueta}] ✓ Respuesta recibida en {_elapsed:.1f}s  "
          f"(tokens: {_usage.input_tokens} in / {_usage.output_tokens} out)")

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


# ─── Color Oracle — Paleta canónica ──────────────────────────────────────────

def _llamada_color_oracle(brand_context: dict) -> list[str]:
    """
    Llamada ligera a Claude Haiku (temp=0) para identificar los 2-3 colores
    canónicos reales de la marca. Inputs: logo, screenshot web, pre_palette HSV.
    Devuelve lista de 2-3 HEX validados, o [] si los inputs son insuficientes
    o la llamada falla (no crítico — el pipeline continúa sin ella).
    """
    content = []

    if brand_context.get("logo_b64"):
        content.append({"type": "image", "source": {
            "type": "base64",
            "media_type": brand_context["logo_type"],
            "data": brand_context["logo_b64"],
        }})

    if brand_context.get("url_screenshot_b64"):
        content.append({"type": "image", "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": brand_context["url_screenshot_b64"],
        }})

    pre = brand_context.get("pre_palette", [])
    if pre:
        content.append({"type": "text", "text": (
            f"Algorithmically pre-filtered color candidates "
            f"(from CSS variables, meta theme-color, and hero pixel sampling):\n"
            f"  {', '.join(pre)}\n"
            f"These are already consolidated — near-duplicates have been merged."
        )})

    if not content:
        return []

    content.append({"type": "text",
                    "text": "Identify the 2-3 canonical brand colors from the assets above."})

    try:
        resultado = _llamar_claude(
            [{"role": "user", "content": content}],
            PROMPT_COLOR_ORACLE,
            "ColorOracle",
            temperatura=TEMP_COLOR_ORACLE,
            model=MODEL_COLOR_ORACLE,
        )
        if isinstance(resultado, dict):
            cols = [
                c for c in resultado.get("canonical_colors", [])
                if isinstance(c, str) and c.startswith("#") and len(c) == 7
            ]
            if 2 <= len(cols) <= 3:
                conf = resultado.get("confidence", "?")
                print(f"  [ColorOracle] ✓ {cols}  (confianza: {conf})")
                return cols
            else:
                print(f"  [ColorOracle] Resultado fuera de rango ({len(cols)} colores) — ignorado")
    except Exception as e:
        print(f"  [ColorOracle] Error (no crítico, continuando sin paleta canónica): {e}")

    return []


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
    canonical = brand_context.get("canonical_palette", [])

    # ── Datos web — qué se envía depende de si ya tenemos paleta canónica ──────
    # Cuando canonical_palette está definida (Firecrawl o Color Oracle), los colores
    # ya son la fuente de verdad. Solo se envían datos de estilo/contexto web, no
    # listas de colores crudos redundantes que confundirían a Claude.
    # Cuando NO hay canonical_palette, se envía todo para que Claude pueda extraer.

    if url_data.get("ok"):
        _cols = url_data.get('colores_detectados', [])
        if canonical:
            # Con paleta canónica: solo información de estilo (no colores — ya los tenemos)
            url_texto = (
                f"\nWEB CORPORATIVA ({url_data.get('url', '')}):\n"
                f"- Estilo visual: {url_data.get('descripcion_estilo', '—')}\n"
                f"- Densidad: {url_data.get('densidad_visual', '—')} | "
                f"Gradientes: {'sí' if url_data.get('tiene_gradientes') else 'no'}\n"
            )
        else:
            # Sin paleta canónica: enviar todo — Claude necesita los colores
            _cols_str = ', '.join(_cols[:6]) if _cols else '(ninguno detectado en CSS)'
            url_texto = (
                f"\nWEB CORPORATIVA ({url_data.get('url', '')}):\n"
                f"- Colores CSS (variables, meta theme-color, inline styles): {_cols_str}\n"
                f"- Estilo: {url_data.get('descripcion_estilo', '—')}\n"
            )
            hero_colors = brand_context.get("url_hero_colors", [])
            if hero_colors:
                url_texto += (
                    f"- COLORES HERO DE LA WEB (píxeles del banner/cabecera): {', '.join(hero_colors)}\n"
                    f"  → Son la fuente más fiable cuando no hay brandbook.\n"
                    f"  → Úsalos como primary/secondary/accent (ignorando el color del logo).\n"
                )

    # Screenshot: solo cuando no hay paleta canónica (da referente visual a Claude)
    url_screenshot_b64 = brand_context.get("url_screenshot_b64")
    if url_screenshot_b64 and not canonical:
        content.append({"type": "text", "text": (
            "SCREENSHOT VISUAL DE LA WEB CORPORATIVA.\n"
            "Identifica el color dominante del HERO/BANNER (zona superior).\n"
            "Ese color es el PRIMARY de la marca — NO el color del texto del logotipo.\n"
            "Busca el color del FONDO de la cabecera, no el color del texto sobre ella."
        )})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg",
            "data": url_screenshot_b64,
        }})

    # Tipografías de Firecrawl (guía, no mandatorio — brandbook tiene prioridad)
    fc_fonts = brand_context.get("firecrawl_fonts", {})
    if fc_fonts.get("heading"):
        content.append({"type": "text", "text": (
            f"TIPOGRAFÍAS DETECTADAS POR FIRECRAWL:\n"
            f"  Heading: {fc_fonts['heading']} | Body: {fc_fonts.get('body', '—')}\n"
            f"Si el brandbook especifica otra fuente, el brandbook tiene prioridad."
        )})

    # Paleta canónica — verdad absoluta cuando está disponible
    if canonical:
        _c0 = canonical[0]
        _c1 = canonical[1] if len(canonical) > 1 else canonical[0]
        _c2 = canonical[2] if len(canonical) > 2 else "null"
        content.append({"type": "text", "text": (
            f"PALETA CANÓNICA VERIFICADA — VERDAD ABSOLUTA:\n"
            f"  primary   = {_c0}\n"
            f"  secondary = {_c1}\n"
            f"  accent    = {_c2}\n"
            f"  colors_extended = exactamente {json.dumps(canonical)}\n\n"
            f"INSTRUCCIÓN: usa estos valores exactos. No añadas ni quites colores. "
            f"colors_extended debe contener únicamente estos {len(canonical)} colores."
        )})

    award  = pedido.get("award", {})
    evento = pedido.get("evento", {})
    _prioridad = ("PRIORIDAD DE FUENTES: paleta canónica verificada > brandbook PDF > web > logo."
                  if canonical else
                  "PRIORIDAD: brandbook PDF > colores web/hero > logo.")
    content.append({"type": "text", "text": (
        f"DATOS:\n- Empresa: {pedido.get('id_cliente', '—')}\n"
        f"- Evento: {evento.get('nombre', '—')}\n"
        f"- Premio: {award.get('headline', '—')}\n{url_texto}"
        f"{_prioridad}\n"
        "Analiza los assets y extrae el vocabulario visual completo."
    )})

    resultado = _llamar_claude(
        [{"role": "user", "content": content}],
        PROMPT_A_BRAND_ANALYSIS,
        "BrandAnalysis",
        temperatura=TEMP_BRAND_ANALYSIS,
        model=MODEL_BRAND_ANALYSIS,
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


# ─── Guardado ─────────────────────────────────────────────────────────────────

def guardar_spec(spec: dict, id_pedido: str) -> Path:
    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    ruta = SPECS_DIR / f"{id_pedido}_design_spec.json"
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    return ruta


# ─── Agente 3 — Hormigón y Acero (monolito) ──────────────────────────────────

PROMPT_B_HORMIGON_ACERO = """\
Eres el director creativo de un estudio de galardones corporativos de alta gama especializado
en escultura monolítica de hormigón. Tu trabajo: diseñar 3 propuestas de trofeo físico.

━━━ PRINCIPIO DE DISEÑO — MONOLITO DE HORMIGÓN ━━━
Cada trofeo es un bloque único de hormigón: un solo volumen continuo, sin piezas ensambladas,
sin acero, sin color añadido. La identidad y la creatividad se expresan EXCLUSIVAMENTE mediante:
  • La FORMA del volumen (silueta, proporciones, geometría)
  • Los GRABADOS EN PROFUNDIDAD (relieves, incisiones, letras cinceladas, motivos en bajorrelieve)

━━━ PRINCIPIO — LA FORMA Y EL GRABADO NACEN DE LA MARCA ━━━
La forma del monolito debe derivar de la identidad concreta de esta marca:

  ▸ ¿Tiene la marca una letra inicial, un símbolo icónico o un logotipo reconocible?
    → La silueta exterior del trofeo puede ser ese símbolo extruido en hormigón macizo.

  ▸ ¿El sector sugiere una metáfora volumétrica?
    cervecera → barril, arco, letra inicial | banca → pilar, arco, volumen institucional
    tecnología → cubo, nodo, torre | sostenible → forma orgánica, piedra erosionada

  ▸ ¿La estética del brandbook sugiere formas?
    brutalismo → bloque macizo | geometría suiza → prisma preciso | art déco → pirámide

FORMAS MONOLÍTICAS DE REFERENCIA (no obligatorias):
  Prismáticas:    bloque_rectangular | prisma_esbelto | cubo_macizo | trapezoide | losa_inclinada
  Cilíndricas:    cilindro_vertical | medio_cilindro | totem_circular | disco_grueso
  Tipográficas:   símbolo_logo_extruido | letra_inicial_maciza | siglas_monumentales
  Orgánicas:      masa_erosionada | guijarro_monumental | forma_irregular_tallada
  Arquitectónicas: pilar_monolítico | estela | obelisco_truncado | dintel | arco_macizo
  Geométricas:    pentágono_extruido | hexágono_macizo | rombo_vertical
  Escultóricas:   torsión_suave | forma_cóncava | cuña_angular | masa_asimétrica_estable

━━━ TRATAMIENTOS DE GRABADO ━━━
  "grabado_profundo" | "bajorrelieve_logo" | "tipografia_cincelada" | "geometria_incisa" | "textura_selectiva"

━━━ TRATAMIENTOS DE TEXTO ━━━
  "grabado_bajo_relieve" | "tipografia_cincelada" | "fundido_en_masa"

━━━ REGLAS ━━━
  □ 3 formas completamente distintas entre sí
  □ Al menos una usa la silueta o símbolo del logo como forma exterior
  □ Los 3 grabado_treatment diferentes
  □ PROHIBIDO: múltiples piezas, acero, color, incrustaciones, elementos flotantes

JERARQUÍA DEL TEXTO (grabado en superficie):
  1. Nombre del premiado (recipient) — grabado más prominente
  2. Nombre del premio (headline)
  3. Nombre de la organización (subtitle)

━━━ CAMPO forma_descripcion_prompt ━━━
Descripción en INGLÉS del trofeo para el generador de imagen. Reglas:
  1. Siempre empezar con "Single monolithic block of refined grey concrete —"
  2. MATERIAL: mencionar "raw grey CONCRETE (rough porous surface, visible aggregate)"
  3. TIPOGRAFÍA: si es letra/símbolo, especificar estilo exacto ("blackletter fractur", "bold geometric sans-serif")
  4. CONTEOS: "EXACTLY N (word) [forma exacta]" para elementos repetidos
  5. CONECTIVIDAD: si hay letras con partes no conectadas (punto de la "i", etc.) → usar bajorrelieve
  6. Terminar con "no floating elements, all parts attached to the base"

Ejemplo correcto:
  "Single monolithic block of refined grey concrete — tall rectangular prism.
   Front face has EXACTLY 5 (five) classic 5-pointed stars carved 6mm deep in a row.
   Lower third has award text engraved in Roman capitals. No floating elements."

Devuelve EXCLUSIVAMENTE un JSON array de 3 conceptos, sin markdown:

[
  {
    "proposal_id": 1,
    "pattern_name": "nombre evocador 2-3 palabras en español",
    "design_rationale": "por qué esta forma refleja la identidad de ESTA marca (1 frase)",
    "forma_escultorica": "nombre descriptivo del volumen",
    "forma_descripcion_prompt": "English physical description starting with 'Single monolithic block...'",
    "grabado_treatment": "grabado_profundo|bajorrelieve_logo|tipografia_cincelada|geometria_incisa|textura_selectiva",
    "text_treatment": "grabado_bajo_relieve|tipografia_cincelada|fundido_en_masa",
    "award_text": {
      "headline": "nombre del premio exacto",
      "recipient": "nombre del premiado exacto",
      "subtitle": "nombre de la organización — NUNCA el organizador del evento"
    }
  },
  { "proposal_id": 2, ... },
  { "proposal_id": 3, ... }
]

Responde SOLO con el JSON array.\
"""

_FORMAS_VALIDAS = {
    "bloque_rectangular", "prisma_esbelto", "cubo_macizo", "trapezoide", "losa_inclinada",
    "cilindro_vertical", "medio_cilindro", "totem_circular", "disco_grueso",
    "simbolo_logo_extruido", "letra_inicial_maciza", "siglas_monumentales",
    "masa_erosionada", "guijarro_monumental", "forma_irregular_tallada",
    "pilar_monolitico", "estela", "obelisco_truncado", "dintel", "arco_macizo",
    "pentágono_extruido", "hexágono_macizo", "rombo_vertical",
    "torsión_suave", "forma_cóncava", "cuña_angular", "masa_asimétrica_estable",
    # Legacy
    "columnar", "abstracto", "tipografico", "arquitectonico", "organico",
}
_FORMAS_FALLBACK = ["bloque_rectangular", "prisma_esbelto", "cubo_macizo",
                    "losa_vertical", "estela", "forma_irregular_tallada"]

_PERSPECTIVAS_FORMA = [
    "símbolo tipográfico: letra inicial o logotipo de la marca como cuerpo del trofeo",
    "metáfora sectorial: forma que evoca el sector industrial de la marca",
    "esencia del brandbook: la estética visual del manual traducida a volumen",
    "abstracción cromática: la forma surge del contraste entre los colores de marca",
    "monumentalidad minimal: bloque macizo con relieve del elemento más icónico de la marca",
    "tensión estructural: piezas separadas unidas por el color de marca como elemento conector",
    "silueta corporativa: la forma exterior del logo o símbolo extruida en hormigón",
    "geometría de marca: las formas geométricas que definen la identidad visual, en volumen",
    "referencia cultural: elemento del patrimonio cultural del sector de la marca",
    "dinamismo y dirección: forma que transmite el movimiento o valor más representativo de la marca",
]


def _llamada_design_concepts_hormigon_acero(
    pedido: dict,
    brand_analysis: dict,
    canonical_palette: list | None = None,
    brand_context: dict | None = None,
) -> list:
    """Genera 3 formas escultóricas monolíticas derivadas de la identidad de marca."""
    import uuid as _uuid
    award  = pedido.get("award", {})
    evento = pedido.get("evento", {})
    ctx    = brand_context or {}

    run_id        = _uuid.uuid4().hex[:10]
    recipient_txt = award.get("recipient") or "Nombre del Premiado"
    headline_txt  = award.get("headline")  or "Excellence Award"
    subtitle_txt  = award.get("subtitle")  or "Sustain Awards"
    fecha_line    = f"\n- Fecha/Año: {award.get('fecha', '')}" if award.get("fecha") else ""

    perspectivas = random.Random(run_id).sample(_PERSPECTIVAS_FORMA, min(3, len(_PERSPECTIVAS_FORMA)))

    content = []

    semilla_txt = (
        f"SEMILLA CREATIVA (run_id={run_id}):\n"
        f"  P1 → explorar desde: \"{perspectivas[0]}\"\n"
        f"  P2 → explorar desde: \"{perspectivas[1]}\"\n"
        f"  P3 → explorar desde: \"{perspectivas[2]}\"\n"
    )
    content.append({"type": "text", "text": semilla_txt})

    if ctx.get("logo_b64") and ctx.get("logo_type"):
        content.append({"type": "image", "source": {
            "type": "base64",
            "media_type": ctx["logo_type"],
            "data": ctx["logo_b64"],
        }})
        content.append({"type": "text", "text": (
            "Logo de la marca (imagen anterior). Analiza:\n"
            "  - Letra inicial o símbolo: estilo tipográfico exacto\n"
            "  - Elementos contables: cuenta el número EXACTO\n"
            "  - Topología: ¿partes no conectadas? → usar bajorrelieve en vez de extrusión\n"
            "Al menos una propuesta debe materializar un elemento de este logo.\n"
            "En forma_descripcion_prompt: empieza con 'Single monolithic block of refined grey concrete —'"
        )})

    brand_name = brand_analysis.get("brand_name", "")
    content.append({"type": "text", "text": (
        f"ANÁLISIS DE MARCA:\n{json.dumps(brand_analysis, ensure_ascii=False)}\n\n"
        f"TEXTO DEL GALARDÓN:\n"
        f"- Premiado   : {recipient_txt}\n"
        f"- Premio     : {headline_txt}\n"
        f"- Organización: {subtitle_txt}\n"
        f"{fecha_line}\n"
        f"- Evento     : {evento.get('nombre', '')}\n\n"
        f"Genera 3 formas monolíticas distintas y representativas de {brand_name or 'esta marca'}. "
        f"Usa EXACTAMENTE los textos indicados en award_text."
    )})

    print(f"  [DesignConceptsMaterial] run_id={run_id} · perspectivas: {[p[:35] for p in perspectivas]}")

    resultado = _llamar_claude(
        [{"role": "user", "content": content}],
        PROMPT_B_HORMIGON_ACERO,
        "DesignConceptsMaterial",
        temperatura=TEMP_DESIGN_CONCEPTS,
        model=MODEL_DESIGN_CONCEPTS,
    )
    return resultado if isinstance(resultado, list) else []


def _validar_concepto_material(c: dict, idx: int) -> dict:
    """Valida y normaliza un concepto de Hormigón y Acero."""
    c.setdefault("proposal_id", idx + 1)
    c.setdefault("pattern_name", f"Propuesta {idx + 1}")
    c.setdefault("design_rationale", "")
    c.setdefault("grabado_treatment", "grabado_profundo")
    c.setdefault("text_treatment", "grabado_bajo_relieve")
    c.setdefault("color_treatment", "acero_pintado")
    c.setdefault("award_text", {})

    if not c.get("forma_escultorica"):
        c["forma_escultorica"] = _FORMAS_FALLBACK[idx % len(_FORMAS_FALLBACK)]

    if not c.get("forma_descripcion_prompt"):
        forma = c.get("forma_escultorica", "abstract monolithic form")
        c["forma_descripcion_prompt"] = (
            f"Single monolithic block of refined grey concrete — {forma} shape. "
            "Raw portland cement surface with visible aggregate. Studio white background. "
            "No floating elements, all parts attached to the base."
        )
    return c


def diseñar_desde_contexto_material(
    pedido: dict,
    brand_context: dict,
    material_config: dict,
) -> tuple[list, dict]:
    """
    Pipeline de Capa 1 para Agente 3 — trofeos monolíticos de hormigón.

    Color omitido intencionalmente: el trofeo es siempre hormigón gris puro.
    Solo se usa Brand Analysis para entender sector, identidad visual y
    tipografía del logo — la información que guía la FORMA escultórica.

    Devuelve (conceptos[3], spec_completo).
    """
    id_pedido       = pedido.get("id_pedido", "TEST")
    material_nombre = material_config.get("nombre", "Material")

    print(f"\n{'─'*50}")
    print(f"  CAPA 1 · Agente 3 — {material_nombre}  [A:{MODEL_BRAND_ANALYSIS} / B:{MODEL_DESIGN_CONCEPTS}]")
    print(f"  Pedido: {id_pedido}")
    print(f"  Modo: hormigón gris puro — Color Oracle y Firecrawl omitidos")
    print(f"{'─'*50}")

    # Color Oracle y Firecrawl omitidos en Agente 3:
    # El trofeo es siempre hormigón gris monocromático — los colores de marca
    # no se aplican al objeto físico, por lo que extraerlos es innecesario.
    brand_context["canonical_palette"] = []

    # ── Brand Analysis ────────────────────────────────────────────────────────────
    # Se mantiene para conocer: sector, tono de marca, estilo tipográfico del logo.
    # Esta información guía la elección de la FORMA escultórica, no el color.
    print("\n[A] Brand Analysis (identidad visual — sin colores)...")
    brand_analysis = _llamada_brand_analysis(pedido, brand_context)

    brand_name = brand_analysis.get("brand_name", "—")
    brand_tone = brand_analysis.get("brand_tone", "—")
    typo       = brand_analysis.get("typography", {})
    print(f"  Marca: {brand_name} · Tono: {brand_tone} · Fuente: {typo.get('font_name','—')}")

    # ── Design Concepts — Formas Escultóricas (3 propuestas) ─────────────────────
    print(f"\n[B] Design Concepts — Formas {material_nombre} (3 propuestas)...")
    conceptos = _llamada_design_concepts_hormigon_acero(
        pedido, brand_analysis,
        canonical_palette=[],
        brand_context=brand_context,
    )
    conceptos = [
        _validar_concepto_material(c, i)
        for i, c in enumerate(conceptos[:3])
    ]

    # Forzar textos del cliente si los proporcionó
    _award_input = pedido.get("award", {})
    _hl_fixed  = _award_input.get("headline", "").strip()
    _rec_fixed = _award_input.get("recipient", "").strip()
    _sub_fixed = _award_input.get("subtitle", "").strip()
    if _hl_fixed or _rec_fixed or _sub_fixed:
        for c in conceptos:
            at = c.setdefault("award_text", {})
            if _hl_fixed:  at["headline"]  = _hl_fixed
            if _rec_fixed: at["recipient"] = _rec_fixed
            if _sub_fixed: at["subtitle"]  = _sub_fixed

    while len(conceptos) < 3:
        conceptos.append(_validar_concepto_material({}, len(conceptos)))

    print(f"\n  ┌── Formas generadas ─────────────────────────────")
    for c in conceptos:
        print(f"  │  P{c['proposal_id']}: {c['pattern_name']}")
        print(f"  │       forma    : {c.get('forma_escultorica','?')}")
        print(f"  │       grabado  : {c.get('grabado_treatment','?')}")
        print(f"  │       rationale: {c.get('design_rationale','')[:70]}")
    print(f"  └────────────────────────────────────────────────")

    spec = {
        "id_pedido":      id_pedido,
        "material":       material_config.get("id", ""),
        "brand_analysis": brand_analysis,
        "design_concepts": conceptos,
    }
    ruta = guardar_spec(spec, id_pedido)
    print(f"  → Spec: {ruta.name}")

    return conceptos, spec
