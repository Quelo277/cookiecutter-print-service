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
    # 1. Agregamos un borde blanco generoso para despegar la imagen de los bordes del lienzo.
    # 2. Limpiamos el ruido para que la silueta sea clara.
    subprocess.run([
        "convert", input_path, 
        "-bordercolor", "white", "-border", "50",
        "-trim", "+repage", # Elimina bordes basura de la imagen original
        "-border", "20",     # Agrega espacio de seguridad real
        "-colorspace", "Gray", 
        "-negate", 
        "-threshold", "50%", 
        output_pnm
    ], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    # Usamos -a 0 para que no suavice demasiado y pierda detalles internos
    subprocess.run(["potrace", "-s", "--unit", "1", "-a", "0", "-o", output_svg, bnw_pnm], check=True)

def image_to_stl(image_path: str, output_name: str, **kwargs) -> dict:
    wh = float(kwargs.get("wall_height") or WALL_HEIGHT)
    wt = float(kwargs.get("wall_thickness") or WALL_THICKNESS)
    detail_height = wh * 0.6 

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

        # LÓGICA OPENSCAD: 
        # Construimos el cortante DESDE la silueta, no restando el lienzo.
        scad_code = f"""
$fn = 32;
module original_path() {{
    // Importamos con un pequeño escalado si es necesario
    import("{p['svg']}", center=true, dpi=96);
}}

// 1. PARED DE CORTE (Contorno exterior)
// Hacemos un "minkowski" o un offset simple para crear el grosor hacia afuera
color("orange")
linear_extrude(height={wh})
    difference() {{
        offset(r={wt}) original_path();
        original_path();
    }}

// 2. SELLO INTERNO (El dibujo completo)
// Lo extruimos a menor altura para marcar la masa sin cortarla
color("darkorange")
linear_extrude(height={detail_height})
    original_path();

// 3. SOPORTE DE UNIÓN (Base fina para que no se separen las piezas)
linear_extrude(height=1.2)
    offset(r={wt * 0.5}) original_path();
"""
        with open(p["scad"], "w") as f: f.write(scad_code)
        
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True)
        
        m = mesh.Mesh.from_file(p["stl"])
        volume_mm3, _, _ = m.get_mass_properties()
        dims = [float(m.x.max() - m.x.min()), float(m.y.max() - m.y.min()), float(m.z.max() - m.z.min())]
        
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
