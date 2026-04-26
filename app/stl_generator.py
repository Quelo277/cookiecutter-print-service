import os
import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional, Tuple
from stl import mesh
from PIL import Image
import numpy as np

from app.config import (
    WALL_HEIGHT, WALL_THICKNESS, STL_DIR, UPLOAD_DIR, PREVIEW_DIR,
    COSTO_FILAMENTO_POR_CM3, COSTO_BASE, MARGEN, CURRENCY, CURRENCY_SYMBOL
)

def _cleanup_vps_disk():
    """Mantiene el VPS de Gema Makers con espacio suficiente."""
    now = time.time()
    for folder in [UPLOAD_DIR, PREVIEW_DIR, Path("/tmp")]:
        for f in folder.glob("*"):
            try:
                if f.is_file() and (now - f.stat().st_mtime) > 900:
                    if "gema_gen_" in f.name or folder != Path("/tmp"):
                        f.unlink()
            except: pass

def _binarize_image(input_path: str, output_pnm: str) -> None:
    """
    PROCESADO EQUILIBRADO:
    Mantiene las líneas pero asegura fondo blanco para evitar el monobloque.
    """
    subprocess.run([
        "convert", input_path,
        "-alpha", "remove", "-background", "white", "-flatten",
        "-fuzz", "10%", "-trim", "+repage",      # Limpieza de bordes vacíos
        "-colorspace", "gray",
        "-level", "25%,75%,1.0",                 # Aumenta el contraste de las líneas
        "-threshold", "60%",                     # Menos agresivo que 85%
        "-bordercolor", "white", "-border", "10", # Espacio de seguridad para Potrace
        output_pnm
    ], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    """Convierte a vector optimizado para OpenSCAD."""
    subprocess.run([
        "potrace", "-s", "--unit", "1", 
        "--turdsize", "20",       # Ignora motas de polvo pequeñas
        "--alphamax", "0.6",      # Curvas más suaves
        "-o", output_svg, bnw_pnm
    ], check=True)

def image_to_stl(image_path: str, output_name: str, **kwargs) -> dict:
    _cleanup_vps_disk()
    wh = float(kwargs.get("wall_height") or WALL_HEIGHT)
    wt = float(kwargs.get("wall_thickness") or WALL_THICKNESS)
    detail_height = wh * 0.6 

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

        # LÓGICA SCAD REFORZADA: Evita el monobloque y el objeto vacío
        scad_code = f"""
$fn = 20; 
module silhouette() {{
    // El offset r=0.01 asegura que OpenSCAD detecte la geometría
    offset(r=0.01) import("{p['svg']}", center=true, dpi=96);
}}

// 1. PARED DE CORTE (Exterior)
color("orange")
linear_extrude(height={wh})
    difference() {{
        offset(r={wt}) silhouette();
        silhouette();
    }}

// 2. STAMP / DETALLES INTERNOS (Sólido interno)
color("darkorange")
linear_extrude(height={detail_height})
    silhouette();

// 3. BASE DE UNIÓN (Soporte fino de 1mm)
linear_extrude(height=1.0)
    offset(r={wt}) silhouette();
"""
        with open(p["scad"], "w") as f:
            f.write(scad_code)
        
        # Ejecución con captura de errores
        res = subprocess.run(["openscad", "-o", p["stl"], p["scad"]], 
                             capture_output=True, text=True, timeout=120)
        
        if res.returncode != 0:
            return {"exito": False, "mensaje": f"OpenSCAD Error: {res.stderr}"}

        m = mesh.Mesh.from_file(p["stl"])
        volume_mm3, _, _ = m.get_mass_properties()
        
        minx, maxx = float(np.min(m.x)), float(np.max(m.x))
        miny, maxy = float(np.min(m.y)), float(np.max(m.y))
        minz, maxz = float(np.min(m.z)), float(np.max(m.z))
        dims = [round(maxx - minx, 2), round(maxy - miny, 2), round(maxz - minz, 2)]

        shutil.copy2(p["stl"], str(STL_DIR / f"{output_name}.stl"))
        
        return {
            "exito": True,
            "job_id": output_name,
            "volumen_cm3": round(float(volume_mm3)/1000.0, 4),
            "dimensiones": dims,
            "mensaje": "Generado correctamente"
        }

    except Exception as e:
        return {"exito": False, "mensaje": str(e)}
    finally:
        if work_dir.exists(): shutil.rmtree(work_dir)
def validate_image(image_path: str) -> Tuple[bool, str]:
    """Valida que el archivo sea una imagen real y no supere el tamaño."""
    try:
        # Verificar que el archivo existe
        path = Path(image_path)
        if not path.exists():
            return False, "El archivo no fue guardado correctamente."

        # Validar tamaño (puedes usar MAX_IMAGE_SIZE_BYTES de config)
        if path.stat().st_size > (5 * 1024 * 1024): # 5MB de backup si no toma la config
            return False, "La imagen es demasiado pesada (máx 5MB)."

        # Validar que PIL pueda abrirla
        with Image.open(image_path) as img:
            img.verify()
        return True, "Imagen válida"
    except Exception as e:
        return False, f"Archivo de imagen corrupto o no soportado: {str(e)}"

def calculate_price(volumen_cm3: float) -> float:
    """Calcula el precio final basado en los costos de Gema Makers."""
    # (Volumen * costo filamento + costo base operacional) * margen de ganancia
    precio = (volumen_cm3 * COSTO_FILAMENTO_POR_CM3 + COSTO_BASE) * MARGEN
    return round(precio, 2)
