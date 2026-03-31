import { state, dom, DEFAULT_CANVAS } from './state.js';
import { escapeHtml, showToast } from './utils.js';
import { insertAsset } from './editor.js';

function isFullCanvasRect(node, width, height) {
  if (!node || node.tagName?.toLowerCase() !== 'rect') return false;
  const rectWidth = parseFloat(node.getAttribute('width') || '0');
  const rectHeight = parseFloat(node.getAttribute('height') || '0');
  const x = parseFloat(node.getAttribute('x') || '0');
  const y = parseFloat(node.getAttribute('y') || '0');
  return x === 0 && y === 0 && Math.abs(rectWidth - width) < 0.01 && Math.abs(rectHeight - height) < 0.01;
}

function serializeAssetSvg() {
  const clone = state.svgDoc.cloneNode(true);
  const width = parseFloat(clone.getAttribute('width') || clone.viewBox?.baseVal?.width || DEFAULT_CANVAS.width);
  const height = parseFloat(clone.getAttribute('height') || clone.viewBox?.baseVal?.height || DEFAULT_CANVAS.height);

  Array.from(clone.children).forEach((child) => {
    const label = (child.getAttribute?.('inkscape:label') || child.getAttribute?.('data-label') || '').toLowerCase();
    const id = (child.getAttribute?.('id') || '').toLowerCase();
    if (id === 'layer-background' || label === 'background') {
      child.remove();
      return;
    }
    if (isFullCanvasRect(child, width, height)) {
      child.remove();
    }
  });

  return new XMLSerializer().serializeToString(clone);
}

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

export async function saveCurrentSvgAsAsset(overwrite = false, assetName = '') {
  if (!state.svgDoc) {
    showToast('Load or generate an SVG first.', 3200);
    return;
  }

  const suggested = assetName || state.svgFilename.replace(/\.svg$/i, '').replace(/[-_]+/g, ' ').trim() || 'Custom asset';
  const name = overwrite ? assetName : window.prompt('Asset name', suggested);
  if (!name || !name.trim()) return;

  const response = await fetch('/api/assets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: name.trim(),
      svg: serializeAssetSvg(),
      overwrite,
    }),
  });

  const data = await response.json();
  if (response.status === 409 && !overwrite) {
    const shouldOverwrite = window.confirm(`${name.trim()} already exists. Overwrite it?`);
    if (shouldOverwrite) {
      return saveCurrentSvgAsAsset(true, name.trim());
    }
    return;
  }

  if (!response.ok) {
    throw new Error(data.detail || response.statusText || 'Failed to save asset.');
  }

  state.assets = data.assets || state.assets;
  await loadAssets();
  showToast(`Saved ${name.trim()} to the asset catalogue`);
}
