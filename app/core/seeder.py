import random

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logger import logger
from app.core.security import get_password_hash
from app.database.models import Product, User

settings = get_settings()

CATEGORIES: dict[str, list[str]] = {
    "Electronics": [
        "Quantum Processor V2",
        "Neural Edge Compute Module",
        "Optic-Fibre Core Bus",
        "HyperDrive SSD 4TB",
        "Photon GPU Accelerator",
        "Silicon Photonics Switch",
        "AI Inference Chipset",
        "Modular Power Rail 850W",
        "Cryo-Cooled Memory Stack",
        "Nano-Sensor Array Hub",
    ],
    "Apparel": [
        "AeroFlex Performance Jacket",
        "CarbonWeave Running Shoes",
        "Thermal Smart Gloves",
        "Lumen Reflective Hoodie",
        "Adaptive Fit Training Shorts",
        "Merino Tech Base Layer",
        "StormShield Rain Poncho",
        "Velocity Compression Tights",
        "Arctic Pro Insulated Vest",
        "PulseTrack Fitness Band Sleeve",
    ],
    "Home Appliances": [
        "AuraPure Air Purifier",
        "HydroSync Smart Humidifier",
        "NexusBrew Espresso Station",
        "SilentWave Robot Vacuum",
        "CrystalClear Water Filter",
        "SolarHeat Induction Cooktop",
        "ZenSleep White Noise Hub",
        "FreshLock Vacuum Sealer",
        "CloudMist Aromatherapy Diffuser",
        "EcoWash Compact Washer",
    ],
    "Hardware": [
        "TitanForge Workstation Chassis",
        "Precision Torque Driver Kit",
        "Modular Rack Mount Enclosure",
        "Carbon Fiber Tool Chest",
        "Industrial Grade Cable Manager",
        "Anti-Static Work Mat Pro",
        "Laser Alignment Jig",
        "Heavy Duty Server Rails",
        "Thermal Paste Application Kit",
        "Micro-Soldering Station X1",
    ],
    "Cooling": [
        "Superfluid Cooling Loop",
        "Phase-Change Heat Sink",
        "Liquid Nitrogen Adapter Kit",
        "Dual-Radiator Fan Array",
        "Graphene Thermal Pad Set",
        "Cryo Chamber Mini Cooler",
        "Vortex Air Channel Module",
        "Copper Vapor Chamber Block",
        "Silent Pump Reservoir Combo",
        "Thermal Monitoring Sensor Pack",
    ],
    "Cabling": [
        "Platinum Shielded Ethernet Spool",
        "Fiber Optic Patch Panel",
        "USB-C Thunderbolt Braided Cable",
        "HDMI 2.1 Ultra High Speed Cord",
        "Power Distribution PDU Strip",
        "Coaxial Signal Booster Line",
        "SATA III Data Ribbon Pack",
        "DisplayPort Daisy Chain Cable",
        "Modular PSU Cable Kit",
        "Lightning-Safe Surge Protector",
    ],
    "Accessories": [
        "ErgoLift Monitor Arm",
        "Magnetic Cable Organizer",
        "RGB Desk Mat XL",
        "Wireless Charging Dock Pro",
        "Portable SSD Enclosure",
        "Bluetooth Mechanical Keyboard",
        "Precision Mouse Pad Hybrid",
        "Webcam Privacy Shutter Kit",
        "Laptop Stand Aluminum Pro",
        "Noise Cancelling Headset Elite",
    ],
    "Software": [
        "Inventory Analytics Suite License",
        "Cloud Sync Pro Subscription",
        "DevOps Pipeline Toolkit",
        "Security Audit Scanner Pack",
        "Data Visualization Dashboard",
        "API Gateway Manager License",
        "Automated Backup Orchestrator",
        "Compliance Reporting Module",
        "Multi-Tenant Admin Console",
        "Real-Time Monitoring Agent",
    ],
    "Office": [
        "Executive Standing Desk",
        "Mesh Ergonomic Task Chair",
        "Acoustic Panel Wall Set",
        "Smart Whiteboard 65 inch",
        "Document Scanner Pro",
        "Conference Speakerphone Hub",
        "LED Task Lamp Adjustable",
        "Filing Cabinet Secure Lock",
        "Collaboration Table Module",
        "Privacy Screen Filter Pack",
    ],
    "Networking": [
        "Enterprise Wi-Fi 7 Router",
        "Managed PoE Switch 48-Port",
        "Mesh Node Extender Pack",
        "VPN Security Gateway",
        "Network Attached Storage 8Bay",
        "5G Cellular Failover Modem",
        "Rackmount Patch Bay 24U",
        "DNS Traffic Filter Appliance",
        "Load Balancer Edge Device",
        "Optical Line Terminal Unit",
    ],
}

IMAGE_URLS: list[str] = [
    "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=400",
    "https://images.unsplash.com/photo-1593642632823-8f785ba67e45?w=400",
    "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=400",
    "https://images.unsplash.com/photo-1498049794561-7780e7231661?w=400",
    "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400",
    "https://images.unsplash.com/photo-1505744386214-509eec59e1c2?w=400",
    "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=400",
    "https://images.unsplash.com/photo-1560472354-b33ff0c44a43?w=400",
    "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=400",
    "https://images.unsplash.com/photo-1571171637578-41c2d251d399?w=400",
]


