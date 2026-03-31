import { state, dom } from './state.js';
import { showToast } from './utils.js';
import { clearSelection, updateSceneSummary } from './editor.js';

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
  clearSelection();
  dom.dropHint.style.opacity = '1';
  updateSceneSummary({ scene: null, summary: 'No scene yet.', planner: 'n/a', warnings: [] });
  showToast('Canvas cleared');
}
