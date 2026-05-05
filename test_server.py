"""
TEST SERVER - Sustain Awards
Servidor local de prueba con formulario HTML.

Uso:
    python test_server.py

Luego abre: http://localhost:5000
"""

import os
import sys
import uuid

# Windows usa cp1252 por defecto — forzar UTF-8 en el stream existente (in-place)
# reconfigure() modifica el stream actual, no crea uno nuevo, por lo que Flask/Werkzeug
# también usan la nueva codificación desde el inicio.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import base64
import shutil
from pathlib import Path


def _cargar_claves(ruta: str = "lakla.txt") -> None:
    """
    Lee el fichero de claves y las inyecta como variables de entorno.
    Identifica cada clave por su prefijo:
      sk-proj-  → OPENAI_API_KEY
      sk-ant-   → ANTHROPIC_API_KEY
    Las líneas vacías y los comentarios (#) se ignoran.
    """
    fichero = Path(__file__).parent / ruta
    if not fichero.exists():
        print(f"  [claves] Fichero '{ruta}' no encontrado — usando variables de entorno existentes")
        return

    cargadas = []
    with open(fichero, encoding="utf-8") as f:
        for linea in f:
            clave = linea.strip()
            if not clave or clave.startswith("#"):
                continue
            if clave.startswith("sk-proj-"):
                os.environ["OPENAI_API_KEY"] = clave
                cargadas.append("OPENAI_API_KEY")
            elif clave.startswith("sk-ant-"):
                os.environ["ANTHROPIC_API_KEY"] = clave
                cargadas.append("ANTHROPIC_API_KEY")
            elif clave.startswith("fc-"):
                os.environ["FIRECRAWL_API_KEY"] = clave
                cargadas.append("FIRECRAWL_API_KEY")

    if cargadas:
        print(f"  [claves] Cargadas desde '{ruta}': {', '.join(cargadas)}")
    else:
        print(f"  [claves] '{ruta}' encontrado pero sin claves reconocidas")


_cargar_claves()
from pathlib import Path
from io import BytesIO

from flask import Flask, request, render_template, jsonify, send_from_directory

# Asegurar que scripts/ sea importable
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from scripts import capa0_normalizer as capa0
from scripts import capa1_ia         as capa1
from scripts import capa2_renderer   as capa2
from scripts import capa3_compositor as capa3

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB máximo

PROJECT_ROOT = Path(__file__).resolve().parent

# ─── Rutas Flask ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("form.html")


@app.route("/resultados")
def resultados():
    return render_template("results.html")


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory(PROJECT_ROOT / "assets", filename)


@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    traceback.print_exc()
    return jsonify({"error": f"Error del servidor: {str(e)}"}), 500

@app.errorhandler(413)
def handle_too_large(e):
    return jsonify({"error": "El archivo es demasiado grande. Máximo permitido: 100 MB."}), 413


@app.route("/feedback", methods=["POST"])
def feedback():
    """Guarda un diseño bien valorado como ejemplo de aprendizaje para la IA."""
    import json as _json
    data = request.get_json()
    job_id      = data.get("job_id")
    proposal_id = data.get("proposal_id")

    if not job_id or proposal_id is None:
        return jsonify({"error": "Datos incompletos"}), 400

    try:
        # Leer la spec guardada por Capa 1
        spec_path = PROJECT_ROOT / "outputs" / "design_specs" / f"{job_id}_design_spec.json"
        if not spec_path.exists():
            return jsonify({"error": "Spec no encontrado. ¿El servidor fue reiniciado?"}), 404

        with open(spec_path, encoding="utf-8") as f:
            spec = _json.load(f)

        briefs = spec.get("design_briefs", [])
        brief  = next((b for b in briefs if b.get("proposal_id") == proposal_id), None)
        if not brief:
            return jsonify({"error": "Propuesta no encontrada en la spec"}), 404

        # Carpeta de aprendizaje
        aprendizaje_dir = PROJECT_ROOT / "assets" / "aprendizaje"
        aprendizaje_dir.mkdir(parents=True, exist_ok=True)

        # Nombre base único (evita duplicados si se pulsa dos veces)
        nombre_base = f"{job_id}_p{proposal_id}"
        json_dst = aprendizaje_dir / f"{nombre_base}.json"
        img_dst  = aprendizaje_dir / f"{nombre_base}.jpg"

        # Guardar brief JSON
        with open(json_dst, "w", encoding="utf-8") as f:
            _json.dump(brief, f, ensure_ascii=False, indent=2)

        # Copiar imagen del mockup si existe
        img_src = PROJECT_ROOT / "outputs" / "mockups" / f"mockup_{job_id}_p{proposal_id}.jpg"
        if img_src.exists():
            shutil.copy2(img_src, img_dst)

        # Contar cuántos ejemplos hay ya guardados
        total = len(list(aprendizaje_dir.glob("*.json")))
        print(f"  [Aprendizaje] Diseño guardado: {nombre_base} · Total acumulado: {total}")
        return jsonify({"ok": True, "total_ejemplos": total})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generar", methods=["POST"])
