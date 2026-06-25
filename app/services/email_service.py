from app.core.config import get_settings
from app.core.mailer import send_email, send_password_reset_email

settings = get_settings()


async def send_welcome_email(user_email: str, name: str) -> None:
    subject = "Welcome to NexusAI Storefront!"
    body_text = (
        f"Dear {name},\n\n"
        f"Welcome to NexusAI: Smart Inventory Engine!\n"
        f"Your account has been successfully configured.\n"
        f"Explore our premium catalog at {settings.APP_BASE_URL}\n\n"
        f"Best regards,\nThe NexusAI Team"
    )
    body_html = f"""
    <html><body style="font-family:Inter,sans-serif;background:#0b0f19;color:#e2e8f0;padding:24px;">
    <div style="max-width:520px;margin:auto;background:#111827;border:1px solid #334155;border-radius:16px;padding:24px;">
    <h2 style="color:#818cf8;">Welcome to NexusAI</h2>
    <p>Dear {name},</p>
    <p>Your account is ready. Start shopping at our premium inventory marketplace.</p>
    <p><a href="{settings.APP_BASE_URL}" style="color:#818cf8;">Visit Storefront →</a></p>
    </div></body></html>
    """
    await send_email(user_email, subject, body_text, body_html)


async def send_order_confirmation(user_email: str, order) -> None:
    items_lines = []
    for item in order.items:
        items_lines.append(f"- {item.product.name} x{item.quantity} @ ${item.unit_price:.2f}")
    items_block = "\n".join(items_lines)
    subject = f"Order Confirmation #{order.id}"
    body_text = (
        f"Thank you for your purchase!\n\n"
        f"Order #{order.id}\n"
        f"{items_block}\n\n"
        f"Subtotal: ${order.subtotal:.2f}\n"
        f"Discount: -${order.discount_amount:.2f}\n"
        f"Total: ${order.total_amount:.2f}\n"
        f"Status: {order.status}\n\n"
        f"Receipt: {settings.APP_BASE_URL}/orders/{order.id}/receipt"
    )
    await send_email(user_email, subject, body_text)


async def send_low_stock_alert(admin_emails: list[str], product) -> None:
    recipient = admin_emails[0] if admin_emails else settings.ADMIN_EMAIL
    subject = f"CRITICAL: Low Stock — {product.name}"
    body_text = (
        f"Low stock alert for SKU #{product.id}\n"
        f"Name: {product.name}\n"
        f"Category: {product.category}\n"
        f"Current Stock: {product.stock}\n"
        f"Threshold: {settings.LOW_STOCK_THRESHOLD}\n"
    )
    await send_email(recipient, subject, body_text)


async def send_password_reset(user_email: str, full_name: str, reset_token: str) -> None:
    await send_password_reset_email(user_email, reset_token, full_name)
