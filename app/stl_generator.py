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

def _cleanup_vps_disk():
    """Mantiene el disco limpio para Gema Makers."""
    now = time.time()
    for folder in [UPLOAD_DIR, PREVIEW_DIR, Path("/tmp")]:
        for f in folder.glob("*"):
            try:
                if f.is_file() and (now - f.stat().st_mtime) > 600:
                    if "gema_gen_" in f.name or folder != Path("/tmp"):
                        f.unlink()
            except: pass

def _binarize_image(input_path: str, output_pnm: str) -> None:
    """
    PRE-PROCESAMIENTO AGRESIVO:
    Forzamos que el dibujo sea NEGRO y el fondo sea BLANCO PURO.
    El secreto de Papooch es un threshold alto y un margen de seguridad.
    """
    subprocess.run([
        "convert", input_path,
        "-alpha", "remove", "-background", "white", "-flatten", # Fondo blanco
        "-fuzz", "15%", "-trim", "+repage", # Elimina bordes vacíos/sucios
        "-shave", "2x2", # Afeita 2px de todo el borde por si hay líneas
        "-bordercolor", "white", "-border", "20", # Crea un 'foso' blanco protector
        "-colorspace", "gray",
        "-threshold", "85%", # Papooch usa un valor alto para asegurar limpieza
        output_pnm
    ], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    """
    Vectorización limpia. 
    --turdsize 50 elimina ruidos (puntos sueltos).
    """
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
    detail_h = wh * 0.6 

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

        # LÓGICA OPENSCAD PARA CORTANTE TIPO GEMA MAKERS
        scad_code = f"""
$fn = 20;
module silhouette() {{
    import("{p['svg']}", center=true, dpi=96);
}}

// 1. PARED DE CORTE (Outline)
linear_extrude(height={wh})
    difference() {{
        offset(r={wt}) silhouette();
        silhouette();
    }}

// 2. DETALLES INTERNOS (Stamp)
// En lugar de un bloque sólido, extruimos solo los bordes del dibujo interno
linear_extrude(height={detail_h})
    difference() {{
        offset(r=0.4) silhouette();
        offset(r=-0.4) silhouette();
    }}

// 3. SOPORTE DE UNIÓN (Base que sigue la forma del personaje)
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
            "mensaje": "Generado sin bloque de fondo"
        }
    except Exception as e:
        return {"exito": False, "mensaje": str(e)}
    finally:
        if work_dir.exists(): shutil.rmtree(work_dir)
