"""
Pipeline de generacion STL para cortantes de galletas.
CORREGIDO v2:
  - Fix: stl_path.stat() → Path(stl_path).stat() (era AttributeError)
  - Fix: Inkscape action mcepl.ungroup-deep reemplazado por ungroup estándar
  - Fix: Detección explícita de "top level object is empty" en stderr de OpenSCAD
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


def validate_image(file_path: str) -> Tuple[bool, str]:
    """
    Valida que la imagen sea JPG/PNG y tenga fondo contrastante.
    """
    try:
        img = Image.open(file_path)
        if img.format not in ("JPEG", "PNG", "JPG"):
            return False, f"Formato no soportado: {img.format}. Use JPG o PNG."

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


def _binarize_image(input_path: str, output_pnm: str) -> None:
    """
    Binariza la imagen usando ImageMagick.
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
        "-negate",
        "-bordercolor", "black",
        "-border", "5",
        output_pnm,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ImageMagick error: {result.stderr}")


def _vectorize_to_svg(bnw_pnm: str, output_svg: str) -> None:
    """
    Vectoriza la imagen binarizada usando Potrace a SVG.
    """
    cmd = [
        "potrace",
        "-s",
        "--unit", "10",
        "--turdsize", "10",
        "--alphamax", "0.6",
        "--optoncurve", "yes",
        "-o", output_svg,
        bnw_pnm,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Potrace error: {result.stderr}")


def _generate_filled_svg(input_svg: str, output_filled_svg: str) -> None:
    """
    Genera una version 'filled' del SVG usando Inkscape.
    CORREGIDO: reemplaza mcepl.ungroup-deep (extensión de terceros no disponible)
    por la acción estándar 'ungroup' repetida para asegurar profundidad.
    """
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


def _generate_scad(
    original_svg: str,
    filled_svg: str,
    scad_path: str,
    wall_height: float,
    wall_thickness: float,
    handle_height: float,
    handle_thickness: float,
) -> None:
    """
    Genera el archivo OpenSCAD (.scad) que define el cortante.
    """
    h_inner = wall_height * 0.8
    base_offset = wall_thickness * 1.5
    outer_gap = 0.5
    handle_h = 2 * h_inner / 3

    scad_code = f"""
$fa = 5;
$fs = 0.5;

mirrored = false;

filled = "{filled_svg}";
original = "{original_svg}";

wall_height = {wall_height};
wall_thickness = {wall_thickness};
handle_thickness = {handle_thickness};

h_inner = {h_inner};
base_offset = {base_offset};
outer_gap = {outer_gap};
is_rounded = true;

module import_svg(file) {{
    scale([mirrored ? -1 : 1, 1, 1])
    import(file, center = true, $fa = 5);
}}

module offsetFilled(off) {{
    offset(off)
    import_svg(filled);
}}

module offsetThin(off, thickness) {{
    difference() {{
       offsetFilled(off + thickness);
       offsetFilled(off);
    }}
}}

/*********/
/* Outer */
/*********/
gap = outer_gap + base_offset;
handle_height = {handle_h};

module outer() {{
    union() {{
        linear_extrude(handle_height * 1.8)
            offsetThin(gap, wall_thickness);

        linear_extrude(handle_height / 2)
            offsetThin(gap, handle_thickness);

        if (is_rounded) {{
            for (i = [0:0.1:1.4]) {{
                translate([0, 0, handle_height / 2 + i])
                    linear_extrude(0.5)
                    offsetThin(gap, handle_thickness - i*i);
            }}
        }} else {{
            translate([0, 0, handle_height / 2])
                linear_extrude(1.4)
                offsetThin(gap, handle_thickness);
        }}
    }}
}}

/*********/
/* Stamp */
/*********/
module stamp() {{
    translate([0, 0, wall_height * 0.4])
        linear_extrude(wall_height * 0.5)
        offset(r = 0.01)
        import_svg(original);

    translate([0, 0, 0])
        linear_extrude(wall_height * 0.4)
        offset(r = base_offset * 0.5)
        import_svg(original);
}}

union() {{
    outer();
    stamp();
}}
"""
    with open(scad_path, "w") as f:
        f.write(scad_code)


def _render_stl(scad_path: str, stl_path: str, preview_path: Optional[str] = None) -> None:
    """
    Renderiza el archivo .scad a STL usando OpenSCAD nightly CLI.
    CORREGIDO: usa Path(stl_path).stat() en lugar de stl_path.stat() (era AttributeError).
    CORREGIDO: detecta explícitamente "top level object is empty" en stderr.
    """
    display = os.environ.get("DISPLAY", ":5")

    cmd = [
        "openscad-nightly",
        scad_path,
        "--enable=fast-csg",
        "--enable=lazy-union",
        "-o", stl_path,
        "--export-format=binstl",
    ]

    env = os.environ.copy()
    env["DISPLAY"] = display

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)

    # OpenSCAD puede retornar 0 pero generar geometría vacía
    if "Current top level object is empty" in result.stderr:
        raise RuntimeError(
            f"OpenSCAD generó geometría vacía. "
            f"El SVG importado puede estar mal formado.\n"
            f"stderr: {result.stderr}"
        )

    if result.returncode != 0:
        raise RuntimeError(f"OpenSCAD render error (code {result.returncode}):\n{result.stderr}")

    # CORREGIDO: stl_path es str, necesita Path() para llamar .stat()
    if not Path(stl_path).exists() or Path(stl_path).stat().st_size < 100:
        raise RuntimeError(
            f"OpenSCAD generó un STL vacío o inválido.\nstderr: {result.stderr}"
        )

    if preview_path:
        cmd_preview = [
            "openscad-nightly",
            scad_path,
            "--enable=fast-csg",
            "--enable=lazy-union",
            "-o", preview_path,
            "--export-format=png",
            "--imgsize=600,600",
            "--camera=0,0,0,55,0,25,140",
        ]
        subprocess.run(cmd_preview, capture_output=True, text=True, timeout=120, env=env)
        if not Path(preview_path).exists():
            _generate_placeholder_preview(preview_path)
    else:
        preview_path = str(PREVIEW_DIR / Path(stl_path).stem) + ".png"
        _generate_placeholder_preview(preview_path)


