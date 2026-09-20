'use strict';

const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let state = null;
let connected = false;
let isWaiting = false;
const providerNames = { omlx: 'oMLX', codex: 'Codex', claude: 'Claude' };

async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Request failed');
  return body;
}

function notice(text) {
  const el = $('notice');
  el.textContent = text;
  el.hidden = !text;
}

function addMessage(role, text, provider = null) {
  const container = $('chat-messages');
  const msg = document.createElement('div');
  msg.className = `message ${role}`;

  const label = document.createElement('div');
  label.className = 'message-label';
  if (role === 'user') label.textContent = 'You';
  else if (provider) label.textContent = providerNames[provider] || provider;
  else label.textContent = 'Assistant';

  const content = document.createElement('div');
  content.className = 'message-content';
  content.textContent = text;

  msg.appendChild(label);
  msg.appendChild(content);
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
}

function addLoading() {
  const container = $('chat-messages');
  const msg = document.createElement('div');
  msg.className = 'message assistant loading';
  msg.id = 'loading-indicator';

  const label = document.createElement('div');
  label.className = 'message-label';
  label.textContent = 'Thinking...';

  const content = document.createElement('div');
  content.className = 'loading';
  content.innerHTML = '<span></span><span></span><span></span>';

  msg.appendChild(label);
  msg.appendChild(content);
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
}

function removeLoading() {
  const indicator = $('loading-indicator');
  if (indicator) indicator.remove();
}

function detectProvider(text) {
  const lower = text.toLowerCase();
  if (/\b(use|with|via|using)\s+(claude|anthropic)\b/.test(lower)) return 'claude-only';
  if (/\b(use|with|via|using)\s+(codex|chatgpt|openai)\b/.test(lower)) return 'codex-only';
  if (/\b(use|with|via|using)\s+(omlx|local|offline)\b/.test(lower)) return 'omlx-only';
  return null;
}

function updateProviderStatus() {
  if (!state) return;

  const providers = ['omlx', 'claude', 'codex'];
  providers.forEach(name => {
    const el = $(`status-${name}`);
    if (!el) return;

    const p = state.providers[name] || { state: 'unknown' };
    const isReady = p.state === 'ready';

    el.className = `status-indicator ${isReady ? 'ready' : ''}`;
    el.textContent = `● ${providerNames[name]}`;
  });
}

async function submitMessage() {
  const input = $('prompt');
  const text = input.value.trim();

  if (!text || isWaiting) return;

  // Add user message
  addMessage('user', text);

  // Detect provider or use selected
  const detectedProvider = detectProvider(text);
  const mode = detectedProvider || $('route').value;

  // Clear input
  input.value = '';
  input.focus();

  // Set waiting state
  isWaiting = true;
  input.disabled = true;

  try {
    addLoading();

    // Submit to War Room
    const result = await api('/api/run', {
      prompt: text,
      workspace: '',
      mode: mode,
      tools: $('tools').checked
    });

    // Wait for response
    let attempts = 0;
    const maxAttempts = 60;
    while (attempts < maxAttempts) {
      await new Promise(r => setTimeout(r, 500));

      // Check state for response
      const newState = await api('/api/state', undefined);
      const task = newState.runs.find(r => r.id === result.id);

      if (task && task.messages && task.messages.length > 0) {
        const lastMessage = task.messages[task.messages.length - 1];
        if (lastMessage.role === 'assistant' || lastMessage.provider) {
          removeLoading();
          addMessage('assistant', lastMessage.text, lastMessage.provider);
          break;
        }
      }

      attempts++;
    }

    if (attempts >= maxAttempts) {
      removeLoading();
      addMessage('assistant', 'No response received');
    }

    notice('');
  } catch (error) {
    removeLoading();
    addMessage('assistant', `Error: ${error.message}`);
    notice(error.message);
  } finally {
    isWaiting = false;
    input.disabled = false;
    input.focus();
  }
}

async function refresh() {
  try {
    state = await api('/api/state', undefined);
    connected = true;
    updateProviderStatus();
  } catch (error) {
    connected = false;
    notice(error.message);
  }
}

// Setup event listeners
$('chat-form').onsubmit = (e) => {
  e.preventDefault();
  submitMessage();
};

$('prompt').onkeydown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    submitMessage();
  }
};

// Initialize
(async () => {
  const token = new URLSearchParams(location.hash.slice(1)).get('token');
  if (token) {
    history.replaceState(null, '', location.pathname);
    try {
      await api('/api/unlock', { token });
    } catch (error) {
      notice(error.message);
      return;
    }
  }

  await refresh();
  setInterval(refresh, 3000);

  // Focus input on load
  $('prompt').focus();
})();
