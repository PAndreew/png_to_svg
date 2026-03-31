export const SVG_NS = 'http://www.w3.org/2000/svg';
export const DEFAULT_CANVAS = { width: 1024, height: 768, background: '#f8fafc' };

export const state = {
  zoom: 1,
  panX: 0,
  panY: 0,
  isPanning: false,
  panStart: null,
  panOrigin: null,
  currentTool: 'select',
  svgDoc: null,
  selectedEl: null,
  currentScene: null,
  sceneMeta: new Map(),
  assets: [],
  history: [],
  isGenerating: false,
  svgFilename: 'pictogram.svg',
  importColors: 8,
};

export const dom = {
  canvasPane: document.getElementById('canvas-pane'),
  svgContainer: document.getElementById('svg-container'),
  overlay: document.getElementById('sel-overlay'),
  dropHint: document.getElementById('drop-hint'),
  messages: document.getElementById('messages'),
  promptInput: document.getElementById('prompt-input'),
  sendBtn: document.getElementById('send-btn'),
  zoomLabel: document.getElementById('zoom-label'),
  propsBody: document.getElementById('props-body'),
  assetGrid: document.getElementById('asset-grid'),
  sceneSummary: document.getElementById('scene-summary'),
  toast: document.getElementById('toast'),
  toolSelect: document.getElementById('tool-select'),
  toolPan: document.getElementById('tool-pan'),
  toolDelete: document.getElementById('tool-delete'),
  btnOpenSvg: document.getElementById('btn-open-svg'),
  btnImportImage: document.getElementById('btn-import-image'),
  btnSaveAsset: document.getElementById('btn-save-asset'),
  svgInput: document.getElementById('svg-input'),
  imageInput: document.getElementById('image-input'),
};
