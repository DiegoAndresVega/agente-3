"""
CAPA 2 - Compositor de mockup
Sustain Awards - Agente 2

Recibe los datos del pedido y genera DOS propuestas visuales
del trofeo personalizado con la identidad del cliente.

Uso:
    python scripts/capa2_compositor.py

Flujo:
    1. Carga pedido desde mock_orders.json
    2. Carga modelo de trofeo y coordenadas desde trophy_catalog.json
    3. Genera 2 diseños distintos respetando la identidad visual del cliente
    4. Compone cada diseño sobre la foto real del trofeo
    5. Guarda los mockups en outputs/mockups/
"""

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np


# -------------------------------------------------
# 1. CARGAR DATOS
# -------------------------------------------------

def cargar_pedido(id_pedido):
    with open("data/mock_orders.json", "r", encoding="utf-8") as f:
        datos = json.load(f)
    for pedido in datos["pedidos"]:
        if pedido["id_pedido"] == id_pedido:
            return pedido
    raise ValueError(f"Pedido {id_pedido} no encontrado")


def cargar_modelo_trofeo(id_modelo):
    with open("data/trophy_catalog.json", "r", encoding="utf-8") as f:
        catalogo = json.load(f)
    for modelo in catalogo["modelos"]:
        if modelo["id"] == id_modelo:
            return modelo
    raise ValueError(f"Modelo {id_modelo} no encontrado en catalogo")


# -------------------------------------------------
# 2. UTILIDADES DE DISEÑO
# -------------------------------------------------

def hex_to_rgb(hex_color):
    """Convierte #RRGGBB a tupla (R, G, B)."""
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def cargar_fuentes(size_lg=18, size_md=14, size_sm=12, size_xs=11):
    """Carga fuentes del sistema con fallback a default."""
    rutas = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    rutas_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    def load(paths, size):
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except:
                continue
        return ImageFont.load_default()

    return {
        "bold_lg": load(rutas, size_lg),
        "bold_md": load(rutas, size_md),
        "regular": load(rutas_regular, size_sm),
        "small":   load(rutas_regular, size_xs),
    }


def preparar_logo(logo_path, modo="blanco"):
    """
    Carga el logo y lo prepara según el modo:
    - 'blanco': logo en blanco (para fondos oscuros)
    - 'color': logo en sus colores originales sin fondo
    """
    logo = Image.open(logo_path).convert("RGBA")
    arr = np.array(logo)

    # Eliminar fondo blanco/casi blanco
    white_mask = (arr[:,:,0] > 230) & (arr[:,:,1] > 230) & (arr[:,:,2] > 230)
    arr[white_mask, 3] = 0

    if modo == "blanco":
        opaque = arr[:,:,3] > 30
        arr[opaque] = [255, 255, 255, 255]

    return Image.fromarray(arr)


def escalar_logo(logo, max_w, max_h):
    ratio = min(max_w / logo.width, max_h / logo.height)
    return logo.resize((int(logo.width * ratio), int(logo.height * ratio)), Image.LANCZOS)


def texto_centrado(draw, texto, y, font, color, ancho_canvas):
    """Dibuja texto centrado horizontalmente. Soporta saltos de línea con \\n."""
    lineas = texto.split('\n')
    line_h = font.getbbox("A")[3] + 5
    for i, linea in enumerate(lineas):
        bbox = draw.textbbox((0, 0), linea, font=font)
        tw = bbox[2] - bbox[0]
        x = (ancho_canvas - tw) // 2
        draw.text((x, y + i * line_h), linea, fill=color, font=font)
    return y + len(lineas) * line_h


# -------------------------------------------------
# 3. GENERADORES DE DISEÑO
# -------------------------------------------------

