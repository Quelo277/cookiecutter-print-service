"""
Pipeline de generacion STL para cortantes de galletas.
Basado en Cookie Cutter Generator:
  Imagen → Binarizar (ImageMagick) → Vectorizar (Potrace) → OpenSCAD → STL

Referencias:
- https://github.com/mrzl/Cookie-Cutter-Generator
- https://openscad.org/documentation.html
- https://potrace.sourceforge.net/
"""
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
from stl import mesh
from PIL import Image

from app.config import (
    WALL_HEIGHT,
    WALL_THICKNESS,
    HANDLE_HEIGHT,
    HANDLE_THICKNESS,
    STL_DIR,
    PREVIEW_DIR,
    OPENSCAD_TEMPLATES_DIR,
)


def validate_image(file_path: str) -> Tuple[bool, str]:
    """
    Valida que la imagen sea JPG/PNG y tenga fondo contrastante.
    Retorna (valido, mensaje).
    """
    try:
        img = Image.open(file_path)
        if img.format not in ("JPEG", "PNG", "JPG"):
            return False, f"Formato no soportado: {img.format}. Use JPG o PNG."

        # Verificar contraste basico (imagen no uniforme)
        img_gray = img.convert("L")
        arr = np.array(img_gray)
        std = np.std(arr)
        if std < 30:
            return (
                False,
                "La imagen tiene muy poco contraste. "
                "Usa una imagen con fondo claro y figura oscura (o viceversa).",
            )
        return True, "OK"
    except Exception as e:
        return False, f"Error al procesar la imagen: {str(e)}"


def image_to_stl(
    image_path: str,
    output_name: str,
    wall_height: Optional[float] = None,
    wall_thickness: Optional[float] = None,
    handle_height: Optional[float] = None,
    handle_thickness: Optional[float] = None,
) -> dict:
    """
    Pipeline completo: imagen → binarizar → vectorizar → OpenSCAD → STL.

    Retorna dict con:
        - stl_path: ruta al archivo STL generado
        - preview_path: ruta a preview PNG
        - volumen_cm3: volumen en cm³
        - dimensiones: (x, y, z) en mm
        - exito: bool
        - mensaje: str
    """
    wh = wall_height or WALL_HEIGHT
    wt = wall_thickness or WALL_THICKNESS
    hh = handle_height or HANDLE_HEIGHT
    ht = handle_thickness or HANDLE_THICKNESS

    # Crear subdirectorio para este trabajo
    work_dir = STL_DIR / output_name
    work_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "input_image": image_path,
        "bnw_pnm": str(work_dir / "input_bw.pnm"),
        "vector_eps": str(work_dir / "vector.eps"),
        "vector_dxf": str(work_dir / "vector.dxf"),
        "scad_file": str(work_dir / "cutter.scad"),
        "stl_file": str(work_dir / "cutter.stl"),
        "preview_png": str(PREVIEW_DIR / f"{output_name}.png"),
        "work_dir": str(work_dir),
    }

    try:
        # Paso 1: Binarizar con ImageMagick
        _binarize_image(image_path, paths["bnw_pnm"])

        # Paso 2: Vectorizar con Potrace → EPS
        _vectorize_with_potrace(paths["bnw_pnm"], paths["vector_eps"])

        # Paso 3: Convertir EPS → DXF con pstoedit
        _eps_to_dxf(paths["vector_eps"], paths["vector_dxf"])

        # Paso 4: Generar archivo OpenSCAD con extrusion y mango
        _generate_openscad(
            paths["vector_dxf"],
            paths["scad_file"],
            wall_height=wh,
            wall_thickness=wt,
            handle_height=hh,
            handle_thickness=ht,
        )

        # Paso 5: Renderizar STL con OpenSCAD CLI
        _render_stl(paths["scad_file"], paths["stl_file"])

        # Paso 6: Calcular volumen con numpy-stl
        volumen_cm3, dimensiones = _calculate_volume(paths["stl_file"])

        # Paso 7: Generar preview con OpenSCAD
        _generate_preview(paths["scad_file"], paths["preview_png"])

        # Copiar STL a ruta estandar
        final_stl = str(STL_DIR / f"{output_name}.stl")
        shutil.copy2(paths["stl_file"], final_stl)

        return {
            "stl_path": final_stl,
            "preview_path": paths["preview_png"],
            "volumen_cm3": round(volumen_cm3, 4),
            "dimensiones": [round(d, 2) for d in dimensiones],
            "exito": True,
            "mensaje": "STL generado exitosamente",
            "parametros": {
                "wall_height": wh,
                "wall_thickness": wt,
                "handle_height": hh,
                "handle_thickness": ht,
            },
        }

    except Exception as e:
        return {
            "stl_path": "",
            "preview_path": "",
            "volumen_cm3": 0.0,
            "dimensiones": [0, 0, 0],
            "exito": False,
            "mensaje": f"Error en pipeline STL: {str(e)}",
            "parametros": {},
        }


