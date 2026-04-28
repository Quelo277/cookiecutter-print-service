import os, uuid
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import UPLOAD_DIR, MAX_IMAGE_SIZE_BYTES, CURRENCY, CURRENCY_SYMBOL, PUBLIC_URL
from app.stl_generator import validate_image, image_to_stl, calculate_price

app = FastAPI(title="Gema Makers STL Service")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "currency": CURRENCY,
            "currency_symbol": CURRENCY_SYMBOL,
            "public_url": PUBLIC_URL,
        },
    )


@app.post("/api/upload")
async def upload_image(
    file: UploadFile = File(...),
    wall_height: Optional[float] = Form(None),
    wall_thickness: Optional[float] = Form(None),
):
    job_id = str(uuid.uuid4())[:12]
    ext = Path(file.filename).suffix.lower()
    upload_path = UPLOAD_DIR / f"{job_id}{ext}"

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(400, f"Imagen demasiado grande (máx {MAX_IMAGE_SIZE_BYTES // 1024 // 1024} MB)")

    with open(upload_path, "wb") as f:
        f.write(contents)

    valido, mensaje = validate_image(str(upload_path))
    if not valido:
        raise HTTPException(400, mensaje)

    res = image_to_stl(
        str(upload_path),
        job_id,
        wall_height=wall_height,
        wall_thickness=wall_thickness,
    )

    if not res["exito"]:
        raise HTTPException(500, res["mensaje"])

    return {
        "job_id":       job_id,
        # URLs de descarga para ambas piezas
        "stl_url":          f"/api/download/{job_id}_cutter.stl",
        "stl_cutter_url":   f"/api/download/{job_id}_cutter.stl",
        "stl_stamp_url":    f"/api/download/{job_id}_stamp.stl",
        # Previews
        "preview_url":          f"/static/uploads/previews/{job_id}_cutter.png",
        "preview_cutter_url":   f"/static/uploads/previews/{job_id}_cutter.png",
        "preview_stamp_url":    f"/static/uploads/previews/{job_id}_stamp.png",
        # Volúmenes
        "volumen_cm3":          res["volumen_cm3"],
        "volumen_cutter_cm3":   res["volumen_cutter_cm3"],
        "volumen_stamp_cm3":    res["volumen_stamp_cm3"],
        "dimensiones_mm":       res["dimensiones"],
        "precio":               calculate_price(res["volumen_cm3"]),
        "mensaje":              res["mensaje"],
        "exito":                True,
    }


@app.get("/api/download/{filename}")
async def download(filename: str):
    from app.config import STL_DIR
    filepath = STL_DIR / filename
    if not filepath.exists():
        raise HTTPException(404, f"Archivo no encontrado: {filename}")
    return FileResponse(filepath, filename=filename)


@app.get("/health")
async def health():
    return {"status": "ok"}
