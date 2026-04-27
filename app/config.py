"""
Configuracion de CookieCutterPrintService.
Todas las variables se cargan desde el entorno con valores por defecto seguros.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables desde .env si existe
load_dotenv()

# Directorio base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Servidor ---
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# --- Base de datos ---
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "db" / "orders.db"))

# --- Precios y moneda ---
CURRENCY = os.getenv("CURRENCY", "ARS")
CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "$")
COSTO_FILAMENTO_POR_CM3 = float(os.getenv("COSTO_FILAMENTO_POR_CM3", "0.5"))
COSTO_BASE = float(os.getenv("COSTO_BASE", "300.0"))
MARGEN = float(os.getenv("MARGEN", "1.4"))

# --- SMTP (opcional) ---
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@cookiecutter.local")
SMTP_TO = os.getenv("SMTP_TO", "admin@cookiecutter.local")
SMTP_ENABLED = bool(SMTP_HOST)

# --- OpenSCAD / Pipeline ---
WALL_HEIGHT = float(os.getenv("WALL_HEIGHT", "15"))
WALL_THICKNESS = float(os.getenv("WALL_THICKNESS", "1.2"))
HANDLE_HEIGHT = float(os.getenv("HANDLE_HEIGHT", "8"))
HANDLE_THICKNESS = float(os.getenv("HANDLE_THICKNESS", "3"))
MAX_IMAGE_SIZE_MB = int(os.getenv("MAX_IMAGE_SIZE_MB", "10"))
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024

# --- URLs ---
PUBLIC_URL = os.getenv("PUBLIC_URL", f"http://localhost:{PORT}")

# --- Directorios ---
UPLOAD_DIR = BASE_DIR / "frontend" / "static" / "uploads"
STL_DIR = UPLOAD_DIR / "stl"
PREVIEW_DIR = UPLOAD_DIR / "previews"
OPENSCAD_TEMPLATES_DIR = BASE_DIR / "openscad_templates"

# Asegurar que los directorios existen
for d in [UPLOAD_DIR, STL_DIR, PREVIEW_DIR, Path(DATABASE_PATH).parent]:
    d.mkdir(parents=True, exist_ok=True)
# Validar que las herramientas de sistema estan disponibles
def validate_tools():
    """Verifica que las herramientas de sistema necesarias estan instaladas."""
    import shutil
    tools = {
        "inkscape": "Inkscape (SVG processing)",
        "openscad-nightly": "OpenSCAD nightly (SVG import, fast-csg)",
        "convert": "ImageMagick (convert)",
        "potrace": "Potrace (bitmap tracing)",
    }
    missing = []
    for cmd, name in tools.items():
        if not shutil.which(cmd):
            missing.append(name)
    if missing:
        raise RuntimeError(
            f"Herramientas faltantes: {', '.join(missing)}. "
            "Asegurate de instalarlas antes de ejecutar la aplicacion."
        )
