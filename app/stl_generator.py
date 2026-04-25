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
    cmd = [
        "inkscape", input_svg, "--batch-process",
        "--actions=select-all;path-combine;path-fill;export-filename:" + output_filled_svg + ";export-do"
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
linear_extrude(height={wh}) difference() {{
    offset(r={wt}) rellena();
    rellena();
}}
translate([120, 0, 0]) {{
    linear_extrude(height=2) offset(r=-0.6) rellena();
    linear_extrude(height=5) offset(r=-0.6) original();
}}
"""
        with open(p["scad"], "w") as f: f.write(scad_code)
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True)
        
        m = mesh.Mesh.from_file(p["stl"])
        volume_mm3, _, _ = m.get_mass_properties()
        dims = [m.x.max()-m.x.min(), m.y.max()-m.y.min(), m.z.max()-m.z.min()]
        shutil.copy2(p["stl"], str(STL_DIR / f"{output_name}.stl"))
        
        return {
            "exito": True,
            "volumen_cm3": round(volume_mm3 / 1000.0, 4),
            "dimensiones": [round(d, 2) for d in dims],
            "mensaje": "OK"
        }
    except Exception as e:
        return {"exito": False, "mensaje": str(e), "volumen_cm3": 0, "dimensiones": [0,0,0]}

def calculate_price(volumen_cm3: float) -> dict:
    costo_mat = volumen_cm3 * COSTO_FILAMENTO_POR_CM3
    total = (costo_mat + COSTO_BASE) * MARGEN
    return {
        "precio_final": round(total, 2),
        "volumen_cm3": round(volumen_cm3, 4),
        "moneda": CURRENCY,
        "simbolo": CURRENCY_SYMBOL
    }
