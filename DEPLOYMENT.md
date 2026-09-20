# War Room Deployment & Auto-Startup

## Overview

The War Room is a multi-provider LLM controller that integrates **oMLX** (local), **Ollama/Mistral** (local), and **Claude/Codex** (cloud). This guide covers setup, auto-startup on machine restart, and troubleshooting.

## Quick Start

### Manual Startup
```bash
cd /Users/local.local/Documents/Codex/2026-09-20/i-x20/outputs/war-room
python3 server.py --no-browser
# Access: http://127.0.0.1:8765
```

### Auto-Startup on Machine Restart

War Room is configured to start automatically in the correct sequence when your Mac restarts:

1. **oMLX** (port 8000) — Local ML inference engine
2. **Ollama** (port 11434) — Mistral model server  
3. **War Room** (port 8765) — Web controller

**Status:** ✅ Already configured. No action needed.

**Location:** LaunchAgent at `~/Library/LaunchAgents/com.warroom.complete.plist`

To verify auto-startup is enabled:
```bash
launchctl list | grep com.warroom
# Should show: "1281    0    com.warroom.complete"
```

## System Architecture

### Running Services

| Service | Port | Purpose | Memory |
|---------|------|---------|--------|
| oMLX | 8000 | Local model inference | 150MB |
| Ollama | 11434 | Mistral model hosting | 4.8GB |
| War Room | 8765 | Web controller | 80MB |

### Startup Sequence

The startup script (`/Users/local.local/bin/war-room-startup.sh`) handles the orchestration:

```
1. Start oMLX → wait for port 8000 to respond
   ↓
2. Start Ollama → wait for port 11434 to respond
   ↓  
3. Start War Room → wait for port 8765 to respond
   ↓
✓ All services ready
```

Each service has a 30-second timeout. If a service doesn't respond, startup continues anyway.

## Provider Configuration

### oMLX (Local)
- **Model:** Auto-detects available model in oMLX
- **Default:** claude-3-5-sonnet-20241022 (if Qwen too large for memory)
- **Max tokens:** 32,000 thinking depth
- **Thinking:** Full extended reasoning

**Dynamic Model Detection:**
The `omlx_mcp.py` file now queries the oMLX API to detect which model is actually loaded, instead of hardcoding a model that may not fit in memory. This ensures War Room always uses whatever model oMLX can actually serve.

```python
# Automatically detects the loaded model
MODEL = _get_loaded_model()  # Queries /v1/models endpoint
```

### Ollama (Local)
- **Model:** mistral:latest (4.4GB)
- **Port:** 11434
- **Max tokens:** 8,000 thinking depth

To load a different model:
```bash
ollama pull mistral:latest
# or another model
ollama pull llama2
```

### Claude (Cloud)
- **Model:** haiku (default), requires Anthropic API key
- **Auth:** Sign in via Claude Code app
- **Token Cache:** Enabled for cost optimization

### Codex (Cloud)  
- **Model:** gpt-4-like inference
- **Auth:** ChatGPT subscription required
- **Auto-Approve:** Enabled for seamless execution

## Environment Variables

Optional configuration via environment variables:

```bash
# oMLX
export OMLX_HOST="127.0.0.1"          # Default
export OMLX_PORT="8000"               # Default
export OMLX_KEY="omlx"                # Default
export OMLX_MODEL="auto-detect"       # Auto-detects from API (2026-09-20 feature)

# Ollama
export OLLAMA_HOST="127.0.0.1:11434"  # Default

# War Room
export WARROOM_PORT="8765"            # Default
```

## Database

**Location:** `~/.state/state.sqlite3` (relative to war-room directory)

**Tables:**
- `runs` — Task history and execution state
- `providers` — Health status cache
- `llm_context` — Per-workspace, per-LLM conversation storage

**Storage estimate:** ~10MB per 1000 tasks

## Logs

After startup, check logs for any issues:

```bash
# Overall startup
tail -f /tmp/war-room-startup.log

# Service-specific logs
tail -f /tmp/omlx.log              # oMLX logs
tail -f /tmp/ollama.log            # Ollama logs  
tail -f /tmp/war-room.log          # War Room logs
tail -f ~/Documents/.war-room-debug.log  # Debug logs
```

## Manual Service Control

