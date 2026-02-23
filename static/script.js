/**
 * Meta Agent CX — Frontend Logic
 *
 * Handles:
 *  - User input and form submission
 *  - API calls to the backend
 *  - Rendering of agent config (persona, flow, functions, JSON)
 *  - Tab navigation and clipboard copy
 *  - Toast notifications
 */

// ── DOM Elements ──
const userPrompt = document.getElementById('user-prompt');
const languageSelect = document.getElementById('language-select');
const platformSelect = document.getElementById('platform-select');
const createBtn = document.getElementById('create-btn');
const btnText = document.getElementById('btn-text');
const btnSpinner = document.getElementById('btn-spinner');
const outputPanel = document.getElementById('output-panel');
const statsBar = document.getElementById('stats-bar');

// ── State ──
let currentData = null;

// ━━━━━━━━━━━━━━━━━━━━━━━━ Quick Prompts ━━━━━━━━━━━━━━━━━━━━━━━━

document.querySelectorAll('.quick-prompt-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    userPrompt.value = chip.dataset.prompt;
    userPrompt.focus();
    // Visual pulse
    userPrompt.style.borderColor = 'var(--accent-primary)';
    setTimeout(() => { userPrompt.style.borderColor = ''; }, 800);
  });
});

// ━━━━━━━━━━━━━━━━━━━━━━━━ Create Agent ━━━━━━━━━━━━━━━━━━━━━━━━

createBtn.addEventListener('click', handleCreate);

async function handleCreate() {
  const prompt = userPrompt.value.trim();
  if (!prompt) {
    showToast('Please describe the agent you want to create.', 'error');
    userPrompt.focus();
    return;
  }
  if (prompt.length < 10) {
    showToast('Please provide a more detailed description (at least 10 characters).', 'error');
    return;
  }

  setLoading(true);

  try {
    const response = await fetch('/api/create-agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_prompt: prompt,
        language: languageSelect.value,
        platform: platformSelect.value,
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `Server error (${response.status})`);
    }

    const data = await response.json();
    currentData = data;
    renderOutput(data);
    showToast(`✅ Agent "${data.agent_config?.persona?.name || 'Agent'}" created successfully!`, 'success');

  } catch (error) {
    console.error('Error creating agent:', error);
    showToast(`❌ ${error.message}`, 'error');
  } finally {
    setLoading(false);
  }
}

function setLoading(loading) {
  createBtn.disabled = loading;
  btnText.textContent = loading ? 'Generating...' : '🚀 Generate CX Agent';
  btnSpinner.style.display = loading ? 'block' : 'none';
}

// ━━━━━━━━━━━━━━━━━━━━━━━━ Render Output ━━━━━━━━━━━━━━━━━━━━━━━━

function renderOutput(data) {
  outputPanel.style.display = 'block';
  outputPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const config = data.agent_config;
  if (!config) return;

  // Stats
  renderStats(config);

  // Tabs
  renderPersonaTab(config);
  renderFlowTab(config);
  renderFunctionsTab(config);
  renderToolsTab(data.openai_tools_schema || []);
  renderFullJsonTab(data);
}

// ── Stats ──
function renderStats(config) {
  const intents = config.intents?.length || 0;
  const functions = config.functions?.length || 0;
  const nodes = config.conversation_flow?.nodes?.length || 0;
  const slots = new Set();
  (config.conversation_flow?.nodes || []).forEach(n => {
    if (n.collect_slot) slots.add(n.collect_slot);
  });

  statsBar.innerHTML = `
    <div class="stat-card">
      <div class="stat-value">${intents}</div>
      <div class="stat-label">Intents</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${functions}</div>
      <div class="stat-label">Functions</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${nodes}</div>
      <div class="stat-label">Flow Nodes</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${slots.size}</div>
      <div class="stat-label">Data Slots</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${config.status?.toUpperCase() || 'DRAFT'}</div>
      <div class="stat-label">Status</div>
    </div>
  `;
}

