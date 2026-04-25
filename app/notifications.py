"""
Servicio de notificaciones por email para nuevos pedidos.
SMTP configurable via variables de entorno.
"""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import (
    SMTP_ENABLED,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    SMTP_FROM,
    SMTP_TO,
    PUBLIC_URL,
)


def send_order_notification(order_data: dict) -> bool:
    """
    Envia notificacion por email cuando se recibe un nuevo pedido.
    Retorna True si se envio correctamente, False si fallo o esta desactivado.
    """
    if not SMTP_ENABLED:
        return False

    try:
        subject = f"Nuevo pedido #{order_data['id']} - CookieCutterPrintService"

        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #FF6B35;">Nuevo Pedido Recibido</h2>
            <table style="border-collapse: collapse; width: 100%; max-width: 500px;">
                <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>ID:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">#{order_data['id']}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Cliente:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{order_data['nombre']}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Email:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{order_data['email']}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Telefono:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{order_data.get('telefono', 'N/A')}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Archivo:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{order_data['filename_original']}</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Volumen:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd;">{order_data['volumen_cm3']} cm3</td></tr>
                <tr><td style="padding: 8px; border-bottom: 1px solid #ddd; color: #FF6B35;"><strong>Precio:</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #ddd; color: #FF6B35; font-size: 1.2em;">
                        {order_data.get('simbolo', '$')}{order_data['precio']:.2f} {order_data['moneda']}
                    </td></tr>
            </table>
            <p style="margin-top: 20px;">
                <a href="{PUBLIC_URL}/api/orders/{order_data['id']}" 
                   style="background: #FF6B35; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                    Ver Detalle del Pedido
                </a>
            </p>
        </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = SMTP_TO
        msg.attach(MIMEText(body_html, "html"))

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, SMTP_TO, msg.as_string())

        return True

    except Exception as e:
        print(f"[EMAIL] Error enviando notificacion: {e}")
        return False
