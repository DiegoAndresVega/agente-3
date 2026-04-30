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

from flask import Flask, request, render_template_string, jsonify

# Asegurar que scripts/ sea importable
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

from scripts import capa0_normalizer as capa0
from scripts import capa1_ia         as capa1
from scripts import capa2_renderer   as capa2
from scripts import capa3_compositor as capa3

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB máximo

PROJECT_ROOT = Path(__file__).resolve().parent

# ─── HTML ─────────────────────────────────────────────────────────────────────

HTML_FORM = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sustain Awards · Test de diseño IA</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f5f0;
      color: #1a1a1a;
      min-height: 100vh;
    }
    header {
      background: #1a1a1a;
      color: #fff;
      padding: 20px 40px;
      display: flex;
      align-items: center;
      gap: 16px;
    }
    header h1 { font-size: 1.2rem; font-weight: 600; letter-spacing: 0.05em; }
    header span { font-size: 0.8rem; color: #888; background: #333;
                  padding: 3px 10px; border-radius: 20px; }
    .container { max-width: 760px; margin: 40px auto; padding: 0 20px 60px; }
    .card {
      background: #fff;
      border-radius: 12px;
      padding: 36px;
      margin-bottom: 24px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    h2 { font-size: 1rem; font-weight: 600; color: #555;
         text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 24px;
         padding-bottom: 12px; border-bottom: 1px solid #eee; }
    .field { margin-bottom: 20px; }
    label { display: block; font-size: 0.85rem; font-weight: 500;
            color: #444; margin-bottom: 6px; }
    label .hint { font-weight: 400; color: #999; font-size: 0.8rem; }
    input[type="text"], select {
      width: 100%; padding: 10px 14px; border: 1.5px solid #e0e0e0;
      border-radius: 8px; font-size: 0.95rem; background: #fafafa;
      transition: border-color .2s;
    }
    input[type="text"]:focus, select:focus {
      outline: none; border-color: #1a1a1a; background: #fff;
    }
    .upload-area {
      border: 2px dashed #ddd; border-radius: 8px; padding: 20px;
      text-align: center; cursor: pointer; transition: all .2s;
      background: #fafafa;
    }
    .upload-area:hover { border-color: #1a1a1a; background: #f0f0f0; }
    .upload-area input { display: none; }
    .upload-area .icon { font-size: 2rem; margin-bottom: 8px; }
    .upload-area p { font-size: 0.9rem; color: #666; }
    .upload-area p strong { color: #1a1a1a; }
    .upload-area .filename { font-size: 0.85rem; color: #2a7a2a;
                             margin-top: 8px; font-weight: 500; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .btn {
      width: 100%; padding: 14px; background: #1a1a1a; color: #fff;
      border: none; border-radius: 8px; font-size: 1rem; font-weight: 600;
      cursor: pointer; transition: background .2s; letter-spacing: 0.02em;
    }
    .btn:hover { background: #333; }
    .btn:disabled { background: #999; cursor: not-allowed; }
    .loading {
      display: none; text-align: center; padding: 40px;
    }
    .spinner {
      width: 40px; height: 40px; border: 3px solid #eee;
      border-top-color: #1a1a1a; border-radius: 50%;
      animation: spin 0.8s linear infinite; margin: 0 auto 16px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .loading p { color: #666; font-size: 0.95rem; }
    .loading .sub { font-size: 0.8rem; color: #999; margin-top: 6px; }
    .error-msg {
      background: #fff3f3; border: 1px solid #fcc; border-radius: 8px;
      padding: 16px 20px; color: #c00; font-size: 0.9rem; display: none;
    }
    /* Resultados — ocupa todo el ancho de la ventana */
    .results {
      display: none;
      position: relative;
      left: 50%;
      transform: translateX(-50%);
      width: 98vw;
      max-width: 98vw;
      box-sizing: border-box;
      padding: 32px 2vw 40px;
    }
    .results h2 { color: #1a1a1a; }
    .analisis {
      background: #f8f8f8; border-radius: 8px; padding: 16px 20px;
      margin-bottom: 20px; font-size: 0.88rem; line-height: 1.7;
      max-width: 760px;
    }
    .analisis strong { color: #1a1a1a; }
    .mockups-grid {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 10px;
      margin-top: 16px;
    }
    .mockup-card {
      background: #fff; border-radius: 10px; overflow: hidden;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .mockup-card img { width: 100%; display: block; max-height: 52vh; object-fit: contain; background: #f0f0f0; }
    .mockup-info { padding: 8px 10px; }
    .mockup-info h3 { font-size: 0.78rem; font-weight: 600; margin-bottom: 2px; }
    .mockup-info p { font-size: 0.68rem; color: #666; line-height: 1.3; }
    .colores { display: flex; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
    .color-swatch {
      display: flex; flex-direction: column; align-items: center; gap: 3px;
    }
    .color-swatch .dot {
      width: 24px; height: 24px; border-radius: 50%;
      border: 1.5px solid rgba(0,0,0,0.12);
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .color-swatch .hex {
      font-size: 0.60rem; color: #777; font-family: monospace; letter-spacing: -0.02em;
    }
    .palette-analisis { display: flex; gap: 10px; margin-top: 6px; flex-wrap: wrap; }
    .palette-analisis .color-swatch .dot { width: 28px; height: 28px; }
    .palette-analisis .color-swatch .hex { font-size: 0.65rem; }
    .btn-ampliar {
      display: flex; align-items: center; justify-content: center; gap: 5px;
      width: 100%; padding: 7px 12px; margin-top: 8px;
      background: #f5f5f0; border: 1.5px solid #ddd; border-radius: 6px;
      font-size: 0.80rem; font-weight: 500; color: #444; cursor: pointer;
      transition: all .18s;
    }
    .btn-ampliar:hover { background: #333; color: #fff; border-color: #333; }
    /* Modal lightbox */
    .img-modal {
      display: none; position: fixed; inset: 0; z-index: 9999;
      background: rgba(0,0,0,0.88); backdrop-filter: blur(4px);
      align-items: center; justify-content: center;
    }
    .img-modal.open { display: flex; }
    .img-modal img {
      max-width: 90vw; max-height: 90vh; border-radius: 8px;
      box-shadow: 0 8px 40px rgba(0,0,0,0.6); object-fit: contain;
    }
    .img-modal-close {
      position: fixed; top: 20px; right: 24px; font-size: 2rem;
      color: #fff; cursor: pointer; line-height: 1; opacity: 0.8;
      background: none; border: none; z-index: 10000;
    }
    .img-modal-close:hover { opacity: 1; }
    .razonamiento {
      background: #fffdf0; border-left: 3px solid #f0c040;
      padding: 14px 18px; border-radius: 0 8px 8px 0;
      font-size: 0.88rem; color: #555; line-height: 1.6; margin-top: 20px;
    }
    .btn-reset {
      margin-top: 24px; background: transparent; border: 1.5px solid #1a1a1a;
      color: #1a1a1a;
    }
    .btn-reset:hover { background: #1a1a1a; color: #fff; }
    .btn-row { display: flex; gap: 12px; margin-top: 24px; }
    .btn-row .btn { margin-top: 0; }
    .btn-rehacer {
      flex: 1; padding: 14px; background: #fff;
      border: 1.5px solid #1a1a1a; border-radius: 8px;
      font-size: 1rem; font-weight: 600; color: #1a1a1a;
      cursor: pointer; transition: background .2s;
    }
    .btn-rehacer:hover { background: #f0f0f0; }
    .btn-rehacer:disabled { color: #999; border-color: #ddd; cursor: not-allowed; }
    .btn-download {
      display: flex; align-items: center; justify-content: center; gap: 6px;
      width: 100%; padding: 9px 12px; margin-top: 10px;
      background: #f5f5f0; border: 1.5px solid #ddd; border-radius: 6px;
      font-size: 0.82rem; font-weight: 500; color: #333; cursor: pointer;
      transition: all .18s; text-decoration: none;
    }
    .btn-download:hover { background: #1a1a1a; color: #fff; border-color: #1a1a1a; }
    .btn-megusta {
      display: flex; align-items: center; justify-content: center; gap: 6px;
      width: 100%; padding: 9px 12px; margin-top: 8px;
      background: #fff; border: 1.5px solid #c8e6c9; border-radius: 6px;
      font-size: 0.82rem; font-weight: 500; color: #2e7d32; cursor: pointer;
      transition: all .18s;
    }
    .btn-megusta:hover:not(:disabled) { background: #e8f5e9; border-color: #2e7d32; }
    .btn-megusta:disabled {
      background: #e8f5e9; border-color: #a5d6a7; color: #388e3c; cursor: default;
    }
    .btn-download-all {
      display: flex; align-items: center; justify-content: center; gap: 8px;
      width: 100%; padding: 11px; margin-top: 16px;
      background: #fff; border: 1.5px solid #1a1a1a; border-radius: 8px;
      font-size: 0.9rem; font-weight: 600; color: #1a1a1a; cursor: pointer;
      transition: all .18s; text-decoration: none;
    }
    .btn-download-all:hover { background: #1a1a1a; color: #fff; }
  </style>
</head>
<body>

<header>
  <h1>SUSTAIN AWARDS</h1>
  <span>Test · Diseño con IA</span>
</header>

<div class="container">

  <!-- FORMULARIO -->
  <form id="form" enctype="multipart/form-data">

    <div class="card">
      <h2>Assets del cliente</h2>

      <div class="field">
        <label>Logo <span class="hint">(PNG o JPG · recomendado)</span></label>
        <div class="upload-area" onclick="document.getElementById('logo_file').click()">
          <input type="file" id="logo_file" name="logo" accept=".png,.jpg,.jpeg">
          <div class="icon">🖼️</div>
          <p><strong>Haz clic para subir</strong> o arrastra aquí</p>
          <p>PNG o JPG</p>
          <div class="filename" id="logo_name"></div>
        </div>
      </div>

      <div class="field">
        <label>Brandbook / Manual de identidad <span class="hint">(PDF · opcional)</span></label>
        <div class="upload-area" onclick="document.getElementById('pdf_file').click()">
          <input type="file" id="pdf_file" name="brandbook" accept=".pdf">
          <div class="icon">📄</div>
          <p><strong>Haz clic para subir</strong> o arrastra aquí</p>
          <p>PDF</p>
          <div class="filename" id="pdf_name"></div>
        </div>
      </div>

      <div class="field">
        <label>Fuente corporativa <span class="hint">(.ttf o .otf · opcional — máxima fidelidad tipográfica)</span></label>
        <div class="upload-area" onclick="document.getElementById('font_file').click()">
          <input type="file" id="font_file" name="font" accept=".ttf,.otf">
          <div class="icon">Aa</div>
          <p><strong>Haz clic para subir</strong> o arrastra aquí</p>
          <p>TTF u OTF — fuente exacta del brandbook</p>
          <div class="filename" id="font_name"></div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Contexto <span class="hint" style="font-size:0.8rem;font-weight:400;text-transform:none">(todo opcional — la IA lo infiere del logo)</span></h2>

      <div class="row">
        <div class="field">
          <label>Nombre de empresa / cliente <span class="hint">(opcional)</span></label>
          <input type="text" name="empresa" placeholder="La IA lo detecta del logo">
        </div>
        <div class="field">
          <label>URL web corporativa <span class="hint">(mejora el análisis)</span></label>
          <input type="text" name="url_corporativa" placeholder="https://www.empresa.com">
        </div>
      </div>

      <div class="row">
        <div class="field">
          <label>Nombre del evento <span class="hint">(opcional)</span></label>
          <input type="text" name="evento_nombre" placeholder="Ej: Innovation Awards 2026">
        </div>
        <div class="field">
          <label>Lugar · Fecha <span class="hint">(opcional)</span></label>
          <input type="text" name="evento_fecha" placeholder="Ej: Madrid · Junio 2026">
        </div>
      </div>
    </div>

    <div class="card">
      <h2>Galardón <span class="hint" style="font-size:0.8rem;font-weight:400;text-transform:none">(la IA genera los textos si los dejas vacíos)</span></h2>

      <div class="field">
        <label>Título del premio <span class="hint">(opcional — headline principal)</span></label>
        <input type="text" name="headline"
               placeholder="La IA lo genera según la marca y el evento">
      </div>

      <div class="row">
        <div class="field">
          <label>Destinatario <span class="hint">(opcional)</span></label>
          <input type="text" name="recipient" placeholder="Nombre del Premiado">
        </div>
        <div class="field">
          <label>Año <span class="hint">(opcional)</span></label>
          <input type="text" name="año" placeholder="2026">
        </div>
      </div>

      <div class="field">
        <label>Subtítulo / mérito <span class="hint">(opcional)</span></label>
        <input type="text" name="subtitle"
               placeholder="La IA lo genera si lo dejas vacío">
      </div>

      <div class="field">
        <label>Modelo de trofeo</label>
        <select name="modelo_trofeo">
          <option value="totem_basic">Totem Basic (madera)</option>
          <option value="placa_a5">Placa A5 (aluminio)</option>
          <option value="copetin">Copetin (metal)</option>
        </select>
      </div>
    </div>

    <div class="error-msg" id="error_msg"></div>

    <button type="submit" class="btn" id="btn_submit">
      Generar diseño con IA →
    </button>

  </form>

  <!-- LOADING -->
  <div class="loading" id="loading">
    <div class="spinner"></div>
    <p>El agente está generando tu diseño...</p>
    <p class="sub">Analizando identidad de marca y creando las propuestas</p>
  </div>

  <!-- RESULTADOS -->
  <div class="results card" id="results">
    <h2>Propuestas generadas por IA</h2>

    <div class="analisis" id="analisis_texto"></div>

    <div class="mockups-grid" id="mockups_grid"></div>

    <a class="btn-download-all" id="btn_download_all" href="#" onclick="descargarTodas(event)">
      ⬇ Descargar todas las propuestas
    </a>

    <div class="razonamiento" id="razonamiento_texto"></div>

    <div class="btn-row">
      <button class="btn-rehacer" id="btn_rehacer" onclick="rehacer()">
        ↺ Rehacer (mismos datos)
      </button>
      <button class="btn btn-reset" style="flex:1" onclick="resetForm()">
        ← Nuevo diseño
      </button>
    </div>
  </div>

</div>

<script>
  // Preview nombre de archivo en upload areas
  document.getElementById('logo_file').addEventListener('change', function() {
    document.getElementById('logo_name').textContent = this.files[0]?.name || '';
  });
  document.getElementById('pdf_file').addEventListener('change', function() {
    document.getElementById('pdf_name').textContent = this.files[0]?.name || '';
  });
  document.getElementById('font_file').addEventListener('change', function() {
    document.getElementById('font_name').textContent = this.files[0]?.name || '';
  });

  // Drag & drop en upload areas
  document.querySelectorAll('.upload-area').forEach(area => {
    area.addEventListener('dragover', e => {
      e.preventDefault(); area.style.borderColor = '#1a1a1a';
    });
    area.addEventListener('dragleave', () => area.style.borderColor = '');
    area.addEventListener('drop', e => {
      e.preventDefault(); area.style.borderColor = '';
      const input = area.querySelector('input[type=file]');
      if (e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        input.dispatchEvent(new Event('change'));
      }
    });
  });

  // Submit del formulario
  document.getElementById('form').addEventListener('submit', async function(e) {
    e.preventDefault();

    const btn = document.getElementById('btn_submit');
    const loading = document.getElementById('loading');
    const errorMsg = document.getElementById('error_msg');
    const results = document.getElementById('results');

    errorMsg.style.display = 'none';
    results.style.display = 'none';
    btn.disabled = true;
    btn.textContent = 'Generando...';
    loading.style.display = 'block';
    document.getElementById('form').style.display = 'none';

    try {
      const formData = new FormData(this);
      _lastFormData = formData;
      const resp = await fetch('/generar', { method: 'POST', body: formData });
      const data = await resp.json();

      if (!resp.ok || data.error) {
        throw new Error(data.error || 'Error desconocido');
      }

      mostrarResultados(data);
    } catch (err) {
      document.getElementById('form').style.display = 'block';
      errorMsg.textContent = '⚠️ ' + err.message;
      errorMsg.style.display = 'block';
      btn.disabled = false;
      btn.textContent = 'Generar diseño con IA →';
    } finally {
      loading.style.display = 'none';
    }
  });

  // Almacena los mockups, job_id y FormData para rehacer y feedback
  let _mockupsData = [];
  let _jobId = null;
  let _lastFormData = null;

  function _swatches(colors) {
    return (colors || []).filter(c => c && c.startsWith('#')).map(c =>
      `<div class="color-swatch">
         <div class="dot" style="background:${c}" title="${c}"></div>
         <span class="hex">${c.toUpperCase()}</span>
       </div>`
    ).join('');
  }

  function mostrarResultados(data) {
    _mockupsData = data.mockups;
    _jobId = data.job_id;

    const analisis = data.analisis_marca;
    const swatchesAnalisis = _swatches(analisis.colores_principales);
    document.getElementById('analisis_texto').innerHTML =
      `<strong>Empresa:</strong> ${analisis.descripcion_empresa}<br>
       <strong>Personalidad de marca:</strong> ${analisis.personalidad_marca}<br>
       <strong>Estilo recomendado:</strong> ${analisis.estilo_recomendado}<br>
       <strong>Colores de marca:</strong>
       <div class="palette-analisis">${swatchesAnalisis}</div>`;

    const grid = document.getElementById('mockups_grid');
    grid.innerHTML = '';
    window._imgSrcs = [];
    data.mockups.forEach((m, i) => {
      const imgSrc = `data:image/jpeg;base64,${m.imagen_b64}`;
      window._imgSrcs.push(imgSrc);
      const nombreArchivo = m.nombre.replace(/[^a-zA-Z0-9_-]/g, '_') + '.jpg';
      const btnId = `btn_mg_${i}`;
      const swatches = _swatches(m.palette && m.palette.length ? m.palette : [m.color_primario, m.color_secundario]);
      grid.innerHTML += `
        <div class="mockup-card">
          <img src="${imgSrc}" alt="${m.nombre}" style="cursor:zoom-in"
               onclick="abrirImagen(${i})">
          <div class="mockup-info">
            <h3>${m.nombre}</h3>
            <p>${m.concepto}</p>
            <div class="colores">${swatches}</div>
            <button class="btn-ampliar" onclick="abrirImagen(${i})">
              &#128269; Ampliar imagen
            </button>
            <button class="btn-megusta" id="${btnId}"
                    onclick="meGusta(this, '${data.job_id}', ${m.proposal_id})">
              👍 Este diseño me gusta
            </button>
            <a class="btn-download" href="${imgSrc}"
               download="${nombreArchivo}">
              ⬇ Descargar propuesta ${i + 1}
            </a>
          </div>
        </div>`;
    });

    document.getElementById('razonamiento_texto').innerHTML =
      '<strong>Razonamiento IA:</strong> ' + data.razonamiento;

    document.getElementById('results').style.display = 'block';
  }

  async function meGusta(btn, jobId, proposalId) {
    btn.disabled = true;
    btn.textContent = '⏳ Guardando...';
    try {
      const resp = await fetch('/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId, proposal_id: proposalId })
      });
      const data = await resp.json();
      if (data.ok) {
        btn.textContent = '✅ Guardado como referencia';
      } else {
        btn.textContent = '⚠️ Error al guardar';
        btn.disabled = false;
      }
    } catch {
      btn.textContent = '⚠️ Error de conexión';
      btn.disabled = false;
    }
  }

  function descargarTodas(e) {
    e.preventDefault();
    _mockupsData.forEach((m, i) => {
      const a = document.createElement('a');
      a.href = 'data:image/jpeg;base64,' + m.imagen_b64;
      a.download = m.nombre.replace(/[^a-zA-Z0-9_-]/g, '_') + '.jpg';
      document.body.appendChild(a);
      // Pequeño delay entre descargas para que el navegador las procese
      setTimeout(() => { a.click(); document.body.removeChild(a); }, i * 300);
    });
  }

  async function rehacer() {
    if (!_lastFormData) return;
    const btn = document.getElementById('btn_rehacer');
    const loading = document.getElementById('loading');
    const results = document.getElementById('results');

    btn.disabled = true;
    btn.textContent = 'Generando...';
    results.style.display = 'none';
    loading.style.display = 'block';

    try {
      const resp = await fetch('/generar', { method: 'POST', body: _lastFormData });
      const data = await resp.json();
      if (!resp.ok || data.error) throw new Error(data.error || 'Error desconocido');
      mostrarResultados(data);
    } catch (err) {
      results.style.display = 'block';
      alert('Error al rehacer: ' + err.message);
    } finally {
      loading.style.display = 'none';
      btn.disabled = false;
      btn.textContent = '↺ Rehacer (mismos datos)';
    }
  }

  function resetForm() {
    document.getElementById('results').style.display = 'none';
    document.getElementById('form').reset();
    document.getElementById('logo_name').textContent = '';
    document.getElementById('pdf_name').textContent = '';
    document.getElementById('font_name').textContent = '';
    document.getElementById('form').style.display = 'block';
    document.getElementById('btn_submit').disabled = false;
    document.getElementById('btn_submit').textContent = 'Generar diseño con IA →';
  }
</script>

<!-- Modal lightbox — debe estar ANTES del script de inicialización -->
<div class="img-modal" id="img-modal">
  <button class="img-modal-close" id="img-modal-close">&#x2715;</button>
  <img id="img-modal-img" src="" alt="Diseño ampliado">
</div>

<script>
  // Array global de src — onclick usa índice en lugar de incrustar base64 en atributos
  window._imgSrcs = [];

  window.abrirImagen = function(idx) {
    const src = window._imgSrcs[idx];
    if (!src) return;
    document.getElementById('img-modal-img').src = src;
    document.getElementById('img-modal').classList.add('open');
  };

  (function() {
    const modal = document.getElementById('img-modal');
    document.getElementById('img-modal-close').onclick = () => modal.classList.remove('open');
    modal.addEventListener('click', e => { if (e.target === modal) modal.classList.remove('open'); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') modal.classList.remove('open'); });
  })();
</body>
</html>
"""

# ─── Rutas Flask ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML_FORM)


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
        pedido = {
            "id_pedido":     job_id,
            "id_cliente":    request.form.get("empresa", ""),
            "modelo_trofeo": request.form.get("modelo_trofeo", "totem_basic"),
            "cantidad": 1,
            "presupuesto": 0,
            "evento": {
                "nombre": request.form.get("evento_nombre", ""),
                "fecha":  request.form.get("año", ""),
                "lugar":  request.form.get("evento_fecha", ""),
            },
            "award": {
                "headline":  request.form.get("headline", ""),
                "recipient": request.form.get("recipient", ""),
                "subtitle":  request.form.get("subtitle", ""),
                "fecha":     request.form.get("año", ""),
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
        return jsonify({
            "job_id": job_id,
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
