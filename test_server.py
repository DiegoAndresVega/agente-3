"""
TEST SERVER — Agente 3 · Sustain Awards Custom
Genera visualizaciones completas de trofeos con forma dinámica por material.

Uso:
    python test_server.py
    Luego abre: http://localhost:5002
"""

import os
import sys
import uuid

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import base64
import shutil
from pathlib import Path
from io import BytesIO

from flask import Flask, request, jsonify, send_from_directory


def _cargar_claves(ruta: str = "lakla.txt") -> None:
    fichero = Path(__file__).parent / ruta
    if not fichero.exists():
        print(f"  [claves] Fichero '{ruta}' no encontrado — usando variables de entorno")
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


_cargar_claves()

sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from scripts import capa0_normalizer as capa0
from scripts import capa1_ia         as capa1
from scripts import capa3_compositor as capa3
from scripts import capa_imagen      as capa_img

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

PROJECT_ROOT   = Path(__file__).resolve().parent
FRONTEND_DIR   = PROJECT_ROOT / "frontend"
MATERIAL_ID_DEFAULT = "hormigon_acero"


# ─── Rutas Flask ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


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
    return jsonify({"error": "Archivo demasiado grande. Máximo: 100 MB."}), 413


@app.route("/feedback", methods=["POST"])
def feedback():
    """Guarda un diseño validado como ejemplo de aprendizaje."""
    import json as _json
    data        = request.get_json()
    job_id      = data.get("job_id")
    proposal_id = data.get("proposal_id")

    if not job_id or proposal_id is None:
        return jsonify({"error": "Datos incompletos"}), 400

    try:
        spec_path = PROJECT_ROOT / "outputs" / "design_specs" / f"{job_id}_design_spec.json"
        if not spec_path.exists():
            return jsonify({"error": "Spec no encontrado"}), 404

        with open(spec_path, encoding="utf-8") as f:
            spec = _json.load(f)

        briefs = spec.get("design_concepts", [])
        brief  = next((b for b in briefs if b.get("proposal_id") == proposal_id), None)
        if not brief:
            return jsonify({"error": "Propuesta no encontrada"}), 404

        aprendizaje_dir = PROJECT_ROOT / "assets" / "aprendizaje"
        aprendizaje_dir.mkdir(parents=True, exist_ok=True)

        nombre_base = f"{job_id}_p{proposal_id}"
        json_dst = aprendizaje_dir / f"{nombre_base}.json"
        img_dst  = aprendizaje_dir / f"{nombre_base}.jpg"

        with open(json_dst, "w", encoding="utf-8") as f:
            _json.dump(brief, f, ensure_ascii=False, indent=2)

        img_src = PROJECT_ROOT / "outputs" / "mockups" / f"mockup_{job_id}_p{proposal_id}.jpg"
        if img_src.exists():
            shutil.copy2(img_src, img_dst)

        total = len(list(aprendizaje_dir.glob("*.json")))
        return jsonify({"ok": True, "total_ejemplos": total})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/generar", methods=["POST"])
