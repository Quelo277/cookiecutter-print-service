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
    try:
        img = Image.open(file_path)
        if img.format not in ("JPEG", "PNG", "JPG"):
            return False, f"Formato no soportado: {img.format}. Use JPG o PNG."
        img_gray = img.convert("L")
        arr = np.array(img_gray)
        if np.std(arr) < 30:
            return False, "La imagen tiene muy poco contraste."
        return True, "OK"
    except Exception as e:
        return False, str(e)

def _binarize_image(input_path: str, output_pnm: str) -> None:
    # Optimizamos para que Potrace detecte bien los bordes
    cmd = [
        "convert", input_path,
        "-resize", "1000x1000>",
        "-colorspace", "Gray",
        "-negate", 
        "-threshold", "50%",
        output_pnm,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    cmd = ["potrace", "-s", "-o", output_svg, bnw_pnm]
    subprocess.run(cmd, check=True, capture_output=True)

def _generate_filled_svg(input_svg: str, output_filled_svg: str) -> None:
    """Simula el paso clave de Papooch usando Inkscape."""
    cmd = [
        "inkscape",
        input_svg,
        "--batch-process",
        "--actions=select-all;path-combine;path-fill;export-filename:" + output_filled_svg + ";export-do",
    ]
    subprocess.run(cmd, check=True, capture_output=True)

def _generate_openscad_code(svg_path: str, filled_svg_path: str, scad_path: str, wh, wt, hh, ht) -> None:
    scad_code = f"""
$fn = 16;
wall_height = {wh};
wall_thickness = {wt};
handle_height = {hh};
handle_thickness = {ht};
tolerancia = 0.6;

module original() {{ import("{svg_path}", center = true, dpi = 96); }}
module rellena() {{ import("{filled_svg_path}", center = true, dpi = 96); }}

// PIEZA 1: CORTANTE (Usa la versión rellena para evitar el bloque rectangular)
module pieza_cortante() {{
    union() {{
        linear_extrude(height = wall_height)
            difference() {{
                offset(r = wall_thickness) rellena();
                rellena();
            }}
        linear_extrude(height = handle_height)
            difference() {{
                offset(r = handle_thickness) rellena();
                rellena();
            }}
    }}
}}

// PIEZA 2: SELLO (Base sólida + detalles del original)
module pieza_sello() {{
    translate([120, 0, 0]) {{
        union() {{
            linear_extrude(height = 2)
                offset(r = -tolerancia) rellena();
            
            linear_extrude(height = 5)
                offset(r = -tolerancia) original();

            translate([0, 0, 2]) cylinder(h = wall_height - 2, r = 10);
        }}
    }}
}}

pieza_cortante();
pieza_sello();
"""
    with open(scad_path, "w") as f:
        f.write(scad_code)

def image_to_stl(image_path, output_name, **kwargs) -> dict:
    wh = kwargs.get("wall_height") or WALL_HEIGHT
    wt = kwargs.get("wall_thickness") or WALL_THICKNESS
    hh = kwargs.get("handle_height") or HANDLE_HEIGHT
    ht = kwargs.get("handle_thickness") or HANDLE_THICKNESS

    work_dir = STL_DIR / output_name
    work_dir.mkdir(parents=True, exist_ok=True)

    p = {
        "pnm": str(work_dir / "temp.pnm"),
        "svg": str(work_dir / "orig.svg"),
        "filled": str(work_dir / "filled.svg"),
        "scad": str(work_dir / "model.scad"),
        "stl": str(work_dir / "model.stl"),
        "preview": str(PREVIEW_DIR / f"{output_name}.png")
    }

    try:
        _binarize_image(image_path, p["pnm"])
        _vectorize_to_svg(p["pnm"], p["svg"])
        _generate_filled_svg(p["svg"], p["filled"])
        _generate_openscad_code(p["svg"], p["filled"], p["scad"], wh, wt, hh, ht)
        
        # Renderizado
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True, timeout=300)
        
        # Datos finales
        m = mesh.Mesh.from_file(p["stl"])
        vol, _, _ = m.get_mass_properties()
        dims = [m.x.max()-m.x.min(), m.y.max()-m.y.min(), m.z.max()-m.z.min()]
        
        final_stl = str(STL_DIR / f"{output_name}.stl")
        shutil.copy2(p["stl"], final_stl)
        
        # Generar preview
        subprocess.run(["openscad", "-o", p["preview"], "--imgsize=800,800", p["scad"]], timeout=120)

        return {
            "exito": True, "mensaje": "OK",
            "stl_path": final_stl, "preview_path": p["preview"],
            "volumen_cm3": round(vol/1000.0, 4),
            "dimensiones": [round(d, 2) for d in dims],
            "parametros": {"wh": wh, "wt": wt, "hh": hh, "ht": ht}
        }
    except Exception as e:
        return {"exito": False, "mensaje": str(e), "volumen_cm3": 0, "dimensiones": [0,0,0]}

def calculate_price(volumen_cm3: float) -> dict:
    from app.config import COSTO_FILAMENTO_POR_CM3, COSTO_BASE, MARGEN, CURRENCY, CURRENCY_SYMBOL
    costo_mat = volumen_cm3 * COSTO_FILAMENTO_POR_CM3
    total = (costo_mat + COSTO_BASE) * MARGEN
    return {
        "precio_final": round(total, 2), "volumen_cm3": round(volumen_cm3, 4),
        "costo_materiales": round(costo_mat, 2), "costo_base": COSTO_BASE,
        "margen": MARGEN, "moneda": CURRENCY, "simbolo": CURRENCY_SYMBOL
    }
