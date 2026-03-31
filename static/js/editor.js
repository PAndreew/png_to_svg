import { state, dom, SVG_NS, DEFAULT_CANVAS } from './state.js';
import { escapeHtml, randomId, showToast, assetMarkup } from './utils.js';

export function parseTransform(el) {
  const text = (el.getAttribute('transform') || '').trim();
  const parsed = {
    translate: { x: 0, y: 0 },
    rotate: { angle: 0, cx: 0, cy: 0 },
    scale: { x: 1, y: 1 },
    skewX: 0,
    skewY: 0,
  };
  const translate = text.match(/translate\(([-\d.]+)(?:[ ,]([-.\d]+))?\)/);
  if (translate) {
    parsed.translate.x = parseFloat(translate[1]) || 0;
    parsed.translate.y = parseFloat(translate[2]) || 0;
  }
  const rotate = text.match(/rotate\(([-\d.]+)(?:[ ,]([-.\d]+)[ ,]([-.\d]+))?\)/);
  if (rotate) {
    parsed.rotate.angle = parseFloat(rotate[1]) || 0;
    parsed.rotate.cx = parseFloat(rotate[2]) || 0;
    parsed.rotate.cy = parseFloat(rotate[3]) || 0;
  }
  const scale = text.match(/scale\(([-\d.]+)(?:[ ,]([-.\d]+))?\)/);
  if (scale) {
    parsed.scale.x = parseFloat(scale[1]) || 1;
    parsed.scale.y = parseFloat(scale[2] || scale[1]) || 1;
  }
  const skewX = text.match(/skewX\(([-\d.]+)\)/);
  const skewY = text.match(/skewY\(([-\d.]+)\)/);
  if (skewX) parsed.skewX = parseFloat(skewX[1]) || 0;
  if (skewY) parsed.skewY = parseFloat(skewY[1]) || 0;
  return parsed;
}

export function serializeTransform(values) {
  const parts = [];
  if (values.translate) parts.push(`translate(${values.translate.x.toFixed(2)} ${values.translate.y.toFixed(2)})`);
  if (values.rotate) parts.push(`rotate(${values.rotate.angle.toFixed(2)} ${values.rotate.cx.toFixed(2)} ${values.rotate.cy.toFixed(2)})`);
  if (values.scale) parts.push(`scale(${values.scale.x.toFixed(4)} ${values.scale.y.toFixed(4)})`);
  if (values.skewX) parts.push(`skewX(${values.skewX.toFixed(2)})`);
  if (values.skewY) parts.push(`skewY(${values.skewY.toFixed(2)})`);
  return parts.join(' ').trim();
}

export function scenePointFromClient(clientX, clientY) {
  const rect = dom.canvasPane.getBoundingClientRect();
  return {
    x: (clientX - rect.left - state.panX) / state.zoom,
    y: (clientY - rect.top - state.panY) / state.zoom,
  };
}

export function composeTransform(meta) {
  if (meta.transform) return meta.transform;
  const x = meta.x ?? 512;
  const y = meta.y ?? 384;
  const rotation = meta.rotation ?? 0;
  const scale = meta.scale ?? 1;
  return `translate(${Number(x).toFixed(2)} ${Number(y).toFixed(2)}) rotate(${Number(rotation).toFixed(2)} 0 0) scale(${Number(scale).toFixed(4)} ${Number(scale).toFixed(4)})`;
}

export function applyViewport() {
  dom.svgContainer.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
  dom.overlay.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
  dom.zoomLabel.textContent = `${Math.round(state.zoom * 100)}%`;
  drawHandles();
}

export function setZoom(nextZoom, cx, cy) {
  const old = state.zoom;
  state.zoom = Math.max(0.08, Math.min(10, nextZoom));
  const paneRect = dom.canvasPane.getBoundingClientRect();
  const px = cx ?? paneRect.width / 2;
  const py = cy ?? paneRect.height / 2;
  state.panX = px - (px - state.panX) * (state.zoom / old);
  state.panY = py - (py - state.panY) * (state.zoom / old);
  applyViewport();
}

