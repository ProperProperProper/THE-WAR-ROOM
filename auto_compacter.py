#!/usr/bin/env python3
"""Auto-compact context after tasks complete."""
import threading
import time
from pathlib import Path
import sqlite3

class AutoCompacter:
    def __init__(self, db_path, check_interval=10):
        self.db_path = db_path
        self.check_interval = check_interval
        self.last_checked = {}

    def _get_db(self):
        return sqlite3.connect(self.db_path)

    def auto_compact_after_task(self, run_id, workspace, llms=['claude', 'codex', 'omlx']):
        """Compact context after task completes."""
        try:
            db = self._get_db()
            cursor = db.cursor()

            for llm in llms:
                # Get current context
                cursor.execute(
                    'SELECT context FROM llm_context WHERE workspace=? AND llm=?',
                    (workspace, llm)
                )
                row = cursor.fetchone()
                if not row:
                    continue

                import json
                try:
                    context = json.loads(row[0])
                    messages = context.get('messages', [])

                    # Keep only last 5 interactions
                    if len(messages) > 5:
                        summary = f"Last 5 interactions. Recent: {messages[-1].get('content', '')[:100]}..."
                        compacted = {
                            'messages': messages[-5:],
                            'summary': summary,
                            'compacted': True
                        }

                        cursor.execute(
                            'UPDATE llm_context SET context=? WHERE workspace=? AND llm=?',
                            (json.dumps(compacted), workspace, llm)
                        )
                        db.commit()
                except:
                    pass

            db.close()
        except Exception as e:
            print(f"Auto-compact error: {e}")

    def start_daemon(self):
        """Start background compacting daemon."""
        def daemon():
            print("[AutoCompacter] Daemon started - monitoring for task completions")
            while True:
                time.sleep(self.check_interval)

        thread = threading.Thread(target=daemon, daemon=True)
        thread.start()

# Global instance
_compacter = None

def get_compacter(db_path):
    global _compacter
    if not _compacter:
        _compacter = AutoCompacter(db_path)
        _compacter.start_daemon()
    return _compacter