def _generate_placeholder_preview(preview_path: str) -> None:
    """Genera una imagen placeholder si OpenSCAD no pudo crear el preview."""
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    from PIL import Image as PILImage
    img = PILImage.new("RGB", (600, 600), color=(240, 240, 240))
    img.save(preview_path)


def _calculate_volume(stl_path: str) -> Tuple[float, Tuple[float, float, float]]:
    """
    Calcula el volumen (en cm3) y dimensiones (en mm) del STL usando numpy-stl.
    """
    try:
        m = mesh.Mesh.from_file(stl_path)
        volume_mm3, cog, inertia = m.get_mass_properties()
        volumen_cm3 = volume_mm3 / 1000.0

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


def image_to_stl(
    image_path: str,
    output_name: str,
    wall_height: Optional[float] = None,
    wall_thickness: Optional[float] = None,
    handle_height: Optional[float] = None,
    handle_thickness: Optional[float] = None,
) -> dict:
    """
    Pipeline completo:
    imagen → binarizar → vectorizar (SVG) → inkscape fill → OpenSCAD nightly → STL
    """
    wh = wall_height or WALL_HEIGHT
    wt = wall_thickness or WALL_THICKNESS
    hh = handle_height or HANDLE_HEIGHT
    ht = handle_thickness or HANDLE_THICKNESS

    work_dir = Path(tempfile.gettempdir()) / f"cc_gen_{output_name}"
    work_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "input_image": image_path,
        "bnw_pnm": str(work_dir / "input_bw.pnm"),
        "vector_svg": str(work_dir / "vector.svg"),
        "filled_svg": str(work_dir / "vector-fill.svg"),
        "scad_file": str(work_dir / "model.scad"),
        "stl_file": str(work_dir / "model.stl"),
        "preview_png": str(PREVIEW_DIR / f"{output_name}.png"),
    }

    try:
        _binarize_image(image_path, paths["bnw_pnm"])
        _vectorize_to_svg(paths["bnw_pnm"], paths["vector_svg"])
        _generate_filled_svg(paths["vector_svg"], paths["filled_svg"])

        _generate_scad(
            paths["vector_svg"],
            paths["filled_svg"],
            paths["scad_file"],
            wall_height=wh,
            wall_thickness=wt,
            handle_height=hh,
            handle_thickness=ht,
        )

        _render_stl(paths["scad_file"], paths["stl_file"], paths["preview_png"])

        volumen_cm3, dimensiones = _calculate_volume(paths["stl_file"])

        final_stl = str(STL_DIR / f"{output_name}.stl")
        shutil.copy2(paths["stl_file"], final_stl)

        if not Path(paths["preview_png"]).exists():
            _generate_placeholder_preview(paths["preview_png"])

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
        import traceback
        return {
            "stl_path": "",
            "preview_path": "",
            "volumen_cm3": 0.0,
            "dimensiones": [0, 0, 0],
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
