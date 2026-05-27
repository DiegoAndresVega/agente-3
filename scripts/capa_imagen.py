"""
CAPA IMAGEN — Generación completa del trofeo con gpt-image-1
Agente 3 — Sustain Awards Custom

A diferencia del Agente 2 (que genera fondos para overlay),
esta capa genera el trofeo completo: forma + material + texto integrado.

La IA crea la visualización del objeto físico de una vez.
"""

import os
import base64
import time
import numpy as np
from io import BytesIO

import openai as _openai
from PIL import Image, ImageDraw

from scripts.config import (
    USE_DALLE,
    IMAGE_QUALITY as CALIDAD_IMAGEN,
    IMAGE_MODEL_OPENAI,
    REPLICATE_LORA_MODEL,
    LORA_TRIGGER_WORD,
    USE_LORA,
    USE_GPT_EDIT,
)


# ─── Cliente OpenAI ──────────────────────────────────────────────────────────

def _cliente() -> _openai.OpenAI:
    return _openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))


# ─── Prompt base de calidad ──────────────────────────────────────────────────

_PROMPT_BASE_TROFEO = """\
Create a photorealistic premium studio product render of a custom-made trophy, \
always presented with a clean, elegant, contemporary and highly believable aesthetic.

The trophy must appear as a refined sculptural object — a single monolithic mass with \
sober, minimalist and monumental presence. The overall visual language should feel \
precise, silent, weighty and suitable for high-end custom trophy design.

Image style and composition:
- Vertical 4:5 aspect ratio
- Centered composition
- Trophy isolated on a seamless studio background in solid light grey #d7d7d7
- Slightly left three-quarter perspective, almost frontal
- Neutral product photography lens
- No wide-angle distortion
- No dramatic camera angle

Lighting:
- Soft diffused professional studio lighting
- Broad soft key light from the upper front area
- Gentle fill light to preserve detail in all planes
- Clean contact shadow under the object
- Very subtle rim light only if necessary to separate mass from background
- Controlled highlights that reveal surface texture
- No harsh glare
- No dramatic cinematic lighting

Material — refined recycled concrete:
- Dense and solid appearance, heavy physical presence
- Subtle mineral grain with fine porosity and soft micro-roughness
- Strictly monochromatic: uniform cement grey throughout
- No color variation, no tonal gradients, no pigmented zones
- Matte finish — no satin, no gloss, no polished sections
- Premium and refined, never rough construction-grade concrete
- Never dirty, damaged or excessively coarse
- Clean smooth surfaces — no text, no letters, no numbers, no words on the surface

Form language — monolithic sculpture:
- Single monolithic block: one continuous volume from a single mass of concrete
- No assembled parts, no stacked separate elements, no joined geometries
- No metallic elements, no steel components, no inlays, no applied materials
- Form references: brutalist sculpture, Donald Judd specific objects, \
Tadao Ando concrete, Heizer monoliths — Kaaba-like density and silence

Physical plausibility — CRITICAL:
- The trophy must be physically buildable and self-standing in reality
- Every part must be structurally connected to the base or main body
- NO floating elements of any kind
- The center of gravity must be plausibly stable on a flat surface

Strictly avoid:
- ANY text, letters, numbers, words, or writing on the concrete surface
- Floating, suspended or disconnected elements
- Multiple separate volumes with no physical connection
- Two-tone or color treatments of any kind
- Metallic coatings, lacquered elements, enamel panels or colored inlays
- Polished or reflective surface sections

Output quality:
- Premium catalog-quality studio render
- Ultra-detailed surface fidelity
- Sharp, clean, quiet visual tone
- Realistic concrete texture and shadow rendering\
"""

# Versión del prompt base sin ninguna referencia a texto/grabado — para el LoRA.
# Flux interpreta cualquier mención de "engraving" o "text" como instrucción
# de generar caracteres en la imagen. Este prompt genera la forma limpia.
_PROMPT_BASE_TROFEO_LORA = """\
Studio product photography of a sculptural award trophy. \
Single monolithic sculptural form on neutral grey background #d7d7d7. \
Soft diffused studio lighting, clean contact shadow at base. Portrait orientation. \
No text, no letters, no numbers, no words, no markings anywhere on the surface. \
Sharp focus, clean composition, premium trophy photography.\
"""


# ─── Helpers de prompt ───────────────────────────────────────────────────────

