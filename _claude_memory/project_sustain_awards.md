---
name: Agente Diseño Gráfico — Contexto general
description: Qué es el proyecto, para qué empresa, objetivo y estado actual
type: project
---

# Agente Diseño Gráfico — Sustain Awards

**Empresa:** Sustain Awards (sustainawards.com) — empresa de trofeos personalizados.

**Objetivo del proyecto:** Backend de IA que recibe los assets de un cliente (logo, brandbook PDF, URL corporativa, texto del galardón) y genera automáticamente 3 mockups de diseño personalizados para el trofeo. El cliente elige uno y ese diseño se imprime en el trofeo físico.

**Nombre interno del proyecto:** "Agente Diseño Gráfico" / "Pipeline IA Diseño"

**Estado actual (marzo 2026):** Versión 0.1 — Prueba de concepto completamente funcional en local. Pendiente de prueba real con API key de Anthropic.

**Carpeta raíz del proyecto:**
`C:\Users\diego\Desktop\practicas\diseño_grafico\`

**Documentación oficial del proyecto:**
`C:\Users\diego\Desktop\practicas\diseño_grafico\AGENTE 2 - Diseño gráfico\`
Contiene: spec completa (PDF), roadmap v3 (PDF), conversaciones previas, arquitecturas 1 y 2.

**Informe de avance generado (HTML):**
`AGENTE 2 - Diseño gráfico\avance-pipeline-ia.html` — presentación para la empresa con task list, costes, flujo y preguntas.

## Decisiones de diseño confirmadas
- 3 propuestas por pedido (no 6)
- La IA elige los 3 mejores arquetipos de 8 disponibles
- Análisis de URL corporativa con requests + BeautifulSoup
- Renderer programático MVP (no templates fijos)
- Funciona 100% en local; al ir a producción solo cambia el wrapper HTTP
- El JSON de mock_orders.json simula exactamente lo que llegará del formulario HTML

## Modelo de IA en uso
- `claude-opus-4-6` (actualmente configurado en capa1_ia.py)
- Coste por pedido con Opus: ~$0.36
- Coste por pedido con Sonnet 4.6: ~$0.03 (recomendado para producción)

## Bloqueante actual
- Falta `ANTHROPIC_API_KEY` para ejecutar pruebas reales
- Crear cuenta en console.anthropic.com, añadir créditos, exportar la key

**Why:** El sistema está terminado a nivel de código pero no se ha podido verificar con una llamada real a Claude. Todo lo demás está listo.

**How to apply:** Al retomar el proyecto, el primer paso es siempre verificar si ya tienen la API key. Si sí, ejecutar `python orchestrador.py ORD-2026-001 --dry-run` para validar.
