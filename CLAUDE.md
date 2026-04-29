# Sustain Awards — Contexto del proyecto

## Qué es
Generador automático de diseños para trofeos físicos con impresión UV.
Input: datos del premiado + assets de marca (logo/URL/brandbook) → Output: 6 mockups JPG.

## Stack
Python 3.x · Flask · Claude API (Anthropic) · OpenAI DALL-E · Firecrawl · PIL/NumPy · Playwright

## Cómo ejecutar
```
source venv/bin/activate && python test_server.py   # http://localhost:5001
python orchestrador.py ORD-XXXX                     # CLI
```
Claves API: se cargan automáticamente desde `lakla.txt` (sk-proj-=OpenAI, sk-ant-=Anthropic, fc-=Firecrawl).

## Pipeline (orden de ejecución)
```
capa0_normalizer.py  → Extrae logo/PDF/URL. Llama Firecrawl si hay FIRECRAWL_API_KEY.
capa1_ia.py          → 3 llamadas Claude: Color Oracle (Haiku) → Brand Analysis (Sonnet) → Design Concepts (Sonnet)
capa2_renderer.py    → Renderiza 6 diseños: fondo DALL-E o PIL + logo + texto (Playwright/PIL)
capa3_compositor.py  → Composita diseño sobre foto real del trofeo
capa_dalle.py        → Generación de fondos: DALL-E o 13 generadores PIL aleatorios
```

## Sistema de colores (flujo por prioridad)
1. **Firecrawl** (si FIRECRAWL_API_KEY): HTML analysis → `canonical_palette` → skip screenshot + skip Color Oracle
2. **Brandbook PDF**: verdad absoluta → skip Color Oracle
3. **Color Oracle** (Haiku, temp=0): logo + screenshot + pre_palette HSV → `canonical_palette`
4. `canonical_palette` se inyecta como "VERDAD ABSOLUTA" en Brand Analysis y Design Concepts

## Restricciones de impresión UV (obligatorias)
Ver `.claude/skills/sustain-printing.md`. Puntos críticos:
- Sin fondos sólidos oscuros (variación de textura en tinta UV)
- Sin tintas metálicas reales (simular con gradientes)
- Fade obligatorio en bordes para fondos oscuros
- Restricciones por material: madera (bold only), piedra (max 2 colores), metal (claros preferidos)

## Ficheros clave
| Fichero | Función |
|---|---|
| `scripts/config.py` | Modelos, APIs, feature flags (USE_DALLE, FIRECRAWL_API_KEY) |
| `scripts/capa0_normalizer.py` | `normalizar_pedido()` → brand_context |
| `scripts/capa1_ia.py` | `diseñar_desde_contexto()` · PROMPT_A/B/COLOR_ORACLE |
| `scripts/capa2_renderer.py` | `renderizar_diseno()` — Playwright + PIL |
| `scripts/capa_dalle.py` | `generar_fondo()` — DALL-E + 13 generadores PIL |
| `data/trophy_catalog.json` | Catálogo de trofeos con constraints físicos |
| `test_server.py` | Servidor Flask + carga de `lakla.txt` en arranque |
| `lakla.txt` | Claves API (en .gitignore — NO commitear) |

## Estado actual (abril 2026)
- Logo es opcional (basta con URL o brandbook)
- Firecrawl integrado como capa primaria de color (€14/mes plan Hobby)
- 13 generadores PIL aleatorios + 51 estilos DALL-E para variedad de fondos
- Diagnóstico de colores en consola: muestra si canonical_palette fue respetada por Claude
- Cuando Firecrawl activo: screenshot omitido (HTML analysis > pixel extraction)

## Convenciones
- `brand_context` dict: fluye de capa0 → capa1
- `concepto` dict: fluye de capa1 → capa2/capa_dalle (lleva `_secondary`, `_accent`, `_colors_extended`, `_run_id`)
- Temperatura: Brand Analysis=0.3 · Design Concepts=1.0 · Color Oracle=0.0
