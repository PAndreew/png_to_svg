import { state, dom } from './state.js';
import { showToast } from './utils.js';
import { loadSVGString, syncSceneFromCanvas, updateSceneSummary } from './editor.js';

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
    appendMessage('assistant', `Error: ${error.message}`);
    showToast('Generation failed', 3000);
  } finally {
    state.isGenerating = false;
    dom.sendBtn.disabled = false;
  }
}
