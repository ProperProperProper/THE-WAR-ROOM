#!/usr/bin/env python3
"""Intelligent routing that learns which provider is best for each task type."""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
import re

class IntelligentRouter:
    def __init__(self, db_path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize routing metrics table."""
        db = sqlite3.connect(self.db_path)
        cursor = db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS routing_metrics (
                id INTEGER PRIMARY KEY,
                task_type TEXT,
                provider TEXT,
                success BOOLEAN,
                response_time REAL,
                tokens_used INTEGER,
                created_at REAL,
                UNIQUE(task_type, provider)
            )
        ''')
        db.commit()
        db.close()

    def _classify_task(self, prompt):
        """Classify task type from prompt."""
        lower_prompt = prompt.lower()

        # Documentation tasks
        if any(word in lower_prompt for word in ['document', 'explain', 'describe', 'guide', 'tutorial', 'readme']):
            return 'documentation'

        # Code analysis
        if any(word in lower_prompt for word in ['debug', 'analyze', 'review', 'check', 'test']):
            return 'analysis'

        # Code generation
        if any(word in lower_prompt for word in ['write', 'generate', 'create', 'implement', 'code', 'function']):
            return 'generation'

        # Trading/Finance
        if any(word in lower_prompt for word in ['trade', 'order', 'swap', 'price', 'liquidity', 'dex']):
            return 'trading'

        # Complex reasoning
        if any(word in lower_prompt for word in ['why', 'how', 'architecture', 'design', 'strategy']):
            return 'reasoning'

        return 'general'

    def record_execution(self, prompt, provider, success, response_time, tokens_used=0):
        """Record execution metrics for learning."""
        task_type = self._classify_task(prompt)

        try:
            db = sqlite3.connect(self.db_path)
            cursor = db.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO routing_metrics
                (task_type, provider, success, response_time, tokens_used, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (task_type, provider, success, response_time, tokens_used, datetime.now().timestamp()))

            db.commit()
            db.close()
        except Exception as e:
            print(f"Routing metric error: {e}")

    def get_best_provider(self, prompt):
        """Get best provider for this prompt based on history."""
        task_type = self._classify_task(prompt)

        try:
            db = sqlite3.connect(self.db_path)
            cursor = db.cursor()

            # Find provider with highest success rate and lowest avg response time
            cursor.execute('''
                SELECT provider,
                       COUNT(*) as attempts,
                       SUM(CAST(success AS INT)) as successes,
                       AVG(response_time) as avg_time
                FROM routing_metrics
                WHERE task_type = ?
                GROUP BY provider
                ORDER BY (CAST(SUM(success) AS FLOAT) / COUNT(*)) DESC,
                         AVG(response_time) ASC
                LIMIT 1
            ''', (task_type,))

            row = cursor.fetchone()
            db.close()

            if row:
                provider, attempts, successes, avg_time = row
                success_rate = successes / attempts if attempts > 0 else 0
                print(f"[Router] {task_type}: {provider} ({success_rate:.0%} success, {avg_time:.2f}s)")
                return provider

            return 'auto'  # Default to auto routing
        except Exception as e:
            print(f"Routing lookup error: {e}")
            return 'auto'

    def get_routing_stats(self):
        """Get statistics for all task types and providers."""
        try:
            db = sqlite3.connect(self.db_path)
            cursor = db.cursor()

            cursor.execute('''
                SELECT task_type, provider,
                       COUNT(*) as attempts,
                       SUM(CAST(success AS INT)) as successes,
                       AVG(response_time) as avg_time
                FROM routing_metrics
                GROUP BY task_type, provider
                ORDER BY task_type, avg_time ASC
            ''')

            stats = {}
            for task_type, provider, attempts, successes, avg_time in cursor.fetchall():
                if task_type not in stats:
                    stats[task_type] = []
                success_rate = successes / attempts if attempts > 0 else 0
                stats[task_type].append({
                    'provider': provider,
                    'attempts': attempts,
                    'success_rate': f"{success_rate:.0%}",
                    'avg_time': f"{avg_time:.2f}s"
                })

            db.close()
            return stats
        except Exception as e:
            print(f"Stats error: {e}")
            return {}

# Global instance
_router = None

def get_router(db_path):
    global _router
    if not _router:
        _router = IntelligentRouter(db_path)
    return _router
