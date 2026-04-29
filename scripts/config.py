"""
Configuración centralizada de modelos, proveedores y feature flags.
Todos los valores pueden sobreescribirse con variables de entorno.

Uso:
    from scripts.config import MODEL_DESIGN_CONCEPTS, USE_DALLE

Coste orientativo por pedido (6 conceptos, 3 con imágenes IA):
    Demo/pruebas           USE_DALLE=false          ~$0.03  (solo Claude Haiku)
    Producción estándar    config por defecto        ~$0.17-0.23
    Producción económica   IMAGE_PROVIDER=replicate  ~$0.05-0.08 (Flux Schnell)
    Máxima calidad         MODEL_DESIGN_CONCEPTS=claude-opus-4-7  ~$0.30-0.40
"""
import os


# ─── Modelos de lenguaje ──────────────────────────────────────────────────────

# Call A: Análisis de marca — extracción estructurada JSON, precisión > creatividad.
# Opciones: "claude-haiku-4-5-20251001" (rápido/barato), "claude-sonnet-4-6", "gpt-4o-mini"
MODEL_BRAND_ANALYSIS = os.getenv("MODEL_BRAND_ANALYSIS", "claude-sonnet-4-6")
TEMP_BRAND_ANALYSIS  = float(os.getenv("TEMP_BRAND_ANALYSIS", "0.3"))

# Call B: Conceptos de diseño — el más importante para calidad creativa.
# Opciones: "claude-sonnet-4-6" (recomendado), "claude-opus-4-7" (premium), "gpt-4o"
MODEL_DESIGN_CONCEPTS = os.getenv("MODEL_DESIGN_CONCEPTS", "claude-sonnet-4-6")
TEMP_DESIGN_CONCEPTS  = float(os.getenv("TEMP_DESIGN_CONCEPTS", "1.0"))

# Color Oracle: identificación de paleta canónica — rápido, barato, determinista.
# Haiku es suficiente: tarea de extracción visual, no creativa. Temp=0 para consistencia.
MODEL_COLOR_ORACLE = os.getenv("MODEL_COLOR_ORACLE", "claude-haiku-4-5-20251001")
TEMP_COLOR_ORACLE  = float(os.getenv("TEMP_COLOR_ORACLE", "0.0"))

# Firecrawl: capa primaria de identificación de color y tipografía por URL.
# Sin key → se salta silenciosamente y el pipeline usa el Color Oracle como fallback.
# Obtener key en: firecrawl.dev — plan Hobby €14/mes cubre ~1.000-3.000 marcas/mes.
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")


# ─── Generación de imágenes ───────────────────────────────────────────────────

# Proveedor de imágenes: "openai" | "replicate"
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "openai")

# OpenAI — gpt-image-1 quality=medium ~$0.042/img, quality=low ~$0.011/img
IMAGE_MODEL_OPENAI = os.getenv("IMAGE_MODEL_OPENAI", "gpt-image-1")
IMAGE_QUALITY      = os.getenv("IMAGE_QUALITY", "medium")  # "low" | "medium" | "high"

# Replicate (Flux) — alternativa más económica
# flux-schnell: ~$0.003/img  (10x más barato, buena calidad para fondos)
# flux-dev:     ~$0.030/img  (calidad comparable a gpt-image-1)
REPLICATE_MODEL = os.getenv("REPLICATE_MODEL", "black-forest-labs/flux-schnell")


# ─── Motor de renderizado tipográfico ────────────────────────────────────────

# "playwright" — Chromium headless, Google Fonts reales, text-shadow, máxima calidad
# "pil"        — PIL puro, sin Chromium, más rápido, fuentes del sistema
RENDER_ENGINE = os.getenv("RENDER_ENGINE", "playwright")


# ─── Feature flags ────────────────────────────────────────────────────────────

# Activar generación de imágenes IA (False = solo fondos PIL, sin coste de API)
USE_DALLE = os.getenv("USE_DALLE", "true").lower() == "true"

# Activar few-shot learning con ejemplos previos aprobados por el usuario
USE_FEW_SHOT = os.getenv("USE_FEW_SHOT", "true").lower() == "true"
MAX_FEW_SHOT = int(os.getenv("MAX_FEW_SHOT", "15"))