export function fitToWindow() {
  if (!state.svgDoc) return;
  const pane = dom.canvasPane.getBoundingClientRect();
  const width = parseFloat(state.svgDoc.getAttribute('width')) || state.svgDoc.viewBox.baseVal.width || DEFAULT_CANVAS.width;
  const height = parseFloat(state.svgDoc.getAttribute('height')) || state.svgDoc.viewBox.baseVal.height || DEFAULT_CANVAS.height;
  state.zoom = Math.min((pane.width - 40) / width, (pane.height - 40) / height);
  state.panX = (pane.width - width * state.zoom) / 2;
  state.panY = (pane.height - height * state.zoom) / 2;
  applyViewport();
}

export function getBBox(el) {
  try { return el.getBBox(); } catch { return { x: 0, y: 0, width: 0, height: 0 }; }
}

export function svgPoint(x, y, ctm) {
  const point = state.svgDoc.createSVGPoint();
  point.x = x;
  point.y = y;
  return point.matrixTransform(ctm);
}

export function drawHandles() {
  dom.overlay.innerHTML = '';
  if (!state.selectedEl || !state.svgDoc) return;
  const bbox = getBBox(state.selectedEl);
  if (!bbox.width && !bbox.height) return;
  const ctm = state.selectedEl.getCTM?.();
  if (!ctm) return;
  const tl = svgPoint(bbox.x, bbox.y, ctm);
  const tr = svgPoint(bbox.x + bbox.width, bbox.y, ctm);
  const br = svgPoint(bbox.x + bbox.width, bbox.y + bbox.height, ctm);
  const bl = svgPoint(bbox.x, bbox.y + bbox.height, ctm);
  const tm = svgPoint(bbox.x + bbox.width / 2, bbox.y, ctm);
  const bm = svgPoint(bbox.x + bbox.width / 2, bbox.y + bbox.height, ctm);
  const ml = svgPoint(bbox.x, bbox.y + bbox.height / 2, ctm);
  const mr = svgPoint(bbox.x + bbox.width, bbox.y + bbox.height / 2, ctm);
  const center = svgPoint(bbox.x + bbox.width / 2, bbox.y + bbox.height / 2, ctm);
  const rotatePoint = { x: tm.x, y: tm.y - 28 };

  const box = document.createElementNS(SVG_NS, 'polygon');
  box.setAttribute('points', `${tl.x},${tl.y} ${tr.x},${tr.y} ${br.x},${br.y} ${bl.x},${bl.y}`);
  box.setAttribute('class', 'sel-box');
  dom.overlay.appendChild(box);

  const stem = document.createElementNS(SVG_NS, 'line');
  stem.setAttribute('x1', String(tm.x));
  stem.setAttribute('y1', String(tm.y));
  stem.setAttribute('x2', String(rotatePoint.x));
  stem.setAttribute('y2', String(rotatePoint.y));
  stem.setAttribute('class', 'rotate-stem');
  dom.overlay.appendChild(stem);

  const handles = [
    { point: tl, type: 'resize', rx: -1, ry: -1 },
    { point: tr, type: 'resize', rx: 1, ry: -1 },
    { point: br, type: 'resize', rx: 1, ry: 1 },
    { point: bl, type: 'resize', rx: -1, ry: 1 },
    { point: tm, type: 'resize', rx: 0, ry: -1 },
    { point: bm, type: 'resize', rx: 0, ry: 1 },
    { point: ml, type: 'resize', rx: -1, ry: 0 },
    { point: mr, type: 'resize', rx: 1, ry: 0 },
    { point: { x: (tm.x + tr.x) / 2, y: (tm.y + tr.y) / 2 }, type: 'skew', axis: 'x' },
    { point: { x: (tl.x + ml.x) / 2, y: (tl.y + ml.y) / 2 }, type: 'skew', axis: 'y' },
    { point: rotatePoint, type: 'rotate', center },
  ];

  handles.forEach((handle) => {
    const rect = document.createElementNS(SVG_NS, 'rect');
    rect.setAttribute('x', String(handle.point.x - 5));
    rect.setAttribute('y', String(handle.point.y - 5));
    rect.setAttribute('width', '10');
    rect.setAttribute('height', '10');
    rect.setAttribute('class', `handle ${handle.type}`);
    rect.addEventListener('mousedown', (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (handle.type === 'resize') startResize(event, handle, bbox);
      if (handle.type === 'skew') startSkew(event, handle);
      if (handle.type === 'rotate') startRotate(event, handle.center);
    });
    dom.overlay.appendChild(rect);
  });
}

