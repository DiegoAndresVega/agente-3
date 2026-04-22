---
name: Agente Diseño Gráfico — Mapa de archivos del proyecto
description: Todos los archivos relevantes del proyecto, su función y estado
type: project
---

# Mapa de archivos — Agente Diseño Gráfico

## Raíz del proyecto
`C:\Users\diego\Desktop\practicas\diseño_grafico\`

```
diseño_grafico/
├── orchestrador.py              ← CLI principal del pipeline
├── test_server.py               ← Servidor Flask de prueba local (puerto 5000)
│
├── scripts/
│   ├── __init__.py              ← Hace scripts/ un paquete Python (necesario para imports)
│   ├── capa0_normalizer.py      ← Normalización de assets (logo, PDF, URL)
│   ├── capa1_ia.py              ← Agente IA — 3 llamadas Claude
│   ├── capa2_renderer.py        ← Renderer programático (dibuja desde JSON)
│   ├── capa3_compositor.py      ← Compositing sobre foto del trofeo
│   └── capa2_compositor.py      ← Módulo anterior (mantenido, no se toca)
│
├── data/
│   ├── mock_orders.json         ← 2 pedidos de ejemplo (ORD-2026-001, ORD-2026-002)
│   └── trophy_catalog.json      ← Catálogo de modelos con coordenadas calibradas
│
├── assets/
│   ├── logos/
│   │   ├── logo_ofesauto.png    ← Logo de ejemplo (cliente Ofesauto)
│   │   └── greenenergy_logo.png ← Logo de ejemplo (cliente GreenEnergy)
│   ├── trophies/
│   │   ├── Sustain-Awards-BASIC-Totem-3.jpg  ← Foto real del trofeo (CALIBRADA ✅)
│   │   └── Sustain-Awards-BASIC-Totem-5.jpg  ← Foto alternativa (no usada actualmente)
│   └── brand_books/
│       └── MANUAL INICIATIVAS SOCIALES.pdf   ← PDF de ejemplo (nota: nombre con espacios)
│
├── outputs/
│   └── mockups/                 ← Aquí se guardan los JPG generados
│
├── AGENTE 2 - Diseño gráfico/
│   ├── avance-pipeline-ia.html  ← Informe de avance para la empresa (generado)
│   ├── sustain-awards-spec-completa.pdf
│   ├── sustain-awards-roadmap-v3.pdf
│   └── Conversacion con Claude.docx
│
└── venv/                        ← Entorno virtual Python
```

## Notas importantes sobre archivos
- El PDF del brand book en disco se llama `MANUAL INICIATIVAS SOCIALES.pdf` (con espacios)
  pero mock_orders.json lo referencia como `MANUAL_INICIATIVAS_SOCIALES.pdf` (con guiones bajos).
  Esto está resuelto en `capa0_normalizer.py` con fuzzy matching en `resolver_asset()`.
- `placa_a5_placeholder.png` referenciado en trophy_catalog.json NO EXISTE en disco.
- Los logos de ejemplo son logos reales de empresas usados solo para pruebas locales.