### Start/Stop Individual Services

```bash
# oMLX
/Users/local.local/.omlx/bin/omlx serve --port 8000 &
pkill -f "omlx serve"

# Ollama
ollama serve &
pkill -f "ollama serve"

# War Room  
cd /Users/local.local/Documents/Codex/2026-09-20/i-x20/outputs/war-room
python3 server.py --no-browser &
pkill -f "server.py --no-browser"
```

### Restart All Services

```bash
/Users/local.local/bin/war-room-startup.sh
```

### Restart Via LaunchAgent

```bash
# Unload
launchctl unload ~/Library/LaunchAgents/com.warroom.complete.plist

# Load  
launchctl load ~/Library/LaunchAgents/com.warroom.complete.plist

# Check status
launchctl list | grep com.warroom
```

## Troubleshooting

### "Model not loaded" / oMLX shows unavailable

**Problem:** War Room says oMLX model isn't available.

**Solution:** oMLX dynamically detects which model is loaded. If it shows "Model not loaded", check what's actually available:

```bash
curl -s http://127.0.0.1:8000/v1/models | python3 -m json.tool
# Shows: {"object":"list","data":[{"id":"claude-3-5-sonnet-20241022",...}]}
```

If oMLX isn't responding:
```bash
# Restart oMLX
pkill -f "omlx serve"
/Users/local.local/.omlx/bin/omlx serve --port 8000 &
```

### Ollama not responding

**Problem:** "Ollama server not running on localhost:11434"

**Solution:**
```bash
# Check if running
ps aux | grep ollama

# Restart
pkill -f "ollama serve"
ollama serve &
sleep 5

# Verify
curl -s http://127.0.0.1:11434/api/tags | python3 -m json.tool
```

### War Room doesn't auto-start

**Problem:** After restart, War Room isn't running.

**Solution:**
```bash
# Check LaunchAgent is loaded
launchctl list | grep com.warroom

# If missing, load it
launchctl load ~/Library/LaunchAgents/com.warroom.complete.plist

# Check logs for startup errors
tail -f /tmp/war-room-startup.log
tail -f /tmp/war-room-startup-error.log
```

### Memory pressure / system slow

War Room can use significant memory when all services are running:
- oMLX: ~150MB
- Ollama + Mistral: ~4.8GB
- War Room: ~80MB
- **Total: ~5GB**

If memory is tight:
```bash
# Stop Ollama (frees 4.8GB)
pkill -f "ollama serve"

# War Room will fall back to Claude automatically
# (requires valid Claude subscription)
```

## Production Deployment Notes

### Memory Constraints
- **Recommended:** 16GB+ RAM
- **Minimum:** 8GB (Ollama disabled, Claude-only mode)
- **Qwen2.5-Coder-7B:** Requires 8GB free (7.9GB model + overhead)

### Cloud Provider Authentication
- **Claude:** Sign in via Claude Code app (`~/.local/bin/claude auth`)
- **Codex:** ChatGPT subscription required

### Security
- War Room runs locally on 127.0.0.1 (localhost only)
- No credentials stored in repository (all via `.env` or app auth)
- API calls are local-only except to cloud providers

### Monitoring
```bash
# Check all services are up
netstat -an | grep -E "8000|11434|8765" | grep LISTEN

# Monitor processes
watch -n 2 'ps aux | grep -E "omlx|ollama|server.py"'

# Check provider health via API
curl -s http://127.0.0.1:8765/api/state | python3 -m json.tool | grep -A 30 '"providers"'
```

## Version History

### 2026-09-20
- ✅ **New:** Auto-startup LaunchAgent with sequential service launch
- ✅ **Fixed:** oMLX now dynamically detects loaded model instead of hardcoding
- ✅ **Updated:** Deployment documentation
- ✅ **Status:** All providers working, auto-startup on restart enabled

### Earlier Versions
- Initial War Room release with multi-provider routing
- MCP architecture implementation
- Context persistence and auto-compact
- Fine-tuning support for oMLX and Mistral

## Support

For issues or questions:
1. Check logs in `/tmp/` and `~/Documents/.war-room-debug.log`
2. Verify provider health via `curl http://127.0.0.1:8765/api/state`
3. Review service status with `netstat -an | grep LISTEN`
