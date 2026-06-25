import io
from datetime import datetime
from typing import Optional

from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import Order, Product


async def generate_sales_excel(db: AsyncSession, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> bytes:
    query = select(Order).options(selectinload(Order.items), selectinload(Order.user)).order_by(Order.created_at.desc())
    if date_from:
        query = query.where(Order.created_at >= date_from)
    if date_to:
        query = query.where(Order.created_at <= date_to)
    result = await db.execute(query)
    orders = result.scalars().all()

    wb = Workbook()
    ws_orders = wb.active
    ws_orders.title = "Orders"
    ws_orders.append(["Order ID", "Customer", "Status", "Subtotal", "Discount", "Total", "Coupon", "Date"])

    for order in orders:
        ws_orders.append([
            order.id,
            order.user.full_name if order.user else "N/A",
            order.status,
            order.subtotal,
            order.discount_amount,
            order.total_amount,
            order.coupon_code or "",
            order.created_at.strftime("%Y-%m-%d %H:%M"),
        ])

    ws_inv = wb.create_sheet("Inventory")
    prod_res = await db.execute(select(Product).order_by(Product.id))
    products = prod_res.scalars().all()
    ws_inv.append(["ID", "Name", "Category", "Price", "Stock"])
    for p in products:
        ws_inv.append([p.id, p.name, p.category, p.price, p.stock])

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


async def generate_sales_pdf(db: AsyncSession, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> bytes:
    query = select(Order).options(selectinload(Order.user)).order_by(Order.created_at.desc())
    if date_from:
        query = query.where(Order.created_at >= date_from)
    if date_to:
        query = query.where(Order.created_at <= date_to)
    result = await db.execute(query)
    orders = result.scalars().all()

    sales_res = await db.execute(select(func.sum(Order.total_amount)))
    total_sales = sales_res.scalar() or 0

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("NexusAI Sales Report", styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]),
        Paragraph(f"Total Revenue: ${total_sales:,.2f}", styles["Heading2"]),
        Spacer(1, 20),
    ]

    data = [["Order", "Customer", "Status", "Total", "Date"]]
    for order in orders[:50]:
        data.append([
            str(order.id),
            order.user.full_name if order.user else "N/A",
            order.status,
            f"${order.total_amount:,.2f}",
            order.created_at.strftime("%Y-%m-%d"),
        ])

    table = Table(data, colWidths=[50, 120, 80, 80, 80])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
