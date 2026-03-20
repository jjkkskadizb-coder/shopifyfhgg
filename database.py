# database.py
import os
import aiosqlite
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Database:
    def __init__(self):
        # Get database URL from environment, default to local SQLite
        self.db_url = os.getenv('DATABASE_URL', 'sqlite:///bot_database.db')
        self.conn = None
        
    async def connect(self):
        """Connect to database"""
        try:
            if self.db_url.startswith('sqlite:///'):
                # Extract database file path
                db_file = self.db_url.replace('sqlite:///', '')
                
                # Ensure directory exists
                db_path = Path(db_file)
                db_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Connect to SQLite
                self.conn = await aiosqlite.connect(db_file)
                await self.conn.execute("PRAGMA foreign_keys = ON")
                
                # Create tables
                await self.create_tables()
                print(f"✅ Database connected: {db_file}")
                return True
            else:
                raise ValueError(f"Unsupported database URL: {self.db_url}")
                
        except Exception as e:
            print(f"❌ Database connection error: {e}")
            raise
    
    async def create_tables(self):
        """Create all necessary tables"""
        await self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_premium BOOLEAN DEFAULT 0,
                premium_expiry TIMESTAMP,
                premium_days INTEGER DEFAULT 0,
                is_banned BOOLEAN DEFAULT 0,
                banned_by INTEGER,
                banned_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS keys (
                key TEXT PRIMARY KEY,
                days INTEGER NOT NULL,
                used BOOLEAN DEFAULT 0,
                used_by INTEGER,
                used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS proxies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ip TEXT NOT NULL,
                port INTEGER NOT NULL,
                username TEXT,
                password TEXT,
                proxy_type TEXT DEFAULT 'http',
                proxy_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                site TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, site),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS checked_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card TEXT NOT NULL,
                status TEXT NOT NULL,
                response TEXT,
                gateway TEXT,
                price TEXT,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_users_premium ON users(is_premium);
            CREATE INDEX IF NOT EXISTS idx_users_banned ON users(is_banned);
            CREATE INDEX IF NOT EXISTS idx_proxies_user ON proxies(user_id);
            CREATE INDEX IF NOT EXISTS idx_sites_user ON sites(user_id);
            CREATE INDEX IF NOT EXISTS idx_cards_status ON checked_cards(status);
        ''')
        await self.conn.commit()
    
    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
    
    async def execute(self, query, params=None):
        """Execute a query"""
        if params is None:
            params = []
        cursor = await self.conn.execute(query, params)
        await self.conn.commit()
        return cursor
    
    async def fetch_all(self, query, params=None):
        """Fetch all results"""
        if params is None:
            params = []
        cursor = await self.conn.execute(query, params)
        return await cursor.fetchall()
    
    async def fetch_one(self, query, params=None):
        """Fetch one result"""
        if params is None:
            params = []
        cursor = await self.conn.execute(query, params)
        return await cursor.fetchone()

# Global database instance
db = Database()

# ==================== Database Functions ====================

async def init_db():
    """Initialize database"""
    await db.connect()

async def ensure_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    """Ensure user exists in database"""
    try:
        # Check if user exists
        user = await db.fetch_one("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        
        if not user:
            # Create new user
            await db.execute(
                "INSERT INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, last_name)
            )
            return True
        return True
    except Exception as e:
        print(f"Error ensuring user: {e}")
        return False

async def get_user(user_id: int):
    """Get user details"""
    try:
        return await db.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
    except Exception as e:
        print(f"Error getting user: {e}")
        return None

async def is_premium_user(user_id: int) -> bool:
    """Check if user has premium access"""
    try:
        user = await db.fetch_one(
            "SELECT is_premium, premium_expiry FROM users WHERE user_id = ?",
            (user_id,)
        )
        
        if not user:
            return False
        
        is_premium = user[3]  # is_premium column
        expiry = user[4]  # premium_expiry column
        
        if not is_premium:
            return False
        
        if expiry:
            # Check if not expired
            expiry_date = datetime.fromisoformat(expiry) if isinstance(expiry, str) else expiry
            if expiry_date < datetime.utcnow():
                # Expired, update status
                await db.execute(
                    "UPDATE users SET is_premium = 0 WHERE user_id = ?",
                    (user_id,)
                )
                return False
        
        return True
    except Exception as e:
        print(f"Error checking premium: {e}")
        return False

async def add_premium_user(user_id: int, days: int):
    """Add premium access to user"""
    try:
        expiry_date = datetime.utcnow() + timedelta(days=days)
        
        await db.execute(
            """UPDATE users 
               SET is_premium = 1, premium_expiry = ?, premium_days = ? 
               WHERE user_id = ?""",
            (expiry_date.isoformat(), days, user_id)
        )
        return True
    except Exception as e:
        print(f"Error adding premium: {e}")
        return False

async def remove_premium(user_id: int):
    """Remove premium access from user"""
    try:
        await db.execute(
            "UPDATE users SET is_premium = 0, premium_expiry = NULL WHERE user_id = ?",
            (user_id,)
        )
        return True
    except Exception as e:
        print(f"Error removing premium: {e}")
        return False

async def is_banned_user(user_id: int) -> bool:
    """Check if user is banned"""
    try:
        user = await db.fetch_one("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        return user[0] == 1 if user else False
    except Exception as e:
        print(f"Error checking banned: {e}")
        return False

async def ban_user(user_id: int, banned_by: int):
    """Ban a user"""
    try:
        await db.execute(
            "UPDATE users SET is_banned = 1, banned_by = ?, banned_at = ? WHERE user_id = ?",
            (banned_by, datetime.utcnow().isoformat(), user_id)
        )
        return True
    except Exception as e:
        print(f"Error banning user: {e}")
        return False

async def unban_user(user_id: int):
    """Unban a user"""
    try:
        await db.execute(
            "UPDATE users SET is_banned = 0, banned_by = NULL, banned_at = NULL WHERE user_id = ?",
            (user_id,)
        )
        return True
    except Exception as e:
        print(f"Error unbanning user: {e}")
        return False

async def create_key(key: str, days: int):
    """Create a new premium key"""
    try:
        await db.execute(
            "INSERT INTO keys (key, days) VALUES (?, ?)",
            (key, days)
        )
        return True
    except Exception as e:
        print(f"Error creating key: {e}")
        return False

async def get_key_data(key: str):
    """Get key data"""
    try:
        return await db.fetch_one("SELECT * FROM keys WHERE key = ?", (key,))
    except Exception as e:
        print(f"Error getting key: {e}")
        return None

async def use_key(user_id: int, key: str):
    """Use a premium key"""
    try:
        # Get key data
        key_data = await db.fetch_one(
            "SELECT key, days, used FROM keys WHERE key = ?",
            (key,)
        )
        
        if not key_data:
            return False, "Invalid key!"
        
        if key_data[2] == 1:  # used
            return False, "Key already used!"
        
        # Mark key as used
        await db.execute(
            "UPDATE keys SET used = 1, used_by = ?, used_at = ? WHERE key = ?",
            (user_id, datetime.utcnow().isoformat(), key)
        )
        
        # Add premium access
        days = key_data[1]
        await add_premium_user(user_id, days)
        
        return True, days
    except Exception as e:
        print(f"Error using key: {e}")
        return False, str(e)

async def get_all_keys():
    """Get all keys"""
    try:
        rows = await db.fetch_all("SELECT * FROM keys ORDER BY created_at DESC")
        return [dict(row) for row in rows] if rows else []
    except Exception as e:
        print(f"Error getting keys: {e}")
        return []

async def add_proxy_db(user_id: int, proxy_data: dict):
    """Add proxy for user"""
    try:
        await db.execute(
            """INSERT INTO proxies 
               (user_id, ip, port, username, password, proxy_type, proxy_url) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, proxy_data['ip'], proxy_data['port'], 
             proxy_data.get('username'), proxy_data.get('password'),
             proxy_data.get('type', 'http'), proxy_data.get('proxy_url'))
        )
        return True
    except Exception as e:
        print(f"Error adding proxy: {e}")
        return False

async def get_all_user_proxies(user_id: int):
    """Get all proxies for user"""
    try:
        rows = await db.fetch_all(
            "SELECT * FROM proxies WHERE user_id = ? ORDER BY id",
            (user_id,)
        )
        return [dict(row) for row in rows] if rows else []
    except Exception as e:
        print(f"Error getting proxies: {e}")
        return []

async def get_proxy_count(user_id: int):
    """Get proxy count for user"""
    try:
        row = await db.fetch_one(
            "SELECT COUNT(*) FROM proxies WHERE user_id = ?",
            (user_id,)
        )
        return row[0] if row else 0
    except Exception as e:
        print(f"Error getting proxy count: {e}")
        return 0

async def get_random_proxy(user_id: int):
    """Get random proxy for user"""
    try:
        rows = await db.fetch_all(
            "SELECT * FROM proxies WHERE user_id = ? ORDER BY RANDOM() LIMIT 1",
            (user_id,)
        )
        return dict(rows[0]) if rows else None
    except Exception as e:
        print(f"Error getting random proxy: {e}")
        return None

async def remove_proxy_by_index(user_id: int, index: int):
    """Remove proxy by index"""
    try:
        # Get proxy first
        proxies = await get_all_user_proxies(user_id)
        if 0 <= index < len(proxies):
            proxy_id = proxies[index]['id']
            await db.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
            return proxies[index]
        return None
    except Exception as e:
        print(f"Error removing proxy: {e}")
        return None

async def remove_proxy_by_url(user_id: int, proxy_url: str):
    """Remove proxy by URL"""
    try:
        await db.execute(
            "DELETE FROM proxies WHERE user_id = ? AND proxy_url = ?",
            (user_id, proxy_url)
        )
        return True
    except Exception as e:
        print(f"Error removing proxy: {e}")
        return False

async def clear_all_proxies(user_id: int):
    """Clear all proxies for user"""
    try:
        count = await get_proxy_count(user_id)
        await db.execute("DELETE FROM proxies WHERE user_id = ?", (user_id,))
        return count
    except Exception as e:
        print(f"Error clearing proxies: {e}")
        return 0

async def add_site_db(user_id: int, site: str):
    """Add site for user"""
    try:
        await db.execute(
            "INSERT INTO sites (user_id, site) VALUES (?, ?)",
            (user_id, site)
        )
        return True
    except aiosqlite.IntegrityError:
        return False
    except Exception as e:
        print(f"Error adding site: {e}")
        return False

async def get_user_sites(user_id: int):
    """Get all sites for user"""
    try:
        rows = await db.fetch_all(
            "SELECT site FROM sites WHERE user_id = ? ORDER BY id",
            (user_id,)
        )
        return [row[0] for row in rows] if rows else []
    except Exception as e:
        print(f"Error getting sites: {e}")
        return []

async def remove_site_db(user_id: int, site: str):
    """Remove site for user"""
    try:
        await db.execute(
            "DELETE FROM sites WHERE user_id = ? AND site = ?",
            (user_id, site)
        )
        return True
    except Exception as e:
        print(f"Error removing site: {e}")
        return False

async def clear_user_sites(user_id: int):
    """Clear all sites for user"""
    try:
        await db.execute("DELETE FROM sites WHERE user_id = ?", (user_id,))
        return True
    except Exception as e:
        print(f"Error clearing sites: {e}")
        return False

async def set_user_sites(user_id: int, sites: list):
    """Set user sites (replace all)"""
    try:
        await clear_user_sites(user_id)
        for site in sites:
            await add_site_db(user_id, site)
        return True
    except Exception as e:
        print(f"Error setting sites: {e}")
        return False

async def save_card_to_db(card: str, status: str, response: str, gateway: str, price: str):
    """Save checked card to database"""
    try:
        await db.execute(
            "INSERT INTO checked_cards (card, status, response, gateway, price) VALUES (?, ?, ?, ?, ?)",
            (card, status, response, gateway, price)
        )
        return True
    except Exception as e:
        print(f"Error saving card: {e}")
        return False

async def get_total_cards_count():
    """Get total number of checked cards"""
    try:
        row = await db.fetch_one("SELECT COUNT(*) FROM checked_cards")
        return row[0] if row else 0
    except Exception as e:
        print(f"Error getting total cards: {e}")
        return 0

async def get_charged_count():
    """Get number of charged cards"""
    try:
        row = await db.fetch_one(
            "SELECT COUNT(*) FROM checked_cards WHERE status = 'CHARGED'"
        )
        return row[0] if row else 0
    except Exception as e:
        print(f"Error getting charged count: {e}")
        return 0

async def get_approved_count():
    """Get number of approved cards"""
    try:
        row = await db.fetch_one(
            "SELECT COUNT(*) FROM checked_cards WHERE status = 'APPROVED'"
        )
        return row[0] if row else 0
    except Exception as e:
        print(f"Error getting approved count: {e}")
        return 0

async def get_all_premium_users():
    """Get all premium users"""
    try:
        rows = await db.fetch_all(
            "SELECT * FROM users WHERE is_premium = 1 ORDER BY premium_expiry DESC"
        )
        return [dict(row) for row in rows] if rows else []
    except Exception as e:
        print(f"Error getting premium users: {e}")
        return []

async def get_total_users():
    """Get total number of users"""
    try:
        row = await db.fetch_one("SELECT COUNT(*) FROM users")
        return row[0] if row else 0
    except Exception as e:
        print(f"Error getting total users: {e}")
        return 0

async def get_premium_count():
    """Get number of premium users"""
    try:
        row = await db.fetch_one("SELECT COUNT(*) FROM users WHERE is_premium = 1")
        return row[0] if row else 0
    except Exception as e:
        print(f"Error getting premium count: {e}")
        return 0

async def get_total_sites_count():
    """Get total number of sites across all users"""
    try:
        row = await db.fetch_one("SELECT COUNT(*) FROM sites")
        return row[0] if row else 0
    except Exception as e:
        print(f"Error getting total sites: {e}")
        return 0

async def get_users_with_sites():
    """Get number of users who have sites"""
    try:
        row = await db.fetch_one("SELECT COUNT(DISTINCT user_id) FROM sites")
        return row[0] if row else 0
    except Exception as e:
        print(f"Error getting users with sites: {e}")
        return 0

async def get_sites_per_user():
    """Get site count per user"""
    try:
        rows = await db.fetch_all(
            "SELECT user_id, COUNT(*) as cnt FROM sites GROUP BY user_id"
        )
        return [dict(row) for row in rows] if rows else []
    except Exception as e:
        print(f"Error getting sites per user: {e}")
        return []

async def get_all_sites_detail():
    """Get all sites with user details"""
    try:
        rows = await db.fetch_all(
            "SELECT user_id, site FROM sites ORDER BY user_id, site"
        )
        return [dict(row) for row in rows] if rows else []
    except Exception as e:
        print(f"Error getting all sites: {e}")
        return []
