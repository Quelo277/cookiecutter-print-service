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
    """
    Valida que el archivo sea una imagen legible para PIL.
    Restaurada para evitar el ImportError en main.py.
    """
    try:
        with Image.open(file_path) as img:
            img.verify()
        return True, "OK"
    except Exception as e:
        return False, str(e)

def _binarize_image(input_path: str, output_pnm: str) -> None:
    # Pre-procesamiento con borde para evitar el rectángulo exterior
    subprocess.run([
        "convert", input_path, 
        "-bordercolor", "white", "-border", "20",
        "-colorspace", "Gray", 
        "-negate", 
        "-threshold", "40%", 
        output_pnm
    ], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    # Vectorización limpia
    subprocess.run(["potrace", "-s", "--unit", "1", "-o", output_svg, bnw_pnm], check=True)

def image_to_stl(image_path: str, output_name: str, **kwargs) -> dict:
    wh = float(kwargs.get("wall_height") or WALL_HEIGHT)
    wt = float(kwargs.get("wall_thickness") or WALL_THICKNESS)
    
    # Altura del dibujo interno (sello) al 50% de la pared de corte
    detail_height = wh * 0.5 

    work_dir = Path(f"/tmp/{output_name}")
    work_dir.mkdir(parents=True, exist_ok=True)

    p = {
        "pnm": str(work_dir / "temp.pnm"),
        "svg": str(work_dir / "orig.svg"),
        "scad": str(work_dir / "model.scad"),
        "stl": str(work_dir / "model.stl"),
    }

    try:
        _binarize_image(image_path, p["pnm"])
        _vectorize_to_svg(p["pnm"], p["svg"])

        # Lógica OpenSCAD: Pared exterior fina + Sello interno
        scad_code = f"""
$fn = 32;
module silhouette() {{
    import("{p['svg']}", center=true, dpi=96);
}}

// 1. PARED DE CORTE (Contorno fino)
color("orange")
linear_extrude(height={wh}) 
    difference() {{
        offset(r={wt/2}) silhouette();
        offset(r=-{wt/2}) silhouette();
    }}

// 2. SELLO INTERNO (Relieve)
color("darkorange")
linear_extrude(height={detail_height}) 
    silhouette();

// 3. BASE DE UNIÓN (Capa técnica de 0.8mm)
linear_extrude(height=0.8)
    offset(r=0.5) silhouette();
"""
        with open(p["scad"], "w") as f: f.write(scad_code)
        
        # Generar STL
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True)
        
        # Calcular propiedades físicas
        m = mesh.Mesh.from_file(p["stl"])
        volume_mm3, _, _ = m.get_mass_properties()
        dims = [
            float(m.x.max() - m.x.min()), 
            float(m.y.max() - m.y.min()), 
            float(m.z.max() - m.z.min())
        ]
        
        shutil.copy2(p["stl"], str(STL_DIR / f"{output_name}.stl"))
        
        return {
            "exito": True,
            "job_id": output_name,
            "volumen_cm3": round(float(volume_mm3)/1000.0, 4),
            "dimensiones": [round(d, 2) for d in dims],
            "stl_url": f"/api/download/{output_name}.stl",
            "mensaje": "OK"
        }
    except Exception as e:
        return {"exito": False, "mensaje": str(e)}

def calculate_price(volumen_cm3: float) -> dict:
    v = float(volumen_cm3)
    costo_mat = v * COSTO_FILAMENTO_POR_CM3
    total = (costo_mat + COSTO_BASE) * MARGEN
    return {
        "precio_final": float(round(total, 2)),
        "costo_materiales": float(round(costo_mat, 2)),
        "volumen_cm3": float(round(v, 4)),
        "moneda": CURRENCY,
        "simbolo": CURRENCY_SYMBOL
    }