def _build_product_catalog(count: int) -> list[Product]:
    catalog: list[Product] = []
    category_names = list(CATEGORIES.keys())
    product_index = 0

    while len(catalog) < count:
        category = category_names[product_index % len(category_names)]
        base_names = CATEGORIES[category]
        variant = base_names[product_index % len(base_names)]
        suffix = f" Gen-{product_index + 1}" if product_index >= len(base_names) else ""
        name = f"{variant}{suffix}"

        roll = random.randint(1, 100)
        if roll <= 10:
            stock = 0
        elif roll <= 35:
            stock = random.randint(1, settings.LOW_STOCK_THRESHOLD - 1)
        else:
            stock = random.randint(settings.LOW_STOCK_THRESHOLD, 250)

        price = round(random.uniform(19.99, 2499.99), 2)
        image_url = IMAGE_URLS[product_index % len(IMAGE_URLS)]

        catalog.append(
            Product(
                name=name,
                category=category,
                price=price,
                stock=stock,
                image_url=image_url,
            )
        )
        product_index += 1

    return catalog


async def seed_users(session: AsyncSession) -> None:
    admin_result = await session.execute(
        select(User).where(User.email == settings.ADMIN_EMAIL)
    )
    admin_user = admin_result.scalar_one_or_none()
    if not admin_user:
        session.add(
            User(
                email=settings.ADMIN_EMAIL,
                full_name=settings.ADMIN_FULL_NAME,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                is_admin=True,
                role="super_admin",
            )
        )
        logger.info("Seeded super_admin user: %s", settings.ADMIN_EMAIL)
    else:
        admin_user.hashed_password = get_password_hash(settings.ADMIN_PASSWORD)
        admin_user.role = "super_admin"
        admin_user.is_admin = True
        logger.info("Updated existing admin user credentials: %s", settings.ADMIN_EMAIL)

    manager_result = await session.execute(
        select(User).where(User.email == settings.MANAGER_EMAIL)
    )
    if not manager_result.scalar_one_or_none():
        session.add(
            User(
                email=settings.MANAGER_EMAIL,
                full_name=settings.MANAGER_FULL_NAME,
                hashed_password=get_password_hash(settings.MANAGER_PASSWORD),
                is_admin=True,  # managers also have admin UI view access
                role="manager",
            )
        )
        logger.info("Seeded manager user: %s", settings.MANAGER_EMAIL)

    guest_result = await session.execute(
        select(User).where(User.email == settings.GUEST_EMAIL)
    )
    if not guest_result.scalar_one_or_none():
        session.add(
            User(
                email=settings.GUEST_EMAIL,
                full_name=settings.GUEST_FULL_NAME,
                hashed_password=get_password_hash(settings.GUEST_PASSWORD),
                is_admin=False,
                role="customer",
            )
        )
        logger.info("Seeded guest user: %s", settings.GUEST_EMAIL)

    await session.commit()


async def seed_products(session: AsyncSession) -> None:
    count_result = await session.execute(select(func.count(Product.id)))
    existing_count = count_result.scalar() or 0

    if existing_count >= settings.SEED_PRODUCT_COUNT:
        logger.info("Product catalog already seeded (%s items). Skipping.", existing_count)
        return

    needed = settings.SEED_PRODUCT_COUNT - existing_count
    logger.info("Seeding %s products into Neon DB...", needed)
    products = _build_product_catalog(needed)
    session.add_all(products)
    await session.commit()
    logger.info("Successfully seeded %s products.", needed)


async def initialize_database(session: AsyncSession) -> None:
    """Seed users, products, warehouses, coupons, and flash sales."""
    await seed_users(session)
    await seed_products(session)
    await seed_warehouses(session)
    await seed_coupons(session)
    await seed_flash_sales(session)


async def seed_warehouses(session: AsyncSession) -> None:
    from app.database.models import Warehouse, WarehouseStock

    result = await session.execute(select(Warehouse))
    if result.scalars().first():
        return

    warehouses = [
        Warehouse(name="East Coast Hub", location="New York, USA"),
        Warehouse(name="West Coast Hub", location="San Francisco, USA"),
        Warehouse(name="EU Distribution Center", location="Amsterdam, NL"),
    ]
    session.add_all(warehouses)
    await session.flush()

    products = (await session.execute(select(Product))).scalars().all()
    for product in products:
        for idx, wh in enumerate(warehouses):
            qty = max(0, product.stock // len(warehouses) + (product.id % 3 if idx == 0 else 0))
            session.add(WarehouseStock(warehouse_id=wh.id, product_id=product.id, quantity=qty))
    await session.commit()
    logger.info("Seeded %s warehouses with distributed stock.", len(warehouses))


async def seed_coupons(session: AsyncSession) -> None:
    from datetime import datetime, timedelta, timezone
    from app.database.models import Coupon

    codes = [
        ("SAVE10", "percent", 10.0, None, 0),
        ("FLAT50", "flat", 50.0, None, 100),
        ("ELECTRONICS15", "percent", 15.0, "Electronics", 200),
    ]
    for code, dtype, value, category, min_amt in codes:
        exists = await session.execute(select(Coupon).where(Coupon.code == code))
        if not exists.scalar_one_or_none():
            session.add(Coupon(
                code=code, discount_type=dtype, discount_value=value, category=category,
                min_order_amount=min_amt, max_uses=1000,
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            ))
    await session.commit()
    logger.info("Seeded promotional coupons.")


async def seed_flash_sales(session: AsyncSession) -> None:
    from datetime import datetime, timedelta, timezone
    from app.database.models import FlashSale

    existing = await session.execute(select(FlashSale))
    if existing.scalars().first():
        return

    products = (await session.execute(select(Product).limit(8))).scalars().all()
    for i, product in enumerate(products):
        session.add(FlashSale(
            product_id=product.id,
            discount_percent=10 + (i * 3),
            ends_at=datetime.now(timezone.utc) + timedelta(hours=24 + i),
            is_active=True,
        ))
    await session.commit()
    logger.info("Seeded %s flash sales.", len(products))