// ── Persona Tab ──
function renderPersonaTab(config) {
  const p = config.persona || {};
  const v = config.voice || {};
  const firstLetter = (p.name || 'A')[0].toUpperCase();

  const traitsHTML = (p.personality_traits || [])
    .map(t => `<span class="trait-badge">${t}</span>`)
    .join('');

  document.getElementById('tab-persona').innerHTML = `
    <div class="persona-preview">
      <div class="persona-avatar">${firstLetter}</div>
      <div class="persona-info">
        <div class="persona-name">${escHtml(p.name || 'Agent')}</div>
        <div class="persona-role">${escHtml(p.role || 'Customer Support Agent')}</div>
        <div class="persona-traits">${traitsHTML}</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap">
          <span class="voice-badge">🎙 ${escHtml(v.voice_id || 'default')} · ${escHtml(v.gender || 'female')}</span>
          <span class="voice-badge">🌐 ${escHtml(v.language || 'en-US')}</span>
          <span class="voice-badge">🔊 ${v.speaking_rate || 1.0}x</span>
        </div>
      </div>
    </div>

    <div class="system-prompt-box">
      <div class="system-prompt-label">System Prompt (LLM Instructions)</div>
      <div class="system-prompt-text">${escHtml(p.system_prompt || '')}</div>
    </div>

    <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:20px;">
      <div class="system-prompt-box" style="margin-top:0">
        <div class="system-prompt-label">Fallback Message</div>
        <div class="system-prompt-text">${escHtml(p.fallback_message || '')}</div>
      </div>
      <div class="system-prompt-box" style="margin-top:0">
        <div class="system-prompt-label">Escalation Message</div>
        <div class="system-prompt-text">${escHtml(p.escalation_message || '')}</div>
      </div>
    </div>
  `;
}

// ── Flow Tab ──
function renderFlowTab(config) {
  const flow = config.conversation_flow;
  if (!flow || !flow.nodes?.length) {
    document.getElementById('tab-flow').innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🔀</div>
        <div class="empty-state-text">No conversation flow generated.</div>
      </div>`;
    return;
  }

  // Build ordered nodes starting from entry
  const nodeMap = {};
  flow.nodes.forEach(n => { nodeMap[n.node_id] = n; });

  const visited = new Set();
  const ordered = [];

  function traverse(nodeId) {
    if (visited.has(nodeId) || !nodeMap[nodeId]) return;
    visited.add(nodeId);
    ordered.push(nodeMap[nodeId]);
    const node = nodeMap[nodeId];
    (node.transitions || []).forEach(t => traverse(t.target_node_id));
  }
  traverse(flow.entry_node_id);

  // Add any unvisited nodes
  flow.nodes.forEach(n => {
    if (!visited.has(n.node_id)) ordered.push(n);
  });

  const nodeIcons = {
    greeting: '👋', collect_info: '📝', api_call: '🌐',
    decision: '🔀', response: '💬', confirm: '✅',
    transfer: '📞', end: '🔚', fallback: '⚠️',
  };

  let html = '<div class="flow-container">';
  ordered.forEach((node, i) => {
    const icon = nodeIcons[node.type] || '⬛';
    const delay = i * 60;
    html += `
      <div class="flow-node" style="animation-delay:${delay}ms">
        <div class="flow-node-icon ${node.type}">${icon}</div>
        <div class="flow-node-content">
          <div class="flow-node-label">${escHtml(node.label)}</div>
          <div class="flow-node-type">${node.type}${node.collect_slot ? ' · slot: ' + node.collect_slot : ''}${node.function_call ? ' · fn: ' + node.function_call : ''}</div>
          ${node.prompt_text ? `<div class="flow-node-prompt">"${escHtml(node.prompt_text)}"</div>` : ''}
        </div>
      </div>`;

    // Connector
    if (i < ordered.length - 1) {
      const transitions = node.transitions || [];
      const labels = transitions.map(t => t.condition).join(' / ');
      html += `
        <div class="flow-connector">
          ${labels ? `<span class="flow-connector-label">${escHtml(labels)}</span>` : ''}
        </div>`;
    }
  });
  html += '</div>';

  document.getElementById('tab-flow').innerHTML = html;
}

// ── Functions Tab ──
function renderFunctionsTab(config) {
  const functions = config.functions || [];
  if (!functions.length) {
    document.getElementById('tab-functions').innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">⚡</div>
        <div class="empty-state-text">No functions defined.</div>
      </div>`;
    return;
  }

  let html = '';
  functions.forEach(fn => {
    const params = (fn.parameters || [])
      .map(p => `<span class="param-badge">${escHtml(p.name)}: ${p.type}</span>`)
      .join('');

    const ep = fn.api_endpoint;
    const methodClass = ep ? `method-${ep.method.toLowerCase()}` : '';

    html += `
      <div class="function-card">
        <div class="function-name">${escHtml(fn.name)}()</div>
        <div class="function-desc">${escHtml(fn.description || '')}</div>
        <div class="function-params">${params}</div>
        ${ep ? `
          <div class="endpoint-badge">
            <span class="method-badge ${methodClass}">${ep.method}</span>
            ${escHtml(ep.url)}
          </div>
        ` : ''}
        ${fn.mock_response ? `
          <details style="margin-top:12px">
            <summary style="cursor:pointer; color:var(--text-muted); font-size:0.82rem">
              Mock Response
            </summary>
            <pre class="json-output" style="margin-top:8px; font-size:0.78rem">${syntaxHighlight(JSON.stringify(fn.mock_response, null, 2))}</pre>
          </details>
        ` : ''}
      </div>`;
  });

  document.getElementById('tab-functions').innerHTML = html;
}

