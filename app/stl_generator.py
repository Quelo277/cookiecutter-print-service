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
    try:
        with Image.open(file_path) as img:
            img.verify()
        return True, "OK"
    except Exception as e:
        return False, str(e)

def _cleanup_vps_disk():
    """Limpia archivos de más de 30 minutos para evitar que el VPS se llene."""
    now = time.time()
    for folder in [UPLOAD_DIR, PREVIEW_DIR, Path("/tmp")]:
        for f in folder.glob("*"):
            if f.is_file() and (now - f.stat().st_mtime) > 1800:
                try:
                    # No borrar archivos esenciales del sistema en /tmp
                    if "gema_gen_" in f.name or folder != Path("/tmp"):
                        f.unlink()
                except:
                    pass

def _binarize_image(input_path: str, output_pnm: str) -> None:
    # ELIMINACIÓN AGRESIVA DEL RECTÁNGULO:
    # 1. -shave 10x10: Corta 10 píxeles de todo el borde (elimina marcos de capturas)
    # 2. -fuzz 15% -trim: Elimina bordes blancos no perfectos
    # 3. -border 10: Agrega un margen blanco limpio para que potrace no toque los bordes
    subprocess.run([
        "convert", input_path,
        "-background", "white", "-flatten",
        "-shave", "10x10",
        "-fuzz", "15%", "-trim", "+repage",
        "-bordercolor", "white", "-border", "10",
        "-threshold", "50%",
        "-negate", 
        output_pnm
    ], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    # --turdsize 50: Ignora motas de polvo y ruidos pequeños que ralentizan OpenSCAD
    subprocess.run([
        "potrace", "-s", "--unit", "1", 
        "--turdsize", "50", 
        "--alphamax", "0.3", # Simplifica curvas para evitar Timeouts
        "-o", output_svg, bnw_pnm
    ], check=True)

def image_to_stl(image_path: str, output_name: str, **kwargs) -> dict:
    # Limpieza automática en cada generación
    _cleanup_vps_disk()

    wh = float(kwargs.get("wall_height") or WALL_HEIGHT)
    wt = float(kwargs.get("wall_thickness") or WALL_THICKNESS)
    detail_height = wh * 0.55 # Un poco más bajo para que se note la diferencia

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

        # El truco en OpenSCAD: La pared nace de la silueta hacia afuera.
        scad_code = f"""
$fn = 18; // Resolución optimizada para velocidad
module silhouette() {{
    import("{p['svg']}", center=true, dpi=96);
}}

// 1. PARED DE CORTE (Silueta + offset de 0.5mm de tolerancia)
color("orange")
linear_extrude(height={wh})
    difference() {{
        offset(r={wt + 0.5}) silhouette();
        offset(r=0.5) silhouette();
    }}

// 2. SELLO INTERNO (El dibujo)
color("darkorange")
linear_extrude(height={detail_height})
    offset(r=0.4) silhouette();

// 3. BASE DE UNIÓN
linear_extrude(height=0.8)
    offset(r={wt + 1.0}) silhouette();
"""
        with open(p["scad"], "w") as f:
            f.write(scad_code)
        
        # Ejecución con tiempo límite
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True, timeout=90)
        
        m = mesh.Mesh.from_file(p["stl"])
        volume_mm3, _, _ = m.get_mass_properties()
        vol_cm3 = float(volume_mm3) / 1000.0
        dims = [float(m.x.max() - m.x.min()), float(m.y.max() - m.y.min()), float(m.z.max() - m.z.min())]

        shutil.copy2(p["stl"], str(STL_DIR / f"{output_name}.stl"))
        
        return {
            "exito": True,
            "job_id": output_name,
            "volumen_cm3": round(vol_cm3, 4),
            "dimensiones": [round(d, 2) for d in dims],
            "stl_url": f"/api/download/{output_name}.stl",
            "mensaje": "Generado correctamente"
        }

    except Exception as e:
        return {"exito": False, "mensaje": str(e)}
    finally:
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