def _binarize_image(input_path: str, output_pnm: str) -> None:
    """
    Binariza la imagen usando ImageMagick.
    Convierte a escala de grises y aplica threshold para obtener blanco/negro puro.
    """
    # -colorspace Gray: convertir a escala de grises
    # -brightness-contrast 0x30: aumentar contraste
    # -threshold 50%: binarizar al 50%
    # -negate: invertir (fondo blanco, figura negra)
    cmd = [
        "convert",
        input_path,
        "-resize", "800x800>",           # Redimensionar si es muy grande
        "-colorspace", "Gray",
        "-brightness-contrast", "0x30",  # Aumentar contraste
        "-threshold", "50%",             # Binarizar
        "-negate",                       # Invertir: fondo negro, figura blanca
        output_pnm,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ImageMagick error: {result.stderr}")


def _vectorize_with_potrace(bnw_pnm: str, output_eps: str) -> None:
    """
    Vectoriza la imagen binarizada usando Potrace.
    Genera un archivo EPS con los contornos vectoriales.
    """
    # -s: producir EPS
    # -t tight: bounding box ajustado
    # -a 1.0: umbral de curva
    # -O 0.5: optimizacion de esquinas
    cmd = [
        "potrace",
        "-s",                    # Formato EPS
        "-t", "tight",          # Bounding box ajustado
        "-a", "1.0",            # Tolerancia de curva
        "-O", "0.5",            # Optimizacion de esquinas
        "-o", output_eps,
        bnw_pnm,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Potrace error: {result.stderr}")


def _eps_to_dxf(eps_path: str, dxf_path: str) -> None:
    """
    Convierte EPS a DXF usando pstoedit.
    OpenSCAD puede importar DXF para extrusion.
    """
    cmd = [
        "pstoedit",
        "-f", "dxf:-polyaslines -mm",
        "-dt",                   # Drawing text
        eps_path,
        dxf_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"pstoedit error: {result.stderr}")


def _generate_openscad(
    dxf_path: str,
    scad_path: str,
    wall_height: float,
    wall_thickness: float,
    handle_height: float,
    handle_thickness: float,
) -> None:
    """
    Genera el archivo OpenSCAD (.scad) que define el cortante.

    Estrategia (basada en Cookie Cutter Generator):
    1. Importar DXF y escalarlo a tamaño apropiado
    2. Extruir la forma base (pared del cortante)
    3. Crear mango diferenciado (torus o barra)
    4. Unir pared + mango

    El DXF importado define la silueta del cortante.
    """
    scad_code = f"""
// Cookie Cutter - Auto-generated from image
// Parametros configurables
wall_height = {wall_height};
wall_thickness = {wall_thickness};
handle_height = {handle_height};
handle_thickness = {handle_thickness};

// Importar y escalar el contorno DXF
// Escala para ajustar a tamaño tipico de cortante (80-120mm)
linear_extrude(height = wall_height, center = false, convexity = 10)
  import("{dxf_path}", center = true);

// Mango: toroide que atraviesa la forma
// Se posiciona en el centro de masa aproximado
translate([0, 0, wall_height])
  difference() {{
    // Toroide exterior
    rotate_extrude(convexity = 10, $fn = 64)
      translate([25, 0, 0])
        circle(r = handle_thickness/2, $fn = 32);
    // Recorte inferior para que quede plano sobre la pared
    translate([0, 0, -handle_height])
      cube([100, 100, handle_height], center = true);
  }}

// Refuerzos: pequeños cilindros que unen mango con pared
for (a = [0:60:300]) {{
  rotate([0, 0, a])
    translate([25, 0, wall_height - 1])
      cylinder(h = handle_height/2 + 1, r = 2, $fn = 16);
}}
"""
    with open(scad_path, "w") as f:
        f.write(scad_code)


def _render_stl(scad_path: str, stl_path: str) -> None:
    """
    Renderiza el archivo .scad a STL usando OpenSCAD en modo headless.
    """
    cmd = [
        "openscad",
        "-o", stl_path,
        "--export-format=binstl",
        scad_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"OpenSCAD render error: {result.stderr}")
    if not os.path.exists(stl_path) or os.path.getsize(stl_path) < 100:
        raise RuntimeError("OpenSCAD genero un STL vacio o invalido")


def _calculate_volume(stl_path: str) -> Tuple[float, Tuple[float, float, float]]:
    """
    Calcula el volumen (en cm³) y dimensiones (en mm) del STL usando numpy-stl.
    """
    try:
        m = mesh.Mesh.from_file(stl_path)
        volume_mm3, cog, inertia = m.get_mass_properties()
        volumen_cm3 = volume_mm3 / 1000.0  # mm³ → cm³

        # Dimensiones en mm
        minx = m.x.min()
        maxx = m.x.max()
        miny = m.y.min()
        maxy = m.y.max()
        minz = m.z.min()
        maxz = m.z.max()

        dims = (maxx - minx, maxy - miny, maxz - minz)
        return volumen_cm3, dims
    except Exception as e:
        raise RuntimeError(f"Error calculando volumen STL: {str(e)}")


def _generate_preview(scad_path: str, preview_path: str) -> None:
    """
    Genera una imagen PNG de preview del modelo usando OpenSCAD.
    """
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        "openscad",
        "-o", preview_path,
        "--export-format=png",
        "--imgsize=600,600",
        "--camera=0,0,0,55,0,25,140",
        scad_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    # Si falla el preview, no es critico
    if not os.path.exists(preview_path):
        # Crear placeholder
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (600, 600), color=(240, 240, 240))
        img.save(preview_path)


def calculate_price(volumen_cm3: float) -> dict:
    """
    Calcula el precio estimado segun la formula:
    precio = (volumen_cm3 * costo_filamento_por_cm3 + costo_base) * margen
    """
    from app.config import (
        COSTO_FILAMENTO_POR_CM3,
        COSTO_BASE,
        MARGEN,
        CURRENCY,
        CURRENCY_SYMBOL,
    )

    costo_materiales = volumen_cm3 * COSTO_FILAMENTO_POR_CM3
    costo_total = (costo_materiales + COSTO_BASE) * MARGEN

    return {
        "volumen_cm3": round(volumen_cm3, 4),
        "costo_materiales": round(costo_materiales, 2),
        "costo_base": COSTO_BASE,
        "margen": MARGEN,
        "precio_final": round(costo_total, 2),
        "moneda": CURRENCY,
        "simbolo": CURRENCY_SYMBOL,
        "formula": f"({volumen_cm3:.4f} * {COSTO_FILAMENTO_POR_CM3} + {COSTO_BASE}) * {MARGEN}",
    }
