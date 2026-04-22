---
name: Agente Diseño Gráfico — Arquitectura técnica del pipeline
description: Las 5 capas del pipeline, su función, inputs, outputs y detalles de implementación
type: project
---

# Arquitectura del Pipeline (5 capas)

## Entorno técnico
- Python 3.13.12, Windows 11
- venv en `venv/Scripts/python`
- Paquetes: anthropic, Pillow 12.1.1, numpy, PyMuPDF, requests, beautifulsoup4, flask
- `scripts/` es un paquete Python (tiene `__init__.py`)
- Imports: `from scripts import capa0_normalizer as capa0` etc.

---

## CAPA 0 — `scripts/capa0_normalizer.py`
**Función:** Normalización de assets del cliente.

Funciones clave:
- `normalizar_pedido(pedido, logo_bytes=None, pdf_bytes=None)` → `brand_context` dict
- `resolver_asset(path)` — fuzzy matching de nombres (maneja `MANUAL_INICIATIVAS_SOCIALES.pdf` vs `MANUAL INICIATIVAS SOCIALES.pdf` con espacios)
- `codificar_imagen(path_o_bytes)` → base64 JPEG
- `codificar_pdf(path_o_bytes)` → base64 raw bytes
- `fetch_url(url)` → dict con `{colores_detectados, densidad_visual, descripcion_estilo, tiene_gradientes, tiene_imagenes_hero, num_imagenes, ok}`

---

## CAPA 1 — `scripts/capa1_ia.py`
**Función:** Agente IA — 3 llamadas secuenciales a Claude.

Modelo: `MODELO_CLAUDE = "claude-opus-4-6"` (línea 32)

3 llamadas:
- **Llamada A (Brand Analysis):** logo b64 + PDF b64 + URL data → vocabulario visual JSON (brand_name, brand_tone, visual_density, colors, logo_analysis, typography, web_context)
- **Llamada B (Archetype Selection):** brand analysis → 3 arquetipos de los 8 disponibles (reglas: siempre 1 minimalista, nunca 2 iguales, ≥1 oscuro + ≥1 claro)
- **Llamada C (Design Briefs):** brand analysis + arquetipos → 3 design_brief JSON completos

Funciones principales:
- `diseñar_desde_contexto(pedido, brand_context)` → `(briefs[3], spec_completo)` — usado por orquestador y test_server
- `diseñar_pedido(id_pedido)` — wrapper CLI, carga de mock_orders.json
- `diseñar_desde_datos(pedido, logo_bytes, logo_ext, pdf_bytes)` — wrapper web, acepta bytes
- `_llamar_claude(mensajes, system_prompt, etiqueta)` — llamada genérica con extracción JSON (maneja markdown fences)
- `_validar_brief(brief, pedido)` — rellena campos faltantes con defaults seguros

## Los 8 arquetipos compositivos
1. Ilustración figurativa hero
2. Tipografía rotada 90° como gráfico
3. Forma geométrica derivada del logo
4. Patrón radial/scatter desde el logo
5. Fondo sólido color de marca + tipografía display
6. Gradiente con formas abstractas flotantes
7. Split cromático vertical u horizontal
8. Minimalismo tipográfico puro (siempre disponible como fallback)

---

## CAPA 2 — `scripts/capa2_renderer.py`
**Función:** Renderer programático — dibuja diseños desde JSON.

Función principal: `renderizar_diseno(brief, w, h, logo_path, award, fuentes, seed)` → Image RGBA

Pasos internos:
1. `_render_fondo()` — sólido o gradiente lineal numpy (vertical/horizontal)
2. `_render_split()` — split cromático con dos rectángulos
3. `_render_formas_flotantes()` — círculos/elipses RGBA, seed para reproducibilidad
4. `_render_logo()` — carga logo, elimina fondo blanco (numpy threshold >230), aplica treatment (blanco/color), escala, posiciona
5. `_render_texto()` — separador + headline/recipient/subtitle/año con jerarquía

Fuentes: busca primero en `C:/Windows/Fonts/` (arialbd.ttf, calibri, segoeui), luego Linux, fallback PIL default.

---

## CAPA 3 — `scripts/capa3_compositor.py`
**Función:** Compositing sobre foto del trofeo.

- `cargar_modelo_trofeo(id_modelo)` → carga `data/trophy_catalog.json`
- `componer(diseno_rgba, trofeo_path, zona)` → Image RGB (paste sobre foto real del trofeo)

---

## Schema del design brief (output Capa 1, input Capa 2)
```json
{
  "proposal_id": 1,
  "pattern_archetype": 6,
  "pattern_name": "Gradiente con formas flotantes",
  "design_rationale": "...",
  "background": {"type": "gradient|solid", "color_1": "#HEX", "color_2": "#HEX", "direction": "vertical|horizontal"},
  "floating_shapes": {"active": true, "shape": "circle|ellipse", "count": 8, "size_min": 0.05, "size_max": 0.25, "opacity": 0.12, "color": "#HEX"},
  "color_split": {"active": false, "direction": "horizontal|vertical", "ratio": 0.45, "color_zone_1": "#HEX", "color_zone_2": "#HEX"},
  "logo": {"treatment": "blanco|color", "position": "top_center|center|top_left", "scale": 0.65},
  "text": {"color": "#HEX", "alignment": "center|left", "headline_size_ratio": 0.07, "margin_h": 0.07}
}
```

---

## Catálogo de trofeos (`data/trophy_catalog.json`)
- **totem_basic** ✅ — foto real `assets/trophies/Sustain-Awards-BASIC-Totem-3.jpg`, zona calibrada (x=490, y=257, 247×793px en imagen 1200×1500)
- **placa_a5** ❌ — placeholder inexistente, coordenadas no calibradas

Para añadir un modelo: 2 fotos distintas perspectivas + medir píxeles exactos donde va el diseño en Paint + entrada en trophy_catalog.json (~15 min).

**IMPORTANTE (confirmado por jefe en reunión 19/03):** El diseño generado es una imagen pequeña que se renderiza solo para la zona editable y se pega encima de la foto real del trofeo. NO se genera la imagen completa del trofeo desde cero. Esto evita alucinaciones, reduce costes y mantiene el aspecto real del producto.

## Inputs del formulario (confirmados en reunión 19/03)
El jefe señaló expresamente que Diego había olvidado incluir el **texto del galardón**:
1. Logo PNG (obligatorio)
2. Brand book PDF (obligatorio)
3. URL corporativa (opcional — puede omitirse si hay brandbook)
4. **Texto de ejemplo del galardón** (obligatorio — aparece en el trofeo físico)

Queda pendiente definir con el jefe y Carlos cuáles son exactamente obligatorios y la prioridad entre ellos.

---

## Orquestador y servidor de prueba
- `orchestrador.py` — CLI: `python orchestrador.py ORD-2026-001 [--dry-run]`
- `test_server.py` — Flask, `python test_server.py` → http://localhost:5000
  - Guarda logo en `assets/logos/_test_{job_id}.{ext}`, lo borra en `finally`
  - Devuelve JSON con mockups en base64
- `data/mock_orders.json` — 2 pedidos de ejemplo: ORD-2026-001 (Ofesauto, totem_basic) y ORD-2026-002 (GreenEnergy, placa_a5)
