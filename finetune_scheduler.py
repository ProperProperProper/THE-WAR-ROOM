#!/usr/bin/env python3
"""Background scheduler for fine-tuning jobs (1AM-7AM daily window)."""
import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from finetune_service import FineTuneService

logger = logging.getLogger('war-room.finetune')

class FineTuneScheduler:
    def __init__(self, state_db_path):
        self.state_db = Path(state_db_path)
        self.state_db.parent.mkdir(parents=True, exist_ok=True)
        self.finetune = FineTuneService(Path.home() / 'Documents')
        self.running = False
        self._init_db()

    def _init_db(self):
        """Initialize training jobs database."""
        with sqlite3.connect(self.state_db) as db:
            db.execute('''
                CREATE TABLE IF NOT EXISTS training_jobs (
                    id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    data_path TEXT NOT NULL,
                    epochs INTEGER DEFAULT 1,
                    batch_size INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'pending',
                    created_at REAL,
                    started_at REAL,
                    completed_at REAL,
                    result TEXT
                )
            ''')

    def queue_training(self, job_id, model, data_path, epochs=1, batch_size=1):
        """Queue a training job for the next 1AM-7AM window."""
        with sqlite3.connect(self.state_db) as db:
            db.execute('''
                INSERT OR REPLACE INTO training_jobs
                (id, model, data_path, epochs, batch_size, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
            ''', (job_id, model, data_path, epochs, batch_size, time.time()))
        logger.info(f'Queued training job {job_id}: {model} on {data_path}')
        return {'queued': True, 'job_id': job_id}

    def in_training_window(self):
        """Check if current time is within 1AM-7AM window."""
        now = datetime.now()
        hour = now.hour
        return 1 <= hour < 7

    def get_pending_jobs(self):
        """Get all pending training jobs."""
        with sqlite3.connect(self.state_db) as db:
            rows = db.execute(
                'SELECT id, model, data_path, epochs, batch_size FROM training_jobs WHERE status = ?',
                ('pending',)
            ).fetchall()
        return [
            {'id': r[0], 'model': r[1], 'data_path': r[2], 'epochs': r[3], 'batch_size': r[4]}
            for r in rows
        ]

    def update_job_status(self, job_id, status, result=None):
        """Update job status and result."""
        with sqlite3.connect(self.state_db) as db:
            timestamp = time.time()
            if status == 'running':
                db.execute(
                    'UPDATE training_jobs SET status = ?, started_at = ? WHERE id = ?',
                    (status, timestamp, job_id)
                )
            elif status == 'completed':
                db.execute(
                    'UPDATE training_jobs SET status = ?, completed_at = ?, result = ? WHERE id = ?',
                    (status, timestamp, json.dumps(result), job_id)
                )
            else:
                db.execute(
                    'UPDATE training_jobs SET status = ?, result = ? WHERE id = ?',
                    (status, json.dumps(result), job_id)
                )

    def process_jobs(self):
        """Process pending training jobs during the window."""
        if not self.in_training_window():
            return

        jobs = self.get_pending_jobs()
        if not jobs:
            return

        for job in jobs:
            try:
                logger.info(f'Starting training job {job["id"]}')
                self.update_job_status(job['id'], 'running')

                result = self.finetune.fine_tune_omlx(
                    job['model'],
                    job['data_path'],
                    epochs=job['epochs'],
                    batch_size=job['batch_size']
                )

                if 'success' in result:
                    self.update_job_status(job['id'], 'completed', result)
                    logger.info(f'Training job {job["id"]} completed successfully')
                else:
                    self.update_job_status(job['id'], 'failed', result)
                    logger.error(f'Training job {job["id"]} failed: {result.get("error")}')
            except Exception as e:
                logger.error(f'Training job {job["id"]} error: {e}')
                self.update_job_status(job['id'], 'failed', {'error': str(e)})

    def run(self):
        """Background scheduler thread."""
        self.running = True
        logger.info('Fine-tuning scheduler started (1AM-7AM window)')

        while self.running:
            try:
                self.process_jobs()
            except Exception as e:
                logger.error(f'Scheduler error: {e}')

            # Check every 5 minutes
            time.sleep(300)

    def start(self):
        """Start scheduler in background thread."""
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread

    def stop(self):
        """Stop the scheduler."""
        self.running = False
        logger.info('Fine-tuning scheduler stopped')
