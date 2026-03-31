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

function groupTitle(groupKey) {
  return {
    layout_assets: 'Layout assets',
    static_environment: 'Static environment',
    dynamic_topdown: 'Dynamic top-down',
    dynamic_sideview: 'Dynamic side-view',
    props_objects: 'Props & objects',
    annotations: 'Annotations',
  }[groupKey] || groupKey.replace(/_/g, ' ');
}

function renderAssetCard(asset) {
  const card = document.createElement('div');
  card.className = 'asset-card';
  card.draggable = true;
  card.innerHTML = `
    <div class="asset-head">
      <span class="swatch" style="background:${escapeHtml(asset.defaultColor || '#94a3b8')}"></span>
      <span class="asset-name">${escapeHtml(asset.label)}</span>
    </div>
    <div class="asset-meta">${escapeHtml(asset.assetClass || asset.role || asset.kind)} · ${escapeHtml(asset.view || 'top')}</div>
    <div class="asset-desc">${escapeHtml(asset.description || asset.kind)}</div>`;
  card.addEventListener('dragstart', (event) => {
    event.dataTransfer.setData('text/plain', asset.kind);
    event.dataTransfer.effectAllowed = 'copy';
  });
  card.addEventListener('click', () => insertAsset(asset.kind, { x: DEFAULT_CANVAS.width / 2, y: DEFAULT_CANVAS.height / 2 }));
  return card;
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
  const groups = new Map();
  state.assets.forEach((asset) => {
    const key = asset.catalogGroup || 'props_objects';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(asset);
  });
  const orderedGroups = ['layout_assets', 'static_environment', 'dynamic_topdown', 'dynamic_sideview', 'props_objects', 'annotations'];
  orderedGroups.forEach((key) => {
    const assets = groups.get(key);
    if (!assets?.length) return;
    const section = document.createElement('section');
    section.className = 'asset-group';
    const header = document.createElement('div');
    header.className = 'asset-group-title';
    header.textContent = groupTitle(key);
    const grid = document.createElement('div');
    grid.className = 'asset-group-grid';
    assets.forEach((asset) => grid.appendChild(renderAssetCard(asset)));
    section.appendChild(header);
    section.appendChild(grid);
    dom.assetGrid.appendChild(section);
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
  const orientationInput = window.prompt(
    'Default facing direction for this asset? Use: right, left, up, or down',
    'right',
  );
  if (!orientationInput) return;
  const orientation = orientationInput.trim().toLowerCase();
  if (!['right', 'left', 'up', 'down'].includes(orientation)) {
    showToast('Orientation must be right, left, up, or down.', 3200);
    return;
  }

  const response = await fetch('/api/assets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: name.trim(),
      svg: serializeAssetSvg(),
      overwrite,
      orientation,
    }),
  });

  const data = await response.json();
  if (response.status === 409 && !overwrite) {
    const shouldOverwrite = window.confirm(`${name.trim()} already exists. Overwrite it?`);
    if (shouldOverwrite) {
      const retryResponse = await fetch('/api/assets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          svg: serializeAssetSvg(),
          overwrite: true,
          orientation,
        }),
      });
      const retryData = await retryResponse.json();
      if (!retryResponse.ok) {
        throw new Error(retryData.detail || retryResponse.statusText || 'Failed to overwrite asset.');
      }
      state.assets = retryData.assets || state.assets;
      await loadAssets();
      showToast(`Saved ${name.trim()} to the asset catalogue`);
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
