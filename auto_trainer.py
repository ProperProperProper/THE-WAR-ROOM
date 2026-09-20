#!/usr/bin/env python3
"""Auto-train oMLX whenever new files are added to inbox."""
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
import subprocess
import sys

class AutoTrainer:
    def __init__(self, inbox_path, check_interval=30):
        self.inbox = Path(inbox_path)
        self.check_interval = check_interval
        self.state_file = self.inbox.parent / '.autotrainer_state.json'
        self.file_hashes = self._load_state()
        self.log_file = Path.home() / '.war-room-state' / 'autotrainer.log'
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_state(self):
        """Load saved file hashes."""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except:
                return {}
        return {}

    def _save_state(self):
        """Save file hashes."""
        self.state_file.write_text(json.dumps(self.file_hashes, indent=2))

    def _log(self, msg):
        """Log message."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {msg}"
        print(log_msg)
        with open(self.log_file, 'a') as f:
            f.write(log_msg + '\n')

    def _get_file_hash(self, path):
        """Get file hash."""
        try:
            content = path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except:
            return None

    def _scan_files(self):
        """Find all code files in inbox."""
        extensions = {'.py', '.js', '.ts', '.md', '.yml', '.yaml', '.json', '.txt'}
        skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build'}

        files = []
        for ext in extensions:
            for f in self.inbox.rglob(f'*{ext}'):
                if not any(skip in f.parts for skip in skip_dirs):
                    files.append(f)
        return sorted(set(files))

    def _detect_changes(self):
        """Detect new or modified files."""
        current_files = self._scan_files()
        current_hashes = {}
        changes = False

        for fpath in current_files:
            fhash = self._get_file_hash(fpath)
            if fhash:
                current_hashes[str(fpath)] = fhash

                # Check if new or modified
                if str(fpath) not in self.file_hashes or self.file_hashes[str(fpath)] != fhash:
                    self._log(f"📝 Changed: {fpath.relative_to(self.inbox.parent)}")
                    changes = True

        # Check for deleted files
        for fpath in self.file_hashes:
            if fpath not in current_hashes:
                self._log(f"🗑 Deleted: {Path(fpath).relative_to(self.inbox.parent)}")
                changes = True

        self.file_hashes = current_hashes
        self._save_state()
        return changes

    def _auto_train(self):
        """Automatically train oMLX."""
        self._log("🚀 AUTO-TRAINING TRIGGERED")

        try:
            result = subprocess.run(
                ['curl', '-s', '-X', 'POST', 'http://127.0.0.1:8765/api/finetune/train-inbox',
                 '-H', 'Content-Type: application/json',
                 '-H', 'Origin: http://127.0.0.1:8765',
                 '-d', '{"epochs": 5, "batch_size": 1}'],
                capture_output=True,
                text=True,
                timeout=300
            )

            resp = json.loads(result.stdout)
            if resp.get('success'):
                examples = resp.get('examples', 0)
                adapter = resp.get('adapter', '').split('/')[-1]
                self._log(f"✅ Training complete: {examples} examples → {adapter}")
            else:
                error = resp.get('error', 'Unknown error')
                self._log(f"❌ Training failed: {error}")
        except Exception as e:
            self._log(f"❌ Error: {str(e)}")

    def run(self):
        """Main loop."""
        self._log("🤖 Auto-Trainer started")
        self._log(f"📁 Watching: {self.inbox}")
        self._log(f"⏱ Check interval: {self.check_interval}s")

        try:
            while True:
                if self._detect_changes():
                    self._auto_train()
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            self._log("⏹ Auto-Trainer stopped")

if __name__ == '__main__':
    inbox = Path.home() / 'Downloads' / 'EthLadder-Training-Inbox'
    trainer = AutoTrainer(inbox, check_interval=30)
    trainer.run()
