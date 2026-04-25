"""
Pipeline de generacion STL para cortantes de galletas.
Optimizado para Gema Makers: Imagen → Binarizar → SVG (Potrace) → OpenSCAD → STL
"""
import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
from stl import mesh
from PIL import Image

from app.config import (
    WALL_HEIGHT,
    WALL_THICKNESS,
    HANDLE_HEIGHT,
    HANDLE_THICKNESS,
    STL_DIR,
    PREVIEW_DIR,
)


def validate_image(file_path: str) -> Tuple[bool, str]:
    """Valida que la imagen sea JPG/PNG y tenga contraste."""
    try:
        img = Image.open(file_path)
        if img.format not in ("JPEG", "PNG", "JPG"):
            return False, f"Formato no soportado: {img.format}. Use JPG o PNG."

        img_gray = img.convert("L")
        arr = np.array(img_gray)
        std = np.std(arr)
        if std < 30:
            return False, "La imagen tiene muy poco contraste. Usa fondo claro y figura oscura."
        return True, "OK"
    except Exception as e:
        return False, f"Error al procesar la imagen: {str(e)}"


def image_to_stl(
    image_path: str,
    output_name: str,
    wall_height: Optional[float] = None,
    wall_thickness: Optional[float] = None,
    handle_height: Optional[float] = None,
    handle_thickness: Optional[float] = None,
) -> dict:
    """Pipeline principal: Imagen -> PNM -> SVG -> OpenSCAD -> STL"""
    wh = wall_height or WALL_HEIGHT
    wt = wall_thickness or WALL_THICKNESS
    hh = handle_height or HANDLE_HEIGHT
    ht = handle_thickness or HANDLE_THICKNESS

    work_dir = STL_DIR / output_name
    work_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "input_image": image_path,
        "bnw_pnm": str(work_dir / "input_bw.pnm"),
        "vector_svg": str(work_dir / "vector.svg"),
        "scad_file": str(work_dir / "cutter.scad"),
        "stl_file": str(work_dir / "cutter.stl"),
        "preview_png": str(PREVIEW_DIR / f"{output_name}.png"),
    }

    try:
        # 1. Binarizar con ImageMagick
        _binarize_image(image_path, paths["bnw_pnm"])

        # 2. Vectorizar a SVG con Potrace
        _vectorize_to_svg(paths["bnw_pnm"], paths["vector_svg"])

        # 3. Generar archivo .scad
        _generate_openscad_svg(
            paths["vector_svg"],
            paths["scad_file"],
            wh, wt, hh, ht
        )

        # 4. Renderizar STL (OpenSCAD CLI)
        _render_stl(paths["scad_file"], paths["stl_file"])

        # 5. Calcular volumen y dimensiones (Blindado para JSON)
        volumen_cm3, dimensiones = _calculate_volume(paths["stl_file"])

        # 6. Generar imagen de preview
        _generate_preview(paths["scad_file"], paths["preview_png"])

        final_stl = str(STL_DIR / f"{output_name}.stl")
        shutil.copy2(paths["stl_file"], final_stl)

        return {
            "stl_path": final_stl,
            "preview_path": paths["preview_png"],
            "volumen_cm3": round(volumen_cm3, 4),
            "dimensiones": [round(d, 2) for d in dimensiones],  # Volvemos a 'dimensiones'
            "exito": True,
            "mensaje": "STL generado exitosamente",
            "parametros": {
                "wall_height": wh, 
                "wall_thickness": wt, 
                "handle_height": hh, 
                "handle_thickness": ht
            },
        }

    except Exception as e:
        return {
            "exito": False,
            "mensaje": f"Error en pipeline STL: {str(e)}",
            "volumen_cm3": 0.0,
            "dimensiones": [0, 0, 0]
        }


