"""
CookieCutterPrintService - FastAPI Backend  .
API REST para conversion de imagenes a cortantes STL y presupuestos de impresion 3D.
"""
import os
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    HOST,
    PORT,
    UPLOAD_DIR,
    STL_DIR,
    PREVIEW_DIR,
    MAX_IMAGE_SIZE_BYTES,
    CURRENCY,
    CURRENCY_SYMBOL,
    PUBLIC_URL,
)
from app.database import init_database, create_order, get_order, list_orders, update_order_status, get_stats
from app.stl_generator import (
    validate_image,
    image_to_stl,
    calculate_price,
)
from app.notifications import send_order_notification

# Inicializar FastAPI
app = FastAPI(
    title="CookieCutterPrintService",
    description="Servicio de presupuesto e impresion 3D de cortantes de galletas",
    version="1.0.0",
)

# Servir archivos estaticos
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Templates Jinja2
templates = Jinja2Templates(directory="frontend/templates")

# Eventos de lifecycle
@app.on_event("startup")
async def startup():
    """Inicializa la base de datos al arrancar."""
    init_database()
    print(f"[STARTUP] Base de datos inicializada en {os.getenv('DATABASE_PATH', './db/orders.db')}")
    print(f"[STARTUP] Currency: {CURRENCY}, Filamento: ${os.getenv('COSTO_FILAMENTO_POR_CM3', '0.5')}/cm3, Base: ${os.getenv('COSTO_BASE', '300')}, Margen: {os.getenv('MARGEN', '1.4')}")


# ============================================================
# RUTAS FRONTEND (HTML)
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Version: 1.0.1 - Limpieza de cache
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={
            "request": request,
            "currency": CURRENCY,
            "currency_symbol": CURRENCY_SYMBOL,
            "public_url": PUBLIC_URL,
        }
    )
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="admin.html", 
        context={
            "request": request, 
            "currency_symbol": CURRENCY_SYMBOL
        }
    )

# ============================================================
# API ENDPOINTS
# ============================================================

@app.post("/api/upload")
async def upload_image(
    file: UploadFile = File(...),
    wall_height: Optional[float] = Form(None),
    wall_thickness: Optional[float] = Form(None),
    handle_height: Optional[float] = Form(None),
    handle_thickness: Optional[float] = Form(None),
):
    """
    Sube una imagen, la convierte a STL y devuelve presupuesto.
    
    Form data:
        - file: imagen JPG/PNG
        - wall_height: altura pared (opcional, default desde env)
        - wall_thickness: grosor pared (opcional)
        - handle_height: altura mango (opcional)
        - handle_thickness: grosor mango (opcional)
    
    Returns:
        - job_id: ID unico del trabajo
        - stl_url: URL para descargar el STL
        - preview_url: URL de la imagen preview
        - volumen_cm3: volumen calculado
        - dimensiones: [x, y, z] en mm
        - precio: objeto con desglose de precios
        - exito: bool
        - mensaje: str
    """
    # Validar extension
    allowed = (".jpg", ".jpeg", ".png")
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Formato no permitido. Use: {', '.join(allowed)}")

    # Guardar archivo subido
    job_id = str(uuid.uuid4())[:12]
    upload_path = UPLOAD_DIR / f"{job_id}{ext}"

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(400, f"Archivo demasiado grande. Max: {MAX_IMAGE_SIZE_BYTES // (1024*1024)} MB")

    with open(upload_path, "wb") as f:
        f.write(contents)

    # Validar imagen
    valido, mensaje = validate_image(str(upload_path))
    if not valido:
        # Limpiar
        upload_path.unlink(missing_ok=True)
        raise HTTPException(400, mensaje)

    # Convertir a STL
    resultado = image_to_stl(
        str(upload_path),
        job_id,
        wall_height=wall_height,
        wall_thickness=wall_thickness,
        handle_height=handle_height,
        handle_thickness=handle_thickness,
    )

    if not resultado["exito"]:
        raise HTTPException(500, resultado["mensaje"])

    # Calcular precio
    precio = calculate_price(resultado["volumen_cm3"])

    return {
        "job_id": job_id,
        "stl_url": f"/api/download/{job_id}.stl",
        "preview_url": f"/static/uploads/previews/{job_id}.png",
        "volumen_cm3": resultado["volumen_cm3"],
        "dimensiones_mm": resultado["dimensiones"],
        "precio": precio,
        "parametros_usados": resultado["parametros"],
        "exito": True,
        "mensaje": resultado["mensaje"],
    }


