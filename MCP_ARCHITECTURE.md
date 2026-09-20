# MCP Architecture - THE WAR ROOM

## Overview
The War Room now uses Model Context Protocol (MCP) for all LLM interactions, providing a clean abstraction layer for provider management, context storage, and routing.

## Architecture

### Components

**1. MCP Server (`mcp_server.py`)**
- Standalone Python process handling all LLM communications
- Manages provider selection and fallback routing
- Handles context storage/retrieval
- Supports auto-compacting after tasks

**2. Controller (`controller.py`)**
- Launches and manages the MCP server subprocess
- Communicates via JSON-RPC over stdin/stdout
- Routes all LLM queries through MCP calls
- Manages task state and health probes

**3. Store (`store.py`)**
- Shared SQLite database backend
- Stores runs, provider health, and LLM context
- Thread-safe with WAL mode for concurrent access
- Imported by both controller and MCP server

**4. Providers (`providers.py`)**
- Adapter functions for Claude, Codex, oMLX
- Context-aware prompting (retrieves previous interactions)
- Auto-saves context after each response
- Session management with auto-compacting

## MCP Methods

### query
```json
{"method": "query", "params": {"prompt": "...", "workspace": "...", "llm": "claude", "store_context": true}}
```
Query a specific LLM with optional context retrieval.

### health
```json
{"method": "health", "params": {"llm": "claude"}}
```
Check provider health status.

### context
```json
{"method": "context", "params": {"workspace": "...", "llm": "claude"}}
```
Retrieve stored context for an LLM.

### clear_context
```json
{"method": "clear_context", "params": {"workspace": "...", "llm": "claude"}}
```
Clear context for specific LLM or all LLMs.

### compact
```json
{"method": "compact", "params": {"workspace": "...", "llm": "claude"}}
```
Compact stored context (called automatically after task completion).

## Data Flow

```
War Room UI
    ↓
Controller.route()
    ↓
Controller.mcp_call()
    ↓
MCP Server (subprocess)
    ├→ Retrieve context from Store
    ├→ Call adapter (claude/codex/omlx)
    ├→ Save new context to Store
    └→ Return response
    ↓
Controller receives answer
```

## Benefits

- **Abstraction**: Easy to add new providers (Bedrock, Vertex, etc.) without changing core logic
- **Separation of Concerns**: LLM logic isolated in MCP server
- **Context Efficiency**: Only summaries sent in subsequent calls, saving tokens
- **Auto-Compacting**: Sessions remain efficient by keeping last 5 interactions after task completion
- **Standardization**: Follows MCP protocol for extensibility

## Session Behavior

- **Claude**: Haiku + auto-compact + prompt-cache
- **Codex**: Auto-approve + session persistence + auto-compact
- **oMLX**: Max 32k thinking + auto-compact
- **Context**: Last 20 interactions per LLM per workspace, compacted to 5 after task completion

## Starting the War Room

The MCP server starts automatically when the Controller initializes. No manual intervention needed.

```bash
python3 server.py
```

The server launches MCP as a subprocess, which begins listening on stdin for requests.
