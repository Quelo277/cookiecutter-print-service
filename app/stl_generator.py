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
    # 1. Quitamos transparencia, aplanamos a blanco.
    # 2. Shave 2x2 para quitar posibles bordes de 1px que detecta potrace.
    # 3. Trim para ajustar a la figura y Border para darle aire limpio.
    subprocess.run([
        "convert", input_path,
        "-background", "white", "-flatten",
        "-shave", "2x2",
        "-trim", "+repage",
        "-bordercolor", "white", "-border", "10",
        "-threshold", "50%",
        "-negate", 
        output_pnm
    ], check=True)

def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    # --turdsize 10 elimina ruidos pequeños
    subprocess.run(["potrace", "-s", "--unit", "1", "--turdsize", "10", "-o", output_svg, bnw_pnm], check=True)

def image_to_stl(image_path: str, output_name: str, **kwargs) -> dict:
    wh = float(kwargs.get("wall_height") or WALL_HEIGHT)
    wt = float(kwargs.get("wall_thickness") or WALL_THICKNESS)
    detail_height = wh * 0.6  # El interior es un 40% más bajo que el borde

    # Usamos una subcarpeta única para limpiar fácil
    work_dir = Path(f"/tmp/gema_tmp_{output_name}")
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

        # OpenSCAD: La pared de corte nace del borde del dibujo hacia AFUERA (offset wt)
        scad_code = f"""
$fn = 32;
module silhouette() {{
    import("{p['svg']}", center=true, dpi=96);
}}

// 1. PARED DE CORTE (Altura total: {wh}mm)
color("orange")
linear_extrude(height={wh})
    difference() {{
        offset(r={wt + 0.5}) silhouette(); // Tolerancia de 0.5mm extra
        silhouette();
    }}

// 2. SELLO INTERNO (Altura menor: {detail_height}mm)
color("darkorange")
linear_extrude(height={detail_height})
    silhouette();

// 3. BASE SOPORTE (Opcional, muy fina para unir todo)
linear_extrude(height=0.8)
    offset(r={wt}) silhouette();
"""
        with open(p["scad"], "w") as f:
            f.write(scad_code)
        
        # Generar el STL
        subprocess.run(["openscad", "-o", p["stl"], p["scad"]], check=True, timeout=60)
        
        # Procesar para el presupuesto
        m = mesh.Mesh.from_file(p["stl"])
        volume_mm3, _, _ = m.get_mass_properties()
        vol_cm3 = float(volume_mm3) / 1000.0
        dims = [float(m.x.max() - m.x.min()), float(m.y.max() - m.y.min()), float(m.z.max() - m.z.min())]

        # Guardamos el STL final
        shutil.copy2(p["stl"], str(STL_DIR / f"{output_name}.stl"))
        
        return {
            "exito": True,
            "job_id": output_name,
            "volumen_cm3": round(vol_cm3, 4),
            "dimensiones": [round(d, 2) for d in dims],
            "stl_url": f"/api/download/{output_name}.stl",
            "mensaje": "Modelo generado"
        }

    except Exception as e:
        return {"exito": False, "mensaje": f"Error: {str(e)}"}
    
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