def _construir_prompt_hormigon_acero(
    forma: dict,
    colores_marca: list[str],
    texto_premiado: str,
    texto_award: str,
    nombre_empresa: str,
    forma_descripcion_prompt: str = "",
) -> str:
    """
    Construye el prompt para gpt-image-1.
    Estructura: [prompt base — monolito hormigón] + [forma específica] + [texto grabado].
    El trofeo es un monolito gris puro: sin color de marca, sin acero, sin incrustaciones.
    La identidad de marca se expresa únicamente a través de grabados en profundidad.
    """
    # ── Forma específica ──────────────────────────────────────────────────────
    if forma_descripcion_prompt and len(forma_descripcion_prompt) > 20:
        descripcion_forma = forma_descripcion_prompt.rstrip(". ")
    else:
        descripcion_forma = forma.get("descripcion_prompt", "Abstract monolithic concrete trophy form")

    # ── Texto del premiado (grabado en superficie) ────────────────────────────
    texto_bloque = ""
    if texto_premiado or texto_award:
        partes = []
        if texto_award:
            partes.append(f'"{texto_award}"')
        if texto_premiado:
            partes.append(f'"{texto_premiado}"')
        if nombre_empresa:
            partes.append(f'"{nombre_empresa}"')
        texto_bloque = (
            f"Award text engraved into the concrete surface: {' / '.join(partes)}. "
            "Engraving is clean, precise, recessed into the monolithic concrete body. "
            "No applied lettering, no color fill in the engraving — concrete grey only. "
        )

    from scripts.prompts_manager import cargar_prompts
    _pm = cargar_prompts()
    if USE_LORA:
        base = _pm.get("prompt_base_trofeo_lora") or _PROMPT_BASE_TROFEO_LORA
    else:
        base = _PROMPT_BASE_TROFEO

    return (
        f"{base}\n\n"
        f"SPECIFIC TROPHY FORM:\n{descripcion_forma}\n\n"
        f"{texto_bloque}"
        "No floating text or applied elements outside the physical concrete body."
    )


# ─── Pipeline LoRA → textura → logo → texto ──────────────────────────────────

