import { state, dom } from './state.js';
import { applyViewport, setZoom, fitToWindow, scenePointFromClient, clearSelection, selectElement, deleteSelected, insertAsset } from './editor.js';
import { sendPrompt } from './chat.js';
import { setTool, exportSvg, clearCanvas, handleSvgInputChange, handleImageInputChange, importFile } from './toolbar.js';
import { loadAssets, saveCurrentSvgAsAsset } from './assets-panel.js';
import { appendMessage } from './chat.js';

// Wire up toolbar button events
dom.toolSelect.onclick = () => setTool('select');
dom.toolPan.onclick = () => setTool('pan');
dom.toolDelete.onclick = deleteSelected;
document.getElementById('btn-fit').onclick = fitToWindow;
document.getElementById('btn-zoom-in').onclick = () => setZoom(state.zoom * 1.2);
document.getElementById('btn-zoom-out').onclick = () => setZoom(state.zoom / 1.2);
dom.btnOpenSvg.onclick = () => dom.svgInput.click();
dom.btnImportImage.onclick = () => dom.imageInput.click();
dom.btnSaveAsset.onclick = async () => {
  try {
    await saveCurrentSvgAsAsset();
  } catch (error) {
    appendMessage('assistant', `Error: ${error.message}`);
  }
};
document.getElementById('btn-export').onclick = exportSvg;
document.getElementById('btn-clear').onclick = clearCanvas;
dom.svgInput.addEventListener('change', handleSvgInputChange);
dom.imageInput.addEventListener('change', handleImageInputChange);
dom.sendBtn.onclick = sendPrompt;

dom.promptInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendPrompt();
  }
});
dom.promptInput.addEventListener('input', () => {
  dom.promptInput.style.height = 'auto';
  dom.promptInput.style.height = `${Math.min(dom.promptInput.scrollHeight, 120)}px`;
});

dom.canvasPane.addEventListener('wheel', (event) => {
  event.preventDefault();
  const rect = dom.canvasPane.getBoundingClientRect();
  setZoom(state.zoom * (event.deltaY < 0 ? 1.12 : 1 / 1.12), event.clientX - rect.left, event.clientY - rect.top);
}, { passive: false });

dom.canvasPane.addEventListener('mousedown', (event) => {
  if (event.button === 1 || (state.currentTool === 'pan' && event.button === 0)) {
    event.preventDefault();
    state.isPanning = true;
    state.panStart = { x: event.clientX, y: event.clientY };
    state.panOrigin = { x: state.panX, y: state.panY };
    dom.canvasPane.style.cursor = 'grabbing';
  } else if (event.target === dom.canvasPane || event.target === dom.overlay) {
    clearSelection();
  }
});
window.addEventListener('mousemove', (event) => {
  if (!state.isPanning) return;
  state.panX = state.panOrigin.x + (event.clientX - state.panStart.x);
  state.panY = state.panOrigin.y + (event.clientY - state.panStart.y);
  applyViewport();
});
window.addEventListener('mouseup', () => {
  if (!state.isPanning) return;
  state.isPanning = false;
  dom.canvasPane.style.cursor = state.currentTool === 'pan' ? 'grab' : 'default';
});

window.addEventListener('keydown', (event) => {
  if (['TEXTAREA', 'INPUT', 'SELECT'].includes(event.target.tagName)) return;
  if (event.key === 'v' || event.key === 'V') setTool('select');
  if (event.key === 'h' || event.key === 'H') setTool('pan');
  if (event.key === '+' || event.key === '=') setZoom(state.zoom * 1.2);
  if (event.key === '-') setZoom(state.zoom / 1.2);
  if (event.key === '0') fitToWindow();
  if (event.key === 'Delete' || event.key === 'Backspace') deleteSelected();
  if (event.key === 'Escape') clearSelection();
});

dom.canvasPane.addEventListener('dragover', (event) => {
  event.preventDefault();
  event.dataTransfer.dropEffect = 'copy';
});
dom.canvasPane.addEventListener('drop', async (event) => {
  event.preventDefault();
  const [file] = event.dataTransfer.files || [];
  if (file) {
    try {
      await importFile(file);
    } catch (error) {
      appendMessage('assistant', `Error: ${error.message}`);
    }
    return;
  }
  const kind = event.dataTransfer.getData('text/plain');
  if (!kind) return;
  insertAsset(kind, scenePointFromClient(event.clientX, event.clientY));
});

// Init
applyViewport();
appendMessage('assistant', 'Describe a scene, import an SVG, or convert a PNG/JPG into editable vectors.');
loadAssets();
