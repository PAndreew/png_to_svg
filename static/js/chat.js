import { state, dom } from './state.js';
import { escapeHtml, showToast } from './utils.js';
import { loadSVGString, syncSceneFromCanvas, updateSceneSummary } from './editor.js';

function formatJsonBlock(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? '');
  }
}

function buildElementChangeSummary(beforeLayout, finalScene) {
  const beforeElements = new Map((beforeLayout?.elements || []).map((element) => [element.id, element]));
  const finalElements = finalScene?.elements || [];
  const changes = [];

  finalElements.forEach((element) => {
    const before = beforeElements.get(element.id);
    if (!before) {
      changes.push(`added ${element.kind} at (${Math.round(element.x)}, ${Math.round(element.y)})`);
      return;
    }
    const moved = Math.abs((before.x ?? 0) - (element.x ?? 0)) > 0.5 || Math.abs((before.y ?? 0) - (element.y ?? 0)) > 0.5;
    const rotated = Math.abs((before.rotation ?? 0) - (element.rotation ?? 0)) > 0.5;
    const relayered = (before.layer ?? 0) !== (element.layer ?? 0);
    if (!moved && !rotated && !relayered) return;

    const parts = [element.kind];
    if (moved) parts.push(`move (${Math.round(before.x ?? 0)}, ${Math.round(before.y ?? 0)}) → (${Math.round(element.x ?? 0)}, ${Math.round(element.y ?? 0)})`);
    if (rotated) parts.push(`rot ${Math.round(before.rotation ?? 0)}° → ${Math.round(element.rotation ?? 0)}°`);
    if (relayered) parts.push(`layer ${before.layer ?? 0} → ${element.layer ?? 0}`);
    changes.push(parts.join(' · '));
  });

  return changes;
}

function updatePlannerTrace(data) {
  state.plannerTrace = data || null;
  if (!dom.plannerTrace) return;
  if (!data) {
    dom.plannerTrace.innerHTML = '<div class="hint">No planner output yet.</div>';
    return;
  }

  const planner = data.planner || 'unknown';
  const rawScene = data.plannerRawScene;
  const rawText = data.plannerRawText;
  const layoutPlan = data.plannerLayoutPlan;
  const assetResolution = data.plannerAssetResolution;
  const beforeLayout = data.sceneBeforeLayout;
  const finalScene = data.scene;
  const parts = [
    `<div class="trace-row"><strong>Planner:</strong> ${planner}</div>`,
    `<div class="trace-row"><strong>Fallback:</strong> ${data.fallbackUsed ? 'yes' : 'no'}</div>`,
    `<div class="trace-row"><strong>Symbolic layout plan:</strong> ${data.plannerUsedLayoutPlan ? 'yes' : 'no'}</div>`,
  ];

  if (layoutPlan) {
    parts.push('<div class="trace-label">Symbolic layout plan</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(layoutPlan))}</pre>`);
  }

  if (assetResolution) {
    parts.push('<div class="trace-label">Asset resolution</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(assetResolution))}</pre>`);
  }

  if (rawScene) {
    parts.push('<div class="trace-label">Raw planner scene</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(rawScene))}</pre>`);
  } else if (rawText) {
    parts.push('<div class="trace-label">Raw planner text</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(String(rawText))}</pre>`);
  } else {
    parts.push('<div class="hint">No raw LLM planner output for this generation.</div>');
  }

  if (beforeLayout) {
    parts.push('<div class="trace-label">Scene before layout solver</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(beforeLayout))}</pre>`);
  }

  if (finalScene) {
    const changes = buildElementChangeSummary(beforeLayout, finalScene);
    if (changes.length) {
      parts.push('<div class="trace-label">Layout solver changes</div>');
      parts.push(`<div class="trace-list">${changes.map((item) => `<div class="trace-item">${escapeHtml(item)}</div>`).join('')}</div>`);
    } else {
      parts.push('<div class="trace-label">Layout solver changes</div>');
      parts.push('<div class="hint">No position, rotation, or layer changes were applied.</div>');
    }
    parts.push('<div class="trace-label">Final scene after layout solver</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(finalScene))}</pre>`);
  }

  dom.plannerTrace.innerHTML = parts.join('');
}

export function appendMessage(role, content, meta = []) {
  const wrapper = document.createElement('div');
  wrapper.className = `msg ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = content;
  wrapper.appendChild(bubble);
  if (meta.length) {
    const metaLine = document.createElement('div');
    metaLine.className = 'meta-line';
    meta.forEach((item) => {
      const chip = document.createElement('span');
      chip.className = `chip ${item.warning ? 'warning' : ''}`;
      chip.textContent = item.text;
      metaLine.appendChild(chip);
    });
    wrapper.appendChild(metaLine);
  }
  dom.messages.appendChild(wrapper);
  dom.messages.scrollTop = dom.messages.scrollHeight;
  return wrapper;
}

export function appendSpinner(text) {
  const wrapper = document.createElement('div');
  wrapper.className = 'msg assistant';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  const spinner = document.createElement('div');
  spinner.className = 'spinner';
  spinner.textContent = text;
  bubble.appendChild(spinner);
  wrapper.appendChild(bubble);
  dom.messages.appendChild(wrapper);
  dom.messages.scrollTop = dom.messages.scrollHeight;
  return wrapper;
}

export async function sendPrompt() {
  const prompt = dom.promptInput.value.trim();
  if (!prompt || state.isGenerating) return;
  state.isGenerating = true;
  dom.sendBtn.disabled = true;
  dom.promptInput.value = '';
  dom.promptInput.style.height = 'auto';
  appendMessage('user', prompt);
  const spinner = appendSpinner('Generating structured scene...');
  try {
    const response = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt,
        history: state.history,
        current_scene: syncSceneFromCanvas(),
        planner: 'auto',
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || response.statusText);
    spinner.remove();
    if (data.scene) state.currentScene = data.scene;
    updatePlannerTrace(data);
    loadSVGString(data.svg, data);
    state.history.push({ role: 'user', content: prompt });
    state.history.push({ role: 'assistant', content: data.summary || '[scene generated]' });
    const chips = [
      { text: `planner: ${data.planner}` },
      { text: data.mode === 'fallback-image' ? 'image fallback' : 'structured render', warning: data.mode === 'fallback-image' },
    ];
    (data.warnings || []).slice(0, 2).forEach((warning) => chips.push({ text: warning, warning: true }));
    appendMessage('assistant', data.summary || 'Scene rendered on canvas.', chips);
    state.svgFilename = `${(prompt.slice(0, 32).replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'pictogram')}.svg`;
    showToast(data.mode === 'fallback-image' ? 'Fallback render applied' : 'Scene rendered on canvas');
  } catch (error) {
    spinner.remove();
    updatePlannerTrace(null);
    appendMessage('assistant', `Error: ${error.message}`);
    showToast('Generation failed', 3000);
  } finally {
    state.isGenerating = false;
    dom.sendBtn.disabled = false;
  }
}
