"""
Configuración centralizada de modelos y feature flags del Agente 3.
Todos los valores pueden sobreescribirse con variables de entorno.

Coste orientativo por pedido (3 trofeos):
    Demo/pruebas  USE_DALLE=false              ~$0.03  (solo Claude)
    USE_LORA=true  LoRA + gpt edit             ~$0.09/trofeo
    USE_LORA=false gpt-image-1 directo         ~$0.042/trofeo
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

# LoRA (Replicate Flux) — dataset saawdtrophy, 30 imágenes, 1500 steps
# Entrenado: 2026-05-20 · trigger: saawdtrophy · coste ~$0.003/img
REPLICATE_LORA_MODEL = os.getenv(
    "REPLICATE_LORA_MODEL",
    "diegoandresvega/saawdtrophy-lora-v3:c8794783be4354357f0ef5fb89fb8a3987efe5865dd07b692924ea5f56ff1f62"
)
LORA_TRIGGER_WORD = os.getenv("LORA_TRIGGER_WORD", "saawdtrophy")

# USE_LORA=true  → Replicate LoRA (forma) + gpt-image-1 edit (textura+logo)
# USE_LORA=false → gpt-image-1 generate directamente
USE_LORA = os.getenv("USE_LORA", "false").lower() == "true"


# ─── Feature flags ────────────────────────────────────────────────────────────

# USE_DALLE=false → PIL fallback sin coste (solo para pruebas locales)
USE_DALLE = os.getenv("USE_DALLE", "true").lower() == "true"