export function syncSelectedMeta() {
  if (!state.selectedEl?.classList?.contains('scene-asset')) return;
  const id = state.selectedEl.getAttribute('data-scene-id');
  if (!id) return;
  const meta = state.sceneMeta.get(id) || {};
  state.sceneMeta.set(id, {
    ...meta,
    id,
    kind: state.selectedEl.getAttribute('data-kind') || meta.kind,
    label: state.selectedEl.getAttribute('data-label') || meta.label,
    transform: state.selectedEl.getAttribute('transform') || '',
  });
  syncSceneFromCanvas();
}

export function startDrag(event, el) {
  const start = { x: event.clientX, y: event.clientY };
  const initial = parseTransform(el);
  function onMove(moveEvent) {
    const dx = (moveEvent.clientX - start.x) / state.zoom;
    const dy = (moveEvent.clientY - start.y) / state.zoom;
    el.setAttribute('transform', serializeTransform({
      ...initial,
      translate: { x: initial.translate.x + dx, y: initial.translate.y + dy },
    }));
    syncSelectedMeta();
    drawHandles();
  }
  function onUp() {
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  }
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
}

export function startResize(event, handle, bbox) {
  const start = { x: event.clientX, y: event.clientY };
  const initial = parseTransform(state.selectedEl);
  function onMove(moveEvent) {
    const dx = (moveEvent.clientX - start.x) / state.zoom;
    const dy = (moveEvent.clientY - start.y) / state.zoom;
    const next = { ...initial, scale: { ...initial.scale } };
    if (handle.rx) next.scale.x = Math.max(0.2, initial.scale.x + (handle.rx * dx) / Math.max(40, bbox.width));
    if (handle.ry) next.scale.y = Math.max(0.2, initial.scale.y + (handle.ry * dy) / Math.max(40, bbox.height));
    state.selectedEl.setAttribute('transform', serializeTransform(next));
    syncSelectedMeta();
    drawHandles();
  }
  function onUp() {
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  }
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
}

export function startSkew(event, handle) {
  const start = { x: event.clientX, y: event.clientY };
  const initial = parseTransform(state.selectedEl);
  function onMove(moveEvent) {
    const dx = (moveEvent.clientX - start.x) / state.zoom;
    const dy = (moveEvent.clientY - start.y) / state.zoom;
    const next = { ...initial };
    if (handle.axis === 'x') next.skewX = initial.skewX + dx * 0.35;
    if (handle.axis === 'y') next.skewY = initial.skewY + dy * 0.35;
    state.selectedEl.setAttribute('transform', serializeTransform(next));
    syncSelectedMeta();
    drawHandles();
  }
  function onUp() {
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  }
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
}

export function startRotate(event, center) {
  const paneRect = dom.canvasPane.getBoundingClientRect();
  const initial = parseTransform(state.selectedEl);
  const startAngle = Math.atan2(
    event.clientY - (center.y * state.zoom + state.panY + paneRect.top),
    event.clientX - (center.x * state.zoom + state.panX + paneRect.left)
  );
  function onMove(moveEvent) {
    const currentAngle = Math.atan2(
      moveEvent.clientY - (center.y * state.zoom + state.panY + paneRect.top),
      moveEvent.clientX - (center.x * state.zoom + state.panX + paneRect.left)
    );
    const delta = (currentAngle - startAngle) * 180 / Math.PI;
    state.selectedEl.setAttribute('transform', serializeTransform({
      ...initial,
      rotate: { angle: initial.rotate.angle + delta, cx: 0, cy: 0 },
    }));
    syncSelectedMeta();
    drawHandles();
  }
  function onUp() {
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseup', onUp);
  }
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
}

export function selectElement(el) {
  state.selectedEl = el;
  drawHandles();
  renderProps(el);
}

export function clearSelection() {
  state.selectedEl = null;
  dom.overlay.innerHTML = '';
  renderProps(null);
}

export function updateSceneSummary(payload = {}) {
  const scene = payload.scene || state.currentScene;
  const summary = payload.summary || (scene ? 'Scene ready.' : 'No scene yet.');
  const warnings = payload.warnings || scene?.warnings || [];
  const planner = payload.planner || (scene ? 'manual' : 'n/a');
  dom.sceneSummary.innerHTML = '';

  const title = document.createElement('div');
  title.textContent = summary;
  dom.sceneSummary.appendChild(title);

  const meta = document.createElement('div');
  meta.className = 'meta-line';
  const plannerChip = document.createElement('span');
  plannerChip.className = 'chip';
  plannerChip.textContent = `planner: ${planner}`;
  meta.appendChild(plannerChip);
  if (scene?.elements) {
    const countChip = document.createElement('span');
    countChip.className = 'chip';
    countChip.textContent = `${scene.elements.length} elements`;
    meta.appendChild(countChip);
  }
  dom.sceneSummary.appendChild(meta);

  warnings.slice(0, 4).forEach((warning) => {
    const item = document.createElement('div');
    item.className = 'hint';
    item.textContent = `⚠ ${warning}`;
    dom.sceneSummary.appendChild(item);
  });
}

