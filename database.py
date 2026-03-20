import os
import aiosqlite
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

async def init_db():
    """Initialize the database connection and create tables"""
    await db.connect()