def generar():
    logo_tmp_path = None
    try:
        # ── Inputs ────────────────────────────────────────────────────────────
        logo_file   = request.files.get("logo")
        _tiene_logo = logo_file and logo_file.filename != ""
        logo_bytes  = logo_file.read() if _tiene_logo else None
        logo_ext    = Path(logo_file.filename).suffix.lstrip(".") if _tiene_logo else "png"

        url_input      = request.form.get("url_corporativa", "").strip()
        pdf_file_check = request.files.get("brandbook")
        _tiene_pdf     = pdf_file_check and pdf_file_check.filename != ""

        if not _tiene_logo and not url_input and not _tiene_pdf:
            return jsonify({"error": "Proporciona al menos el logo, la URL corporativa o el brandbook"}), 400

        pdf_file  = request.files.get("brandbook")
        pdf_bytes = pdf_file.read() if pdf_file and pdf_file.filename else None

        # Fuente corporativa opcional
        font_file = request.files.get("font")
        if font_file and font_file.filename:
            font_ext = Path(font_file.filename).suffix.lstrip(".").lower()
            if font_ext in ("ttf", "otf"):
                from scripts.font_manager import register_local_font
                font_data = font_file.read()
                font_stem = Path(font_file.filename).stem
                register_local_font(font_stem, font_data, font_ext)

        # Material seleccionado (por ahora solo hormigon_acero)
        material_id = request.form.get("material_id", MATERIAL_ID_DEFAULT)
        material_config = capa3.cargar_modelo_material(material_id)

        # ── Construir pedido ───────────────────────────────────────────────────
        job_id = f"FORM-{uuid.uuid4().hex[:8].upper()}"

        _headline  = request.form.get("headline", "").strip()
        _recipient = request.form.get("recipient", "").strip()
        _subtitle  = request.form.get("subtitle", "").strip()
        _fecha     = (request.form.get("contacto_fecha", "").strip()
                      or request.form.get("evento_fecha", "").strip())

        pedido = {
            "id_pedido":  job_id,
            "id_cliente": "",
            "material_id": material_id,
            "cantidad":   request.form.get("contacto_cantidad", "1"),
            "evento": {
                "nombre": request.form.get("evento_nombre", ""),
                "fecha":  _fecha,
            },
            "award": {
                "headline":  _headline,
                "recipient": _recipient,
                "subtitle":  _subtitle,
                "fecha":     _fecha,
            },
            "contacto": {
                "nombre":   request.form.get("contacto_nombre", ""),
                "email":    request.form.get("contacto_email", ""),
                "telefono": request.form.get("contacto_telefono", ""),
                "fecha":    _fecha,
                "cantidad": request.form.get("contacto_cantidad", "1"),
            },
            "assets": {
                "logo_path":       None,
                "brand_book_path": None,
                "url_corporativa": url_input,
            },
        }

        # Logo temporal
        if logo_bytes:
            logo_tmp_path = PROJECT_ROOT / "assets" / "logos" / f"_test_{job_id}.{logo_ext}"
            logo_tmp_path.write_bytes(logo_bytes)
            pedido["assets"]["logo_path"] = str(logo_tmp_path.relative_to(PROJECT_ROOT))

        os.chdir(PROJECT_ROOT)

        # ── Pipeline ──────────────────────────────────────────────────────────
        # Capa 0: extracción de marca
        brand_context = capa0.normalizar_pedido(
            pedido, logo_bytes=logo_bytes, pdf_bytes=pdf_bytes
        )
        brand_context["logo_path"] = pedido["assets"]["logo_path"]

        # Capa 1: diseño IA — formas escultóricas
        briefs, spec = capa1.diseñar_desde_contexto_material(
            pedido, brand_context, material_config
        )

        # Capas imagen + compositing
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

            # Capa imagen: genera el trofeo completo
            trofeo_img = capa_img.generar_trofeo(
                concepto=concepto,
                material_config=material_config,
                brand_context=brand_context,
                award=award,
            )

            # Capa 3: normaliza y exporta
            mockup_img = capa3.componer(trofeo_img, material_config)

            out_path = PROJECT_ROOT / "outputs" / "mockups" / f"mockup_{job_id}_p{pid}.jpg"
            mockup_img.save(str(out_path), quality=95)

            img_b64 = base64.b64encode(out_path.read_bytes()).decode("utf-8")

            _prim = concepto.get("_primary", "")
            _sec  = concepto.get("_secondary", "")
            _ext  = concepto.get("_colors_extended", [])
            _pal  = [c for c in [_prim, _sec] + list(_ext) if c and len(c) == 7 and c.startswith("#")]
            _pal  = list(dict.fromkeys(_pal))[:5]

            mockups.append({
                "proposal_id":      pid,
                "nombre":           nombre,
                "concepto":         concepto.get("design_rationale", ""),
                "forma_escultorica": concepto.get("forma_escultorica", ""),
                "color_treatment":  concepto.get("color_treatment", ""),
                "text_treatment":   concepto.get("text_treatment", ""),
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

        return jsonify({
            "job_id":         job_id,
            "material_nombre": material_config.get("nombre", ""),
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
    from scripts.config import (
        MODEL_BRAND_ANALYSIS, MODEL_DESIGN_CONCEPTS,
        IMAGE_QUALITY, USE_DALLE, IMAGE_PROVIDER,
    )

    errores = []
    if not os.environ.get("ANTHROPIC_API_KEY"):
        errores.append("  Falta ANTHROPIC_API_KEY")
    if not os.environ.get("OPENAI_API_KEY") and USE_DALLE:
        errores.append("  Falta OPENAI_API_KEY (USE_DALLE=true)")
    if errores:
        print("\n  [ERROR] Faltan variables de entorno:")
        for e in errores:
            print(e)
        sys.exit(1)

    print("\n" + "="*52)
    print("  AGENTE 3 · Sustain Awards Custom")
    print("  Generador de trofeos con forma dinámica")
    print("="*52)

    _ant = os.environ.get("ANTHROPIC_API_KEY", "")
    _oai = os.environ.get("OPENAI_API_KEY", "")
    _fc  = os.environ.get("FIRECRAWL_API_KEY", "")
    _ok  = "✓"
    _nok = "✗"

    print(f"\n  APIs configuradas:")
    print(f"    Anthropic       : {_ok + ' ' + _ant[:8]+'...' if _ant else _nok + ' NO CONFIGURADA'}")
    print(f"    OpenAI / Imagen : {_ok + ' ' + _oai[:8]+'...' if _oai else _nok + ' NO CONFIGURADA — se usará PIL'}")
    print(f"    Firecrawl       : {_ok + ' ' + _fc[:8]+'...'  if _fc  else '— no configurada'}")

    print(f"\n  Modelos:")
    print(f"    Brand Analysis  : {MODEL_BRAND_ANALYSIS}")
    print(f"    Design Concepts : {MODEL_DESIGN_CONCEPTS}")
    _img_info = f"gpt-image-1 ({IMAGE_QUALITY})" if USE_DALLE else "desactivado — usando PIL"
    print(f"    Generación img  : {_img_info}")

    print(f"\n  Material por defecto: {MATERIAL_ID_DEFAULT}")

    print("\n" + "="*52)
    print("  Abre en el navegador: http://localhost:5002")
    print("  Ctrl+C para detener\n")

    app.run(debug=False, port=5002, threaded=False)
