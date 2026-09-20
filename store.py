"""SQLite store for War Room state, runs, and LLM context."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS providers (name TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS llm_context (workspace TEXT, llm TEXT, data TEXT, PRIMARY KEY(workspace, llm))')
        for run in self.runs():
            if run['state'] in ('running', 'queued'):
                run['state'] = 'paused'
                run['detail'] = 'App restarted. Review the task and resume.'
                self.save(run)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, run):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO runs VALUES (?,?)', (run['id'], json.dumps(run)))

    def get(self, ident):
        with self.db() as db:
            row = db.execute('SELECT data FROM runs WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('Task not found')
        return json.loads(row[0])

    def runs(self):
        with self.db() as db:
            rows = db.execute('SELECT data FROM runs').fetchall()
        return sorted([json.loads(row[0]) for row in rows], key=lambda r: r['created'], reverse=True)

    def provider(self, name, data=None):
        with self.db() as db:
            if data is not None:
                db.execute('INSERT OR REPLACE INTO providers VALUES (?,?)', (name, json.dumps(data)))
            row = db.execute('SELECT data FROM providers WHERE name=?', (name,)).fetchone()
        return json.loads(row[0]) if row else {'state': 'unknown', 'detail': 'Not checked yet', 'retry_at': None}

    def llm_context(self, workspace, llm, data=None):
        with self.db() as db:
            if data is not None:
                db.execute('INSERT OR REPLACE INTO llm_context VALUES (?,?,?)', (workspace, llm, json.dumps(data)))
            row = db.execute('SELECT data FROM llm_context WHERE workspace=? AND llm=?', (workspace, llm)).fetchone()
        return json.loads(row[0]) if row else {'messages': [], 'summary': ''}

    def clear_llm_context(self, workspace, llm=None):
        with self.db() as db:
            if llm:
                db.execute('DELETE FROM llm_context WHERE workspace=? AND llm=?', (workspace, llm))
            else:
                db.execute('DELETE FROM llm_context WHERE workspace=?', (workspace,))
