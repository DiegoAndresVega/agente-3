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
    USE_FEW_SHOT, MAX_FEW_SHOT,
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

PROMPT_B_DESIGN_CONCEPTS = """\
Eres el director creativo de una agencia premium de galardones corporativos.
Tu trabajo: generar 6 conceptos de diseño radicalmente distintos para un trofeo/galardón.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESTRICCIONES TÉCNICAS DE IMPRESIÓN UV — SUSTAIN AWARDS (OBLIGATORIAS)
Estos diseños se imprimen con UV sobre metal, madera o piedra. Las siguientes reglas
son requisitos técnicos, no preferencias estéticas. Incumplirlas produce defectos físicos.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RESTRICCIÓN 1 — FONDOS OSCUROS SÓLIDOS (CRÍTICO):
  PROHIBIDO usar un fondo completamente negro o color sólido muy oscuro (#000000–#222222).
  Los rellenos oscuros densos generan variación de textura en la tinta UV sobre metal.
  PERMITIDO: gradientes oscuros (de muy oscuro a menos oscuro), fondos con profundidad visual.
  P1 y P3 deben usar gradientes o texturas visuales, nunca un sólido plano negro.

RESTRICCIÓN 2 — EFECTOS METÁLICOS (CRÍTICO):
  PROHIBIDO describir en dalle_prompt: "metallic", "gold foil", "silver chrome", "reflective ink",
  "brushed metal surface", "mirror finish" como si fueran tintas reales.
  La impresión UV NO soporta tintas metálicas reales.
  PERMITIDO: simular metálico con gradientes, highlights y patrones de luz — descríbelo así:
  "gradient from gold-dark to bright gold with highlight strip" (simulación visual, no tinta).

RESTRICCIÓN 3 — COLORES FLUORESCENTES:
  PROHIBIDO: colores neón puros (rosa fluorescente, verde lima eléctrico, naranja UV).
  USAR: equivalentes CMYK brillantes con saturación alta pero sin especificar "fluorescent".
  Ejemplo: en lugar de "fluorescent yellow" → "vivid warm yellow #FFD700".

RESTRICCIÓN 4 — MARGEN DE BORDES (5mm buffer):
  Todos los elementos de texto, logo y decoración deben estar a mínimo 7% del borde del canvas.
  Las decoraciones geométricas que lleguen al borde deben usar fade/gradiente hacia el extremo.
  NUNCA líneas finas de alto contraste en el límite del canvas — las derivas de corte las rompen.

RESTRICCIÓN 5 — FONDOS CLAROS = TRANSPARENTES:
  Para P2 y P5 (bg_tone=light): el fondo blanco NO se imprime — la placa metálica del trofeo
  ES el fondo. Esto es una ventaja: el metal da aspecto premium sin gastar tinta.
  Diseña el texto y logo para que funcionen DIRECTAMENTE sobre metal plateado/dorado.
  Usa colores de texto que contrasten bien con metal claro (azules oscuros, negros, primario oscuro).

RESTRICCIÓN 6 — GRÁFICOS BOLD Y LEGIBLES:
  Los detalles fotográficos muy finos no se reproducen correctamente en UV sobre metal/madera.
  Usar: formas geométricas limpias, tipografía bold, bloques de color sólido, gradientes suaves.
  EVITAR en dalle_prompt: "photographic detail", "fine grain texture", "intricate pattern".

RESTRICCIÓN 7 — MATERIAL (el brief indicará el material exacto):
  Metal/aluminio: UV funciona bien. Fondos claros o gradientes suaves dan mejor acabado que
    fondos oscuros densos. Preferir diseños donde el metal sea parte del resultado visual.
  Madera: SIN detalles fotográficos finos ni texturas de grano — la madera no los reproduce.
    Solo gráficos bold, tipografía grande y legible, formas geométricas limpias.
  Piedra: MÁXIMO 1-2 colores de tinta, diseño extremadamente simple, sin gradientes complejos.
    El proceso es artesanal sobre zonas grabadas — no es impresión digital.
  Grabado láser: NO especificar colores exactos en zonas de grabado —
    el láser quema/oxida la superficie y el color final no es controlable.

RESTRICCIÓN 8 — BORDES Y FRICCIÓN EN EMBALAJE:
  Fondos oscuros o saturados full-bleed son vulnerables al astillado en bordes durante
  embalaje y envío. Para diseños con fondos oscuros:
  OBLIGATORIO: gradiente/fade que se desvanece en el perímetro exterior (último 8%).
  PROHIBIDO: negro sólido o color saturado hasta el borde absoluto del canvas.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MANDATO CREATIVO:
Cada propuesta es un CONCEPTO VISUAL DISTINTO — no una variación de paleta, sino un lenguaje
visual diferente. Piensa como si fueran 6 agencias distintas respondiendo al mismo brief.
La jerarquía es siempre: Logo → Título → NOMBRE DEL PREMIADO (héroe) → Organización.
El nombre del premiado es SIEMPRE el elemento tipográfico más grande y con mayor contraste.

USO DE LA PALETA — jerarquía proporcional (el primario siempre domina):
  Los colores tienen roles distintos, no son intercambiables ni equivalentes en peso visual.

  CON 1 COLOR: el primario domina el 100% del espacio visual. Usa tints (primario + blanco)
    y shades (primario + negro) para crear profundidad y contraste sin salir de la paleta.

  CON 2 COLORES: el primario ocupa el 60-70% del peso visual del diseño.
    El secundario aparece en MÁXIMO UN elemento estructural por diseño (una banda, un bloque
    o un arco). No puede competir con el primario en superficie. Su función: contraste puntual.
    EJEMPLO marca azul+amarillo: fondo azul + banda amarilla superior = el diseño.
    EJEMPLO marca negro+naranja: fondo negro + bloque naranja lateral = el elemento central.

  CON 3 COLORES: primario lidera en backgrounds y zonas grandes, secundario añade un
    elemento estructural de contraste, acento aparece solo en detalles pequeños
    (una línea fina, un ícono pequeño, un punto de luz). El acento NUNCA es un fondo.

  El secundario/acento son importantes CUALITATIVAMENTE (sin ellos sería monocromático)
  pero NO CUANTITATIVAMENTE en área visual.

  - color_overlay.color: pon SIEMPRE el secundario o acento aquí (no el primario — ya es el fondo).
  - Para el logo treatment "banda": usa secondary como band_color cuando el primario es el fondo.
  - headline_color / recipient_color: varía entre primary, secondary y accent en los 6 conceptos.

LIBERTAD CREATIVA TOTAL — CÓMO USAR LOS 6 SLOTS:
  Cada slot tiene un ROL (propósito), no un archetype fijo. TÚ decides el layout,
  la tipografía, la composición, el fondo y los elementos decorativos.
  El sistema los ejecuta fielmente — no sobrescribe tus decisiones de diseño.

  Layouts disponibles: "stacked" | "spread" | "staggered" | "billboard" | "logo_bottom"
  Anchors: "top" | "center" | "bottom"
  Alineaciones: "left" | "center" | "right"

  CRITERIO DE CALIDAD: cada diseño debe verse como si lo hubiera creado una agencia diferente.
  Usa layouts distintos, composiciones distintas, escalas distintas, decoraciones distintas.

LOS 6 ROLES CREATIVOS (interprétalos con total libertad):

  P1 — PRIMERA IMPRESIÓN IMPACTANTE
    Rol: el diseño más memorable y reconocible de los 6. Debe detenerse en el ojo.
    Puede ser: oscuro y sofisticado / brillante y audaz / minimalista extremo.
    Criterio: si solo mostraras este diseño, ¿recordarías la marca y el premio?

  P2 — CLARIDAD Y LEGIBILIDAD MÁXIMA
    Rol: el diseño más legible y limpio. Prioriza contraste y jerarquía sobre decoración.
    Ideal para: fondos claros con texto de marca de alto contraste, spacing generoso.
    bg_tone=light → el fondo metálico del trofeo actúa como fondo (dalle_prompt="").
    Recipient en el COLOR DE MARCA si contraste ≥ 3:1 sobre metal — editorial y potente.

  P3 — TENSIÓN GRÁFICA Y ENERGÍA
    Rol: diseño con movimiento visual y fuerza tipográfica. El más dinámico de los 6.
    Elige una composición que genere tensión: asimétrica, diagonal, escala extrema.
    layout="staggered" es una buena opción, pero no la única.

  P4 — EL PREMIADO COMO PROTAGONISTA ABSOLUTO
    Rol: el nombre del premiado ES el diseño. Todo lo demás es secundario.
    layout="billboard" normalmente — el nombre ocupa la mayor parte del canvas.
    El fondo puede ser DALLE con color de marca a plena potencia.

  P5 — MINIMALISMO PREMIUM
    Rol: el diseño más minimalista de los 6. Menos es más.
    Espacio en blanco intencional. Tipografía como único elemento decorativo.
    bg_tone=light → metálico del trofeo como fondo (dalle_prompt="").

  P6 — IDENTIDAD DE MARCA PURA
    Rol: la marca habla sola, con claridad y elegancia.
    bg_tone=light o mid — el primario aparece como color de texto o banda, no como fondo oscuro.
    El logo es el ancla visual. dalle_prompt="" o fondo muy sutil del color de marca.
    Diseño limpio: mucho espacio, pocos elementos, el color de marca como acento.

GARANTÍA DE UNICIDAD ENTRE LOS 6 CONCEPTOS — OBLIGATORIO:
  Antes de escribir el JSON final, verifica CADA uno de estos puntos:
  □ ¿bg_tone varía? DISTRIBUCIÓN OBLIGATORIA: P2=light, P5=light, P6=light o mid.
    MÁXIMO 3 dark en total — solo entre P1, P3, P4. Nunca 4 o más dark.
    Un conjunto con 4+ dark ES UN FALLO. P6 no puede ser dark por defecto.
  □ ¿Usan layouts distintos? No repitas el mismo layout más de 2 veces.
  □ ¿Las composiciones (left/center/right para recipient) varían?
  □ ¿Las decoraciones son distintas entre sí?
  □ ¿Los dalle_prompts usan técnicas radicalmente distintas? (nunca dos gradientes radiales)
  □ ¿El recipient_uppercase varía? (al menos 2 conceptos en mayúsculas, 2 en minúsculas)
  □ ¿Los spacing_scale varían? (denso 0.5–0.8 en algunos, aireado 1.4–2.0 en otros)
  Si dos conceptos son similares → modifica el segundo hasta que sean claramente distintos.

COLOR OVERLAY — tinta de coherencia cromática (USAR CON PRUDENCIA):
  Propósito: añadir un velo muy sutil del color de marca sobre el fondo DALLE para cohesión.
  - active=true SOLO si el fondo DALLE necesita anclarse cromáticamente a la marca.
  - opacity MÁXIMA: 0.18 — por encima de eso destruye la creatividad del fondo generado.
  - active=false en P2/P5 (fondos blancos — sin tinta) y en P1 si el fondo ya usa colores de marca.
  - NUNCA uses opacity > 0.20 — el sistema lo recortará igualmente a 0.28 por seguridad.

REGLAS DE COHERENCIA (aplicables a TODOS los conceptos):
  1. Fondos distribuidos: al menos 2 oscuros, al menos 1 claro. Varía bg_tone entre conceptos.
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
  - dalle_prompt = "" → fondo transparente (metal del trofeo). Usar para bg_tone=light.
  - Puedes usar DALLE para CUALQUIER slot, no solo P1/P3/P4. Si tienes una visión artística → exprésala.
  - Los prompts DALLE DEBEN ser visualmente radicalmente distintos entre sí.
    PROHIBIDO: repetir la misma técnica entre conceptos (ej. dos gradientes radiales).

  PERSONALIDAD VISUAL POR CONCEPTO — OBLIGATORIO diferente técnica en cada uno:

  P1 (IMPACTO DE MARCA) → El COLOR PRIMARIO de la marca ES el protagonista del fondo.
    REGLA FUNDAMENTAL: usa el color primario exacto de la marca como base del fondo, NO un oscuro genérico.
    El fondo debe ser INMEDIATAMENTE reconocible como el color de la marca.
    Elige técnica según el primario:
      primario saturado/vibrante (azul, verde, rojo, naranja) →
        gradiente del primario claro al primario profundo — el mismo tono, con profundidad.
        El secundario aparece como único acento luminoso (banda, glow puntual, borde).
      primario oscuro/neutral (navy muy oscuro, negro, gris) →
        gradiente oscuro profundo con acento del secundario como destello de color.
        El secundario es el único punto de vida en el fondo.
    PROHIBIDO: fondo oscuro genérico (negro, carbon, navy genérico) que no sea el color exacto de marca.
    REGLA UV: nunca sólido plano puro — siempre gradiente o textura sutil que dé profundidad.

  P3 (GRÁFICO AUDAZ) → El COLOR PRIMARIO como fondo + elemento geométrico ENORME del secundario.
    El primario ES la base — no un oscuro genérico. Diseño gráfico puro, NOT fotografía.
    REGLA bg_tone (OBLIGATORIA según luminancia del primario):
      primario CÁLIDO/BRILLANTE (naranja, amarillo, rojo vibrante, verde lima) → bg_tone=mid
        El color a plena saturación NO es "oscuro". Un naranja Amazon es bg_tone=mid, no dark.
      primario OSCURO (azul navy, azul oscuro, verde oscuro, negro) → bg_tone=dark
        Gradiente profundo del primario, con el secundario como destello.
    Elige UNA técnica de composición:
      primario saturado brillante → fondo pleno del primario + bloque o arco ENORME del secundario (30-50%)
      primario oscuro saturado → gradiente del primario oscuro + elemento geométrico del secundario claro
      marca con identidad fuerte → rectángulo o triángulo del secundario cortando el canvas en diagonal
    El elemento geométrico ocupa 30-50% del canvas y usa el color secundario exacto.
    NUNCA: base oscura genérica que no sea el color exacto de marca. NUNCA texturas etéreas.

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
    P1 → gradiente muy oscuro con acento dorado o gris platino, luz especular elegante (nunca negro puro plano)
    P3 → gradiente oscuro + geometría limpia y precisa, una sola forma contundente
    P4 → halftone refinado, gradiente oscuro-a-profundo con el primario como acento vibrante

  Marca TECNOLÓGICA / MODERNA / SOSTENIBLE (brand_tone = tecnologico|moderno|sostenible):
    P1 → gradiente oscuro con velo azul-verde del primario, glow neón muy contenido
    P3 → gradiente oscuro + grid o circuito abstracto en el accent, forma geométrica del primario
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
  Distribución sugerida: P1=stacked, P2=spread, P3=staggered, P4=billboard, P5=spread, P6=stacked

VARIEDAD OBLIGATORIA DE TEXTO — los 6 conceptos deben verse claramente distintos:
  □ LAYOUTS: usa al menos 3 layouts distintos. Máximo 2 veces "stacked".
  □ ANCHORS: varía text_anchor entre los 6 conceptos. Usa "top", "center" Y "bottom".
    Ejemplo válido: P1=top, P2=center, P3=center, P4=center, P5=bottom, P6=center.
    NO pongas "center" en los 6 — sería visualmente idéntico.
  □ ALINEACIONES: varía recipient_alignment. No uses "center" en todos.
    Al menos 2 conceptos con "left" o "right", resto "center".

JERARQUÍA FIJA: recipient > headline > subtitle (siempre, en todos los conceptos)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VALIDACIÓN OBLIGATORIA — valida cada concepto contra estas reglas antes de escribir el JSON.
Si alguna regla falla → corrige el concepto antes de incluirlo.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REGLA 1 — LEGIBILIDAD (fallo crítico):
  ¿Se lee todo el texto en 1 segundo? Si no → cambiar colores.
  NUNCA color de texto similar al fondo. SIEMPRE contraste 4.5:1 mínimo.
  Fondo oscuro → texto en blanco, crema o acento muy claro.
  Fondo claro → texto en negro, gris muy oscuro o primario muy saturado/oscuro.
  Un texto que no se lee en el diseño FINAL es inaceptable — cero excepciones.

REGLA 2 — JERARQUÍA VISUAL OBLIGATORIA (en este orden, visible sin dudar):
  1. Nombre del premio (headline) → debe leerse primero
  2. Nombre del premiado (recipient) → EL FOCO PRINCIPAL — el más grande y contrastado
  3. Marca/empresa (subtitle) → cierre visual
  Los tres NO deben competir entre sí. recipient siempre domina por tamaño.

REGLA 3 — CONSISTENCIA DE ESTILO (un único sistema visual por concepto):
  Elige UN lenguaje: corporativo limpio, editorial, gráfico bold, tipográfico puro, etc.
  PROHIBIDO mezclar en el mismo concepto: textura orgánica + grid técnico, serif clásico + neon,
  minimalismo blanco + fondo con ruido agresivo.
  Toda decisión (color, tipografía, decoración, fondo) debe pertenecer al mismo sistema.

REGLA 4 — SIN DECORACIÓN ARBITRARIA:
  decoration_hint: solo incluir un motif si cumple UNA función concreta:
    - separar zonas de contenido (section_header, rule_grid)
    - reforzar la identidad de la marca (diagonal_corners para marcas con lenguaje diagonal)
    - añadir distinción premium al diseño (laurel_arc para galardones de excelencia)
    - guiar el recorrido visual (dot_arc como conector entre headline y recipient)
  Si el motif es simplemente decorativo sin función → usar "none".
  PROHIBIDO: añadir puntos, líneas, o patrones que no cumplan ninguna de estas funciones.

REGLA 5 — RITMO VERTICAL (sin grandes vacíos sin intención):
  El canvas se divide en 3 bloques visuales:
    BLOQUE SUPERIOR (0–35%): logo + headline
    BLOQUE CENTRAL (35–70%): recipient — el foco principal
    BLOQUE INFERIOR (70–100%): subtitle + fecha
  El espacio vacío debe ser INTENCIONADO (diseño editorial, respiración de lujo).
  PROHIBIDO: recipient flotando solo en mitad del canvas con el 60% restante vacío.
  spacing_scale: 0.6–0.9 para diseños compactos, 1.2–1.8 para diseños editoriales aireados.

REGLA 6 — FONDOS QUE SIRVEN AL TEXTO (no compiten):
  El fondo debe ser SOPORTE del texto, no protagonista.
  Si hay imagen o textura → debe ser sutil, oscurecer ligeramente la zona de texto si es necesario.
  Un fondo que distrae del texto = fallo de diseño. Si hay duda → fondo sólido o gradiente suave.
  bg_tone debe reflejar el fondo real elegido: "dark" si primario oscuro, "light" si claro/blanco.

REGLA 7 — LOGO COMO ANCLA VISUAL (no residual):
  El logo SIEMPRE tiene un tamaño visible y está alineado con la composición.
  scale mínimo: 0.45. scale recomendado: 0.55–0.70.
  position: "top_center" por defecto. "bottom_center" solo cuando el diseño lo requiere como cierre.
  treatment apropiado según el fondo: "blanco" sobre oscuro, "negro" sobre claro, "color" sobre neutro.

REGLA 8 — PERCEPCIÓN PREMIUM (producto de valor, no plantilla):
  El diseño debe percibirse como un objeto de valor, no una tarjeta básica.
  Introduce AL MENOS UNO de estos recursos en cada concepto:
    - micro-contraste tipográfico (headline pequeño + recipient enorme → tensión de escala)
    - línea fina editorial (separador de 1px entre zonas)
    - profundidad visual (watermark del logo a 15% de opacidad, overlay sutil de color)
    - tratamiento de color atrevido (color de marca como fondo o como texto hero)
  Un diseño sin ninguno de estos recursos NO es premium.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
    "award_text": { "headline": "nombre del premio", "recipient": "nombre del premiado", "subtitle": "nombre del cliente (brand_name) — NUNCA el nombre del organizador del evento" },
    "decoration_hint": "SOLO si cumple una función (separar, enfatizar, guiar lectura, identidad de marca). Opciones: laurel_arc | diagonal_corners | section_header | badge_frame | corner_brackets | dot_arc | rule_grid | none. Si no cumple función clara → OBLIGATORIO poner none"
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
    MAX_EJEMPLOS = MAX_FEW_SHOT
    if not USE_FEW_SHOT or not APRENDIZAJE_DIR.exists():
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


# ─── Vocabulario creativo aleatorio ──────────────────────────────────────────

_ESTILOS_DALLE = [
    # ── Cinematográfico / atmosférico ──
    "dark cinematic film grain with diagonal golden light rays",
    "foggy low-key atmospheric light with deep silhouette depth",
    "dramatic chiaroscuro — extreme light-shadow contrast, dark renaissance",
    "abstract light painting long exposure trails on near-black background",
    "night photography bokeh light circles out of focus dark",
    "deep atmospheric haze with single luminous color glow point",
    "smoke diffusion in darkness with brand-color backlight",
    # ── Editorial / impresión ──
    "vintage newspaper halftone bold overprint grain texture",
    "risograph two-color overprint misregister grain bold",
    "editorial paper grain with deep ink wash accent marks",
    "screen print silk bold flat color layers overlap texture",
    "letterpress embossed uncoated paper deep press shadows",
    "premium packaging matte board texture subtle emboss shadow",
    "photocopier high contrast xerox grain texture bold marks",
    # ── Geométrico / gráfico ──
    "bold graphic flat color geometric poster — hard edges no gradients",
    "swiss international style grid geometric lines dark background",
    "constructivist bold shapes dynamic diagonals primary colors",
    "art deco geometric gold radial linear pattern dark field",
    "bauhaus primary color bold rectangles overlapping planes",
    "memphis 1980s geometric squiggles bold flat color pattern",
    "de stijl primary color bold grid asymmetric composition",
    "suprematist floating geometric shapes black field abstract",
    # ── Natural / orgánico ──
    "stone marble dark mineral crystalline close-up texture",
    "concrete brutalist surface directional deep shadow",
    "volcanic rock dark crystalline formation angled light",
    "deep forest floor organic texture bokeh background",
    "aerial desert sand dunes abstract shadow ridges",
    "weathered oxidized surface aged patina close-up",
    "deep ocean abyss darkness faint luminescence",
    # ── Digital / tecnología ──
    "abstract data visualization glowing nodes dark network",
    "aurora borealis flowing gradient dark polar sky",
    "deep space nebula gradient star field distance",
    "fiber optic threads glow dark background light",
    "circuit board abstract trace paths dark field glow",
    # ── Pictórico / arte ──
    "hand-painted watercolor wet-on-wet pigment bloom washes",
    "oil painting impasto thick texture abstract gestural",
    "acrylic pour fluid art swirling colors dark base",
    "abstract expressionist bold gestural brushstrokes dark",
    "color field painting saturated zones flat hue boundaries",
    "monotype print ink transfer ghost impression texture",
    "ink calligraphy brushstroke motion blur dark paper",
    # ── Material / lujo ──
    "silk fabric draped dramatically motion deep shadow",
    "deep velvet rich texture specular highlight fold",
    "matte ceramic surface soft gradient light quiet",
    "dark liquid surface refraction caustic light",
    # ── Cultura / histórico ──
    "japanese minimalist ink wash paper asymmetric",
    "art nouveau ornamental organic curve botanical dark",
    "pop art bold flat color Ben-Day halftone dots",
    # ── Puro / minimal ──
    "organic flowing curves soft gradient brand colors dark",
    "deep rich gradient dark vignette premium depth",
    "abstract minimal form negative space dark background",
    # ── Brand-forward / vibrante — color de marca como protagonista ──
    "bold flat color field in brand primary color — subtle texture, clean geometric depth, no dark overlay",
    "vibrant brand-color gradient light-to-deep same hue, single dominant brand color, premium feel",
    "brand primary color at full saturation with subtle halftone dot texture, vivid and clean",
    "clean geometric color split — brand primary dominant field with accent color bold panel",
    "solid brand color background, minimal light vignette from center, no darkness, brand identity",
    "brand identity color block at full saturation — slight inner glow, no atmospheric darkness",
]

_MOTIFS_DECORATIVOS = [
    "laurel_arc",
    "diagonal_corners",
    "section_header",
    "badge_frame",
    "corner_brackets",
    "dot_arc",
    "rule_grid",
    "none",
    "none",  # peso extra para evitar decoración innecesaria
    "none",
]

_TRATAMIENTOS_TIPO = [
    "ultra condensed bold display — maximum typographic impact",
    "classic serif editorial contrast with sans details",
    "letter-spaced minimal caps — luxury breathing room",
    "mixed scale: giant recipient overshadowing micro-caption details",
    "italic dynamic energy — forward momentum tension",
    "monospaced technical precision — data-driven authority",
    "rounded warm friendly — approachable premium",
    "heavy slab serif impact — grounded institutional authority",
    "extra light thin weight — restraint and luxury",
    "bold wide tracking all-caps editorial statement",
    "humanist warmth — balanced readable proportions",
    "dramatic size contrast: headline whisper, recipient shout",
]

_PALETAS_MOOD = [
    "full luminance range — pure black to brand primary highlight",
    "monochromatic depth — single brand hue from near-black to shade",
    "primary dominant with secondary spark accent",
    "dark field with single luminous color focal point",
    "muted desaturated base with vivid brand color pop",
    "dual-tone split — primary half dark, secondary half richer",
    "gradient span — dark through brand palette spectrum",
    "high contrast — brand primary as only light source on black",
]


def _vocabulario_creativo_aleatorio(seed_hint: str = "", run_id: str = "") -> dict:
    """
    Vocabulario creativo único por run: estilos DALL-E, motifs, tipografía y paleta mood.
    Seed a resolución de 30s + run_id garantiza variedad máxima entre ejecuciones.
    """
    import time
    seed_str = f"{run_id}{seed_hint}{int(time.time() // 30)}"
    seed_int = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed_int)
    return {
        "estilos":      rng.sample(_ESTILOS_DALLE, min(6, len(_ESTILOS_DALLE))),
        "motifs":       rng.sample(_MOTIFS_DECORATIVOS, min(6, len(_MOTIFS_DECORATIVOS))),
        "tipograficos": rng.sample(_TRATAMIENTOS_TIPO, min(6, len(_TRATAMIENTOS_TIPO))),
        "paletas":      rng.sample(_PALETAS_MOOD, min(6, len(_PALETAS_MOOD))),
    }


# ─── Llamada B — Design Concepts ─────────────────────────────────────────────

def _llamada_design_concepts(pedido: dict, brand_analysis: dict,
                             canonical_palette: list | None = None,
                             has_brandbook: bool = False) -> list:
    award  = pedido.get("award", {})
    evento = pedido.get("evento", {})

    ejemplos = _cargar_ejemplos_aprendizaje()
    content  = []

    # ── Semilla creativa generativa — run_id único garantiza variedad entre marcas ──
    import uuid
    run_id        = uuid.uuid4().hex[:10]
    recipient_txt = award.get("recipient") or ""
    vocab = _vocabulario_creativo_aleatorio(seed_hint=recipient_txt[:12], run_id=run_id)
    semilla_txt = (
        f"SEMILLA CREATIVA (run_id={run_id}) — garantiza unicidad entre ejecuciones.\n"
        "Usa estas sugerencias como punto de partida, adaptándolas a la identidad de la marca.\n"
        "Son inspiración, no mandatos — tu criterio creativo prevalece sobre ellas.\n\n"
        f"  P1 → Sugerencia DALLE: \"{vocab['estilos'][0]}\" | Motif sugerido: \"{vocab['motifs'][0]}\" | Tipo: \"{vocab['tipograficos'][0]}\"\n"
        f"  P2 → Motif sugerido: \"{vocab['motifs'][1]}\" | Tipo: \"{vocab['tipograficos'][1]}\"\n"
        f"  P3 → Sugerencia DALLE: \"{vocab['estilos'][2]}\" | Motif sugerido: \"{vocab['motifs'][2]}\" | Tipo: \"{vocab['tipograficos'][2]}\"\n"
        f"  P4 → Sugerencia DALLE: \"{vocab['estilos'][3]}\" | Motif sugerido: \"{vocab['motifs'][3]}\" | Tipo: \"{vocab['tipograficos'][3]}\"\n"
        f"  P5 → Motif sugerido: \"{vocab['motifs'][4]}\" | Tipo: \"{vocab['tipograficos'][4]}\"\n"
        f"  P6 → Sugerencia DALLE: \"{vocab['estilos'][5]}\" | Motif sugerido: \"{vocab['motifs'][5]}\" | Tipo: \"{vocab['tipograficos'][5]}\"\n\n"
        "REGLA DE UNICIDAD: los dalle_prompts de P1, P3, P4, P6 deben usar técnicas visuales distintas entre sí.\n"
        "Si una sugerencia no encaja con la marca, reemplázala por algo mejor para esa marca.\n"
    )
    # Almacenar run_id en el vocabulario para propagarlo a los conceptos
    vocab["_run_id"] = run_id
    content.insert(0, {"type": "text", "text": semilla_txt})

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

    # Inyectar restricciones del trofeo si están disponibles
    trophy = pedido.get("_trophy", {})
    if trophy:
        constraints = trophy.get("constraints", {})
        layouts_ok  = constraints.get("layouts_permitidos", [])
        layouts_str = ", ".join(f'"{l}"' for l in layouts_ok) if layouts_ok else "todos"
        margen_pct  = int(constraints.get("margen_h_pct", 0.08) * 100)
        content.append({"type": "text", "text": (
            f"RESTRICCIONES FÍSICAS DEL TROFEO — {trophy.get('nombre', '')} "
            f"({trophy.get('ancho', '?')}×{trophy.get('alto', '?')}px · {trophy.get('material', '')}):\n"
            f"  Forma: {constraints.get('descripcion_para_ia', 'rectangular estándar')}\n"
            f"  Layouts PERMITIDOS: {layouts_str}\n"
            f"  Margen horizontal MÍNIMO: {margen_pct}% (el renderer lo aplicará automáticamente)\n"
            f"  ⚠ OBLIGATORIO: usar SOLO los layouts indicados. "
            f"El sistema rechazará cualquier layout no permitido para este trofeo."
        )})

        # Restricción específica según material del trofeo
        _material = trophy.get("material", "metal").lower()
        _restriccion_material = {
            "madera":    ("Solo gráficos bold y tipografía grande y legible. "
                          "PROHIBIDO: fondos con texturas fotográficas, grano fino, detalles pequeños. "
                          "La madera no reproduce detalles finos en impresión UV."),
            "piedra":    ("MÁXIMO 1-2 colores de tinta. Diseño extremadamente simple. "
                          "Sin gradientes complejos. El proceso es artesanal sobre zonas grabadas."),
            "aluminio":  ("Fondos claros o gradientes suaves producen mejor acabado que fondos oscuros densos. "
                          "Preferir diseños donde el metal plateado sea parte del resultado visual."),
        }.get(_material,
              "Fondos claros o gradientes suaves producen mejor resultado que fondos oscuros densos. "
              "Evitar negro sólido puro — siempre con gradiente o profundidad visual.")
        content.append({"type": "text", "text": (
            f"RESTRICCIÓN DE MATERIAL — este trofeo es de {_material.upper()}:\n"
            f"  {_restriccion_material}\n"
            f"  Todos los diseños deben adaptarse a estas limitaciones físicas reales."
        )})

    # Restricción de paleta canónica.
    # Fuente de verdad: canonical_palette (Firecrawl/Oracle) > colors_extended de Brand Analysis.
    # Se aplica siempre que haya paleta canónica, independientemente del número de colores.
    _ext = brand_analysis.get("colors", {}).get("colors_extended", [])
    _palette_source = canonical_palette if canonical_palette else (_ext if _ext and len(_ext) <= 4 else [])
    if _palette_source:
        _pal_str = ", ".join(_palette_source)
        _source_label = "FIRECRAWL/COLOR ORACLE" if canonical_palette else "BRAND ANALYSIS"
        content.append({"type": "text", "text": (
            f"PALETA OBLIGATORIA [{_source_label}] — RESTRICCIÓN ESTRICTA (no negociable para los 6 diseños):\n"
            f"  Únicos colores de marca permitidos: {_pal_str}\n\n"
            f"  PROHIBIDO en recipient_color, headline_color, color_overlay.color, band_color:\n"
            f"    - Inventar variantes, tints o complementarios no incluidos en la lista\n"
            f"    - Usar grises de marca o neutros como color de identidad\n"
            f"    - Usar dorado (#FFD700, #F5C518, #D4AF37) si no aparece en la lista\n\n"
            f"  PERMITIDO SIEMPRE: #FFFFFF y #1A1A1A como colores de texto para contraste.\n\n"
            f"  OBJETIVO: los 6 diseños son variaciones del mismo sistema cromático.\n"
            f"  La variedad viene de proporciones, layouts y fondos — NO de añadir colores nuevos."
        )})

    # Sin brandbook, el 3er color (accent) puede ser un CTA de la web, no identidad de marca.
    # Instrucción: usarlo solo como detalle pequeño, nunca como fondo o banda dominante.
    if len(_palette_source) == 3 and not has_brandbook:
        _accent_warn = _palette_source[2]
        content.append({"type": "text", "text": (
            f"ADVERTENCIA — ACENTO SIN VALIDAR ({_accent_warn}):\n"
            f"  Este tercer color proviene de la web (posiblemente un botón CTA), "
            f"no de un brandbook validado. Puede NO ser identidad de marca consolidada.\n"
            f"  ÚSALO CON MODERACIÓN: solo en detalles pequeños — una línea fina, un punto "
            f"de luz, un pequeño ícono. NUNCA como fondo completo, banda principal o elemento "
            f"que compita en área con el primario ({_palette_source[0]}) "
            f"o el secundario ({_palette_source[1]}).\n"
            f"  Los 6 diseños deben ser claramente dominados por {_palette_source[0]} y {_palette_source[1]}."
        )})

    resultado = _llamar_claude(
        [{"role": "user", "content": content}],
        PROMPT_B_DESIGN_CONCEPTS,
        "DesignConcepts",
        temperatura=TEMP_DESIGN_CONCEPTS,
        model=MODEL_DESIGN_CONCEPTS,
    )
    # Propagar run_id a cada concepto para seed único en generadores PIL
    _run_id = vocab.get("_run_id", "")
    if isinstance(resultado, list) and _run_id:
        for c in resultado:
            if isinstance(c, dict):
                c["_run_id"] = _run_id
    return resultado if isinstance(resultado, list) else []


# ─── Validación ───────────────────────────────────────────────────────────────

def _validar_concepto(c: dict, idx: int, font_style_category: str = "",
                      primary_color: str = "", secondary_color: str = "",
                      accent_color: str = "", colors_extended: list | None = None,
                      trophy_constraints: dict | None = None) -> dict:
    # ── Parámetros FORZADOS — 6 arquetipos visuales distintos ──
    # Claude controla colores, dalle_prompt y award_text; el sistema controla estructura.
    # JERARQUÍA FIJA: recipient (100%) > headline (45-50%) > subtitle (22-25%)
    _layouts  = ["stacked", "spread",  "staggered", "billboard","spread",  "stacked"]
    _rec_sz   = [0.18,      0.22,      0.20,        0.22,       0.18,      0.16]
    _hl_sz    = [0.090,     0.100,     0.082,       0.090,      0.085,     0.080]
    _sub_sz   = [0.040,     0.048,     0.038,       0.042,      0.040,     0.037]
    _spacing  = [1.2,       0.8,       0.6,         0.8,        1.0,       1.6]
    _upper    = [False,     True,      True,        True,       False,     False]

    # Seed de variedad por run: mismo slot distinto entre ejecuciones.
    # _run_id cambia cada ejecución → seed diferente → variante de posición diferente.
    import hashlib as _hlib
    _vseed = int(_hlib.md5(
        f"{c.get('_run_id', '')}{c.get('proposal_id', 1)}".encode()
    ).hexdigest()[:6], 16)
    _vi = _vseed % 4  # 4 variantes posibles de posicionamiento por slot

    # Tablas de variedad: 4 filas (variantes) × 6 columnas (slots P1-P6)
    # Las variantes rotan anchor y alineaciones para que cada ejecución sea distinta.
    _ANCHOR_VAR = [
        ["top",    "center", "center", "center", "top",    "center"],  # var 0 (base)
        ["center", "top",    "center", "center", "bottom", "top"   ],  # var 1
        ["top",    "center", "center", "center", "center", "bottom"],  # var 2
        ["bottom", "top",    "center", "center", "top",    "center"],  # var 3
    ]
    _HL_ALN_VAR = [
        ["left",   "center", "right",  "center", "right",  "center"],  # var 0
        ["center", "left",   "right",  "center", "center", "left"  ],  # var 1
        ["left",   "center", "right",  "center", "left",   "right" ],  # var 2
        ["right",  "left",   "right",  "center", "right",  "center"],  # var 3
    ]
    _REC_ALN_VAR = [
        ["left",   "center", "left",   "center", "right",  "center"],  # var 0
        ["center", "left",   "left",   "center", "center", "right" ],  # var 1
        ["left",   "right",  "left",   "center", "left",   "center"],  # var 2
        ["right",  "center", "left",   "center", "right",  "left"  ],  # var 3
    ]
    _SUB_ALN_VAR = [
        ["left",   "center", "right",  "center", "right",  "center"],  # var 0
        ["center", "left",   "right",  "center", "center", "left"  ],  # var 1
        ["left",   "center", "right",  "center", "left",   "right" ],  # var 2
        ["right",  "left",   "right",  "center", "right",  "center"],  # var 3
    ]
    _anchors  = _ANCHOR_VAR [_vi]
    _hl_alns  = _HL_ALN_VAR [_vi]
    _rec_alns = _REC_ALN_VAR[_vi]
    _sub_alns = _SUB_ALN_VAR[_vi]

    # ── Defaults (solo se aplican si Claude no proporcionó el campo) ───────────
    # Usar colores de marca como fallback; si no hay, usar blanco/gris neutro (nunca dorado fijo)
    def _lum(h: str) -> float:
        try:
            h = h.lstrip("#")
            return (int(h[0:2],16)*299 + int(h[2:4],16)*587 + int(h[4:6],16)*114) / (255000)
        except Exception:
            return 0.5

    _light_brand = next(
        (c for c in [accent_color, secondary_color] if c and len(c) == 7 and _lum(c) > 0.35),
        "#FFFFFF"
    )
    _dark_brand = next(
        (c for c in [secondary_color, accent_color] if c and len(c) == 7 and _lum(c) < 0.35),
        "#1A1A1A"
    )
    _rec_cols = ["#FFFFFF", _light_brand, "#FFFFFF", _light_brand, "#FFFFFF", _dark_brand]
    _hl_cols  = [_light_brand, _dark_brand, "#FFFFFF", "#E0E0E0", _light_brand, _dark_brand]
    _sub_cols = ["#CCCCCC", "#888888", "#CCCCCC", "#AAAAAA", "#999999", "#888888"]

    i6 = idx % 6

    # Aplicar defaults para campos que Claude no generó
    defaults = {
        "proposal_id":      idx + 1,
        "pattern_name":     f"Concepto {idx + 1}",
        "design_rationale": "Diseño corporativo premium.",
        "dalle_prompt":     "Soft abstract gradient background, warm neutral tones, subtle geometric shapes, premium clean. No text, no logos, no people. Premium award background.",
        "bg_tone":          "mid",
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

    # Aplicar la estructura tipográfica respetando propuestas válidas de Claude.
    # Si Claude propuso un valor dentro del rango válido → preservarlo.
    # Si Claude no propuso o el valor está fuera de rango → usar el default del slot.
    ts = c.setdefault("text_style", {})

    _VALID_LAYOUTS = {"stacked", "spread", "staggered", "billboard", "logo_bottom"}
    _VALID_ANCHORS = {"top", "center", "bottom"}
    _VALID_ALIGNS  = {"left", "center", "right"}

    def _soft_str(field, default, valid_set):
        v = ts.get(field)
        return v if (v and v in valid_set) else default

    def _soft_float(field, default, lo, hi):
        try:
            v = float(ts.get(field) or default)
            return max(lo, min(hi, v))
        except (TypeError, ValueError):
            return default

    ts["layout"]               = _soft_str("layout",    _layouts[i6], _VALID_LAYOUTS)
    ts["text_anchor"]          = _soft_str("text_anchor", _anchors[i6], _VALID_ANCHORS)
    ts["recipient_size_ratio"] = _soft_float("recipient_size_ratio", _rec_sz[i6],  0.10, 0.28)
    ts["headline_size_ratio"]  = _soft_float("headline_size_ratio",  _hl_sz[i6],   0.050, 0.14)
    ts["subtitle_size_ratio"]  = _soft_float("subtitle_size_ratio",  _sub_sz[i6],  0.025, 0.065)
    ts["spacing_scale"]        = _soft_float("spacing_scale",        _spacing[i6], 0.5, 2.5)
    ts["recipient_uppercase"]  = ts.get("recipient_uppercase") if ts.get("recipient_uppercase") is not None else _upper[i6]
    ts["recipient_alignment"]  = _soft_str("recipient_alignment", _rec_alns[i6], _VALID_ALIGNS)
    ts["headline_alignment"]   = _soft_str("headline_alignment",  _hl_alns[i6],  _VALID_ALIGNS)
    ts["subtitle_alignment"]   = _soft_str("subtitle_alignment",  _sub_alns[i6],  _VALID_ALIGNS)

    # Validar layout contra los permitidos por el trofeo
    if trophy_constraints:
        layouts_ok = trophy_constraints.get("layouts_permitidos", [])
        if layouts_ok and ts.get("layout") not in layouts_ok:
            ts["layout"] = layouts_ok[i6 % len(layouts_ok)]

    # Propagar categoría de estilo tipográfico al renderer para fallback inteligente
    if font_style_category:
        ts["font_style_category"] = font_style_category

    # Propagar colores de marca — renderer y generadores PIL los usan como
    # elementos estructurales, bandas, meshes y paletas de variedad.
    # _primary es crítico para que generar_fondo() inyecte el HEX exacto en el prompt DALL-E.
    if primary_color:
        c["_primary"] = primary_color
    if secondary_color:
        c["_secondary"] = secondary_color
    if accent_color:
        c["_accent"] = accent_color
    if colors_extended:
        c["_colors_extended"] = [col for col in colors_extended if col]

    # Garantía de no colisión logo–texto:
    # - "center" solo permitido para watermark (semi-transparente, intencional)
    # - cualquier logo opaco en "center" se mueve a top_center
    logo = c.setdefault("logo", {})
    if logo.get("position") == "center" and logo.get("treatment") != "watermark":
        logo["position"] = "top_center"

    # Preservar decoration_hint de Claude; si no viene, asignar "none"
    if "decoration_hint" not in c or not c["decoration_hint"]:
        c["decoration_hint"] = "none"

    # Eliminar motifs puramente decorativos sin función visual definida.
    # starburst y halftone_overlay son los más propensos a ser arbitrarios.
    _MOTIFS_FUNCIONALES = {
        "laurel_arc", "diagonal_corners", "section_header",
        "badge_frame", "corner_brackets", "dot_arc", "rule_grid", "none", "auto",
    }
    if c.get("decoration_hint") not in _MOTIFS_FUNCIONALES:
        c["decoration_hint"] = "none"

    # Garantizar escala mínima del logo — no puede ser residual
    logo = c.setdefault("logo", {})
    if float(logo.get("scale", 0.55)) < 0.45:
        logo["scale"] = 0.45

    # Garantizar spacing_scale mínimo de 0.5 — sin canvas casi vacío
    ts = c.setdefault("text_style", {})
    if float(ts.get("spacing_scale", 1.0)) < 0.5:
        ts["spacing_scale"] = 0.5

    return c


# ─── Guardado ─────────────────────────────────────────────────────────────────

def guardar_spec(spec: dict, id_pedido: str) -> Path:
    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    ruta = SPECS_DIR / f"{id_pedido}_design_spec.json"
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    return ruta


# ─── Sanitizador de dalle_prompt ──────────────────────────────────────────────

def _sanitizar_dalle_prompt(prompt: str, bg_tone: str) -> str:
    """
    Reemplaza vocabulario oscuro en dalle_prompt cuando bg_tone es mid o light.
    DALL-E genera fondos oscuros si el prompt los describe, independientemente
    de bg_tone. Esta función alinea el texto del prompt con el tono deseado.
    Solo actúa para bg_tone in ("mid", "light"). Los reemplazos son word-boundary
    para evitar sustituir partes de palabras (ej: "dark red" → "vivid red").
    """
    if bg_tone not in ("mid", "light"):
        return prompt
    import re
    _reemplazos = [
        (r'\bdark background\b',  'vivid saturated background'),
        (r'\bdarkened\b',         'saturated'),
        (r'\bdark tones?\b',      'brand tones'),
        (r'\bdark\b',             'vivid'),
        (r'\bblack\b',            'deep brand-colored'),
        (r'\bcarbon\b',           'saturated'),
        (r'\bmidnight\b',         'bold'),
        (r'\bobsidian\b',         'vivid'),
        (r'\bshadow\b',           'accent'),
        (r'\bcharcoal\b',         'saturated'),
        (r'\bdim\b',              'bright'),
        (r'\bmoody\b',            'energetic'),
        (r'\bnoir\b',             'bold'),
        (r'\bgloomy\b',           'atmospheric'),
        (r'\bdusk\b',             'golden hour'),
    ]
    result = prompt
    for pattern, replacement in _reemplazos:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


# ─── Pipeline principal ───────────────────────────────────────────────────────

def diseñar_desde_contexto(pedido: dict, brand_context: dict) -> tuple[list, dict]:
    """
    Pipeline de Capa 1: 2 llamadas a Claude.
    Devuelve (conceptos[6], spec_completo).
    """
    id_pedido = pedido.get("id_pedido", "TEST")

    print(f"\n{'─'*50}")
    print(f"  CAPA 1 · Agente Diseñador IA  [A:{MODEL_BRAND_ANALYSIS} / B:{MODEL_DESIGN_CONCEPTS}]")
    print(f"  Pedido: {id_pedido}")
    print(f"{'─'*50}")

    # ── Color Oracle: paleta canónica antes del análisis completo ────────────────
    # Prioridad:
    #   (1) Brandbook PDF → skip Oracle
    #   (2) Firecrawl confirmó logo_color + ≥1 saturado → skip Oracle
    #       El logo es la fuente más fiable; añadir secundarios del screenshot introduce ruido.
    #   (3) Firecrawl encontró 2+ colores sin logo confirmado → Oracle valida el primario
    #       Si el primario de Oracle difiere >40° del de Firecrawl, Oracle gana.
    #   (4) Firecrawl insuficiente o sin URL → Oracle como fuente principal
    _tiene_brandbook    = bool(brand_context.get("pdf_resumen"))
    _fc_saturated_count = brand_context.get("_fc_saturated_count", 0)
    _fc_logo_confirmed  = brand_context.get("_fc_logo_confirmed", False)
    _tiene_firecrawl    = bool(brand_context.get("canonical_palette")) and _fc_saturated_count >= 2

    def _hue_dist(h1: str, h2: str) -> float:
        import colorsys
        def _hue(h):
            try:
                r, g, b = int(h[1:3], 16)/255, int(h[3:5], 16)/255, int(h[5:7], 16)/255
                return colorsys.rgb_to_hsv(r, g, b)[0]
            except Exception:
                return 0.0
        d = abs(_hue(h1) - _hue(h2))
        return min(d, 1.0 - d)

    if _tiene_brandbook:
        brand_context["canonical_palette"] = []
        print("  → Brandbook disponible — Color Oracle omitido")

    elif _fc_logo_confirmed and _fc_saturated_count >= 1:
        # Firecrawl devolvió logo_color, pero puede ser una alucinación (ej: Apple → verde).
        # Si tenemos el logo real, Oracle lo valida contra los píxeles del logo.
        # Sin logo → confiar en Firecrawl (no hay forma de verificar).
        _tiene_logo_fc = bool(brand_context.get("logo_path"))
        if _tiene_logo_fc:
            print(f"\n[0.5] Color Oracle (validador logo) — verificando logo_color Firecrawl={brand_context['canonical_palette'][0]}...")
            _canon_fc_val = _llamada_color_oracle(brand_context)
            if _canon_fc_val:
                _fc_prim  = brand_context["canonical_palette"][0]
                _ora_prim = _canon_fc_val[0]
                _dist_fc  = _hue_dist(_fc_prim, _ora_prim)
                if _dist_fc > 0.11:
                    brand_context["canonical_palette"] = _consolidar_hsv(_canon_fc_val, max_grupos=3)
                    print(f"  [Oracle] logo_color Firecrawl={_fc_prim} ≠ logo real ({_ora_prim}, Δ={_dist_fc:.2f}) → Oracle corrige")
                else:
                    print(f"  [Oracle] logo_color confirmado: {_fc_prim} ≈ {_ora_prim} (Δ={_dist_fc:.2f}) → Firecrawl válido")
            else:
                print(f"  [Oracle] Sin resultado — Firecrawl respetado: {brand_context['canonical_palette']}")
        else:
            print(f"\n[0.5] Color Oracle: omitido — logo_color Firecrawl sin logo para validar: {brand_context['canonical_palette']}")

    elif _tiene_firecrawl:
        # Firecrawl 2+ colores pero sin logo_color confirmado → Oracle valida el primario
        _tiene_logo = bool(brand_context.get("logo_path"))
        if _tiene_logo:
            print(f"\n[0.5] Color Oracle (validador) — verificando primario de Firecrawl contra logo...")
            _canon_val = _llamada_color_oracle(brand_context)
            if _canon_val:
                _fc_primary  = brand_context["canonical_palette"][0]
                _ora_primary = _canon_val[0]
                _dist = _hue_dist(_fc_primary, _ora_primary)
                if _dist > 0.11:  # >40° → el primario de Firecrawl es dudoso, Oracle corrige
                    brand_context["canonical_palette"] = _consolidar_hsv(_canon_val, max_grupos=3)
                    print(f"  [Oracle] Primario Firecrawl={_fc_primary} difiere del logo ({_ora_primary}, Δ={_dist:.2f}) → Oracle gana")
                else:
                    print(f"  [Oracle] Primario confirmado: {_fc_primary} ≈ {_ora_primary} (Δ={_dist:.2f}) → Firecrawl respetado")
            else:
                print(f"  [Oracle] Sin resultado — Firecrawl respetado: {brand_context['canonical_palette']}")
        else:
            print(f"\n[0.5] Color Oracle: omitido — Firecrawl identificó {_fc_saturated_count} colores (sin logo): {brand_context['canonical_palette']}")

    else:
        # Firecrawl insuficiente o sin URL → Oracle como fuente principal
        if brand_context.get("canonical_palette"):
            print(f"\n[0.5] Color Oracle (Haiku) — Firecrawl insuficiente ({_fc_saturated_count} saturados), completando...")
        else:
            print("\n[0.5] Color Oracle (Haiku)...")
        _canon = _llamada_color_oracle(brand_context)
        _fc_existente = brand_context.get("canonical_palette", [])
        if _fc_existente and _canon:
            _raw_merged = _fc_existente + [c for c in _canon if c not in _fc_existente]
            _merged = _consolidar_hsv(_raw_merged, max_grupos=3)
            brand_context["canonical_palette"] = _merged
            print(f"  → Paleta completada (Firecrawl + Oracle): {_merged}")
        elif _canon:
            brand_context["canonical_palette"] = _consolidar_hsv(_canon, max_grupos=3)
            print(f"  → Oracle: {brand_context['canonical_palette']}")
        else:
            print("  → Sin resultado — Brand Analysis usará todas las fuentes disponibles")

    print("\n[A] Brand Analysis...")
    brand_analysis = _llamada_brand_analysis(pedido, brand_context)
    colores = brand_analysis.get("colors", {})
    print(f"  → Tono   : {brand_analysis.get('brand_tone', '—')}")
    print(f"  → Primary: {colores.get('primary', '—')}")

    # Diagnóstico: ¿Brand Analysis respetó la paleta canónica enviada?
    _canon_enviada = brand_context.get("canonical_palette", [])
    _ext_resultado = colores.get("colors_extended", [])
    if _canon_enviada and _ext_resultado:
        _respetada = (all(c in _ext_resultado for c in _canon_enviada)
                      and len(_ext_resultado) <= len(_canon_enviada) + 1)
        _estado = "✓ RESPETADA" if _respetada else "⚠ DIVERGENCIA"
        print(f"  → Paleta canónica  : {_estado}")
        print(f"    Enviada al modelo: {_canon_enviada}")
        print(f"    Colors_extended  : {_ext_resultado}")
    elif _ext_resultado:
        print(f"  → Colors_extended  : {_ext_resultado}")

    # Override programático: si hay canonical_palette, los colores de marca son no negociables.
    # El LLM puede divergir creativamente — el código garantiza que la paleta real siempre gana.
    _canon_pal = brand_context.get("canonical_palette", [])
    if _canon_pal:
        colores["primary"]         = _canon_pal[0]
        colores["secondary"]       = _canon_pal[1] if len(_canon_pal) >= 2 else colores.get("secondary")
        colores["accent"]          = _canon_pal[2] if len(_canon_pal) >= 3 else colores.get("accent")
        colores["colors_extended"] = _canon_pal[:]
        brand_analysis["colors"]   = colores
        print(f"  [OVERRIDE] canonical_palette aplicada forzosamente: {_canon_pal}")
        print(f"  [OVERRIDE] primary={colores['primary']} · secondary={colores.get('secondary','—')} · accent={colores.get('accent','—')}")

    n_aprendizaje = len(list(APRENDIZAJE_DIR.glob("*.json"))) if APRENDIZAJE_DIR.exists() else 0
    typo = brand_analysis.get("typography", {})
    style_cat = typo.get("font_style_category", "")
    print(f"  → Fuente  : {typo.get('google_fonts_name', '—')} [{style_cat or '?'}]")

    secondary_col   = colores.get("secondary", "") or ""
    accent_col      = colores.get("accent", "")    or ""
    colors_extended = colores.get("colors_extended", [])

    print(f"\n[B] Design Concepts (ejemplos acumulados: {n_aprendizaje})...")
    trophy_constraints = pedido.get("_trophy", {}).get("constraints", {})
    _canon_pal   = brand_context.get("canonical_palette") or []
    primary_col  = colores.get("primary", "") or ""
    _has_brandbook = bool(brand_context.get("pdf_resumen"))
    conceptos = _llamada_design_concepts(pedido, brand_analysis, canonical_palette=_canon_pal,
                                         has_brandbook=_has_brandbook)
    conceptos = [_validar_concepto(c, i, style_cat,
                                   primary_color=primary_col,
                                   secondary_color=secondary_col,
                                   accent_color=accent_col,
                                   colors_extended=colors_extended,
                                   trophy_constraints=trophy_constraints)
                 for i, c in enumerate(conceptos[:6])]

    # Garantía dura: máximo 3 fondos oscuros. Convierte los extras a "mid" (P6 → P4 → P3).
    _dark_ids = [c["proposal_id"] for c in conceptos if c.get("bg_tone") == "dark"]
    if len(_dark_ids) > 3:
        _convert_priority = [6, 4, 3, 1]
        for _pid in _convert_priority:
            if len(_dark_ids) <= 3:
                break
            for c in conceptos:
                if c["proposal_id"] == _pid and c.get("bg_tone") == "dark":
                    c["bg_tone"] = "mid"
                    _dark_ids.remove(_pid)
                    print(f"  [postproceso] P{_pid}: dark→mid (límite 3 fondos oscuros)")
                    break

    # Primario cálido/brillante + bg_tone=dark en P3/P4 = inconsistencia de marca.
    # Un naranja, amarillo o rojo vibrante a plena potencia no es un fondo oscuro.
    # Convertir P3 y P4 a "mid" cuando el primario tiene alta luminancia.
    def _luminancia(hex_c: str) -> float:
        try:
            h = hex_c.lstrip("#")
            return (int(h[0:2],16)*299 + int(h[2:4],16)*587 + int(h[4:6],16)*114) / (255*1000)
        except Exception:
            return 0.5

    _prim_lum = _luminancia(primary_col)
    if _prim_lum > 0.38:   # naranja #FF9900≈0.49, rojo #C9102D≈0.19, azul≈0.20, amarillo≈0.85
        for c in conceptos:
            if c.get("bg_tone") == "dark" and c.get("proposal_id") in (3, 4):
                c["bg_tone"] = "mid"
                print(f"  [postproceso] P{c['proposal_id']}: dark→mid (primario cálido {primary_col} lum={_prim_lum:.2f})")

    # Sanitizar dalle_prompt para que el vocabulario coincida con bg_tone resultante.
    # DALL-E ignora bg_tone; si el prompt describe escenas oscuras para una propuesta mid/light
    # se generará un fondo oscuro igualmente. Este sanitizador reemplaza términos oscuros
    # por equivalentes de tono medio sin alterar la creatividad del diseño.
    for c in conceptos:
        _dp = c.get("dalle_prompt", "")
        if _dp and c.get("bg_tone") in ("mid", "light"):
            _dp_nuevo = _sanitizar_dalle_prompt(_dp, c["bg_tone"])
            if _dp_nuevo != _dp:
                c["dalle_prompt"] = _dp_nuevo
                print(f"  [postproceso] P{c['proposal_id']}: dalle_prompt sanitizado (bg={c['bg_tone']})")

    while len(conceptos) < 6:
        conceptos.append(_validar_concepto({}, len(conceptos), style_cat,
                                           primary_color=primary_col,
                                           secondary_color=secondary_col,
                                           accent_color=accent_col,
                                           colors_extended=colors_extended,
                                           trophy_constraints=trophy_constraints))

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
