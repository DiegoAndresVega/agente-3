"""
Configuración centralizada de modelos y feature flags del Agente 3.
Todos los valores pueden sobreescribirse con variables de entorno.

Coste orientativo por pedido (3 trofeos):
    Demo/pruebas   USE_DALLE=false              ~$0.03  (solo Claude)
    USE_LORA=true  LoRA solamente               ~$0.009/trofeo
    USE_LORA=true  + USE_GPT_EDIT=true          ~$0.09/trofeo (añade textura+logo)
    USE_LORA=false gpt-image-1 directo          ~$0.042/trofeo
"""
import os


# ─── Modelos Claude ───────────────────────────────────────────────────────────

MODEL_BRAND_ANALYSIS  = os.getenv("MODEL_BRAND_ANALYSIS",  "claude-sonnet-4-6")
TEMP_BRAND_ANALYSIS   = float(os.getenv("TEMP_BRAND_ANALYSIS",  "0.3"))

MODEL_DESIGN_CONCEPTS = os.getenv("MODEL_DESIGN_CONCEPTS", "claude-sonnet-4-6")
TEMP_DESIGN_CONCEPTS  = float(os.getenv("TEMP_DESIGN_CONCEPTS", "1.0"))

MODEL_COLOR_ORACLE    = os.getenv("MODEL_COLOR_ORACLE",    "claude-haiku-4-5-20251001")
TEMP_COLOR_ORACLE     = float(os.getenv("TEMP_COLOR_ORACLE",    "0.0"))

FIRECRAWL_API_KEY     = os.getenv("FIRECRAWL_API_KEY", "")


# ─── Generación de imágenes ───────────────────────────────────────────────────

# OpenAI gpt-image-1 — quality=medium ~$0.042/img
IMAGE_MODEL_OPENAI = os.getenv("IMAGE_MODEL_OPENAI", "gpt-image-1")
IMAGE_QUALITY      = os.getenv("IMAGE_QUALITY", "medium")  # "low" | "medium" | "high"

# LoRA (Replicate Flux) — dataset saawdtrophy, trigger: saawdtrophy
# Entrenado: 2026-05-27 · modelo: diegoandresvega/trofeos
REPLICATE_LORA_MODEL = os.getenv(
    "REPLICATE_LORA_MODEL",
    "diegoandresvega/trofeos:748ed324b91f3d9bf5ce01a01b307d1cc772d0ee29fea2188e49294eda564d75"
)
LORA_TRIGGER_WORD = os.getenv("LORA_TRIGGER_WORD", "saawdtrophy")

# USE_LORA=true  → Replicate LoRA genera la forma del trofeo
# USE_LORA=false → gpt-image-1 generate directamente
USE_LORA = os.getenv("USE_LORA", "false").lower() == "true"


# ─── Feature flags ────────────────────────────────────────────────────────────

# USE_DALLE=false → PIL fallback sin coste (solo para pruebas locales)
USE_DALLE = os.getenv("USE_DALLE", "true").lower() == "true"

# USE_GPT_EDIT=true  → aplica textura hormigón + graba logo con gpt-image-1 edit
# USE_GPT_EDIT=false → imagen del LoRA es el resultado final (suspendido por defecto)
USE_GPT_EDIT = os.getenv("USE_GPT_EDIT", "true").lower() == "true"
