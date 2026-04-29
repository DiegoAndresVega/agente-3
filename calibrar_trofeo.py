"""
Herramienta de calibración de zona imprimible para trofeos.

Uso:
    python calibrar_trofeo.py

- Haz clic izquierdo para ir añadiendo puntos alrededor del área imprimible.
- Sigue el contorno en orden (sentido horario o antihorario, sin saltar).
- Pulsa ENTER o cierra la ventana cuando el polígono esté completo.
- Se generará automáticamente:
    assets/trophies/copetin_mask.png   ← máscara blanco/negro
    data/copetin_calibracion.json      ← datos para el catálogo
"""

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from PIL import Image, ImageDraw, ImageTk

PROJECT_ROOT = Path(__file__).resolve().parent
TROPHY_ID    = "copetin"
IMG_PATH     = PROJECT_ROOT / "assets" / "trophies" / f"{TROPHY_ID}.png"
MASK_PATH    = PROJECT_ROOT / "assets" / "trophies" / f"{TROPHY_ID}_mask.png"
JSON_PATH    = PROJECT_ROOT / "data" / f"{TROPHY_ID}_calibracion.json"

# ── Escalar la imagen si es más grande que la pantalla ──────────────────────
MAX_W, MAX_H = 900, 800

img_orig = Image.open(IMG_PATH).convert("RGBA")
orig_w, orig_h = img_orig.size
scale = min(MAX_W / orig_w, MAX_H / orig_h, 1.0)
disp_w = int(orig_w * scale)
disp_h = int(orig_h * scale)
img_display = img_orig.resize((disp_w, disp_h), Image.LANCZOS)

points_display = []   # coordenadas en la imagen mostrada
dot_ids        = []   # IDs de los círculos en el canvas
line_ids       = []   # IDs de las líneas en el canvas

# ── Tkinter ──────────────────────────────────────────────────────────────────
root = tk.Tk()
root.title(f"Calibrar zona imprimible — {TROPHY_ID}.png  (escala {scale:.2f}x)")
root.resizable(False, False)

tk_img  = ImageTk.PhotoImage(img_display)
canvas  = tk.Canvas(root, width=disp_w, height=disp_h, cursor="crosshair")
canvas.pack()
canvas.create_image(0, 0, anchor="nw", image=tk_img)

info_var = tk.StringVar(value="Haz clic para añadir puntos alrededor del área imprimible. ENTER para terminar.")
tk.Label(root, textvariable=info_var, bg="#1a1a1a", fg="#fff",
         font=("Helvetica", 12), pady=6).pack(fill="x")

btn_frame = tk.Frame(root, bg="#f0f0f0")
btn_frame.pack(fill="x", padx=10, pady=6)
tk.Button(btn_frame, text="↩ Deshacer último punto",
          command=lambda: deshacer(), width=22).pack(side="left", padx=4)
tk.Button(btn_frame, text="✓ Guardar y terminar",
          bg="#1a1a1a", fg="white", command=lambda: guardar(), width=20).pack(side="right", padx=4)


def redraw_polygon():
    for lid in line_ids:
        canvas.delete(lid)
    line_ids.clear()
    n = len(points_display)
    if n >= 2:
        for i in range(n - 1):
            lid = canvas.create_line(*points_display[i], *points_display[i+1],
                                     fill="#00ff00", width=2)
            line_ids.append(lid)
    if n >= 3:
        lid = canvas.create_line(*points_display[-1], *points_display[0],
                                 fill="#00ff88", width=2, dash=(4, 3))
        line_ids.append(lid)
    info_var.set(f"{n} puntos marcados. ENTER o 'Guardar' cuando el contorno esté completo.")


_drag_start = [None]

def on_press(event):
    _drag_start[0] = (event.x, event.y)
    return "break"

