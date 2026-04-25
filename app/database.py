"""
Base de datos SQLite para CookieCutterPrintService.
Gestiona pedidos de impresion 3D de cortantes de galletas.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from app.config import DATABASE_PATH


def init_database():
    """Inicializa la base de datos con las tablas necesarias."""
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)

    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                email TEXT NOT NULL,
                telefono TEXT,
                filename_original TEXT NOT NULL,
                filename_stl TEXT NOT NULL,
                volumen_cm3 REAL NOT NULL,
                precio REAL NOT NULL,
                moneda TEXT NOT NULL DEFAULT 'ARS',
                estado TEXT NOT NULL DEFAULT 'pendiente',
                notas TEXT,
                metadata_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(email)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_estado ON orders(estado)
        """)
        conn.commit()


@contextmanager
def get_db():
    """Context manager para conexiones SQLite."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def create_order(
    nombre: str,
    email: str,
    filename_original: str,
    filename_stl: str,
    volumen_cm3: float,
    precio: float,
    moneda: str = "ARS",
    telefono: Optional[str] = None,
    notas: Optional[str] = None,
    metadata_dict: Optional[Dict[str, Any]] = None,
) -> int:
    """Crea un nuevo pedido y devuelve su ID."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO orders (
                nombre, email, telefono, filename_original, filename_stl,
                volumen_cm3, precio, moneda, notas, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nombre,
                email,
                telefono,
                filename_original,
                filename_stl,
                volumen_cm3,
                precio,
                moneda,
                notas,
                json.dumps(metadata_dict) if metadata_dict else None,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    """Obtiene un pedido por su ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        if row:
            return dict(row)
        return None


def list_orders(estado: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Lista pedidos, opcionalmente filtrados por estado."""
    with get_db() as conn:
        if estado:
            rows = conn.execute(
                "SELECT * FROM orders WHERE estado = ? ORDER BY created_at DESC LIMIT ?",
                (estado, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


def update_order_status(order_id: int, estado: str) -> bool:
    """Actualiza el estado de un pedido."""
    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE orders SET estado = ?, updated_at = ? WHERE id = ?
            """,
            (estado, datetime.now().isoformat(), order_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_stats() -> Dict[str, Any]:
    """Obtiene estadisticas de pedidos."""
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM orders").fetchone()["c"]
        pendientes = conn.execute(
            "SELECT COUNT(*) as c FROM orders WHERE estado = 'pendiente'"
        ).fetchone()["c"]
        completados = conn.execute(
            "SELECT COUNT(*) as c FROM orders WHERE estado = 'completado'"
        ).fetchone()["c"]
        ingresos = conn.execute(
            "SELECT COALESCE(SUM(precio), 0) as s FROM orders"
        ).fetchone()["s"]
        return {
            "total_orders": total,
            "pendientes": pendientes,
            "completados": completados,
            "ingresos_totales": round(ingresos, 2),
        }