def generar_diseno_v1_oscuro(w, h, identidad, award, logo_path, fuentes):
    """
    Propuesta 1: Fondo color primario, logo en blanco, acentos en secundario.
    Estilo corporativo sobrio.
    """
    c1 = hex_to_rgb(identidad["color_primario"])
    c2 = hex_to_rgb(identidad["color_secundario"])

    d = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(d)

    # Fondo primario
    draw.rectangle([0, 0, w, h], fill=(*c1, 255))

    # Franja superior secundaria
    draw.rectangle([0, 0, w, int(h * 0.05)], fill=(*c2, 255))

    # Logo en blanco
    logo = preparar_logo(logo_path, modo="blanco")
    logo = escalar_logo(logo, int(w * 0.75), int(h * 0.20))
    lx = (w - logo.width) // 2
    d.paste(logo, (lx, int(h * 0.08)), logo)

    # Separador
    sep_y = int(h * 0.40)
    draw.line([(int(w*0.08), sep_y), (int(w*0.92), sep_y)],
              fill=(*c2, 200), width=1)

    # Textos
    y = int(h * 0.44)
    y = texto_centrado(draw, award["headline"], y, fuentes["bold_lg"], (255,255,255,255), w)
    y += 8
    y = texto_centrado(draw, award["recipient"], y, fuentes["bold_md"], (*c2, 230), w)
    y += 8
    y = texto_centrado(draw, award["subtitle"], y, fuentes["regular"], (255,255,255,180), w)
    y += 6
    texto_centrado(draw, award["fecha"], y, fuentes["small"], (*c2, 180), w)

    # Franja inferior secundaria
    draw.rectangle([0, int(h * 0.94), w, h], fill=(*c2, 255))

    return d


def generar_diseno_v2_claro(w, h, identidad, award, logo_path, fuentes):
    """
    Propuesta 2: Fondo blanco, logo en color, textos en primario.
    Estilo limpio y minimalista.
    """
    c1 = hex_to_rgb(identidad["color_primario"])
    c2 = hex_to_rgb(identidad["color_secundario"])

    d = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(d)

    # Fondo blanco
    draw.rectangle([0, 0, w, h], fill=(255, 255, 255, 255))

    # Borde primario
    draw.rectangle([0, 0, w, h], outline=(*c1, 255), width=4)

    # Franja superior primaria
    draw.rectangle([0, 0, w, int(h * 0.06)], fill=(*c1, 255))

    # Logo en color
    logo = preparar_logo(logo_path, modo="color")
    logo = escalar_logo(logo, int(w * 0.75), int(h * 0.20))
    lx = (w - logo.width) // 2
    d.paste(logo, (lx, int(h * 0.10)), logo)

    # Separador
    sep_y = int(h * 0.42)
    draw.line([(int(w*0.08), sep_y), (int(w*0.92), sep_y)],
              fill=(*c1, 200), width=1)

    # Textos
    y = int(h * 0.46)
    y = texto_centrado(draw, award["headline"], y, fuentes["bold_lg"], (*c1, 255), w)
    y += 8
    y = texto_centrado(draw, award["recipient"], y, fuentes["bold_md"], (*c2, 255), w)
    y += 8
    y = texto_centrado(draw, award["subtitle"], y, fuentes["regular"], (*c1, 180), w)
    y += 6
    texto_centrado(draw, award["fecha"], y, fuentes["small"], (*c1, 150), w)

    # Franja inferior secundaria
    draw.rectangle([0, int(h * 0.93), w, h], fill=(*c2, 255))

    return d


# -------------------------------------------------
# 4. COMPOSITOR - pega el diseño sobre el trofeo
# -------------------------------------------------

def componer_mockup(imagen_trofeo_path, diseno, zona):
    trofeo = Image.open(imagen_trofeo_path).convert("RGBA")
    diseno_final = diseno.resize((zona["ancho"], zona["alto"]), Image.LANCZOS)
    trofeo.paste(diseno_final, (zona["x"], zona["y"]), diseno_final)
    return trofeo.convert("RGB")


# -------------------------------------------------
# 5. UTILIDAD: resolver textos con sugerencias IA
# -------------------------------------------------

def resolver_award(award: dict) -> dict:
    """
    Devuelve una copia del dict award donde headline y subtitle
    usan los valores sugeridos por la IA si están presentes,
    cayendo al original si no.
    """
    resolved = dict(award)
    if award.get("headline_ia"):
        resolved["headline"] = award["headline_ia"]
    if award.get("subtitle_ia"):
        resolved["subtitle"] = award["subtitle_ia"]
    return resolved


# -------------------------------------------------
# 6. ORQUESTADOR PARA PEDIDOS ENRIQUECIDOS (CAPA 1 → CAPA 2)
# -------------------------------------------------

