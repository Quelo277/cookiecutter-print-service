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

def _cleanup_old_files(directory: Path, max_age_seconds: int = 3600):
    """Borra archivos más viejos de 1 hora para salvar el disco del VPS."""
    now = time.time()
    for f in directory.iterdir():
        if f.is_file() and (now - f.stat().st_mtime) > max_age_seconds:
            try:
                f.unlink()
            except:
                pass

def _binarize_image(input_path: str, output_pnm: str) -> None:
    # 1. Forzamos fondo blanco y eliminamos cualquier rastro de transparencia.
    # 2. -fuzz 10% -trim elimina bordes que no sean 100% blancos.
    # 3. -shave elimina el perímetro físico por si hay una línea de 1px.
    subprocess.run([
        "convert", input_path,
        "-background", "white", "-flatten",
        "-fuzz", "10%", "-trim", "+repage",
        "-shave", "5x5", 
        "-bordercolor", "white", "-border", "10",
        "-threshold", "50%",
        "-negate", 
        output_pnm
    ], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    # --turdsize 20: ignora manchas pequeñas (menos ruido = OpenSCAD más rápido)
    # --alphamax 0.5: simplifica curvas para evitar el Timeout
    subprocess.run([
        "potrace", "-s", "--unit", "1", 
        "--turdsize", "20", 
        "--alphamax", "0.5", 
        "-o", output_svg, bnw_pnm
    ], check=True)

def image_to_stl(image_path: str, output_name: str, **kwargs) -> dict:
    # Limpieza preventiva de disco en cada uso
    _cleanup_old_files(UPLOAD_DIR)
    _cleanup_old_files(PREVIEW_DIR)
    _cleanup_old_files(Path("/tmp"), 1800)

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

        # Optimizamos el SCAD para que no tarde tanto
        scad_code = f"""
$fn = 20; // Reducimos resolución para evitar Timeouts
module silhouette() {{
    import("{p['svg']}", center=true, dpi=96);
}}

// 1. CORTANTE EXTERIOR
linear_extrude(height={wh})
    difference() {{
        offset(r={wt + 0.5}) silhouette();
        offset(r=0.5) silhouette();
    }}

// 2. DETALLE INTERNO
linear_extrude(height={detail_height})
    offset(r=0.5) silhouette();

// 3. SOPORTE DE UNIÓN
linear_extrude(height=1.0)
    offset(r={wt + 0.8}) silhouette();
"""
        with open(p["scad"], "w") as f:
            f.write(scad_code)
        
        # Aumentamos el timeout a 120s por las dudas, pero con $fn=20 debería volar.
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True, timeout=120)
        
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
            "mensaje": "OK"
        }

    except subprocess.TimeoutExpired:
        return {"exito": False, "mensaje": "La imagen es muy compleja y superó el tiempo de espera."}
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