def on_release(event):
    # Solo registrar si el ratón no se movió más de 8px (clic, no arrastre)
    if _drag_start[0] is None:
        return "break"
    dx = abs(event.x - _drag_start[0][0])
    dy = abs(event.y - _drag_start[0][1])
    if dx < 8 and dy < 8:
        x, y = event.x, event.y
        points_display.append((x, y))
        dot = canvas.create_oval(x-5, y-5, x+5, y+5, fill="#ff3300", outline="#fff", width=1)
        dot_ids.append(dot)
        redraw_polygon()
    _drag_start[0] = None
    return "break"

def on_click(event):
    return "break"   # bloquear comportamiento por defecto


def deshacer():
    if points_display:
        points_display.pop()
        canvas.delete(dot_ids.pop())
        redraw_polygon()


def guardar():
    if len(points_display) < 3:
        messagebox.showwarning("Faltan puntos", "Necesitas al menos 3 puntos para definir el área.")
        return

    # Convertir coordenadas de pantalla a coordenadas originales
    pts_orig = [(int(x / scale), int(y / scale)) for x, y in points_display]

    # Calcular bounding box del polígono
    xs = [p[0] for p in pts_orig]
    ys = [p[1] for p in pts_orig]
    bb_x, bb_y = min(xs), min(ys)
    bb_w, bb_h = max(xs) - bb_x, max(ys) - bb_y

    # Generar máscara
    mask = Image.new("L", (orig_w, orig_h), 0)       # negro = no imprimible
    draw = ImageDraw.Draw(mask)
    draw.polygon(pts_orig, fill=255)                   # blanco = zona imprimible
    mask.save(MASK_PATH)
    print(f"  ✓ Máscara guardada: {MASK_PATH.name}  ({orig_w}x{orig_h}px)")

    # Guardar JSON de calibración
    calibracion = {
        "id": TROPHY_ID,
        "imagen_original": f"{orig_w}x{orig_h}px",
        "escala_usada": round(scale, 4),
        "puntos_poligono": pts_orig,
        "bounding_box": {"x": bb_x, "y": bb_y, "ancho": bb_w, "alto": bb_h},
        "mascara": str(MASK_PATH.relative_to(PROJECT_ROOT)),
        "entrada_catalogo": {
            "id": TROPHY_ID,
            "nombre": "Copetin",
            "material": "metal",
            "precio_base": 0,
            "imagen_base": f"assets/trophies/{TROPHY_ID}.png",
            "zona_imprimible": {
                "x": bb_x,
                "y": bb_y,
                "ancho": bb_w,
                "alto": bb_h,
                "forma": "mascara",
                "mascara": str(MASK_PATH.relative_to(PROJECT_ROOT)),
                "puntos_poligono": pts_orig,
                "calibrado": True,
                "metodo_calibracion": "calibrar_trofeo.py — polígono manual"
            },
            "area_impresion_mm": {"ancho": 0, "alto": 0}
        }
    }
    JSON_PATH.write_text(json.dumps(calibracion, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ JSON guardado: {JSON_PATH.name}")
    print(f"\n  Bounding box: x={bb_x} y={bb_y}  {bb_w}x{bb_h}px")
    print(f"  Puntos del polígono ({len(pts_orig)}): {pts_orig[:3]}...")
    print(f"\n  ➜ Revisa {JSON_PATH.name} y copia 'entrada_catalogo' en data/trophy_catalog.json")

    messagebox.showinfo("¡Calibración guardada!",
        f"Máscara: {MASK_PATH.name}\n"
        f"JSON:    {JSON_PATH.name}\n\n"
        f"Zona imprimible: {bb_w}x{bb_h}px\n"
        f"Puntos marcados: {len(pts_orig)}\n\n"
        "Abre data/copetin_calibracion.json y copia\n"
        "el bloque 'entrada_catalogo' en trophy_catalog.json.")
    root.destroy()


canvas.bind("<ButtonPress-1>",   on_press)
canvas.bind("<ButtonRelease-1>", on_release)
canvas.bind("<B1-Motion>",       lambda e: "break")   # bloquear arrastre
root.bind("<Return>",    lambda e: guardar())
root.bind("<BackSpace>", lambda e: deshacer())

root.mainloop()
