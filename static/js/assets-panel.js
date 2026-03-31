import { state, dom, DEFAULT_CANVAS } from './state.js';
import { escapeHtml } from './utils.js';
import { insertAsset } from './editor.js';

export async function loadAssets() {
  try {
    const response = await fetch('/api/assets');
    const data = await response.json();
    state.assets = data.assets || [];
  } catch {
    state.assets = [];
  }
  dom.assetGrid.innerHTML = '';
  state.assets.forEach((asset) => {
    const card = document.createElement('div');
    card.className = 'asset-card';
    card.draggable = true;
    card.innerHTML = `<div class="asset-head"><span class="swatch" style="background:${escapeHtml(asset.defaultColor || '#94a3b8')}"></span><span class="asset-name">${escapeHtml(asset.label)}</span></div><div class="asset-desc">${escapeHtml(asset.description || asset.kind)}</div>`;
    card.addEventListener('dragstart', (event) => {
      event.dataTransfer.setData('text/plain', asset.kind);
      event.dataTransfer.effectAllowed = 'copy';
    });
    card.addEventListener('click', () => insertAsset(asset.kind, { x: DEFAULT_CANVAS.width / 2, y: DEFAULT_CANVAS.height / 2 }));
    dom.assetGrid.appendChild(card);
  });
}
