import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple
from stl import mesh
from PIL import Image

from app.config import (
    WALL_HEIGHT, WALL_THICKNESS, STL_DIR, 
    COSTO_FILAMENTO_POR_CM3, COSTO_BASE, MARGEN, CURRENCY, CURRENCY_SYMBOL
)

def validate_image(file_path: str) -> Tuple[bool, str]:
    try:
        with Image.open(file_path) as img:
            img.verify()
        return True, "OK"
    except Exception as e:
        return False, str(e)

def _binarize_image(input_path: str, output_pnm: str) -> None:
    # Agregamos un borde blanco y usamos -trim para asegurar que no haya bordes negros
    # que potrace interprete como un rectángulo exterior.
    subprocess.run([
        "convert", input_path,
        "-alpha", "remove", 
        "-bordercolor", "white", "-border", "10",
        "-trim", "+repage",
        "-threshold", "50%",
        "-negate", # Invertimos para que potrace detecte la figura
        output_pnm
    ], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    # potrace genera el SVG de la silueta negra
    subprocess.run(["potrace", "-s", "--unit", "1", "-o", output_svg, bnw_pnm], check=True)

def image_to_stl(image_path: str, output_name: str, **kwargs) -> dict:
    wh = float(kwargs.get("wall_height") or WALL_HEIGHT)
    wt = float(kwargs.get("wall_thickness") or WALL_THICKNESS)
    
    # Altura del dibujo interno al 60% de la pared de corte
    detail_height = wh * 0.6 

    work_dir = Path(f"/tmp/gema_{output_name}")
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

        # Lógica OpenSCAD:
        # offset(r=0.5) sobre la silueta para la tolerancia que pediste.
        scad_code = f"""
$fn = 32;
module silhouette() {{
    import("{p['svg']}", center=true, dpi=96);
}}

// 1. PARED DE CORTE (Solo el contorno con tolerancia de 0.5mm)
color("orange")
linear_extrude(height={wh})
    difference() {{
        offset(r={wt + 0.5}) silhouette();
        offset(r=0.5) silhouette();
    }}

// 2. DETALLE INTERNO (Más bajo que el contorno)
color("darkorange")
linear_extrude(height={detail_height})
    offset(r=0.5) silhouette();

// 3. BASE DE UNIÓN (Para que las piezas internas no queden sueltas)
linear_extrude(height=1.0)
    offset(r={wt + 1}) silhouette();
"""
        with open(p["scad"], "w") as f:
            f.write(scad_code)
        
        # Ejecutar OpenSCAD
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True)
        
        # Medir volumen y dimensiones
        m = mesh.Mesh.from_file(p["stl"])
        volume_mm3, _, _ = m.get_mass_properties()
        volumen_cm3 = float(volume_mm3) / 1000.0
        
        dims = [
            float(m.x.max() - m.x.min()), 
            float(m.y.max() - m.y.min()), 
            float(m.z.max() - m.z.min())
        ]

        # Guardar resultado final
        final_stl = STL_DIR / f"{output_name}.stl"
        shutil.copy2(p["stl"], str(final_stl))
        
        # --- LIMPIEZA DE DISCO ---
        # Borramos la carpeta temporal de esta operación
        shutil.rmtree(work_dir)
        
        return {
            "exito": True,
            "job_id": output_name,
            "volumen_cm3": round(volumen_cm3, 4),
            "dimensiones": [round(d, 2) for d in dims],
            "stl_url": f"/api/download/{output_name}.stl",
            "mensaje": "Generado con éxito"
        }
    except Exception as e:
        if work_dir.exists():
            shutil.rmtree(work_dir)
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
