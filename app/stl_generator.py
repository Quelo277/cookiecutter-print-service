"""
Pipeline de generacion STL para cortantes de galletas.
v4 - DOS PIEZAS SEPARADAS:
  - Pieza 1: CUTTER  → solo la pared perimetral (silueta) que corta la masa
  - Pieza 2: STAMP   → base sólida con relieve, calza dentro del cutter con tolerancia
"""
import os
import subprocess
import shutil
import tempfile
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
)

# Tolerancia entre stamp y cutter (mm) para que calce sin forzar
FIT_TOLERANCE = 0.3


def validate_image(file_path: str) -> Tuple[bool, str]:
    try:
        img = Image.open(file_path)
        if img.format not in ("JPEG", "PNG", "JPG"):
            return False, f"Formato no soportado: {img.format}. Use JPG o PNG."
        img_gray = img.convert("L")
        arr = np.array(img_gray)
        if np.std(arr) < 30:
            return (
                False,
                "La imagen tiene muy poco contraste. "
                "Usa una imagen con fondo claro y figura oscura (o viceversa).",
            )
        return True, "OK"
    except Exception as e:
        return False, f"Error al procesar la imagen: {str(e)}"


def _binarize_image(input_path: str, output_pnm: str) -> None:
    """
    Binariza la imagen para Potrace.
    CORREGIDO: SIN -negate. Potrace traza pixels NEGROS.
    Con -negate el fondo quedaba negro y Potrace trazaba el fondo
    (rectángulo gigante) en lugar de la figura.
    La imagen debe tener figura oscura sobre fondo claro (validado antes).
    """
    cmd = [
        "convert",
        input_path,
        "-alpha", "remove",
        "-background", "white",
        "-flatten",
        "-fuzz", "10%",
        "-trim", "+repage",
        "-resize", "800x800>",
        "-colorspace", "Gray",
        "-brightness-contrast", "0x40",
        "-threshold", "50%",
        # SIN -negate: figura queda negra (trazada por Potrace), fondo blanco (ignorado)
        "-bordercolor", "white",   # borde blanco = no se traza
        "-border", "5",
        output_pnm,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ImageMagick error: {result.stderr}")


def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    cmd = [
        "potrace",
        "-s",
        "--unit", "10",
        "--turdsize", "10",
        "--alphamax", "0.6",
        "-O", "0.2",
        "-o", output_svg,
        bnw_pnm,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Potrace error: {result.stderr}")


def _generate_filled_svg(input_svg: str, output_filled_svg: str) -> None:
    cmd = [
        "inkscape",
        "-g",
        "--actions=" +
        "select-all;" +
        "ungroup;" +
        "ungroup;" +
        "ungroup;" +
        "select-all;" +
        "object-to-path;" +
        "select-all;" +
        "path-break-apart;" +
        "select-all;" +
        "path-union;" +
        f"export-filename:{output_filled_svg};" +
        "export-do;" +
        "quit-immediate;",
        input_svg,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not Path(output_filled_svg).exists():
        raise RuntimeError(
            f"Inkscape no generó el SVG filled.\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )


def _generate_scad_cutter(
    filled_svg: str,
    scad_path: str,
    wall_height: float,
    wall_thickness: float,
) -> None:
    """
    Genera el SCAD para la PIEZA 1: el cortante (cutter).
    Solo la pared perimetral hueca — es la parte que corta la masa.
    Incluye un aro de agarre en la parte superior.
    """
    outer_gap = 0.5
    base_offset = wall_thickness * 1.5
    gap = outer_gap + base_offset
    handle_h = wall_height * 0.5
    handle_thickness = wall_thickness * 2.0

    scad_code = f"""
$fa = 5;
$fs = 0.5;

filled = "{filled_svg}";
wall_height   = {wall_height};
wall_thickness = {wall_thickness};
handle_thickness = {handle_thickness};
gap           = {gap};
handle_h      = {handle_h};

module filled_shape(off) {{
    offset(off)
    import(filled, center = true, $fa = 5);
}}

// Pared delgada = anillo entre offset externo e interno
module cutter_wall(height, thickness) {{
    linear_extrude(height)
    difference() {{
        filled_shape(gap + thickness);
        filled_shape(gap);
    }}
}}

// Aro de agarre en la parte superior (más grueso para agarrar)
module handle_ring() {{
    translate([0, 0, wall_height * 0.6])
    linear_extrude(handle_h)
    difference() {{
        filled_shape(gap + handle_thickness);
        filled_shape(gap);
    }}
}}

union() {{
    cutter_wall(wall_height, wall_thickness);
    handle_ring();
}}
"""
    with open(scad_path, "w") as f:
        f.write(scad_code)


def _generate_scad_stamp(
    original_svg: str,
    filled_svg: str,
    scad_path: str,
    wall_height: float,
    wall_thickness: float,
) -> None:
    """
    Genera el SCAD para la PIEZA 2: el estampador (stamp).
    Base sólida que calza DENTRO del cutter con tolerancia FIT_TOLERANCE.
    En la cara inferior tiene las líneas de la figura en relieve para
    estampar el diseño en la galleta.
    """
    outer_gap = 0.5
    base_offset = wall_thickness * 1.5
    gap = outer_gap + base_offset

    # El stamp debe ser más chico que el interior del cutter por la tolerancia
    stamp_offset = gap - FIT_TOLERANCE

    base_h = 2.5          # altura de la base sólida (mm)
    relief_h = 1.2        # altura del relieve (mm) — las líneas que marcan la galleta
    total_h = base_h + relief_h

    scad_code = f"""
$fa = 5;
$fs = 0.5;

original = "{original_svg}";
filled   = "{filled_svg}";

stamp_offset = {stamp_offset};
base_h       = {base_h};
relief_h     = {relief_h};
total_h      = {total_h};

module filled_shape(off) {{
    offset(off)
    import(filled, center = true, $fa = 5);
}}

module original_shape() {{
    import(original, center = true, $fa = 5);
}}

// Base sólida que calza dentro del cutter
module stamp_base() {{
    linear_extrude(base_h)
    filled_shape(stamp_offset);
}}

// Relieve de la figura (cara inferior = hacia la galleta)
// Usamos mirror para que al presionar sobre la masa quede orientado correctamente
module stamp_relief() {{
    translate([0, 0, base_h])
    linear_extrude(relief_h)
    // El relieve son todas las líneas internas de la figura
    difference() {{
        filled_shape(stamp_offset * 0.95);
        original_shape();
    }}
}}

union() {{
    stamp_base();
    stamp_relief();
}}
"""
    with open(scad_path, "w") as f:
        f.write(scad_code)


def _run_openscad(scad_path: str, output_path: str, extra_args: list = None) -> None:
    """Ejecuta OpenSCAD CLI para exportar a STL o PNG."""
    display = os.environ.get("DISPLAY", ":5")
    cmd = [
        "openscad-nightly",
        scad_path,
        "--enable=fast-csg",
        "--enable=lazy-union",
        "-o", output_path,
    ]
    if extra_args:
        cmd.extend(extra_args)

    env = os.environ.copy()
    env["DISPLAY"] = display

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)

    if "Current top level object is empty" in result.stderr:
        raise RuntimeError(
            f"OpenSCAD generó geometría vacía. El SVG puede estar mal formado.\n"
            f"stderr: {result.stderr}"
        )
    if result.returncode != 0:
        raise RuntimeError(
            f"OpenSCAD error (code {result.returncode}):\n{result.stderr}"
        )
    if not Path(output_path).exists() or Path(output_path).stat().st_size < 100:
        raise RuntimeError(
            f"OpenSCAD generó un archivo vacío o inválido.\nstderr: {result.stderr}"
        )


def _generate_placeholder_preview(preview_path: str) -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    from PIL import Image as PILImage
    img = PILImage.new("RGB", (600, 600), color=(240, 240, 240))
    img.save(preview_path)


def _calculate_volume(stl_path: str) -> Tuple[float, Tuple[float, float, float]]:
    try:
        m = mesh.Mesh.from_file(stl_path)
        volume_mm3, _, _ = m.get_mass_properties()
        volumen_cm3 = float(volume_mm3) / 1000.0
        dims = (
            float(m.x.max()) - float(m.x.min()),
            float(m.y.max()) - float(m.y.min()),
            float(m.z.max()) - float(m.z.min()),
        )
        return volumen_cm3, dims
    except Exception as e:
        raise RuntimeError(f"Error calculando volumen STL: {str(e)}")


def image_to_stl(
    image_path: str,
    output_name: str,
    wall_height: Optional[float] = None,
    wall_thickness: Optional[float] = None,
    handle_height: Optional[float] = None,
    handle_thickness: Optional[float] = None,
) -> dict:
    """
    Pipeline completo — genera DOS STLs:
      {output_name}_cutter.stl  → pared perimetral (corta la masa)
      {output_name}_stamp.stl   → base con relieve (estampa el diseño)
    """
    wh = float(wall_height or WALL_HEIGHT)
    wt = float(wall_thickness or WALL_THICKNESS)

    work_dir = Path(tempfile.gettempdir()) / f"cc_gen_{output_name}"
    work_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "bnw_pnm":        str(work_dir / "input_bw.pnm"),
        "vector_svg":     str(work_dir / "vector.svg"),
        "filled_svg":     str(work_dir / "vector-fill.svg"),
        "scad_cutter":    str(work_dir / "cutter.scad"),
        "scad_stamp":     str(work_dir / "stamp.scad"),
        "stl_cutter_tmp": str(work_dir / "cutter.stl"),
        "stl_stamp_tmp":  str(work_dir / "stamp.stl"),
        "stl_cutter":     str(STL_DIR / f"{output_name}_cutter.stl"),
        "stl_stamp":      str(STL_DIR / f"{output_name}_stamp.stl"),
        "preview_cutter": str(PREVIEW_DIR / f"{output_name}_cutter.png"),
        "preview_stamp":  str(PREVIEW_DIR / f"{output_name}_stamp.png"),
    }

    try:
        # 1. Imagen → binarizar → vectorizar
        _binarize_image(image_path, paths["bnw_pnm"])
        _vectorize_to_svg(paths["bnw_pnm"], paths["vector_svg"])
        _generate_filled_svg(paths["vector_svg"], paths["filled_svg"])

        # 2. Generar SCAD para cada pieza
        _generate_scad_cutter(
            filled_svg=paths["filled_svg"],
            scad_path=paths["scad_cutter"],
            wall_height=wh,
            wall_thickness=wt,
        )
        _generate_scad_stamp(
            original_svg=paths["vector_svg"],
            filled_svg=paths["filled_svg"],
            scad_path=paths["scad_stamp"],
            wall_height=wh,
            wall_thickness=wt,
        )

        # 3. Renderizar STLs
        _run_openscad(
            paths["scad_cutter"],
            paths["stl_cutter_tmp"],
            ["--export-format=binstl"],
        )
        _run_openscad(
            paths["scad_stamp"],
            paths["stl_stamp_tmp"],
            ["--export-format=binstl"],
        )

        # 4. Calcular volúmenes
        vol_cutter, dims_cutter = _calculate_volume(paths["stl_cutter_tmp"])
        vol_stamp, _            = _calculate_volume(paths["stl_stamp_tmp"])

        # 5. Copiar a directorio final
        shutil.copy2(paths["stl_cutter_tmp"], paths["stl_cutter"])
        shutil.copy2(paths["stl_stamp_tmp"],  paths["stl_stamp"])

        # 6. Previews (PNG)
        for scad, preview in [
            (paths["scad_cutter"], paths["preview_cutter"]),
            (paths["scad_stamp"],  paths["preview_stamp"]),
        ]:
            try:
                _run_openscad(scad, preview, [
                    "--export-format=png",
                    "--imgsize=600,600",
                    "--camera=0,0,0,55,0,25,140",
                ])
            except Exception:
                _generate_placeholder_preview(preview)

        return {
            "stl_path":         paths["stl_cutter"],
            "stl_cutter_path":  paths["stl_cutter"],
            "stl_stamp_path":   paths["stl_stamp"],
            "preview_path":     paths["preview_cutter"],
            "preview_cutter":   paths["preview_cutter"],
            "preview_stamp":    paths["preview_stamp"],
            "volumen_cm3":      round(vol_cutter + vol_stamp, 4),
            "volumen_cutter_cm3": round(vol_cutter, 4),
            "volumen_stamp_cm3":  round(vol_stamp, 4),
            "dimensiones":      [round(float(d), 2) for d in dims_cutter],
            "exito": True,
            "mensaje": "DOS piezas generadas: cutter (silueta) + stamp (estampador con relieve)",
            "parametros": {
                "wall_height":    wh,
                "wall_thickness": wt,
                "fit_tolerance":  FIT_TOLERANCE,
            },
        }

    except Exception as e:
        import traceback
        return {
            "stl_path": "",
            "stl_cutter_path": "",
            "stl_stamp_path": "",
            "preview_path": "",
            "preview_cutter": "",
            "preview_stamp": "",
            "volumen_cm3": 0.0,
            "volumen_cutter_cm3": 0.0,
            "volumen_stamp_cm3": 0.0,
            "dimensiones": [0.0, 0.0, 0.0],
            "exito": False,
            "mensaje": f"Error en pipeline STL: {str(e)}\n{traceback.format_exc()}",
            "parametros": {},
        }
    finally:
        try:
            if work_dir.exists():
                shutil.rmtree(work_dir)
        except Exception:
            pass


def calculate_price(volumen_cm3: float) -> dict:
    from app.config import (
        COSTO_FILAMENTO_POR_CM3,
        COSTO_BASE,
        MARGEN,
        CURRENCY,
        CURRENCY_SYMBOL,
    )
    costo_materiales = float(volumen_cm3) * float(COSTO_FILAMENTO_POR_CM3)
    costo_total = (costo_materiales + float(COSTO_BASE)) * float(MARGEN)
    return {
        "volumen_cm3":       round(float(volumen_cm3), 4),
        "costo_materiales":  round(costo_materiales, 2),
        "costo_base":        float(COSTO_BASE),
        "margen":            float(MARGEN),
        "precio_final":      round(costo_total, 2),
        "moneda":            CURRENCY,
        "simbolo":           CURRENCY_SYMBOL,
        "formula": f"({volumen_cm3:.4f} * {COSTO_FILAMENTO_POR_CM3} + {COSTO_BASE}) * {MARGEN}",
    }
