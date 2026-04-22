---
name: Tareas pendientes y bugs activos
description: Bugs en curso, decisiones abiertas y próximos pasos del pipeline
type: project
originSessionId: 441ddfe6-87cf-4769-b8c1-1dce5dcab318
---
## Bug activo — PDF brandbook visual no llega a Claude

**Síntoma:** `[BrandBook] Error procesando PDF (is no PDF)` → `Brandbook PDF: ✗`

**Causa diagnosticada:**
El texto del PDF SÍ se extrae correctamente (181 páginas, 10 colores HEX, fuentes).
El fallo ocurre en el paso visual dentro de `_extraer_brandbook_completo`:
`fitz.open(stream=bytearray(img_buf.read()), filetype="jpg")` → PyMuPDF 1.27.1
falla al abrir un JPEG como documento para incrustarlo en un PDF nuevo con `show_pdf_page`.

**Archivo:** `scripts/capa0_normalizer.py` → función `_extraer_brandbook_completo`

**PDF de prueba:** `C:\Users\diego\Desktop\practicas\diseño_grafico\pruebas\brandbook_completo.pdf`
— Tamaño: 73.8 MB, 181 páginas. Marca: Juaneda Hospitals.

**Solución acordada (NO implementada — esperar "revisa lo que te he dicho"):**
En lugar de incrustar JPEGs en un PDF nuevo (`nuevo.new_page` + `show_pdf_page`),
enviar cada página directamente como bloque `image` (JPEG base64) en el content de Claude.
Esto evita la capa de "PDF envoltorio" que falla en PyMuPDF 1.27.
Requiere:
1. En `capa0_normalizer.py`: `_extraer_brandbook_completo` devuelve lista de JPEG b64
   en lugar de un PDF b64.
2. En `capa1_ia.py`: `_llamada_brand_analysis` añade cada JPEG como bloque
   `{"type": "image", "source": {"type": "base64", ...}}` al content de Claude.
   Eliminar el bloque `{"type": "document", ...}` del PDF visual.

**Why:** PyMuPDF 1.27 cambió el manejo interno de streams JPEG. La estrategia de
páginas-como-imágenes es más robusta y más directa para la API de Claude
(que acepta image blocks nativamente, sin necesidad de PDF envoltorio).

---

## Estado general del proyecto (2026-04-12)

### Funciona correctamente
- Pipeline completo: logo → Claude A → Claude B → DALLE fondo → DALLE texto → chroma key → render PIL
- 4 layouts de texto: stacked, spread, staggered, billboard
- Auto-corrección de logo (luminancia + distancia cromática), preservación luminancia interna
- Google Fonts integration (font_manager.py)
- Extracción de texto del PDF (colores HEX, Pantone, fuentes — todas las páginas) ✓
- Servidor web Flask (test_server.py) en http://localhost:5000

### Parcialmente funciona
- Brandbook PDF → Claude: el TEXTO llega ✓, las páginas visuales NO ✗ (bug arriba)
- Tipografía de marca: nombre se envía a DALLE (ok), PIL solo usa en fallback

### Pendiente
- Fix visual de páginas PDF → Claude (bug principal, solución documentada arriba)
- Favicon (da 500 en Flask — no crítico)

---

## Contexto de negocio (reunión 19/03/2026)
- Coste aprobado: ~30 céntimos/pedido vs ~30€ diseñador humano
- Prioridad 2 del sprint (tras migración Odoo)
- Formulario definitivo pendiente de definir con el jefe (~1 semana desde reunión)
- Catálogo de trofeos: solo Totem Basic calibrado; falta el resto
- Integración PrestaShop: backend listo, falta conector HTTP