def _aplicar_textura_y_logo(
    img: Image.Image,
    logo_b64: str,
    logo_type: str,
    brand_name: str,
) -> Image.Image:
    """
    UNA SOLA llamada gpt-image-1 edit que hace las dos cosas:
    1. Aplica textura real de hormigón
    2. Graba el logo exacto de la marca

    Composite 1024×1024:
    - Izquierda (512×512): trofeo LoRA (a editar)
    - Derecha (512×512):   logo de referencia (fondo blanco)

    Una sola transformación evita el efecto de imagen doble por múltiples resizes.
    """
    try:
        SIDE = 512
        w, h  = img.size

        trophy_panel = img.resize((SIDE, SIDE), Image.LANCZOS)

        logo_raw = base64.b64decode(logo_b64)
        logo_img = Image.open(BytesIO(logo_raw)).convert("RGBA")
        logo_img.thumbnail((int(SIDE * 0.70), int(SIDE * 0.70)), Image.LANCZOS)
        logo_panel = Image.new("RGB", (SIDE, SIDE), (255, 255, 255))
        logo_panel.paste(logo_img,
                         ((SIDE - logo_img.width) // 2, (SIDE - logo_img.height) // 2),
                         logo_img if logo_img.mode == "RGBA" else None)

        composite = Image.new("RGB", (1024, 1024), (200, 200, 200))
        composite.paste(trophy_panel, (0, 0))
        composite.paste(logo_panel,  (SIDE, 0))
        ImageDraw.Draw(composite).line([(SIDE, 0), (SIDE, SIDE)], fill=(80, 80, 80), width=3)

        _DEFAULT_PROMPT_TEXTURA = (
            "This image has two panels: LEFT = sculptural trophy, RIGHT = brand logo symbol. "
            "Apply TWO changes to the LEFT trophy and output it filling the FULL FRAME: "
            "(1) Convert surface to authentic raw concrete — dense grey portland cement, "
            "visible fine aggregate particles, natural porosity, micro-roughness, matte finish. "
            "(2) Reproduce the EXACT visual shape of the logo symbol from the RIGHT panel "
            "as a shallow bas-relief engraving on the trophy front face — copy the precise "
            "contours and geometry exactly as shown, carved into concrete, same grey tone, "
            "slightly darker recessed channels, subtle shadow. "
            "CRITICAL: copy logo shape EXACTLY — do not interpret or rename it. "
            "Do NOT add text, words, letters, numbers or floating elements anywhere. "
            "Output: ONLY the trophy filling the entire frame, clean grey studio background."
        )
        from scripts.prompts_manager import cargar_prompts
        prompt = cargar_prompts().get("prompt_textura_logo") or _DEFAULT_PROMPT_TEXTURA

        buf = BytesIO()
        composite.save(buf, format="PNG")
        comp_kb = buf.tell() // 1024
        buf.seek(0)

        print(f"  ║  → Composite: trofeo {SIDE}×{SIDE} + logo {logo_img.width}×{logo_img.height} ({comp_kb}KB)")
        _t0 = time.time()
        resp = _cliente().images.edit(
            model="gpt-image-1",
            image=("composite.png", buf, "image/png"),
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        print(f"  ║  ← respuesta en {time.time()-_t0:.1f}s")

        result = Image.open(BytesIO(base64.b64decode(resp.data[0].b64_json))).convert("RGB")
        return result.resize((w, h), Image.LANCZOS)

    except Exception as e:
        print(f"  [textura+logo] ✗ falló: {str(e)[:100]} → fallback textura")
        return _aplicar_textura_hormigon(img)


_DEFAULT_PROMPT_TEXTURA_HORMIGON = (
    "This sculptural trophy has a smooth surface. "
    "Convert the material to authentic raw concrete: dense grey portland cement "
    "with visible fine aggregate particles, natural porosity, soft micro-roughness, "
    "matte non-reflective finish. Preserve the EXACT same shape — only change texture. "
    "No text, no logos, no new elements."
)


def _aplicar_textura_hormigon(img: Image.Image) -> Image.Image:
    """
    Llamada gpt-image-1 edit: convierte la textura suave del LoRA
    en hormigón real sin cambiar la forma del trofeo.
    """
    try:
        from scripts.prompts_manager import cargar_prompts
        prompt = cargar_prompts().get("prompt_textura_hormigon") or _DEFAULT_PROMPT_TEXTURA_HORMIGON

        w, h = img.size
        scaled  = img.resize((1024, 1024), Image.LANCZOS)
        buf = BytesIO()
        scaled.save(buf, format="PNG")
        kb = buf.tell() // 1024
        buf.seek(0)
        print(f"  ║  → gpt-image-1 edit | textura ({kb}KB)")
        _t0 = time.time()
        resp = _cliente().images.edit(
            model="gpt-image-1",
            image=("trophy.png", buf, "image/png"),
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        print(f"  ║  ← {time.time()-_t0:.1f}s")
        return Image.open(BytesIO(base64.b64decode(resp.data[0].b64_json))).convert("RGB").resize((w, h), Image.LANCZOS)

    except Exception as e:
        print(f"  [textura] ✗ {str(e)[:100]} → manteniendo LoRA")
        return img

# ─── Fallback PIL ────────────────────────────────────────────────────────────

def _trofeo_pil_fallback(
    ancho: int,
    alto: int,
    color_principal: str,
    concepto: dict,
) -> Image.Image:
    """
    Genera una imagen de placeholder cuando USE_DALLE=False o falla la API.
    Útil para modo demo sin coste de API.
    """
    from PIL import ImageDraw, ImageFont

    img = Image.new("RGB", (ancho, alto), "#F5F5F3")
    draw = ImageDraw.Draw(img)

    # Forma simplificada: rectángulo con color de marca
    cx = ancho // 2
    base_y = int(alto * 0.75)
    top_y  = int(alto * 0.15)
    w_trofeo = int(ancho * 0.35)

    try:
        r, g, b = int(color_principal[1:3], 16), int(color_principal[3:5], 16), int(color_principal[5:7], 16)
        color_rgb = (r, g, b)
        color_acero = (min(r + 40, 255), min(g + 40, 255), min(b + 40, 255))
    except Exception:
        color_rgb  = (74, 74, 74)
        color_acero = (120, 120, 120)

    # Columna principal (hormigón simulado)
    draw.rectangle(
        [cx - w_trofeo // 2, top_y, cx + w_trofeo // 2, base_y],
        fill=(210, 205, 198),
    )
    # Franja de acero con color de marca
    franja_h = int((base_y - top_y) * 0.15)
    draw.rectangle(
        [cx - w_trofeo // 2, top_y + franja_h, cx + w_trofeo // 2, top_y + franja_h * 2],
        fill=color_rgb,
    )
    # Base de acero
    draw.rectangle(
        [cx - int(w_trofeo * 0.7), base_y, cx + int(w_trofeo * 0.7), base_y + 30],
        fill=color_acero,
    )

    # Texto de concepto
    pid = concepto.get("proposal_id", "?")
    forma_nombre = concepto.get("forma_escultorica", "")
    draw.text(
        (cx, int(alto * 0.88)),
        f"[Demo] P{pid} — {forma_nombre}",
        fill=(100, 100, 100),
        anchor="mm",
    )

    return img


# ─── Función principal ────────────────────────────────────────────────────────

def generar_trofeo(
    concepto: dict,
    material_config: dict,
    brand_context: dict,
    award: dict,
    brand_analysis: dict | None = None,
) -> Image.Image:
    """
    Genera la imagen completa del trofeo.

    Pipeline con LoRA:
      1. LoRA (Replicate)     → forma geométrica del trofeo
      2. gpt-image-1 edit     → aplica textura real de hormigón
      3. gpt-image-1 edit     → graba logo exacto de la marca (imagen compuesta)
      4. PIL overlay          → texto del premiado legible

    Pipeline sin LoRA (gpt-image-1 directo):
      1. gpt-image-1 generate → forma + textura + texto en un solo paso
    """
    pid = concepto.get("proposal_id", "?")
    dims = material_config.get("dimensiones_output", {"ancho": 1024, "alto": 1536})
    ancho, alto = dims["ancho"], dims["alto"]

    # Colores de marca
    canonical = brand_context.get("canonical_palette") or []
    if not canonical:
        analysis = brand_context.get("brand_analysis", {}).get("colors", {})
        canonical = [
            c for c in [analysis.get("primary"), analysis.get("secondary"), analysis.get("accent")]
            if c and c.startswith("#") and len(c) == 7
        ]
    color_principal = canonical[0] if canonical else "#4A4A4A"

    # Forma escultórica asignada por capa1
    forma_id = concepto.get("forma_escultorica", "columnar")
    formas   = {f["id"]: f for f in material_config.get("formas_esculturicas", [])}
    forma    = formas.get(forma_id, {"id": forma_id, "nombre": forma_id, "descripcion_prompt": "abstract trophy form"})

    # Textos del premiado
    texto_premiado = award.get("recipient", "")
    texto_award    = award.get("headline", "")
    nombre_empresa = concepto.get("award_text", {}).get("subtitle", "")

    if not USE_DALLE:
        print(f"  [Capa-Imagen] P{pid} → PIL fallback (USE_DALLE=False)")
        return _trofeo_pil_fallback(ancho, alto, color_principal, concepto)

    forma_desc_prompt = concepto.get("forma_descripcion_prompt", "")

    prompt = _construir_prompt_hormigon_acero(
        forma=forma,
        colores_marca=canonical,
        texto_premiado=texto_premiado,
        texto_award=texto_award,
        nombre_empresa=nombre_empresa,
        forma_descripcion_prompt=forma_desc_prompt,
    )

    if USE_LORA:
        print(f"\n  ╔══ PIPELINE LORA P{pid} ══════════════════════════════")
        print(f"  ║  Forma   : {concepto.get('forma_escultorica','?')}")
        print(f"  ║  Texto   : {texto_award} / {texto_premiado}")
        print(f"  ║  Empresa : {concepto.get('award_text',{}).get('subtitle','')}")
        print(f"  ╠── PASO 1: LoRA → forma geométrica ──────────────────")

        img = _generar_con_lora(pid, prompt, ancho, alto, color_principal, concepto)
        print(f"  ║  ✓ Imagen LoRA: {img.size[0]}×{img.size[1]}px")

        if USE_GPT_EDIT:
            print(f"  ╠── PASO 2: gpt-image-1 edit → textura hormigón ──────")
            img = _aplicar_textura_hormigon(img)
        else:
            print(f"  ╠── PASO 2: suspendido (USE_GPT_EDIT=false) ────────")
            print(f"  ║  Imagen LoRA es el resultado final")

        print(f"  ╚══ P{pid} COMPLETADO ══════════════════════════════════\n")
        return img
    else:
        return _generar_con_openai(pid, prompt, ancho, alto, color_principal, concepto)


def _limpiar_prompt_para_lora(prompt: str) -> str:
    """
    Elimina TODO el bloque de texto del premiado del prompt LoRA.
    Flux no renderiza texto legible — el texto se añade después con PIL overlay.
    Mantiene: descripción de forma, material, composición, fotografía.
    Elimina: cualquier instrucción de texto/grabado con contenido específico.
    """
    import re
    # Eliminar bloque de texto del premiado completo
    prompt = re.sub(
        r'Award text[^.]*\.',
        '',
        prompt,
        flags=re.IGNORECASE
    )
    # Eliminar instrucciones de grabado con contenido específico
    prompt = re.sub(
        r'Text cleanly (engraved|applied|cast)[^.]*\.',
        '',
        prompt,
        flags=re.IGNORECASE
    )
    # Eliminar cualquier texto entre comillas
    prompt = re.sub(r'"[^"]{2,80}"(\s*/\s*"[^"]{2,80}")*', '', prompt)
    # Eliminar "No floating text..." que ya no aplica
    prompt = re.sub(r'No floating text[^.]*\.', '', prompt, flags=re.IGNORECASE)
    # Limpiar espacios dobles residuales
    prompt = re.sub(r'  +', ' ', prompt).strip()
    return prompt


def _generar_con_lora(pid, prompt: str, ancho: int, alto: int,
                      color_principal: str, concepto: dict) -> Image.Image:
    """Genera el trofeo usando el LoRA entrenado en Replicate."""
    import urllib.request
    import replicate

    # Para el LoRA: eliminar el bloque de texto específico del prompt.
    # Flux no renderiza texto legible — incluirlo produce caracteres ilegibles.
    # Solo describimos el ÁREA de grabado geométricamente.
    prompt_lora = _limpiar_prompt_para_lora(prompt)
    lora_prompt = f"{LORA_TRIGGER_WORD}, photorealistic color photography, {prompt_lora}"
    aspect      = "2:3" if alto > ancho else "1:1"

    print(f"  [Capa-Imagen] P{pid} · LoRA={REPLICATE_LORA_MODEL[:50]}...")
    print(f"    trigger: {LORA_TRIGGER_WORD} · aspect: {aspect}")
    print(f"    prompt[:120]: {lora_prompt[:120]}...")

    for intento in range(3):
        try:
            _t0 = time.time()
            output = replicate.run(
                REPLICATE_LORA_MODEL,
                input={
                    "prompt":                  lora_prompt,
                    "model":                   "dev",
                    "aspect_ratio":            aspect,
                    "num_outputs":             1,
                    "num_inference_steps":     28,
                    "guidance_scale":          6,
                    "lora_scale":              0.4,
                    "output_format":           "jpg",
                    "output_quality":          95,
                    "disable_safety_checker":  True,
                }
            )
            url = str(output[0]) if isinstance(output, list) else str(output)
            with urllib.request.urlopen(url) as resp:
                img_bytes = resp.read()
            img = Image.open(BytesIO(img_bytes)).convert("RGB")
            if img.size != (ancho, alto):
                img = img.resize((ancho, alto), Image.LANCZOS)
            print(f"  [Capa-Imagen] P{pid} ✓ LoRA generado en {time.time()-_t0:.1f}s ({img.size[0]}×{img.size[1]}px)")
            return img
        except Exception as e:
            espera = 15 if "429" in str(e) else 5
            if intento < 2:
                print(f"  [Capa-Imagen] P{pid} · LoRA intento {intento+1} fallido: {str(e)[:80]}")
                print(f"    → esperando {espera}s...")
                time.sleep(espera)
            else:
                print(f"  [Capa-Imagen] P{pid} · LoRA error persistente → PIL fallback")
                return _trofeo_pil_fallback(ancho, alto, color_principal, concepto)


def _generar_con_openai(pid, prompt: str, ancho: int, alto: int,
                        color_principal: str, concepto: dict) -> Image.Image:
    """Genera el trofeo usando gpt-image-1 (OpenAI)."""
    _prompt_src = "claude-desc" if concepto.get("forma_descripcion_prompt") else "catalog"
    print(f"  [Capa-Imagen] P{pid} · src={_prompt_src} · gpt-image-1 ({CALIDAD_IMAGEN})")
    print(f"    prompt[:150]: {prompt[:150]}...")

    for intento in range(3):
        try:
            client = _cliente()
            size   = "1024x1536" if alto > ancho else "1024x1024"

            respuesta = client.images.generate(
                model=IMAGE_MODEL_OPENAI,
                prompt=prompt,
                n=1,
                size=size,
                quality=CALIDAD_IMAGEN,
            )

            datos_b64 = respuesta.data[0].b64_json
            img_bytes = base64.b64decode(datos_b64)
            img = Image.open(BytesIO(img_bytes)).convert("RGB")

            if img.size != (ancho, alto):
                img = img.resize((ancho, alto), Image.LANCZOS)

            print(f"  [Capa-Imagen] P{pid} ✓ generado ({img.size[0]}×{img.size[1]}px)")
            return img

        except Exception as e:
            if intento < 2:
                print(f"  [Capa-Imagen] P{pid} · intento {intento+1} fallido: {e} — reintentando...")
                time.sleep(2 ** intento)
            else:
                print(f"  [Capa-Imagen] P{pid} · error persistente: {e} — usando PIL fallback")
                return _trofeo_pil_fallback(ancho, alto, color_principal, concepto)