def generar_mockups_desde_pedido(pedido_v1: dict, pedido_v2: dict, id_modelo: str) -> list:
    """
    Variante del orquestador que acepta pedidos ya enriquecidos por Capa 1
    en lugar de cargarlos por ID desde el JSON.

    Parámetros:
        pedido_v1   – Pedido enriquecido para la variante 1 (diseño oscuro)
        pedido_v2   – Pedido enriquecido para la variante 2 (diseño claro)
        id_modelo   – ID del modelo de trofeo (p.ej. "totem_basic")

    Devuelve lista con las rutas de los dos mockups generados.
    """
    id_pedido = pedido_v1.get("id_pedido", "pedido")
    modelo    = cargar_modelo_trofeo(id_modelo)
    zona      = modelo["zona_imprimible"]

    print(f"\nGenerando mockups desde pedido enriquecido: {id_pedido}")
    print(f"  Trofeo : {modelo['nombre']}")
    print(f"  Zona   : x={zona['x']}, y={zona['y']}, "
          f"{zona['ancho']}x{zona['alto']}px")

    fuentes = cargar_fuentes()
    Path("outputs/mockups").mkdir(parents=True, exist_ok=True)
    rutas = []

    pares = [
        (pedido_v1, generar_diseno_v1_oscuro),
        (pedido_v2, generar_diseno_v2_claro),
    ]

    for pedido, fn_diseno in pares:
        award     = resolver_award(pedido["award"])
        identidad = pedido["identidad_visual"]
        logo_path = pedido["assets"]["logo_path"]
        nombre_v  = pedido.get("_variante_nombre", "variante")
        sufijo    = nombre_v.lower().replace(" ", "_")

        print(f"\n  Generando variante: {nombre_v}...")
        w, h   = zona["ancho"], zona["alto"]
        diseno = fn_diseno(w, h, identidad, award, logo_path, fuentes)
        mockup = componer_mockup(modelo["imagen_base"], diseno, zona)

        output_path = f"outputs/mockups/mockup_{id_pedido}_{sufijo}.jpg"
        mockup.save(output_path, quality=95)
        rutas.append(output_path)
        print(f"  Guardado: {output_path}")

    return rutas


# -------------------------------------------------
# 7. ORQUESTADOR PRINCIPAL (uso standalone)
# -------------------------------------------------

def generar_mockups(id_pedido):
    """
    Genera las dos propuestas de mockup para un pedido.
    Devuelve las rutas de los archivos generados.
    """
    print(f"\nGenerando mockups para pedido: {id_pedido}")
    print("-" * 45)

    pedido = cargar_pedido(id_pedido)
    modelo = cargar_modelo_trofeo(pedido["modelo_trofeo"])
    zona   = modelo["zona_imprimible"]

    print(f"  Cliente  : {pedido['id_cliente']}")
    print(f"  Trofeo   : {modelo['nombre']}")
    print(f"  Zona     : x={zona['x']}, y={zona['y']}, "
          f"{zona['ancho']}x{zona['alto']}px "
          f"(calibrado: {zona.get('calibrado', False)})")

    fuentes   = cargar_fuentes()
    award     = pedido["award"]
    identidad = pedido["identidad_visual"]
    logo_path = pedido["assets"]["logo_path"]

    Path("outputs/mockups").mkdir(parents=True, exist_ok=True)
    rutas = []

    versiones = [
        ("v1_oscuro",  generar_diseno_v1_oscuro),
        ("v2_claro",   generar_diseno_v2_claro),
    ]

    for sufijo, fn_diseno in versiones:
        print(f"\n  Generando propuesta {sufijo}...")
        w, h = zona["ancho"], zona["alto"]
        diseno = fn_diseno(w, h, identidad, award, logo_path, fuentes)
        mockup = componer_mockup(modelo["imagen_base"], diseno, zona)

        output_path = f"outputs/mockups/mockup_{id_pedido}_{sufijo}.jpg"
        mockup.save(output_path, quality=95)
        rutas.append(output_path)
        print(f"  Guardado: {output_path}")

    return rutas


# -------------------------------------------------
# 6. EJECUTAR
# -------------------------------------------------

if __name__ == "__main__":
    rutas = generar_mockups("ORD-2026-001")
    print(f"\nMockups generados:")
    for r in rutas:
        print(f"  {r}")
    print("\nRevisa la carpeta outputs/mockups/")