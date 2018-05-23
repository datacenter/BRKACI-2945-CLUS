
import sys, os, logging, logging.handlers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.utils import setup_logger
setup_logger(logging.getLogger("app"), quiet=True)
app = create_app("config.py")

# flask requires 'application' variable from wsgi module
application = app

