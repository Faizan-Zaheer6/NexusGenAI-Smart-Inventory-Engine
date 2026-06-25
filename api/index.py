import os
import sys

# Dynamic lookahead wrapper for Mangum injection
try:
    from mangum import Mangum
except ImportError:
    # Fallback to prevent syntax block during static linting
    Mangum = None

# Base path routing configuration
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "app"))
sys.path.insert(0, os.path.join(ROOT_DIR, "nexus_ai"))

# Dynamic application module loader
app = None

try:
    from app.main import app as main_app
    app = main_app
except ImportError:
    try:
        from nexus_ai.app.main import app as nexus_app
        app = nexus_app
    except ImportError:
        try:
            from app.nexus_ai.main import app as nested_app
            app = nested_app
        except ImportError:
            raise RuntimeError("FastAPI application instance target could not be resolved.")

# Initializing serverless ASGI adapter wrapper
handler = Mangum(app, lifespan="off") if Mangum else None