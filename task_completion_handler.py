#!/usr/bin/env python3
"""Handle task completion events - trigger compacting and logging."""
from auto_compacter import get_compacter
from intelligent_router import get_router
from pathlib import Path

def on_task_complete(run_id, workspace, llm, success, response_time, tokens_used=0):
    """Called when a task completes - triggers all post-task automation."""
    try:
        # 1. Auto-compact context
        compacter = get_compacter(Path.home() / '.war-room-state' / 'state.sqlite3')
        compacter.auto_compact_after_task(run_id, workspace, llms=['claude', 'codex', 'omlx'])

        # 2. Record routing metrics for learning
        router = get_router(Path.home() / '.war-room-state' / 'state.sqlite3')
        if llm and success:
            router.record_execution("", llm, success, response_time, tokens_used)

        print(f"[TaskCompletion] Processed: {run_id} - compacted context, recorded metrics")
        return True
    except Exception as e:
        print(f"[TaskCompletion] Error: {e}")
        return False
