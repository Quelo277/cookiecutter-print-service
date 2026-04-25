import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
from stl import mesh
from PIL import Image

from app.config import (
    WALL_HEIGHT, WALL_THICKNESS, HANDLE_HEIGHT, HANDLE_THICKNESS,
    STL_DIR, PREVIEW_DIR, UPLOAD_DIR,
    COSTO_FILAMENTO_POR_CM3, COSTO_BASE, MARGEN, CURRENCY, CURRENCY_SYMBOL
)

def validate_image(file_path: str) -> Tuple[bool, str]:
    try:
        img = Image.open(file_path)
        return True, "OK"
    except Exception as e:
        return False, str(e)

def _binarize_image(input_path: str, output_pnm: str) -> None:
    subprocess.run(["convert", input_path, "-colorspace", "Gray", "-negate", "-threshold", "50%", output_pnm], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    subprocess.run(["potrace", "-s", "-o", output_svg, bnw_pnm], check=True)

def _generate_filled_svg(input_svg: str, output_filled_svg: str) -> None:
    # Ajuste de acciones para compatibilidad con Inkscape 1.2+ en Linux
    # Intentamos simplificar el proceso para que no falle si falta una acción específica
    cmd = [
        "inkscape", input_svg, 
        "--batch-process",
        "--actions=select-all;object-to-path;path-combine;export-filename:" + output_filled_svg + ";export-do"
    ]
    subprocess.run(cmd, check=True)

def image_to_stl(image_path: str, output_name: str, **kwargs) -> dict:
    wh = kwargs.get("wall_height") or WALL_HEIGHT
    wt = kwargs.get("wall_thickness") or WALL_THICKNESS
    work_dir = Path(f"/tmp/{output_name}")
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

        scad_code = f"""
$fn = 16;
module original() {{ import("{p['svg']}", center=true, dpi=96); }}
module rellena() {{ import("{p['filled']}", center=true, dpi=96); }}

// Cortante (basado en silueta)
linear_extrude(height={wh}) difference() {{
    offset(r={wt}) rellena();
    rellena();
}}
// Sello (detalles + base fina)
translate([120, 0, 0]) {{
    linear_extrude(height=2) offset(r=-0.6) rellena();
    linear_extrude(height=5) offset(r=-0.6) original();
}}
"""
        with open(p["scad"], "w") as f: f.write(scad_code)
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True)
        
        m = mesh.Mesh.from_file(p["stl"])
        volume_mm3, _, _ = m.get_mass_properties()
        
        # FIX CRÍTICO: Convertir de numpy.float32 a float estándar de Python
        dims = [
            float(m.x.max() - m.x.min()), 
            float(m.y.max() - m.y.min()), 
            float(m.z.max() - m.z.min())
        ]
        volumen_final = float(volume_mm3) / 1000.0

        shutil.copy2(p["stl"], str(STL_DIR / f"{output_name}.stl"))
        
        return {
            "exito": True,
            "volumen_cm3": round(volumen_final, 4),
            "dimensiones": [round(d, 2) for d in dims],
            "mensaje": "OK"
        }
    except Exception as e:
        return {"exito": False, "mensaje": str(e), "volumen_cm3": 0.0, "dimensiones": [0.0, 0.0, 0.0]}

def calculate_price(volumen_cm3: float) -> dict:
    # Asegurar que volumen_cm3 sea float estándar
    v = float(volumen_cm3)
    costo_mat = v * COSTO_FILAMENTO_POR_CM3
    total = (costo_mat + COSTO_BASE) * MARGEN
    return {
        "precio_final": float(round(total, 2)),
        "volumen_cm3": float(round(v, 4)),
        "moneda": CURRENCY,
        "simbolo": CURRENCY_SYMBOL
    }