export function rebuildSceneMeta(scene) {
  state.sceneMeta = new Map();
  if (!scene?.elements) return;
  scene.elements.forEach((element, index) => {
    state.sceneMeta.set(String(element.id), {
      ...element,
      layer: element.layer ?? index,
      props: { ...(element.props || {}) },
    });
  });
}

export function loadSVGString(svgText, payload = {}) {
  svgText = svgText.replace(/(xmlns:[a-z]+="[^"]*")(\s+\1)+/g, '$1');
  const parser = new DOMParser();
  const doc = parser.parseFromString(svgText, 'image/svg+xml');
  if (doc.querySelector('parsererror')) {
    showToast('SVG parse error');
    return;
  }
  doc.documentElement.removeAttribute('xmlns:xlink');
  dom.svgContainer.innerHTML = '';
  dom.svgContainer.appendChild(document.adoptNode(doc.documentElement));
  state.svgDoc = dom.svgContainer.querySelector('svg');
  if (!state.svgDoc.getAttribute('width') || !state.svgDoc.getAttribute('height')) {
    const viewBox = (state.svgDoc.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number);
    if (viewBox.length === 4 && Number.isFinite(viewBox[2]) && Number.isFinite(viewBox[3])) {
      state.svgDoc.setAttribute('width', viewBox[2]);
      state.svgDoc.setAttribute('height', viewBox[3]);
    } else {
      state.svgDoc.setAttribute('width', DEFAULT_CANVAS.width);
      state.svgDoc.setAttribute('height', DEFAULT_CANVAS.height);
      state.svgDoc.setAttribute('viewBox', `0 0 ${DEFAULT_CANVAS.width} ${DEFAULT_CANVAS.height}`);
    }
  }
  if (payload.scene) {
    state.currentScene = payload.scene;
    rebuildSceneMeta(payload.scene);
  } else {
    state.currentScene = null;
    state.sceneMeta = new Map();
  }
  attachSVGListeners();
  dom.dropHint.style.opacity = '0';
  dom.dropHint.style.pointerEvents = 'none';
  clearSelection();
  fitToWindow();
  updateSceneSummary({
    ...payload,
    scene: payload.scene || null,
    summary: payload.summary || (payload.scene ? 'Scene ready.' : 'SVG loaded on canvas.'),
    planner: payload.planner || (payload.scene ? 'manual' : 'import'),
    warnings: payload.warnings || [],
  });
}

export function ensureCanvasScene() {
  if (state.svgDoc) return;
  const blank = `<?xml version="1.0" encoding="UTF-8"?><svg xmlns="${SVG_NS}" width="${DEFAULT_CANVAS.width}" height="${DEFAULT_CANVAS.height}" viewBox="0 0 ${DEFAULT_CANVAS.width} ${DEFAULT_CANVAS.height}"><rect width="${DEFAULT_CANVAS.width}" height="${DEFAULT_CANVAS.height}" fill="${DEFAULT_CANVAS.background}"/></svg>`;
  loadSVGString(blank, { scene: { version: 'odd.scene.v1', canvas: { ...DEFAULT_CANVAS }, title: 'Untitled scene', prompt: '', warnings: [], elements: [] }, summary: 'Blank scene ready.', planner: 'manual' });
}

export function attachSVGListeners() {
  if (!state.svgDoc) return;
  const assets = state.svgDoc.querySelectorAll('.scene-asset');
  if (assets.length) {
    assets.forEach((el) => {
      el.style.cursor = 'pointer';
      el.addEventListener('mousedown', onAssetMouseDown);
    });
  } else {
    state.svgDoc.querySelectorAll('path, rect, circle, ellipse, polygon, polyline, line, image, g').forEach((el) => {
      if (el === state.svgDoc || el.parentElement?.closest('.scene-asset')) return;
      el.style.cursor = 'pointer';
      el.addEventListener('mousedown', onAssetMouseDown);
    });
  }
}

export function onAssetMouseDown(event) {
  if (state.currentTool !== 'select' || event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  const el = event.currentTarget.closest('.scene-asset') || event.currentTarget;
  selectElement(el);
  startDrag(event, el);
}

export function findEditableColor(el) {
  const fill = el.getAttribute('fill');
  if (fill && fill !== 'none' && /^#/.test(fill)) return fill;
  const child = el.querySelector('[fill]:not([fill="none"])');
  return child?.getAttribute('fill') || '#111827';
}

export function makeFieldShell(labelText) {
  const wrap = document.createElement('div');
  wrap.className = 'field';
  const label = document.createElement('label');
  label.textContent = labelText;
  wrap.appendChild(label);
  return wrap;
}

export function makeTextField(label, value, onChange) {
  const wrap = makeFieldShell(label);
  const input = document.createElement('input');
  input.type = 'text';
  input.value = value;
  input.onchange = () => onChange(input.value.trim());
  wrap.appendChild(input);
  return wrap;
}

export function makeColorField(label, value, onChange) {
  const wrap = makeFieldShell(label);
  const input = document.createElement('input');
  input.type = 'color';
  input.value = value;
  input.oninput = () => onChange(input.value);
  wrap.appendChild(input);
  return wrap;
}

export function makeRangeField(label, value, min, max, step, onChange) {
  const wrap = makeFieldShell(label);
  const input = document.createElement('input');
  input.type = 'range';
  input.min = min;
  input.max = max;
  input.step = step;
  input.value = value;
  const hint = document.createElement('div');
  hint.className = 'hint';
  hint.textContent = `${value}`;
  input.oninput = () => {
    hint.textContent = `${input.value}`;
    onChange(input.value);
  };
  wrap.appendChild(input);
  wrap.appendChild(hint);
  return wrap;
}

export function makeSelectField(label, value, options, onChange) {
  const wrap = makeFieldShell(label);
  const select = document.createElement('select');
  options.forEach((option) => {
    const item = document.createElement('option');
    item.value = option;
    item.textContent = option;
    item.selected = option === value;
    select.appendChild(item);
  });
  select.onchange = () => onChange(select.value);
  wrap.appendChild(select);
  return wrap;
}

export function renderProps(el) {
  dom.propsBody.innerHTML = '';
  if (!el) {
    dom.propsBody.className = 'hint';
    dom.propsBody.textContent = 'Select an asset or shape to edit it.';
    return;
  }
  dom.propsBody.className = '';
  const assetId = el.getAttribute('data-scene-id');
  const meta = assetId ? state.sceneMeta.get(assetId) : null;
  const container = document.createElement('div');
  container.style.display = 'flex';
  container.style.flexDirection = 'column';
  container.style.gap = '10px';

  if (meta) {
    container.appendChild(makeTextField('Label', meta.label || '', (value) => {
      meta.label = value || meta.kind;
      el.setAttribute('data-label', meta.label);
      state.sceneMeta.set(assetId, meta);
      syncSceneFromCanvas();
    }));
    container.appendChild(makeColorField('Color', meta.color || '#2563eb', (value) => {
      meta.color = value;
      state.sceneMeta.set(assetId, meta);
      rerenderAsset(el);
      syncSceneFromCanvas();
    }));
    if (meta.kind === 'arrow') {
      container.appendChild(makeSelectField('Arrow style', meta.props?.style || 'straight', ['straight', 'left', 'right', 'merge', 'uturn'], (value) => {
        meta.props = { ...(meta.props || {}), style: value };
        state.sceneMeta.set(assetId, meta);
        rerenderAsset(el);
        syncSceneFromCanvas();
      }));
    }
    const transform = parseTransform(el);
    container.appendChild(makeRangeField('Rotation', transform.rotate.angle, -180, 180, 1, (value) => {
      const next = parseTransform(el);
      next.rotate.angle = Number(value);
      el.setAttribute('transform', serializeTransform(next));
      syncSelectedMeta();
      drawHandles();
    }));
  } else {
    container.appendChild(makeColorField('Fill', findEditableColor(el), (value) => {
      el.setAttribute('fill', value);
    }));
  }

  const buttons = document.createElement('div');
  buttons.className = 'button-stack';
  const resetButton = document.createElement('button');
  resetButton.className = 'btn';
  resetButton.textContent = 'Reset transform';
  resetButton.onclick = () => {
    el.setAttribute('transform', 'translate(512.00 384.00) rotate(0.00 0.00 0.00) scale(1.0000 1.0000)');
    syncSelectedMeta();
    drawHandles();
  };
  buttons.appendChild(resetButton);
  container.appendChild(buttons);
  dom.propsBody.appendChild(container);
}

export function rerenderAsset(el) {
  if (!el?.classList?.contains('scene-asset')) return;
  const id = el.getAttribute('data-scene-id');
  const meta = state.sceneMeta.get(id);
  if (!meta) return;
  el.innerHTML = assetMarkup(meta.kind, meta);
  drawHandles();
}

export function syncSceneFromCanvas() {
  if (!state.svgDoc) return state.currentScene;
  const assets = Array.from(state.svgDoc.querySelectorAll('.scene-asset'));
  if (!assets.length) return state.currentScene;
  const elements = assets.map((el, index) => {
    const id = el.getAttribute('data-scene-id') || randomId('asset');
    const kind = el.getAttribute('data-kind') || 'placeholder';
    const label = el.getAttribute('data-label') || kind;
    const meta = state.sceneMeta.get(id) || {};
    const next = {
      ...meta,
      id,
      kind,
      label,
      layer: meta.layer ?? index,
      color: meta.color || '#2563eb',
      props: { ...(meta.props || {}) },
      transform: el.getAttribute('transform') || '',
    };
    state.sceneMeta.set(id, next);
    return next;
  });
  state.currentScene = {
    version: 'odd.scene.v1',
    canvas: {
      width: parseFloat(state.svgDoc.getAttribute('width')) || DEFAULT_CANVAS.width,
      height: parseFloat(state.svgDoc.getAttribute('height')) || DEFAULT_CANVAS.height,
      background: DEFAULT_CANVAS.background,
    },
    title: state.currentScene?.title || 'Edited scene',
    prompt: state.currentScene?.prompt || '',
    warnings: state.currentScene?.warnings || [],
    elements,
  };
  return state.currentScene;
}

export function createSceneAsset(meta) {
  ensureCanvasScene();
  const group = document.createElementNS(SVG_NS, 'g');
  group.setAttribute('class', 'scene-asset');
  group.setAttribute('data-scene-id', meta.id);
  group.setAttribute('data-kind', meta.kind);
  group.setAttribute('data-label', meta.label || meta.kind);
  group.setAttribute('transform', composeTransform(meta));
  group.innerHTML = assetMarkup(meta.kind, meta);
  state.svgDoc.appendChild(group);
  group.addEventListener('mousedown', onAssetMouseDown);
  state.sceneMeta.set(meta.id, { ...meta, props: { ...(meta.props || {}) } });
  state.currentScene = syncSceneFromCanvas();
  updateSceneSummary({ scene: state.currentScene, planner: 'manual', summary: 'Manual edit applied.' });
  dom.dropHint.style.opacity = '0';
  selectElement(group);
  showToast(`${meta.label || meta.kind} added`);
}

export function insertAsset(kind, point) {
  const asset = state.assets.find((item) => item.kind === kind) || { kind, label: kind.replaceAll('_', ' '), defaultColor: '#2563eb' };
  const meta = {
    id: randomId(kind),
    kind,
    label: asset.label,
    color: asset.defaultColor || '#2563eb',
    svgMarkup: asset.svgMarkup || '',
    x: point.x,
    y: point.y,
    rotation: 0,
    scale: ['road', 'intersection', 't_junction', 'roundabout'].includes(kind) ? 0.55 : 1,
    layer: ['road', 'intersection', 't_junction', 'roundabout'].includes(kind) ? 0 : 10,
    props: kind === 'arrow' ? { style: 'straight' } : {},
  };
  createSceneAsset(meta);
}

export function deleteSelected() {
  if (!state.selectedEl) return;
  if (state.selectedEl.classList?.contains('scene-asset')) {
    const id = state.selectedEl.getAttribute('data-scene-id');
    if (id) state.sceneMeta.delete(id);
  }
  state.selectedEl.remove();
  clearSelection();
  syncSceneFromCanvas();
  updateSceneSummary({ scene: state.currentScene, planner: 'manual', summary: 'Element removed.' });
  showToast('Deleted');
}