// ── OpenAI Tools Tab ──
function renderToolsTab(tools) {
  const el = document.getElementById('tab-tools');
  if (!tools?.length) {
    el.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🔧</div>
        <div class="empty-state-text">No OpenAI tool schemas generated.</div>
      </div>`;
    return;
  }

  const jsonStr = JSON.stringify(tools, null, 2);
  el.innerHTML = `
    <button class="copy-btn" onclick="copyToClipboard(this, 'tools-json')">📋 Copy</button>
    <pre class="json-output" id="tools-json">${syntaxHighlight(jsonStr)}</pre>`;
}

// ── Full JSON Tab ──
function renderFullJsonTab(data) {
  const el = document.getElementById('tab-full-json');
  const jsonStr = JSON.stringify(data, null, 2);
  el.innerHTML = `
    <button class="copy-btn" onclick="copyToClipboard(this, 'full-json-output')">📋 Copy</button>
    <pre class="json-output" id="full-json-output">${syntaxHighlight(jsonStr)}</pre>`;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━ Tab Navigation ━━━━━━━━━━━━━━━━━━━━━━━━

document.getElementById('output-tabs').addEventListener('click', (e) => {
  const tab = e.target.closest('.output-tab');
  if (!tab) return;

  document.querySelectorAll('.output-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

  tab.classList.add('active');
  const panelId = `tab-${tab.dataset.tab}`;
  document.getElementById(panelId)?.classList.add('active');
});

// ━━━━━━━━━━━━━━━━━━━━━━━━ Utilities ━━━━━━━━━━━━━━━━━━━━━━━━

function escHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

function syntaxHighlight(json) {
  if (typeof json !== 'string') json = JSON.stringify(json, null, 2);
  json = escHtml(json);
  return json.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?|null)/g,
    match => {
      let cls = 'json-number';
      if (/^"/.test(match)) {
        cls = /:$/.test(match) ? 'json-key' : 'json-string';
      } else if (/true|false/.test(match)) {
        cls = 'json-boolean';
      } else if (/null/.test(match)) {
        cls = 'json-null';
      }
      return `<span class="${cls}">${match}</span>`;
    }
  );
}

function copyToClipboard(btn, sourceId) {
  const el = document.getElementById(sourceId);
  if (!el) return;
  const text = el.textContent;
  navigator.clipboard.writeText(text).then(() => {
    btn.classList.add('copied');
    btn.textContent = '✅ Copied!';
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.textContent = '📋 Copy';
    }, 2000);
  });
}

function showToast(message, type = 'success') {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━ Keyboard Shortcut ━━━━━━━━━━━━━━━━━━━━━━━━

userPrompt.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    createBtn.click();
  }
});
