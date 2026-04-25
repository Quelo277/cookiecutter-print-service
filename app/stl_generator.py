import os
import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional, Tuple
from stl import mesh
from PIL import Image

from app.config import (
    WALL_HEIGHT, WALL_THICKNESS, STL_DIR, UPLOAD_DIR, PREVIEW_DIR,
    COSTO_FILAMENTO_POR_CM3, COSTO_BASE, MARGEN, CURRENCY, CURRENCY_SYMBOL
)

def validate_image(file_path: str) -> Tuple[bool, str]:
    """Valida que el archivo sea una imagen legible."""
    try:
        with Image.open(file_path) as img:
            img.verify()
        return True, "OK"
    except Exception as e:
        return False, str(e)

def _cleanup_vps_disk():
    """Mantiene el disco limpio para evitar los 70GB de basura."""
    now = time.time()
    for folder in [UPLOAD_DIR, PREVIEW_DIR, Path("/tmp")]:
        for f in folder.glob("*"):
            try:
                # Borramos temporales de más de 10 minutos
                if f.is_file() and (now - f.stat().st_mtime) > 600:
                    if "gema_gen_" in f.name or folder != Path("/tmp"):
                        f.unlink()
            except: pass

def _binarize_image(input_path: str, output_pnm: str) -> None:
    """Procesamiento para eliminar el rectángulo y limpiar bordes."""
    subprocess.run([
        "convert", input_path,
        "-alpha", "remove", "-background", "white", "-flatten",
        "-fuzz", "15%", "-trim", "+repage",
        "-shave", "2x2",
        "-bordercolor", "white", "-border", "20",
        "-colorspace", "gray",
        "-threshold", "85%",
        output_pnm
    ], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    """Genera el vector limpio para OpenSCAD."""
    subprocess.run([
        "potrace", "-s", 
        "--unit", "1", 
        "--turdsize", "50", 
        "--alphamax", "0.5",
        "-o", output_svg, 
        bnw_pnm
    ], check=True)

def image_to_stl(image_path: str, output_name: str, **kwargs) -> dict:
    _cleanup_vps_disk()
    wh = float(kwargs.get("wall_height") or WALL_HEIGHT)
    wt = float(kwargs.get("wall_thickness") or WALL_THICKNESS)
    detail_h = wh * 0.5 

    work_dir = Path(f"/tmp/gema_gen_{output_name}")
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

        scad_code = f"""
$fn = 20;
module silhouette() {{
    import("{p['svg']}", center=true, dpi=96);
}}

// 1. PARED DE CORTE
linear_extrude(height={wh})
    difference() {{
        offset(r={wt}) silhouette();
        silhouette();
    }}

// 2. DETALLES INTERNOS
linear_extrude(height={detail_h})
    difference() {{
        offset(r=0.4) silhouette();
        offset(r=-0.4) silhouette();
    }}

// 3. SOPORTE DE UNIÓN
linear_extrude(height=1.0)
    offset(r={wt + 0.8}) silhouette();
"""
        with open(p["scad"], "w") as f:
            f.write(scad_code)
        
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True, timeout=120)
        
        m = mesh.Mesh.from_file(p["stl"])
        volume_mm3, _, _ = m.get_mass_properties()
        shutil.copy2(p["stl"], str(STL_DIR / f"{output_name}.stl"))
        
        return {
            "exito": True,
            "job_id": output_name,
            "volumen_cm3": round(float(volume_mm3)/1000.0, 4),
            "mensaje": "¡Sistema restaurado y mejorado!"
        }
    except Exception as e:
        return {"exito": False, "mensaje": str(e)}
    finally:
        if work_dir.exists(): shutil.rmtree(work_dir)

def calculate_price(volumen_cm3: float) -> dict:
    """Calcula el precio según los costos de Gema Makers."""
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
