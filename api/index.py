import os
import sys
# pyrefly: ignore [missing-import]
from mangum import Mangum
# Python ko project ka root path batane ke liye
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app

handler = Mangum(app, lifespan="off")