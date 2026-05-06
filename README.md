# Sustain Awards — Generador de Diseños para Trofeos con Impresión UV

Herramienta local que genera 6 propuestas de diseño para trofeos físicos a partir de los datos del premiado y los assets de marca del cliente. Los mockups se producen en alta resolución y son aptos para impresión UV directa sobre el trofeo.

---

## Tabla de contenidos

1. [Qué hace](#qué-hace)
2. [Arquitectura y pipeline](#arquitectura-y-pipeline)
3. [Requisitos previos](#requisitos-previos)
4. [Instalación paso a paso](#instalación-paso-a-paso)
5. [Configuración de claves API](#configuración-de-claves-api)
6. [Cómo ejecutar](#cómo-ejecutar)
7. [Variables de entorno y feature flags](#variables-de-entorno-y-feature-flags)
8. [Estructura de archivos](#estructura-de-archivos)
9. [Modelos de trofeo disponibles](#modelos-de-trofeo-disponibles)
10. [Flujo de datos detallado](#flujo-de-datos-detallado)
11. [Costes por pedido (orientativos)](#costes-por-pedido-orientativos)
12. [Restricciones de impresión UV](#restricciones-de-impresión-uv)
13. [Cómo añadir un nuevo trofeo](#cómo-añadir-un-nuevo-trofeo)
14. [Diagnóstico frecuente](#diagnóstico-frecuente)

---

## Qué hace

1. El operador rellena un formulario web con los datos del premio (titular, subtítulo, URL de marca, logo, brandbook PDF).
2. El sistema extrae la identidad cromática y tipográfica de la marca automáticamente.
3. Un LLM genera 6 conceptos de diseño distintos, cada uno con layout, paleta, estilo de fondo y texto adaptados a la marca.
4. Se generan 6 fondos de imagen (DALL-E o generadores PIL) y se compone el diseño final sobre una fotografía real del trofeo.
5. El resultado son 6 mockups JPG listos para enviar al cliente.

**Inputs aceptados:** URL corporativa · Logo (JPG/PNG/SVG/PDF) · PDF brandbook · Combinación de los anteriores.  
**Output:** 6 imágenes JPG composited sobre fotografía real del trofeo, más JSON con especificaciones de diseño.

---

## Arquitectura y pipeline

```
Formulario web (Flask)
        │
        ▼
capa0_normalizer.py     — Normaliza el pedido. Extrae logo, PDF, screenshot de URL.
        │                  Llama a Firecrawl si hay clave → canonical_palette
        ▼
capa1_ia.py             — 3 llamadas a LLM:
        │                  A) Color Oracle (Haiku, temp=0) → canonical_palette
        │                  B) Brand Analysis (Sonnet, temp=0.3) → brand_context JSON
        │                  C) Design Concepts (Sonnet, temp=1.0) → 6 conceptos
        ▼
capa_dalle.py           — Genera fondo por concepto:
        │                  • DALL-E / gpt-image-1 si USE_DALLE=true
        │                  • 13 generadores PIL como fallback o para demos
        ▼
capa2_renderer.py       — Compone diseño sobre fondo:
        │                  • Playwright (Chromium headless) para renderizado tipográfico
        │                  • PIL/NumPy para composición de capas y efectos
        ▼
capa3_compositor.py     — Composita el diseño sobre la foto real del trofeo
        │                  • Modo rectangular (totem_basic)
        │                  • Modo máscara poligonal (copetin)
        ▼
        6 mockups JPG
```

### Sistema de color (por prioridad)

| Prioridad | Fuente | Descripción |
|-----------|--------|-------------|
| 1 | Firecrawl | Análisis HTML de la URL → `canonical_palette` (más preciso) |
| 2 | Brandbook PDF | Extracción directa del PDF del cliente |
| 3 | Color Oracle | Claude Haiku analiza logo + screenshot → `canonical_palette` |

La `canonical_palette` se inyecta como "verdad absoluta" en las llamadas de Brand Analysis y Design Concepts.

---

## Requisitos previos

| Herramienta | Versión mínima | Notas |
|-------------|---------------|-------|
| Python | 3.10+ | 3.12 recomendado |
| pip / venv | incluido en Python 3 | — |
| Chromium (Playwright) | automático | `playwright install chromium` tras instalar deps |
| Git | cualquier versión reciente | — |

**Cuentas y claves necesarias:**

| Servicio | Obligatorio | Uso | URL |
|----------|-------------|-----|-----|
| Anthropic API | **Sí** | Brand Analysis, Design Concepts, Color Oracle | console.anthropic.com |
| OpenAI API | **Sí** (si USE_DALLE=true) | Generación de fondos DALL-E / gpt-image-1 | platform.openai.com |
| Firecrawl | No (mejora calidad) | Extracción de paleta desde URL corporativa | firecrawl.dev (plan Hobby ~€14/mes) |

> Sin clave de Firecrawl el sistema funciona igualmente. Sin clave de OpenAI debe ponerse `USE_DALLE=false` para usar los generadores PIL gratuitos.

---

## Instalación paso a paso

```bash
# 1. Clonar el repositorio
git clone <url-del-repositorio> sustain-awards
cd sustain-awards

# 2. Crear entorno virtual
python3 -m venv venv
source venv/bin/activate          # Linux / macOS
# venv\Scripts\activate           # Windows

# 3. Instalar dependencias Python
pip install -r requirements.txt

# 4. Instalar Chromium para Playwright (renderizado tipográfico)
playwright install chromium

# 5. Crear el fichero de claves (ver siguiente sección)
touch lakla.txt

# 6. Crear carpeta de salida
mkdir -p outputs/mockups outputs/design_specs
```

---

## Configuración de claves API

El servidor lee automáticamente un archivo `lakla.txt` en la raíz del proyecto.  
**Este archivo está en `.gitignore` y nunca se sube al repositorio.**

Formato — una clave por línea, sin comillas, sin espacios:

```
sk-ant-api03-xxxxxxxxxxxxxxxxxxxx   ← Anthropic API key
sk-proj-xxxxxxxxxxxxxxxxxxxx        ← OpenAI API key
fc-xxxxxxxxxxxxxxxxxxxx             ← Firecrawl API key (opcional)
```

El sistema identifica automáticamente cada clave por su prefijo:
- `sk-ant-` → `ANTHROPIC_API_KEY`
- `sk-proj-` → `OPENAI_API_KEY`
- `fc-` → `FIRECRAWL_API_KEY`

**Alternativa con variables de entorno:**

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-proj-..."
export FIRECRAWL_API_KEY="fc-..."     # opcional
```

Si las variables de entorno ya están definidas y no existe `lakla.txt`, el servidor las usa directamente.

---

## Cómo ejecutar

```bash
source venv/bin/activate
python test_server.py
```

Abrir en el navegador: **http://localhost:5001**

El formulario solicita:
- **Modelo de trofeo**: Totem Basic (madera) o Copetin (metal)
- **URL corporativa** de la marca
- **Logo** del cliente (opcional, acepta JPG/PNG/SVG/PDF)
- **Brandbook PDF** (opcional)
- **Headline** del premio (ej. "Premio al Mejor Proyecto")
- **Subtítulo / mérito** (ej. "Categoría Innovación")
- **Nombre del premiado**
- Datos de contacto del pedido

El proceso dura entre **45 y 120 segundos** según el modelo y si DALL-E está activo.

---

## Variables de entorno y feature flags

Todos los valores tienen defaults funcionales. Sobreescribir según necesidad:

| Variable | Default | Opciones | Descripción |
|----------|---------|----------|-------------|
| `USE_DALLE` | `true` | `true` / `false` | Generar fondos con DALL-E. `false` = solo PIL (gratis, más rápido) |
| `RENDER_ENGINE` | `playwright` | `playwright` / `pil` | Motor de tipografía. PIL no requiere Chromium |
| `IMAGE_PROVIDER` | `openai` | `openai` / `replicate` | Proveedor de imagen IA |
| `IMAGE_MODEL_OPENAI` | `gpt-image-1` | — | Modelo de imagen de OpenAI |
| `IMAGE_QUALITY` | `medium` | `low` / `medium` / `high` | Calidad DALL-E (~$0.011 / $0.042 / $0.080 por imagen) |
| `MODEL_BRAND_ANALYSIS` | `claude-sonnet-4-6` | cualquier modelo Claude/GPT | Modelo para análisis de marca |
| `MODEL_DESIGN_CONCEPTS` | `claude-sonnet-4-6` | `claude-opus-4-7` para máxima calidad | Modelo para conceptos de diseño |
| `MODEL_COLOR_ORACLE` | `claude-haiku-4-5-20251001` | — | Modelo para identificación de paleta |
| `USE_FEW_SHOT` | `true` | `true` / `false` | Usar ejemplos aprobados previos como few-shot |

**Modo demo (sin coste de API de imágenes):**
```bash
USE_DALLE=false python test_server.py
```

**Modo solo PIL sin Chromium:**
```bash
USE_DALLE=false RENDER_ENGINE=pil python test_server.py
```

---

## Estructura de archivos

```
sustain-awards/
├── test_server.py              # Servidor Flask principal (punto de entrada)
├── calibrar_trofeo.py          # Herramienta de calibración de máscaras de trofeo
├── requirements.txt            # Dependencias Python
├── lakla.txt                   # Claves API (NO en git, crear manualmente)
│
├── scripts/
│   ├── config.py               # Modelos, feature flags, configuración centralizada
│   ├── capa0_normalizer.py     # Normalización del pedido, extracción de assets
│   ├── capa1_ia.py             # Llamadas LLM: color, marca, conceptos de diseño
│   ├── capa2_renderer.py       # Renderizado tipográfico (Playwright + PIL)
│   ├── capa3_compositor.py     # Composición final sobre foto del trofeo
│   ├── capa_dalle.py           # Generación de fondos (DALL-E + 13 generadores PIL)
│   └── font_manager.py         # Registro de fuentes TTF locales para PIL
│
├── templates/
│   ├── form.html               # Formulario de entrada de datos del pedido
│   └── results.html            # Página de visualización y descarga de mockups
│
├── data/
│   └── trophy_catalog.json     # Catálogo de trofeos con dimensiones y constraints físicos
│
├── assets/
│   ├── fonts/                  # ~50 fuentes TTF (Montserrat, Raleway, Inter, etc.)
│   ├── trophies/               # Fotos reales de los trofeos + máscaras PNG
│   │   ├── Sustain-Awards-BASIC-Totem-3.jpg
│   │   ├── copetin.png
│   │   └── copetin_mask.png    # Máscara poligonal de 32 puntos para copetin
│   └── logos/                  # Logos temporales de clientes (se borran tras el pedido)
│
├── outputs/
│   ├── mockups/                # JPGs generados (en .gitignore)
│   └── design_specs/           # JSON con especificaciones de cada diseño (en .gitignore)
│
└── arquitectura/
    ├── Sustain_Awards_Arquitectura.pdf   # Documentación técnica detallada en PDF
    └── generar_arquitectura.py           # Script para regenerar el PDF
```

---

## Modelos de trofeo disponibles

### Totem Basic — Madera
- Archivo foto: `assets/trophies/Sustain-Awards-BASIC-Totem-3.jpg`
- Área de impresión: rectangular
- Restricciones UV: solo fuentes **bold**, sin fondos sólidos oscuros, fade en bordes

### Copetin — Metal
- Archivo foto: `assets/trophies/copetin.png`
- Área de impresión: máscara poligonal de 32 puntos calibrados
- Máscara: `assets/trophies/copetin_mask.png`
- Restricciones UV: colores claros preferidos, max 2 colores de marca

Los constraints físicos de cada modelo están en `data/trophy_catalog.json`.

---

## Flujo de datos detallado

```
FormData (POST /generar)
    │
    ├── modelo_trofeo        → selecciona trofeo del catálogo
    ├── url_corporativa      → Firecrawl / screenshot → canonical_palette
    ├── logo (file)          → guardado temporal en assets/logos/
    ├── brandbook (file)     → guardado temporal en assets/logos/
    ├── headline             → forzado en award_text de todos los conceptos
    ├── recipient            → forzado en award_text de todos los conceptos
    └── subtitle             → forzado en award_text de todos los conceptos
            │
            ▼
    brand_context dict
    {canonical_palette, primary_color, secondary_color, accent_color,
     font_family, brand_personality, pdf_resumen, ...}
            │
            ▼
    6 × concepto dict
    {proposal_id, layout, bg_tone, dalle_prompt, award_text,
     text_style, palette, _secondary, _accent, _run_id, ...}
            │
            ├── fondo (PIL o DALL-E imagen 1024×1024)
            ├── overlay + efectos UV
            ├── logo de marca
            └── texto renderizado (Playwright HTML → screenshot / PIL directo)
            │
            ▼
    6 mockups JPG composited sobre foto del trofeo
            │
            ▼
    JSON response:
    {job_id, mockups: [{proposal_id, nombre, concepto, imagen_b64,
                        color_primario, color_secundario, palette}, ...]}
```

---

## Costes por pedido (orientativos)

| Modo | Configuración | Coste aproximado |
|------|--------------|-----------------|
| Demo / pruebas | `USE_DALLE=false` | ~$0.03 (solo Claude Haiku) |
| Producción estándar | config por defecto (Sonnet + gpt-image-1 medium) | ~$0.17–0.23 |
| Producción económica | `IMAGE_PROVIDER=replicate` (Flux Schnell) | ~$0.05–0.08 |
| Máxima calidad | `MODEL_DESIGN_CONCEPTS=claude-opus-4-7` | ~$0.30–0.40 |

---

## Restricciones de impresión UV

El sistema aplica automáticamente las siguientes restricciones según el material del trofeo:

- **Fondos oscuros**: máximo 3 de 6 conceptos con `bg_tone=dark`. P2, P5, P6 siempre `light` o `mid`.
- **Fondos sólidos negros**: prohibidos (la tinta UV necesita variación de textura para adherirse).
- **Fade de bordes**: obligatorio en fondos oscuros.
- **Tintas metálicas**: no existen en UV real — se simulan con gradientes dorados/plateados.
- **Madera (Totem Basic)**: solo fuentes bold, sin fondos muy saturados.
- **Metal (Copetin)**: colores claros preferidos, máximo 2 colores de marca.

---

## Cómo añadir un nuevo trofeo

1. Añadir la fotografía del trofeo en `assets/trophies/`.
2. Ejecutar `python calibrar_trofeo.py` para definir el área de impresión:
   - Modo rectangular: clic en las 4 esquinas del área imprimible.
   - Modo máscara: clic en los puntos del contorno (32 puntos recomendados).
3. La herramienta genera la entrada JSON y la máscara PNG correspondiente.
4. Añadir la entrada en `data/trophy_catalog.json`.
5. Añadir la opción en el selector de `templates/form.html`.

---

## Diagnóstico frecuente

**El servidor arranca pero dice "Falta ANTHROPIC_API_KEY"**
→ Verificar que `lakla.txt` existe en la raíz y contiene la clave con prefijo `sk-ant-`.

**Error de Playwright / Chromium**
→ Ejecutar `playwright install chromium` dentro del venv. Alternativa: `RENDER_ENGINE=pil python test_server.py`.

**Los fondos generados son demasiado oscuros**
→ Verificar en la consola que aparece `[postproceso] PX: dalle_prompt sanitizado` para propuestas mid/light. Si no aparece, revisar `_sanitizar_dalle_prompt()` en `capa1_ia.py`.

**Firecrawl no extrae colores**
→ Verificar que la clave `fc-` está en `lakla.txt`. En consola debe aparecer `[firecrawl] canonical_palette: [...]`. Sin clave, el sistema usa Color Oracle como fallback (sin degradación funcional).

**Todos los diseños tienen el mismo layout**
→ Verificar que `TEMP_DESIGN_CONCEPTS=1.0` (config por defecto). Si Claude sigue eligiendo `stacked` repetidamente, revisar la instrucción de variedad en `PROMPT_B` de `capa1_ia.py`.

**Mockups en blanco o sin texto**
→ Revisar `outputs/design_specs/<job_id>_design_spec.json` — contiene el JSON completo de cada concepto y el error específico si lo hay.