def _binarize_image(input_path: str, output_pnm: str) -> None:
    cmd = [
        "convert", input_path,
        "-resize", "1000x1000>",
        "-colorspace", "Gray",
        "-threshold", "50%",
        "-negate",
        output_pnm,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    cmd = ["potrace", "-s", "-o", output_svg, bnw_pnm]
    subprocess.run(cmd, check=True, capture_output=True)


def _generate_openscad_svg(svg_path: str, scad_path: str, wh, wt, hh, ht) -> None:
    """
    Genera un set de dos piezas: 
    1. Cortante exterior con mango.
    2. Sello interior (estampador) con soporte.
    """
    scad_code = f"""
// Parametros de Gema Makers
wall_height = {wh};
wall_thickness = {wt};
handle_height = {hh};
handle_thickness = {ht};
tolerancia = 0.5; // Espacio para que el sello deslice dentro

module pieza_exterior() {{
    union() {{
        // Pared de corte
        linear_extrude(height = wall_height)
            difference() {{
                offset(r = wall_thickness / 2) 
                    import("{svg_path}", center = true, dpi = 96);
                offset(r = -wall_thickness / 2) 
                    import("{svg_path}", center = true, dpi = 96);
            }}
        // Mango exterior
        linear_extrude(height = handle_height)
            difference() {{
                offset(r = handle_thickness) 
                    import("{svg_path}", center = true, dpi = 96);
                offset(r = -wall_thickness / 2) 
                    import("{svg_path}", center = true, dpi = 96);
            }}
    }}
}}

module pieza_interior() {{
    // Desplazamos el sello a la derecha para que se impriman por separado
    // o podes comentarlo si queres generar dos STLs distintos
    translate([100, 0, 0]) {{ 
        union() {{
            // Base del estampado (la que toca la masa)
            linear_extrude(height = 3) // Espesor de la placa del sello
                offset(r = -wall_thickness / 2 - tolerancia) 
                    import("{svg_path}", center = true, dpi = 96);
            
            // Detalles internos (ojos, nariz, etc.) 
            // Suben un poco mas para marcar bien
            linear_extrude(height = 5) 
                offset(r = -wall_thickness / 2 - tolerancia)
                    import("{svg_path}", center = true, dpi = 96);

            // Mango del sello para agarrarlo
            translate([0,0,3])
            cylinder(h = wall_height - 3, r1 = 10, r2 = 8, $fn=32);
        }}
    }}
}}

pieza_exterior();
pieza_interior();
"""
    with open(scad_path, "w") as f:
        f.write(scad_code)


def _render_stl(scad_path: str, stl_path: str) -> None:
    cmd = ["openscad", "-o", stl_path, scad_path]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)


def _calculate_volume(stl_path: str) -> Tuple[float, Tuple[float, float, float]]:
    m = mesh.Mesh.from_file(stl_path)
    volume_mm3, _, _ = m.get_mass_properties()
    
    # .item() o float() para que FastAPI no explote con NumPy
    vol_cm3 = float(volume_mm3 / 1000.0)
    
    dims = (
        float(m.x.max() - m.x.min()),
        float(m.y.max() - m.y.min()),
        float(m.z.max() - m.z.min())
    )
    return vol_cm3, dims


def _generate_preview(scad_path: str, preview_path: str) -> None:
    cmd = [
        "openscad", "-o", preview_path, 
        "--imgsize=600,600", 
        "--colorscheme=Starlight",
        scad_path
    ]
    subprocess.run(cmd, capture_output=True, timeout=120)


def calculate_price(volumen_cm3: float) -> dict:
    """
    Calcula el precio detallado para el frontend.
    """
    from app.config import (
        COSTO_FILAMENTO_POR_CM3, 
        COSTO_BASE, 
        MARGEN, 
        CURRENCY, 
        CURRENCY_SYMBOL
    )
    
    # Aseguramos que volumen sea float nativo
    vol_cm3 = float(volumen_cm3)
    
    costo_materiales = vol_cm3 * COSTO_FILAMENTO_POR_CM3
    precio_final = (costo_materiales + COSTO_BASE) * MARGEN

    return {
        "volumen_cm3": round(vol_cm3, 4),
        "costo_materiales": round(float(costo_materiales), 2),
        "costo_base": float(COSTO_BASE),
        "margen": float(MARGEN),
        "precio_final": round(float(precio_final), 2),
        "moneda": CURRENCY,
        "simbolo": CURRENCY_SYMBOL,
        "formula": f"({vol_cm3:.2f} * {COSTO_FILAMENTO_POR_CM3} + {COSTO_BASE}) * {MARGEN}"
    }