@app.post("/api/order")
async def create_print_order(
    job_id: str = Form(...),
    nombre: str = Form(...),
    email: str = Form(...),
    telefono: Optional[str] = Form(None),
    notas: Optional[str] = Form(None),
    aceptar: bool = Form(...),
):
    """
    Registra un pedido de impresion despues de que el cliente acepta el presupuesto.
    
    Form data:
        - job_id: ID del trabajo devuelto por /api/upload
        - nombre: nombre completo del cliente
        - email: email de contacto
        - telefono: opcional
        - notas: comentarios adicionales
        - aceptar: debe ser 'true' para confirmar
    """
    if not aceptar:
        raise HTTPException(400, "Debe aceptar el presupuesto para continuar")

    # Verificar que existe el STL
    stl_path = STL_DIR / f"{job_id}.stl"
    if not stl_path.exists():
        raise HTTPException(404, "Trabajo no encontrado o STL expirado. Sube la imagen de nuevo.")

    # Obtener metadados del trabajo (los guardamos en un JSON auxiliar)
    metadata_path = STL_DIR / job_id / "metadata.json"
    volumen_cm3 = 0.0
    precio_final = 0.0

    # Calcular de nuevo (el STL existe, asi que podemos recalcular)
    from app.stl_generator import calculate_price
    import json

    # Intentar leer metadata si existe
    meta = {}
    work_dir = STL_DIR / job_id
    if work_dir.exists():
        # Buscar parametros usados
        for f in work_dir.iterdir():
            if f.suffix == ".scad":
                # Extraer parametros del SCAD
                break

    # Recalcular precio
    from stl import mesh
    try:
        m = mesh.Mesh.from_file(str(stl_path))
        volume_mm3, cog, inertia = m.get_mass_properties()
        volumen_cm3 = volume_mm3 / 1000.0
        precio_data = calculate_price(volumen_cm3)
        precio_final = precio_data["precio_final"]
    except Exception:
        raise HTTPException(500, "Error al recalcular el volumen del STL")

    # Buscar archivo original
    original_file = "unknown"
    for ext in (".jpg", ".jpeg", ".png"):
        candidate = UPLOAD_DIR / f"{job_id}{ext}"
        if candidate.exists():
            original_file = candidate.name
            break

    # Crear pedido en DB
    order_id = create_order(
        nombre=nombre,
        email=email,
        telefono=telefono,
        filename_original=original_file,
        filename_stl=f"{job_id}.stl",
        volumen_cm3=volumen_cm3,
        precio=precio_final,
        moneda=CURRENCY,
        notas=notas,
        metadata_dict={
            "job_id": job_id,
            "public_stl_url": f"{PUBLIC_URL}/api/download/{job_id}.stl",
        },
    )

    # Enviar notificacion por email (si esta configurado)
    order_data = {
        "id": order_id,
        "nombre": nombre,
        "email": email,
        "telefono": telefono or "N/A",
        "filename_original": original_file,
        "volumen_cm3": round(volumen_cm3, 4),
        "precio": precio_final,
        "moneda": CURRENCY,
        "simbolo": CURRENCY_SYMBOL,
    }
    email_sent = send_order_notification(order_data)

    return {
        "order_id": order_id,
        "estado": "pendiente",
        "precio_final": precio_final,
        "moneda": CURRENCY,
        "simbolo": CURRENCY_SYMBOL,
        "email_notificado": email_sent,
        "mensaje": "Pedido registrado exitosamente. Te contactaremos pronto.",
    }


@app.get("/api/orders")
async def get_orders(estado: Optional[str] = None, limit: int = 100):
    """Lista todos los pedidos (para panel admin)."""
    orders = list_orders(estado=estado, limit=limit)
    return {"orders": orders, "count": len(orders)}


@app.get("/api/orders/{order_id}")
async def get_order_detail(order_id: int):
    """Obtiene detalle de un pedido especifico."""
    order = get_order(order_id)
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    return order


@app.patch("/api/orders/{order_id}/status")
async def patch_order_status(order_id: int, estado: str):
    """Actualiza el estado de un pedido (pendiente | en_proceso | completado | cancelado)."""
    estados_validos = ("pendiente", "en_proceso", "completado", "cancelado")
    if estado not in estados_validos:
        raise HTTPException(400, f"Estado invalido. Use: {', '.join(estados_validos)}")

    ok = update_order_status(order_id, estado)
    if not ok:
        raise HTTPException(404, "Pedido no encontrado")
    return {"order_id": order_id, "estado": estado, "mensaje": "Estado actualizado"}


@app.get("/api/stats")
async def get_dashboard_stats():
    """Estadisticas para el dashboard."""
    return get_stats()


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Descarga archivos STL."""
    file_path = STL_DIR / filename
    if not file_path.exists() or ".." in filename:
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(
        str(file_path),
        media_type="application/octet-stream",
        filename=filename,
    )


@app.get("/api/stl-preview/{job_id}")
async def stl_preview_data(job_id: str):
    """
    Devuelve el contenido del STL como JSON para preview en Three.js.
    Convierte el STL binario a formato legible por el frontend.
    """
    stl_path = STL_DIR / f"{job_id}.stl"
    if not stl_path.exists():
        raise HTTPException(404, "STL no encontrado")

    try:
        import base64
        with open(stl_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return {"stl_base64": data, "job_id": job_id}
    except Exception as e:
        raise HTTPException(500, f"Error leyendo STL: {str(e)}")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health_check():
    """Endpoint de salud para monitoreo."""
    return {
        "status": "ok",
        "service": "CookieCutterPrintService",
        "timestamp": datetime.now().isoformat(),
        "currency": CURRENCY,
    }
