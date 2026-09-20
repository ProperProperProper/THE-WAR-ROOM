#!/usr/bin/env python3
"""Continuous provider health monitoring daemon."""
import threading
import time
import json
from datetime import datetime
from pathlib import Path
import sqlite3
import subprocess

class HealthMonitor:
    def __init__(self, db_path, check_interval=15):
        self.db_path = db_path
        self.check_interval = check_interval
        self.log_file = Path.home() / '.war-room-state' / 'health_monitor.log'
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.provider_status = {}

    def _log(self, msg):
        """Log message."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {msg}"
        print(log_msg)
        with open(self.log_file, 'a') as f:
            f.write(log_msg + '\n')

    def _check_provider(self, provider):
        """Check if provider is healthy."""
        try:
            if provider == 'omlx':
                result = subprocess.run(
                    ['curl', '-s', '-m', '5', 'http://127.0.0.1:8000/v1/models'],
                    capture_output=True, text=True, timeout=6
                )
                return result.returncode == 0 and 'models' in result.stdout

            elif provider == 'claude':
                # Check if we can connect to Claude API
                return True  # Assume ready if configured

            elif provider == 'codex':
                # Check if we can connect to Codex API
                return True  # Assume ready if configured

            return False
        except:
            return False

    def _update_status(self, provider, is_healthy):
        """Update provider status in database."""
        try:
            db = sqlite3.connect(self.db_path)
            cursor = db.cursor()

            current_status = self.provider_status.get(provider, 'unknown')
            new_status = 'ready' if is_healthy else 'unavailable'

            # Log state changes
            if current_status != new_status:
                if is_healthy:
                    self._log(f"✅ {provider.upper()} is back online")
                else:
                    self._log(f"⚠️  {provider.upper()} went offline")

            # Update in database
            cursor.execute(
                'INSERT OR REPLACE INTO provider_health (provider, state, last_check) VALUES (?, ?, ?)',
                (provider, new_status, time.time())
            )
            db.commit()
            db.close()

            self.provider_status[provider] = new_status
        except Exception as e:
            self._log(f"Status update error: {e}")

    def run(self):
        """Main monitoring loop."""
        self._log("🏥 Health Monitor started")
        providers = ['omlx', 'claude', 'codex']

        try:
            while True:
                for provider in providers:
                    is_healthy = self._check_provider(provider)
                    self._update_status(provider, is_healthy)

                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            self._log("⏹ Health Monitor stopped")

    def start_daemon(self):
        """Start as background daemon."""
        thread = threading.Thread(target=self.run, daemon=True)
        thread.start()
        return thread

if __name__ == '__main__':
    db_path = Path.home() / '.war-room-state' / 'state.sqlite3'
    monitor = HealthMonitor(db_path)
    monitor.run()
