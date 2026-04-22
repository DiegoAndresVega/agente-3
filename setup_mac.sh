#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_mac.sh — Sustain Awards · Instalación automática en macOS
# Uso: bash setup_mac.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "=================================================="
echo "  SUSTAIN AWARDS · Setup Mac"
echo "=================================================="

# ── 1. Python ────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "  [!] Python3 no encontrado."
  echo "      Instala Homebrew primero: https://brew.sh"
  echo "      Luego: brew install python@3.13"
  exit 1
fi
echo "  [OK] Python: $(python3 --version)"

# ── 2. Entorno virtual ───────────────────────────────
if [ ! -d "venv" ]; then
  echo "  [>] Creando entorno virtual..."
  python3 -m venv venv
fi
source venv/bin/activate
echo "  [OK] venv activo: $(python --version)"

# ── 3. Dependencias ──────────────────────────────────
echo "  [>] Instalando dependencias..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  [OK] Dependencias instaladas"

# ── 4. Playwright + Chromium ─────────────────────────
echo "  [>] Instalando Chromium (Playwright)..."
python -m playwright install chromium
echo "  [OK] Chromium listo"

# ── 5. Memoria de Claude Code ────────────────────────
if [ -d "_claude_memory" ]; then
  # Detectar la ruta hashed del proyecto en ~/.claude/projects/
  PROJECT_HASH=$(python3 -c "
import re, os
path = os.path.abspath('.')
# Claude Code codifica la ruta reemplazando / y : con -
encoded = re.sub(r'[/:. ]', '-', path).strip('-')
# También reemplaza ~ con el home si aplica
encoded = encoded.replace(os.path.expanduser('~').replace('/', '-').strip('-'), 'Users-' + os.environ.get('USER', 'user'))
print(encoded)
" 2>/dev/null || echo "")

  CLAUDE_MEM_DIR="$HOME/.claude/projects/$PROJECT_HASH/memory"
  mkdir -p "$CLAUDE_MEM_DIR"
  cp _claude_memory/*.md "$CLAUDE_MEM_DIR/"
  echo "  [OK] Memoria Claude Code instalada → $CLAUDE_MEM_DIR"
else
  echo "  [!] Carpeta _claude_memory no encontrada — saltando migración de memoria"
fi

# ── 6. Directorios necesarios ─────────────────────────
mkdir -p outputs/mockups outputs/design_specs assets/logos assets/fonts assets/brand_books assets/aprendizaje

# ── 7. Verificar claves API ───────────────────────────
echo ""
if [ -f "lakla.txt" ]; then
  echo "  [OK] lakla.txt encontrado — claves API disponibles"
else
  echo "  [!] lakla.txt NO encontrado."
  echo "      Crea el fichero con tus claves API:"
  echo "      sk-proj-...  → OpenAI"
  echo "      sk-ant-...   → Anthropic"
fi

echo ""
echo "=================================================="
echo "  Setup completo. Para arrancar el servidor:"
echo ""
echo "    source venv/bin/activate"
echo "    python test_server.py"
echo ""
echo "  Luego abre: http://localhost:5000"
echo "=================================================="
