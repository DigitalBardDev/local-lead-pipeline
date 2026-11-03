import sqlite3
import json
from pathlib import Path
from core.utils import _acquire_lock, _release_lock
from core.models import Lead
from modules.base_module import BaseModule

class ExportSQLite(BaseModule):
    name: str = "ExportSQLite"
    """
    Exports leads to a local SQLite database so they never leave the user's computer.
    This database powers the Results Viewer tab in the Desktop App.
    """
    supports_concurrency = False

    def __init__(self, config: dict = None):
        super().__init__(config)
        db_filename = self.config.get("sqlite_filename", "leads_database.db")
        self.db_path = Path("output") / db_filename
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # Create table if it doesn't exist
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                website TEXT UNIQUE,
                phone TEXT,
                address TEXT,
                score INTEGER,
                audit_results_json TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def process(self, lead: Lead) -> Lead:
        if not lead.website_url:
            return lead
            
        score = lead.html_score
        audit_json = json.dumps(lead.to_supabase_dict())
        
        lock_file = str(self.db_path) + ".lock"
        _acquire_lock(lock_file)
        try:
            # Upsert based on website
            self.cursor.execute('''
                INSERT INTO leads (name, website, phone, address, score, audit_results_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(website) DO UPDATE SET
                    name=excluded.name,
                    phone=excluded.phone,
                    address=excluded.address,
                    score=excluded.score,
                    audit_results_json=excluded.audit_results_json,
                    timestamp=CURRENT_TIMESTAMP
            ''', (lead.business_name, lead.website_url, lead.phone, lead.location, score, audit_json))
            
            self.conn.commit()
        finally:
            _release_lock(lock_file)
            
        return lead
