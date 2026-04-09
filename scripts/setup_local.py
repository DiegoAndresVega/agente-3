"""
SETUP LOCAL - Sustain Awards Agente 2
Ejecuta este script una sola vez para generar:
- Datos simulados de clientes (mock_orders.json)
- Catalogo de trofeos con coordenadas (trophy_catalog.json)
- Imagenes placeholder de trofeos para testing
- Logos placeholder de clientes para testing

Uso:
    python scripts/setup_local.py
"""

import os
import json
from pathlib import Path
from PIL import Image, ImageDraw


# -------------------------------------------------
# 1. DATOS SIMULADOS - PEDIDOS DE CLIENTE
# Simula lo que llegara desde PrestaShop
# -------------------------------------------------

MOCK_ORDERS = {
    "meta": {
        "descripcion": "Datos simulados que imitan lo que llegara desde PrestaShop"
    },
    "clientes": [
        {
            "id": "cliente_001",
            "empresa": "TechCorp Spain S.L.",
            "url_corporativa": "https://www.techcorp.es",
            "email": "maria@techcorp.es"
        },
        {
            "id": "cliente_002",
            "empresa": "GreenEnergy Global",
            "url_corporativa": "https://www.greenenergy.com",
            "email": "carlos@greenenergy.com"
        }
    ],
    "pedidos": [
        {
            "id_pedido": "ORD-2026-001",
            "id_cliente": "cliente_001",
            "modelo_trofeo": "totem_basic",
            "cantidad": 10,
            "presupuesto": 1500,
            "evento": {
                "nombre": "Tech Innovation Summit 2026",
                "fecha": "15 Mayo 2026",
                "lugar": "Barcelona"
            },
            "award": {
                "headline": "Best Innovation Award",
                "recipient": "John Doe",
                "subtitle": "Por su contribucion al desarrollo tecnologico",
                "fecha": "2026"
            },
            "assets": {
                "logo_path": "assets/logos/techcorp_logo.png",
                "brand_book_path": None,
                "url_corporativa": "https://www.techcorp.es"
            },
            "preferencias": {
                "color_dominante": "#1A73E8",
                "estilo": "moderno"
            }
        },
        {
            "id_pedido": "ORD-2026-002",
            "id_cliente": "cliente_002",
            "modelo_trofeo": "placa_a5",
            "cantidad": 25,
            "presupuesto": 800,
            "evento": {
                "nombre": "Green Future Awards",
                "fecha": "20 Junio 2026",
                "lugar": "Madrid"
            },
            "award": {
                "headline": "Sustainability Excellence Award",
                "recipient": "Ana Martinez",
                "subtitle": "Liderazgo en energias renovables",
                "fecha": "2026"
            },
            "assets": {
                "logo_path": "assets/logos/greenenergy_logo.png",
                "brand_book_path": None,
                "url_corporativa": "https://www.greenenergy.com"
            },
            "preferencias": {
                "color_dominante": "#2ECC71",
                "estilo": "minimalista"
            }
        }
    ]
}


# -------------------------------------------------
# 2. CATALOGO DE TROFEOS CON COORDENADAS
# -------------------------------------------------

TROPHY_CATALOG = {
    "meta": {
        "descripcion": "Modelos de trofeo con coordenadas de zona imprimible"
    },
    "modelos": [
        {
            "id": "totem_basic",
            "nombre": "Totem Basic",
            "material": "madera",
            "precio_base": 45,
            "imagen_base": "assets/trophies/totem_basic_placeholder.png",
            "zona_imprimible": {
                "x": 120, "y": 80, "ancho": 260, "alto": 380,
                "puntos_homografia": [
                    [120, 80],
                    [380, 80],
                    [380, 460],
                    [120, 460]
                ]
            },
            "area_impresion_mm": {"ancho": 100, "alto": 150}
        },
        {
            "id": "placa_a5",
            "nombre": "Placa A5",
            "material": "aluminio",
            "precio_base": 30,
            "imagen_base": "assets/trophies/placa_a5_placeholder.png",
            "zona_imprimible": {
                "x": 60, "y": 50, "ancho": 380, "alto": 280,
                "puntos_homografia": [
                    [65, 55],
                    [435, 50],
                    [440, 325],
                    [60, 330]
                ]
            },
            "area_impresion_mm": {"ancho": 148, "alto": 105}
        }
    ]
}


