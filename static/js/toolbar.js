import { state, dom } from './state.js';
import { showToast } from './utils.js';
import { clearSelection, loadSVGString, updateSceneSummary } from './editor.js';

function readFile(file, mode) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error || new Error(`Failed to read ${file.name}`));
    if (mode === 'data-url') reader.readAsDataURL(file);
    else reader.readAsText(file);
  });
}

function setImportBusy(isBusy) {
  state.isGenerating = isBusy;
  dom.sendBtn.disabled = isBusy;
  dom.btnOpenSvg.disabled = isBusy;
  dom.btnImportImage.disabled = isBusy;
}

export async function importSvgFile(file) {
  const text = await readFile(file, 'text');
  state.svgFilename = `${file.name.replace(/\.svg$/i, '') || 'imported'}-edited.svg`;
  loadSVGString(text, {
    summary: `Imported ${file.name}`,
    planner: 'import',
    warnings: [],
  });
  showToast(`Imported ${file.name}`);
}

export async function importImageFile(file) {
  setImportBusy(true);
  try {
    const image = await readFile(file, 'data-url');
    const response = await fetch('/api/to-svg', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image,
        colors: state.importColors,
        transparent_background: true,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || response.statusText);
    state.svgFilename = `${file.name.replace(/\.[^.]+$/i, '') || 'converted'}.svg`;
    loadSVGString(data.svg, {
      summary: `Image normalized to ${data.colors ?? state.importColors} solid colors and converted to a flat SVG.`,
      planner: 'vectorize',
      warnings: data.warnings || [],
    });
    showToast(`Converted ${file.name} to SVG`);
  } finally {
    setImportBusy(false);
  }
}

export async function importFile(file) {
  if (!file) return;
  const lowerName = file.name.toLowerCase();
  if (lowerName.endsWith('.svg') || file.type === 'image/svg+xml') {
    await importSvgFile(file);
    return;
  }
  if (lowerName.endsWith('.png') || lowerName.endsWith('.jpg') || lowerName.endsWith('.jpeg') || file.type === 'image/png' || file.type === 'image/jpeg') {
    await importImageFile(file);
    return;
  }
  throw new Error('Only .svg, .png, .jpg, and .jpeg files are supported here.');
}

export async function handleSvgInputChange(event) {
  const [file] = event.target.files || [];
  event.target.value = '';
  if (!file) return;
  try {
    await importSvgFile(file);
  } catch (error) {
    showToast(error.message || 'SVG import failed', 3200);
  }
}

export async function handleImageInputChange(event) {
  const [file] = event.target.files || [];
  event.target.value = '';
  if (!file) return;
  try {
    await importImageFile(file);
  } catch (error) {
    showToast(error.message || 'Image conversion failed', 3200);
  }
}

export function setTool(tool) {
  state.currentTool = tool;
  dom.toolSelect.classList.toggle('active', tool === 'select');
  dom.toolPan.classList.toggle('active', tool === 'pan');
  dom.canvasPane.style.cursor = tool === 'pan' ? 'grab' : 'default';
  if (tool !== 'select') clearSelection();
}

export function exportSvg() {
  if (!state.svgDoc) {
    showToast('No SVG to export');
    return;
  }
  const xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(state.svgDoc);
  const blob = new Blob([xml], { type: 'image/svg+xml' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = state.svgFilename;
  link.click();
  URL.revokeObjectURL(link.href);
  showToast(`Exported ${state.svgFilename}`);
}

export function clearCanvas() {
  dom.svgContainer.innerHTML = '';
  state.svgDoc = null;
  state.currentScene = null;
  state.sceneMeta = new Map();
  state.svgFilename = 'pictogram.svg';
  clearSelection();
  dom.dropHint.style.opacity = '1';
  dom.dropHint.style.pointerEvents = 'none';
  updateSceneSummary({ scene: null, summary: 'No scene yet.', planner: 'n/a', warnings: [] });
  showToast('Canvas cleared');
}
