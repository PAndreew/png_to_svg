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
  const toolTrace = data.plannerToolTrace;
  const geometryDraft = data.plannerGeometryDraft;
  const firstPassScene = data.firstPassScene;
  const firstPassPng = data.firstPassPng;
  const reviewRawJson = data.reviewRawJson;
  const reviewRawText = data.reviewRawText;
  const reviewApplied = data.reviewApplied;
  const reviewSummary = data.reviewSummary;
  const stageLog = data.stageLog;
  const beforeLayout = data.sceneBeforeLayout;
  const finalScene = data.scene;
  const parts = [
    `<div class="trace-row"><strong>Planner:</strong> ${planner}</div>`,
    `<div class="trace-row"><strong>Fallback:</strong> ${data.fallbackUsed ? 'yes' : 'no'}</div>`,
    `<div class="trace-row"><strong>Hybrid layout plan:</strong> ${data.plannerUsedLayoutPlan ? 'yes' : 'no'}</div>`,
    `<div class="trace-row"><strong>Review applied:</strong> ${reviewApplied ? 'yes' : 'no'}</div>`,
  ];

  if (stageLog?.length) {
    parts.push('<div class="trace-label">Generation stages</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(stageLog))}</pre>`);
  }

  if (layoutPlan) {
    parts.push('<div class="trace-label">Hybrid layout plan</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(layoutPlan))}</pre>`);
  }

  if (assetResolution) {
    parts.push('<div class="trace-label">Asset resolution</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(assetResolution))}</pre>`);
  }

  if (geometryDraft) {
    parts.push('<div class="trace-label">Geometry phase draft</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(geometryDraft))}</pre>`);
  }

  if (toolTrace && toolTrace.length) {
    parts.push('<div class="trace-label">Planner tool trace</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(toolTrace))}</pre>`);
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

  if (firstPassScene) {
    parts.push('<div class="trace-label">First pass scene</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(firstPassScene))}</pre>`);
  }

  if (firstPassPng) {
    parts.push('<div class="trace-label">First pass preview</div>');
    parts.push(`<div class="trace-preview"><img class="trace-preview-image" src="${escapeHtml(firstPassPng)}" alt="First pass preview"></div>`);
  }

  if (reviewRawJson) {
    parts.push('<div class="trace-label">Review result</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(formatJsonBlock(reviewRawJson))}</pre>`);
  } else if (reviewRawText) {
    parts.push('<div class="trace-label">Review raw text</div>');
    parts.push(`<pre class="trace-pre">${escapeHtml(String(reviewRawText))}</pre>`);
  }

  if (reviewSummary) {
    parts.push(`<div class="trace-row"><strong>Review summary:</strong> ${escapeHtml(reviewSummary)}</div>`);
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

export function appendImageMessage(label, src) {
  if (!src) return null;
  const wrapper = document.createElement('div');
  wrapper.className = 'msg assistant preview-msg';
  const bubble = document.createElement('div');
  bubble.className = 'bubble preview-bubble';
  const caption = document.createElement('div');
  caption.className = 'preview-label';
  caption.textContent = label;
  const image = document.createElement('img');
  image.className = 'preview-image';
  image.alt = label;
  image.src = src;
  bubble.appendChild(caption);
  bubble.appendChild(image);
  wrapper.appendChild(bubble);
  dom.messages.appendChild(wrapper);
  dom.messages.scrollTop = dom.messages.scrollHeight;
  return wrapper;
}

function startGenerationStageSpinner(spinner) {
  const stages = ['fetching assets', 'generating first pass', 'reviewing', 'final render'];
  let index = 0;
  spinner.querySelector('.spinner').textContent = stages[index];
  const interval = window.setInterval(() => {
    index = Math.min(index + 1, stages.length - 1);
    const target = spinner.querySelector('.spinner');
    if (target) target.textContent = stages[index];
  }, 1800);
  return () => window.clearInterval(interval);
}

export async function sendPrompt() {
  const prompt = dom.promptInput.value.trim();
  if (!prompt || state.isGenerating) return;
  state.isGenerating = true;
  dom.sendBtn.disabled = true;
  dom.promptInput.value = '';
  dom.promptInput.style.height = 'auto';
  appendMessage('user', prompt);
  const spinner = appendSpinner('fetching assets');
  const stopStageSpinner = startGenerationStageSpinner(spinner);
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
    stopStageSpinner();
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
    if (data.reviewApplied) chips.push({ text: 'review revised pass' });
    else if (data.reviewRawJson || data.reviewRawText) chips.push({ text: 'review completed' });
    (data.warnings || []).slice(0, 2).forEach((warning) => chips.push({ text: warning, warning: true }));
    if (data.firstPassPng) appendImageMessage('First pass preview', data.firstPassPng);
    appendMessage('assistant', data.summary || 'Scene rendered on canvas.', chips);
    state.svgFilename = `${(prompt.slice(0, 32).replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'pictogram')}.svg`;
    showToast(data.mode === 'fallback-image' ? 'Fallback render applied' : 'Scene rendered on canvas');
  } catch (error) {
    stopStageSpinner();
    spinner.remove();
    updatePlannerTrace(null);
    appendMessage('assistant', `Error: ${error.message}`);
    showToast('Generation failed', 3000);
  } finally {
    state.isGenerating = false;
    dom.sendBtn.disabled = false;
  }
}