def generar():
    logo_tmp_path = None
    try:
        # Logo (opcional — el sistema funciona con URL o brandbook sin logo)
        logo_file  = request.files.get("logo")
        _tiene_logo = logo_file and logo_file.filename != ""
        logo_bytes  = logo_file.read() if _tiene_logo else None
        logo_ext    = Path(logo_file.filename).suffix.lstrip(".") if _tiene_logo else "png"

        # Validar que hay al menos UNA fuente de identidad
        url_input = request.form.get("url_corporativa", "").strip()
        pdf_file_check = request.files.get("brandbook")
        _tiene_pdf = pdf_file_check and pdf_file_check.filename != ""
        if not _tiene_logo and not url_input and not _tiene_pdf:
            return jsonify({"error": "Proporciona al menos el logo, la URL corporativa o el brandbook"}), 400

        # PDF (opcional)
        pdf_file  = request.files.get("brandbook")
        pdf_bytes = pdf_file.read() if pdf_file and pdf_file.filename else None

        # Fuente corporativa (opcional — máxima fidelidad tipográfica)
        _font_upload_stem = ""
        font_file = request.files.get("font")
        if font_file and font_file.filename:
            font_ext = Path(font_file.filename).suffix.lstrip(".").lower()
            if font_ext in ("ttf", "otf"):
                font_data = font_file.read()
                font_stem = Path(font_file.filename).stem
                from scripts.font_manager import register_local_font
                registered = register_local_font(font_stem, font_data, font_ext)
                if registered:
                    _font_upload_stem = font_stem
                    print(f"  [server] Fuente subida: {font_file.filename} → {registered.name}")

        # Construir pedido — campos vacíos quedan como "" para que la IA los genere
        job_id = f"FORM-{uuid.uuid4().hex[:8].upper()}"
        _headline  = request.form.get("headline", "").strip()
        _recipient = request.form.get("recipient", "").strip()
        _subtitle  = request.form.get("subtitle", "").strip()
        _evento_fecha = request.form.get("evento_fecha", "").strip()
        _contacto_fecha = request.form.get("contacto_fecha", "").strip()

        pedido = {
            "id_pedido":     job_id,
            "id_cliente":    "",
            "modelo_trofeo": request.form.get("modelo_trofeo", "totem_basic"),
            "cantidad":      request.form.get("contacto_cantidad", "1"),
            "presupuesto":   0,
            "evento": {
                "nombre": request.form.get("evento_nombre", ""),
                "fecha":  _contacto_fecha or _evento_fecha,
                "lugar":  _evento_fecha,
            },
            "award": {
                "headline":  _headline,
                "recipient": _recipient,
                "subtitle":  _subtitle,
                "fecha":     _contacto_fecha or _evento_fecha,
            },
            "contacto": {
                "nombre":    request.form.get("contacto_nombre", ""),
                "email":     request.form.get("contacto_email", ""),
                "telefono":  request.form.get("contacto_telefono", ""),
                "fecha":     _contacto_fecha,
                "cantidad":  request.form.get("contacto_cantidad", "1"),
            },
            "assets": {
                "logo_path":       None,
                "brand_book_path": None,
                "url_corporativa": request.form.get("url_corporativa", ""),
            },
        }

        # Guardar logo temporal en disco (solo si se subió)
        if logo_bytes:
            logo_tmp_path = PROJECT_ROOT / "assets" / "logos" / f"_test_{job_id}.{logo_ext}"
            logo_tmp_path.write_bytes(logo_bytes)
            pedido["assets"]["logo_path"] = str(logo_tmp_path.relative_to(PROJECT_ROOT))

        os.chdir(PROJECT_ROOT)

        # Capa 0: normalizar assets
        brand_context = capa0.normalizar_pedido(
            pedido, logo_bytes=logo_bytes, pdf_bytes=pdf_bytes
        )
        brand_context["logo_path"] = pedido["assets"]["logo_path"]
        if _font_upload_stem:
            brand_context["fuente_upload"] = _font_upload_stem

        # Cargar modelo del trofeo ANTES de Capa 1 para pasar sus constraints al diseño
        modelo  = capa3.cargar_modelo_trofeo(pedido["modelo_trofeo"])
        zona    = modelo["zona_imprimible"]
        w, h    = zona["ancho"], zona["alto"]
        pedido["_trophy"] = {
            "id":          modelo["id"],
            "nombre":      modelo["nombre"],
            "ancho":       zona["ancho"],
            "alto":        zona["alto"],
            "forma":       zona.get("forma", "rectangular"),
            "material":    modelo.get("material", ""),
            "constraints": modelo.get("diseno_constraints", {}),
        }

        # Capa 1: diseño IA (ya conoce el trofeo vía pedido["_trophy"])
        briefs, spec = capa1.diseñar_desde_contexto(pedido, brand_context)

        # Capas 2+3: render y compositing
        fuentes = capa2.cargar_fuentes()

        (PROJECT_ROOT / "outputs" / "mockups").mkdir(parents=True, exist_ok=True)
        mockups = []

        for concepto in briefs:
            pid    = concepto["proposal_id"]
            nombre = concepto.get("pattern_name", f"propuesta_{pid}")

            award_text = concepto.get("award_text", {})
            award = {
                "headline":  (award_text.get("headline") or pedido["award"]["headline"] or "Excellence Award"),
                "recipient": (award_text.get("recipient") or pedido["award"]["recipient"] or "Nombre del Premiado"),
                "subtitle":  (award_text.get("subtitle") or pedido["award"]["subtitle"] or ""),
                "fecha":     pedido["award"]["fecha"],
            }

            _dc = modelo.get("diseno_constraints", {})
            diseno = capa2.renderizar_diseno(
                concepto, w, h,
                logo_path=brand_context["logo_path"],
                award=award, fuentes=fuentes, seed=pid * 100,
                trophy_margin_h=_dc.get("margen_h_pct"),
                trophy_effective_width=_dc.get("effective_width_px"),
                trophy_zone_l=_dc.get("zone_l_px"),
                trophy_zone_r=_dc.get("zone_r_px"),
                trophy_zona=zona,
            )
            mockup_img = capa3.componer(diseno, modelo["imagen_base"], zona)

            out_path = (PROJECT_ROOT / "outputs" / "mockups" /
                        f"mockup_{job_id}_p{pid}.jpg")
            mockup_img.save(str(out_path), quality=95)

            img_b64 = base64.b64encode(out_path.read_bytes()).decode("utf-8")
            _prim = concepto.get("_primary", "") or concepto.get("color_overlay", {}).get("color", "#333")
            _sec  = concepto.get("_secondary", "")
            _acc  = concepto.get("_accent", "")
            _ext  = concepto.get("_colors_extended", [])
            _pal  = [c for c in [_prim, _sec, _acc] + list(_ext) if c and len(c) == 7 and c.startswith("#")]
            _pal  = list(dict.fromkeys(_pal))[:5]
            mockups.append({
                "proposal_id":      pid,
                "nombre":           nombre,
                "concepto":         concepto.get("design_rationale", ""),
                "color_primario":   _prim,
                "color_secundario": _sec,
                "palette":          _pal,
                "imagen_b64":       img_b64,
            })

        analisis = spec.get("brand_analysis", {})
        _cp = brand_context.get("canonical_palette") or []
        if not _cp:
            _cd = analisis.get("colors", {})
            _cp = [_cd.get("primary", ""), _cd.get("secondary", ""), _cd.get("accent", "")]
            _cp = [c for c in _cp if c and len(c) == 7 and c.startswith("#")]
        _modelo_nombre = modelo.get("nombre", pedido.get("modelo_trofeo", ""))
        return jsonify({
            "job_id": job_id,
            "modelo_nombre": _modelo_nombre,
            "award_headline": pedido["award"].get("headline", ""),
            "analisis_marca": {
                "descripcion_empresa": analisis.get("brand_name", "—"),
                "personalidad_marca":  analisis.get("brand_tone", "—"),
                "colores_principales": _cp,
                "estilo_recomendado":  analisis.get("visual_density", "—"),
            },
            "razonamiento": (spec.get("design_concepts") or [{}])[0].get("design_rationale", "—"),
            "mockups": mockups,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if logo_tmp_path:
            logo_tmp_path.unlink(missing_ok=True)


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    errores = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        errores.append("  Falta ANTHROPIC_API_KEY  → set ANTHROPIC_API_KEY=sk-ant-...")
    if not os.environ.get("OPENAI_API_KEY"):
        errores.append("  Falta OPENAI_API_KEY     → set OPENAI_API_KEY=sk-proj-...")
    if errores:
        print("\n  [ERROR] Faltan variables de entorno:")
        for e in errores:
            print(e)
        sys.exit(1)

    print("\n" + "="*52)
    print("  SUSTAIN AWARDS · Test Server")
    print("="*52)

    # ── Estado de APIs ────────────────────────────────────────────────
    from scripts.capa_dalle import CALIDAD_IMAGEN, USE_DALLE
    from scripts.config import MODEL_BRAND_ANALYSIS, MODEL_DESIGN_CONCEPTS, MODEL_COLOR_ORACLE

    _ok  = "✓"
    _nok = "✗"

    _ant = os.environ.get("ANTHROPIC_API_KEY", "")
    _oai = os.environ.get("OPENAI_API_KEY", "")
    _fc  = os.environ.get("FIRECRAWL_API_KEY", "")

    print(f"\n  APIs configuradas:")
    print(f"    Anthropic       : {_ok + ' ' + _ant[:8]+'...' if _ant else _nok + ' NO CONFIGURADA — los agentes Claude no funcionarán'}")
    print(f"    OpenAI / DALL·E : {_ok + ' ' + _oai[:8]+'...' if _oai else _nok + ' NO CONFIGURADA — se usará PIL como fallback'}")
    print(f"    Firecrawl       : {_ok + ' ' + _fc[:8]+'...'  if _fc  else '— no configurada (se usará Color Oracle como fallback)'}")

    print(f"\n  Modelos:")
    print(f"    Brand Analysis  : {MODEL_BRAND_ANALYSIS}")
    print(f"    Design Concepts : {MODEL_DESIGN_CONCEPTS}")
    print(f"    Color Oracle    : {MODEL_COLOR_ORACLE}")
    _dalle_info = f"gpt-image-1 ({CALIDAD_IMAGEN})" if USE_DALLE else "desactivado — usando PIL"
    print(f"    DALL·E          : {_dalle_info}")

    # ── Playwright ────────────────────────────────────────────────────
    from scripts.capa2_renderer import _get_browser as _pw_prewarm
    _pw_ok = _pw_prewarm()
    print(f"\n  Tipografía:")
    if _pw_ok:
        print(f"    Playwright      : ✓ Chromium v{_pw_ok.version} (Google Fonts reales)")
    else:
        print(f"    Playwright      : ✗ no disponible — usando fuentes del sistema (PIL)")

    print("\n" + "="*52)
    print("  Abre en el navegador: http://localhost:5001")
    print("  Ctrl+C para detener\n")
    app.run(debug=False, port=5001, threaded=False)
