import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("EngottaBot")

# Telegram Bot Token
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN environment variable not set.")

# Admin IDs
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = []
for admin_id in ADMIN_IDS_STR.split(","):
    admin_id = admin_id.strip()
    if admin_id.isdigit():
        ADMIN_IDS.append(int(admin_id))

# PostgreSQL Database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.warning("DATABASE_URL environment variable not set. Database operations will fail.")

# Timezone (default is Asia/Kolkata for bus stops in Kerala, India)
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")

# Banner Image Path (can be a local file path or a public image URL)
BANNER_PATH = os.getenv("BANNER_PATH", "")
