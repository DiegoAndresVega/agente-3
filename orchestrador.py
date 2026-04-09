"""
ORCHESTRADOR — Sustain Awards
Pipeline completo de diseño automático con IA.

Flujo:
    CAPA 0  normalizar_pedido()     → brand_context (logo b64, PDF b64, URL data)
    CAPA 1  diseñar_desde_contexto() → 3 design briefs JSON (3 llamadas Claude)
    CAPA 2  renderizar_diseno()      → 3 imágenes RGBA del diseño
    CAPA 3  componer()               → 3 mockups JPG sobre foto del trofeo

Uso:
    python orchestrador.py ORD-2026-001
    python orchestrador.py ORD-2026-001 --dry-run    # solo Capas 0+1, sin imágenes

Requisitos:
    export ANTHROPIC_API_KEY=sk-ant-...
"""

import sys
import argparse
from pathlib import Path

from scripts import capa0_normalizer as capa0
from scripts import capa1_ia         as capa1
from scripts import capa2_renderer   as capa2
from scripts import capa3_compositor as capa3


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR  = PROJECT_ROOT / "outputs" / "mockups"


def main():
    parser = argparse.ArgumentParser(
        description="Sustain Awards – Pipeline de diseño automático con IA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("id_pedido", help="ID del pedido (ej: ORD-2026-001)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Ejecuta solo Capas 0+1 (análisis IA) sin generar imágenes"
    )
    args = parser.parse_args()

    print("\n" + "=" * 55)
    print("  SUSTAIN AWARDS · Pipeline de Diseño Automático")
    print("=" * 55)

    # ── CAPA 0: normalización ─────────────────────────────────────────────────
    import json
    with open(PROJECT_ROOT / "data" / "mock_orders.json", encoding="utf-8") as f:
        datos = json.load(f)
    pedido = next(
        (p for p in datos["pedidos"] if p["id_pedido"] == args.id_pedido), None
    )
    if pedido is None:
        print(f"\n  [ERROR] Pedido '{args.id_pedido}' no encontrado", file=sys.stderr)
        sys.exit(1)

    print(f"\n>>> CAPA 0: Normalizando assets...")
    try:
        brand_context = capa0.normalizar_pedido(pedido)
    except FileNotFoundError as e:
        print(f"\n  [ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    # ── CAPA 1: diseño IA ─────────────────────────────────────────────────────
    print(f"\n>>> CAPA 1: Diseñador IA (3 llamadas a Claude)...")
    try:
        briefs, spec = capa1.diseñar_desde_contexto(pedido, brand_context)
    except EnvironmentError as e:
        print(f"\n  [ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"\n  [ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        _print_dry_run(briefs, spec)
        print("\n  [DRY-RUN] Completado. Imágenes no generadas.")
        sys.exit(0)

    # ── CAPA 2 + 3: render y compositing ─────────────────────────────────────
    print(f"\n>>> CAPAS 2+3: Renderizando y componiendo mockups...")
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    modelo    = capa3.cargar_modelo_trofeo(pedido["modelo_trofeo"])
    zona      = modelo["zona_imprimible"]
    w, h      = zona["ancho"], zona["alto"]
    fuentes   = capa2.cargar_fuentes()
    logo_path = brand_context.get("logo_path", pedido["assets"].get("logo_path", ""))
    award     = pedido["award"]
    id_pedido = pedido["id_pedido"]
    rutas     = []

    for brief in briefs:
        pid   = brief["proposal_id"]
        nombre = brief.get("pattern_name", f"propuesta_{pid}").lower().replace(" ", "_")
        print(f"\n  Propuesta {pid} — {brief.get('pattern_name', '—')}...")

        # Capa 2: renderizar diseño
        diseno = capa2.renderizar_diseno(
            brief, w, h, logo_path, award, fuentes, seed=pid * 100
        )

        # Capa 3: componer sobre foto del trofeo
        mockup = capa3.componer(diseno, modelo["imagen_base"], zona)

        # Guardar
        output_path = OUTPUTS_DIR / f"mockup_{id_pedido}_p{pid}_{nombre}.jpg"
        mockup.save(str(output_path), quality=95)
        rutas.append(str(output_path))
        print(f"  → Guardado: {output_path.name}")

    # ── Resultado ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  PIPELINE COMPLETADO")
    print("=" * 55)
    analisis = spec.get("brand_analysis", {})
    print(f"\n  Marca    : {analisis.get('brand_name', '—')}")
    print(f"  Tono     : {analisis.get('brand_tone', '—')}")
    print(f"\n  Propuestas generadas:")
    for brief in briefs:
        print(f"    {brief['proposal_id']}. {brief['pattern_name']}")
        print(f"       {brief['design_rationale']}")
    print(f"\n  Mockups:")
    for r in rutas:
        print(f"    → {r}")
    print()


def _print_dry_run(briefs: list, spec: dict):
    analisis = spec.get("brand_analysis", {})
    print(f"\n  Análisis de marca:")
    print(f"    Nombre     : {analisis.get('brand_name', '—')}")
    print(f"    Tono       : {analisis.get('brand_tone', '—')}")
    colores = analisis.get("colors", {})
    print(f"    Primario   : {colores.get('primary', '—')}")
    print(f"    Secundario : {colores.get('secondary', '—')}")
    print(f"\n  Propuestas seleccionadas por la IA:")
    for b in briefs:
        fondo = b.get("background", {})
        print(f"\n  {b['proposal_id']}. {b.get('pattern_name', '—')}")
        print(f"     {b.get('design_rationale', '—')}")
        print(f"     Fondo: {fondo.get('type')} {fondo.get('color_1')} "
              f"{'→ ' + fondo.get('color_2', '') if fondo.get('color_2') else ''}")


if __name__ == "__main__":
    main()