# -------------------------------------------------
# 3. GENERADOR DE IMAGENES PLACEHOLDER
# -------------------------------------------------

def create_trophy_placeholder(filename, width, height, label, zone):
    """
    Genera imagen placeholder del trofeo.
    El rectangulo azul marca donde se pegara el diseno.
    """
    img = Image.new("RGB", (width, height), color=(220, 215, 210))
    draw = ImageDraw.Draw(img)

    # Silueta del trofeo
    draw.rounded_rectangle(
        [30, 30, width - 30, height - 30],
        radius=15,
        fill=(180, 170, 160),
        outline=(140, 130, 120),
        width=3
    )

    # Zona imprimible en azul
    x = zone["x"]
    y = zone["y"]
    w = zone["ancho"]
    h = zone["alto"]

    draw.rectangle(
        [x, y, x + w, y + h],
        fill=(200, 220, 255),
        outline=(30, 100, 220),
        width=2
    )

    draw.text(
        (x + w // 2, y + h // 2 - 15),
        "ZONA IMPRIMIBLE",
        fill=(30, 100, 220),
        anchor="mm"
    )
    draw.text(
        (x + w // 2, y + h // 2 + 10),
        f"{w} x {h} px",
        fill=(30, 100, 220),
        anchor="mm"
    )

    draw.text(
        (width // 2, height - 15),
        label,
        fill=(80, 80, 80),
        anchor="mm"
    )

    img.save(filename)
    print(f"  Trofeo creado: {filename}")


def create_logo_placeholder(filename, text, hex_color):
    """
    Genera logo placeholder con color de marca.
    """
    img = Image.new("RGBA", (300, 120), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)

    draw.rounded_rectangle(
        [0, 0, 299, 119],
        radius=12,
        fill=(r, g, b, 255)
    )

    draw.text(
        (150, 60),
        text,
        fill=(255, 255, 255, 255),
        anchor="mm"
    )

    img.save(filename)
    print(f"  Logo creado: {filename}")


# -------------------------------------------------
# 4. EJECUTAR SETUP
# -------------------------------------------------

def run_setup():
    print("\nSUSTAIN AWARDS - Setup local")
    print("=" * 40)

    print("\n[1/3] Generando datos simulados...")
    with open("data/mock_orders.json", "w", encoding="utf-8") as f:
        json.dump(MOCK_ORDERS, f, indent=2, ensure_ascii=False)
    print("  data/mock_orders.json creado")

    with open("data/trophy_catalog.json", "w", encoding="utf-8") as f:
        json.dump(TROPHY_CATALOG, f, indent=2, ensure_ascii=False)
    print("  data/trophy_catalog.json creado")

    print("\n[2/3] Generando imagenes placeholder de trofeos...")
    create_trophy_placeholder(
        "assets/trophies/totem_basic_placeholder.png",
        500, 600, "Totem Basic",
        {"x": 120, "y": 80, "ancho": 260, "alto": 380}
    )
    create_trophy_placeholder(
        "assets/trophies/placa_a5_placeholder.png",
        500, 380, "Placa A5",
        {"x": 60, "y": 50, "ancho": 380, "alto": 280}
    )

    print("\n[3/3] Generando logos placeholder de clientes...")
    create_logo_placeholder(
        "assets/logos/techcorp_logo.png",
        "TECHCORP", "#1A73E8"
    )
    create_logo_placeholder(
        "assets/logos/greenenergy_logo.png",
        "GREENENERGY", "#2ECC71"
    )

    print("\nSetup completado.")
    print("\nArchivos generados:")
    print("  data/mock_orders.json         -> pedidos simulados de clientes")
    print("  data/trophy_catalog.json      -> modelos con coordenadas")
    print("  assets/trophies/              -> fotos base placeholder")
    print("  assets/logos/                 -> logos placeholder")
    print("\nProximo paso:")
    print("  python scripts/capa0_normalizer.py")


if __name__ == "__main__":
    run_setup()