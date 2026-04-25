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
    """Limpia archivos para mantener el disco en ~20GB."""
    now = time.time()
    for folder in [UPLOAD_DIR, PREVIEW_DIR, Path("/tmp")]:
        for f in folder.glob("*"):
            try:
                # Borramos temporales de más de 15 minutos
                if f.is_file() and (now - f.stat().st_mtime) > 900:
                    if "gema_gen_" in f.name or folder != Path("/tmp"):
                        f.unlink()
            except: pass

def _binarize_image(input_path: str, output_pnm: str) -> None:
    """
    Copiamos la lógica de Papooch: 
    1. Forzar fondo blanco (quitar transparencia).
    2. Convertir a escala de grises.
    3. Aplicar umbral para que el dibujo sea NEGRO y el fondo BLANCO.
    4. NO USAR NEGATE para que potrace ignore el fondo blanco.
    """
    subprocess.run([
        "convert", input_path,
        "-alpha", "remove",       # Quita transparencia
        "-background", "white",    # Fondo blanco
        "-flatten",                # Aplana capas
        "-resize", "1024x1024>",   # Normaliza tamaño para velocidad
        "-threshold", "50%",       # Blanco y negro puro
        "-shave", "2x2",           # Limpia bordes físicos
        "-bordercolor", "white", "-border", "5", # Aire limpio
        output_pnm
    ], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    # Agregamos --black para que potrace se enfoque solo en lo oscuro
    subprocess.run([
        "potrace", "-s", 
        "--unit", "1", 
        "--turdsize", "30", 
        "--alphamax", "0.4",
        "-o", output_svg, 
        bnw_pnm
    ], check=True)

def image_to_stl(image_path: str, output_name: str, **kwargs) -> dict:
    _cleanup_vps_disk()
    wh = float(kwargs.get("wall_height") or WALL_HEIGHT)
    wt = float(kwargs.get("wall_thickness") or WALL_THICKNESS)
    detail_height = wh * 0.5 # Altura del sello interno

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

        # Lógica OpenSCAD simplificada:
        scad_code = f"""
$fn = 20;
module shape() {{
    // Importamos el SVG centrado
    import("{p['svg']}", center=true, dpi=96);
}}

// 1. PARED DE CORTE (Hacia afuera del dibujo)
linear_extrude(height={wh})
    difference() {{
        offset(r={wt}) shape();
        shape();
    }}

// 2. DIBUJO INTERNO (Sello)
linear_extrude(height={detail_height})
    shape();

// 3. BASE DE UNIÓN (Muy fina para no gastar material)
linear_extrude(height=0.8)
    offset(r={wt + 0.5}) shape();
"""
        with open(p["scad"], "w") as f:
            f.write(scad_code)
        
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True, timeout=90)
        
        m = mesh.Mesh.from_file(p["stl"])
        volume_mm3, _, _ = m.get_mass_properties()
        
        shutil.copy2(p["stl"], str(STL_DIR / f"{output_name}.stl"))
        
        return {
            "exito": True,
            "job_id": output_name,
            "volumen_cm3": round(float(volume_mm3)/1000.0, 4),
            "mensaje": "¡Logrado!"
        }
    except Exception as e:
        return {"exito": False, "mensaje": str(e)}
    finally:
        if work_dir.exists(): shutil.rmtree(work_dir)
