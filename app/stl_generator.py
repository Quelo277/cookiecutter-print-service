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

def validate_image(file_path: str) -> Tuple[bool, str]:
    """Valida que el archivo sea una imagen legible."""
    try:
        with Image.open(file_path) as img:
            img.verify()
        return True, "OK"
    except Exception as e:
        return False, str(e)

def _cleanup_vps_disk():
    """Limpia archivos de más de 30 minutos para salvar el disco del VPS."""
    now = time.time()
    for folder in [UPLOAD_DIR, PREVIEW_DIR, Path("/tmp")]:
        for f in folder.glob("*"):
            if f.is_file() and (now - f.stat().st_mtime) > 1800:
                try:
                    # Borramos temporales de Gema o todo en uploads/previews
                    if "gema_gen_" in f.name or folder != Path("/tmp"):
                        f.unlink()
                except:
                    pass

def _binarize_image(input_path: str, output_pnm: str) -> None:
    """
    ELIMINACIÓN AGRESIVA DEL RECTÁNGULO (Lógica Gema Makers):
    Forzamos personaggio negro en fondo blanco, sin el lienzo exterior.
    """
    subprocess.run([
        "convert", input_path,
        "-alpha", "remove", "-background", "white", "-flatten", # Fondo blanco si hay transparencia
        "-shave", "10x10",      # 'Afeita' 10 píxeles de todo el borde (elimina marcos de capturas)
        "-fuzz", "15%", "-trim", "+repage", # Elimina bordes vacíos/sucios
        "-bordercolor", "white", "-border", "10", # Crea un 'foso' blanco protector
        "-threshold", "50%",    # Blanco y negro puro
        "-negate",               # Invertimos para que personaje sea negro y fondo blanco (para potrace)
        output_pnm
    ], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    # --turdsize 30: Ignora manchas y ruidos pequeños (más limpio = Openscad más rápido)
    subprocess.run([
        "potrace", "-s", "--unit", "1", 
        "--turdsize", "30", 
        "--alphamax", "0.4",   # Simplifica curvas para evitar Timeouts
        "-o", output_svg, bnw_pnm
    ], check=True)

def image_to_stl(image_path: str, output_name: str, **kwargs) -> dict:
    # Limpieza automática en cada generación
    _cleanup_vps_disk()

    wh = float(kwargs.get("wall_height") or WALL_HEIGHT)
    wt = float(kwargs.get("wall_thickness") or WALL_THICKNESS)
    
    # Altura del relieve interno al 60% de la pared de corte
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

        # LÓGICA OPENSCAD: Pared exterior fina + Sello interno sólido y escalonado
        scad_code = f"""
$fn = 18; // Resolución optimizada para velocidad
module silhouette() {{
    import("{p['svg']}", center=true, dpi=96);
}}

// 1. PARED DE CORTE (Outline)
color("orange")
linear_extrude(height={wh})
    difference() {{
        offset(r={wt}) silhouette();
        silhouette();
    }}

// 2. DETALLES INTERNOS (Stamp)
// Relieve sólido completo con huecos para los detalles
color("darkorange")
linear_extrude(height={detail_height})
    silhouette();

// 3. BASE DE UNIÓN (Para que las piezas no queden sueltas)
linear_extrude(height=1.0)
    offset(r={wt + 0.8}) silhouette();
"""
        with open(p["scad"], "w") as f:
            f.write(scad_code)
        
        # Ejecutar OpenSCAD con timeout
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True, timeout=120)
        
        # Cargar malla para presupuesto y dimensiones
        m = mesh.Mesh.from_file(p["stl"])
        volume_mm3, _, _ = m.get_mass_properties()
        vol_cm3 = float(volume_mm3) / 1000.0
        
        # Bounding Box: Cálculo exacto de dimensiones
        # MINIMIZAR CAST A FLOAT: Fundamental para evitar el error de JSON
        minx, maxx = float(np.min(m.x)), float(np.max(m.x))
        miny, maxy = float(np.min(m.y)), float(np.max(m.y))
        minz, maxz = float(np.min(m.z)), float(np.max(m.z))
        
        dims = [round(maxx - minx, 2), round(maxy - miny, 2), round(maxz - minz, 2)]

        # Guardar resultado final
        final_stl = STL_DIR / f"{output_name}.stl"
        shutil.copy2(p["stl"], str(final_stl))
        
        return {
            "exito": True,
            "job_id": output_name,
            "volumen_cm3": round(vol_cm3, 4),
            "dimensiones": dims,
            "mensaje": "Generado sin bloque de fondo"
        }

    except Exception as e:
        return {"exito": False, "mensaje": str(e)}
    
    finally:
        # --- LIMPIEZA CRÍTICA DE DISCO ---
        # Borramos toda la carpeta temporal de trabajo
        if work_dir.exists():
            shutil.rmtree(work_dir)

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
