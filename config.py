# config.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Bot Configuration
API_ID = int(os.getenv('API_ID', '36442788'))
API_HASH = os.getenv('API_HASH', 'a46cfef94ef9de4026597c6a4addf073')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8710395950:AAEH9E_ip9dOLqM76p_zb1113o0ubBw_qGY')
ADMIN_ID = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '6598607558').split(',')]
GROUP_ID = int(os.getenv('GROUP_ID', '-1001915538582'))

# Database
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///data/bot_database.db')

# File paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
SITES_FILE = DATA_DIR / 'sites.txt'

# Create directories
DATA_DIR.mkdir(parents=True, exist_ok=True)
