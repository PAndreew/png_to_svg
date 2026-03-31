import { dom, state } from './state.js';

export function escapeHtml(text) {
  return String(text ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;');
}

export function randomId(prefix) {
  return `${prefix}-${Math.random().toString(16).slice(2, 10)}`;
}

let toastTimer = null;
export function showToast(message, ms = 2400) {
  dom.toast.textContent = message;
  dom.toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => dom.toast.classList.remove('show'), ms);
}

// The assetMarkup function - pure SVG shape factory
export function assetMarkup(kind, meta = {}) {
  const color = meta.color || '#2563eb';
  const props = meta.props || {};
  const text = escapeHtml(props.text || meta.label || 'Missing asset');
  if (kind === 'road') return '<rect x="-460" y="-90" width="920" height="180" rx="28" fill="#6b7280"></rect><line x1="-420" y1="0" x2="420" y2="0" stroke="#f8fafc" stroke-width="6" stroke-dasharray="24 18" stroke-linecap="round"></line><line x1="-420" y1="-62" x2="420" y2="-62" stroke="#d1d5db" stroke-width="3" opacity="0.55"></line><line x1="-420" y1="62" x2="420" y2="62" stroke="#d1d5db" stroke-width="3" opacity="0.55"></line>';
  if (kind === 'intersection') return '<rect x="-420" y="-92" width="840" height="184" rx="28" fill="#6b7280"></rect><rect x="-92" y="-320" width="184" height="640" rx="28" fill="#6b7280"></rect><line x1="-390" y1="0" x2="390" y2="0" stroke="#f8fafc" stroke-width="6" stroke-dasharray="24 18" stroke-linecap="round"></line><line x1="0" y1="-290" x2="0" y2="290" stroke="#f8fafc" stroke-width="6" stroke-dasharray="24 18" stroke-linecap="round"></line>';
  if (kind === 't_junction') return '<rect x="-420" y="-92" width="840" height="184" rx="28" fill="#6b7280"></rect><rect x="146" y="-320" width="184" height="320" rx="28" fill="#6b7280"></rect><line x1="-390" y1="0" x2="120" y2="0" stroke="#f8fafc" stroke-width="6" stroke-dasharray="24 18" stroke-linecap="round"></line><line x1="238" y1="-290" x2="238" y2="-30" stroke="#f8fafc" stroke-width="6" stroke-dasharray="24 18" stroke-linecap="round"></line>';
  if (kind === 'roundabout') return '<circle cx="0" cy="0" r="170" fill="#6b7280"></circle><circle cx="0" cy="0" r="78" fill="#f8fafc"></circle><circle cx="0" cy="0" r="42" fill="#86efac" stroke="#16a34a" stroke-width="8"></circle><rect x="-420" y="-46" width="220" height="92" rx="26" fill="#6b7280"></rect><rect x="200" y="-46" width="220" height="92" rx="26" fill="#6b7280"></rect><rect x="-46" y="-320" width="92" height="170" rx="26" fill="#6b7280"></rect><rect x="-46" y="150" width="92" height="170" rx="26" fill="#6b7280"></rect>';
  if (kind === 'crosswalk') return Array.from({ length: 6 }, (_, i) => `<rect x="${-60 + i * 20}" y="-90" width="12" height="180" fill="#f8fafc" opacity="0.96"></rect>`).join('');
  if (kind === 'car') return `<rect x="-44" y="-22" width="88" height="44" rx="12" fill="${escapeHtml(color)}" stroke="#111827" stroke-width="4"></rect><rect x="-24" y="-15" width="48" height="30" rx="8" fill="#dbeafe" stroke="#111827" stroke-width="3"></rect><circle cx="-28" cy="-26" r="7" fill="#111827"></circle><circle cx="28" cy="-26" r="7" fill="#111827"></circle><circle cx="-28" cy="26" r="7" fill="#111827"></circle><circle cx="28" cy="26" r="7" fill="#111827"></circle>`;
  if (kind === 'truck') return `<rect x="-62" y="-24" width="78" height="48" rx="10" fill="${escapeHtml(color)}" stroke="#111827" stroke-width="4"></rect><rect x="16" y="-20" width="42" height="40" rx="8" fill="#fde68a" stroke="#111827" stroke-width="4"></rect><rect x="22" y="-14" width="22" height="14" rx="4" fill="#dbeafe" stroke="#111827" stroke-width="2.5"></rect><circle cx="-40" cy="-28" r="8" fill="#111827"></circle><circle cx="-4" cy="-28" r="8" fill="#111827"></circle><circle cx="22" cy="-28" r="8" fill="#111827"></circle><circle cx="-40" cy="28" r="8" fill="#111827"></circle><circle cx="-4" cy="28" r="8" fill="#111827"></circle><circle cx="22" cy="28" r="8" fill="#111827"></circle>`;
  if (kind === 'bus') return `<rect x="-60" y="-24" width="120" height="48" rx="12" fill="${escapeHtml(color)}" stroke="#111827" stroke-width="4"></rect><rect x="-38" y="-14" width="14" height="16" rx="3" fill="#dbeafe" stroke="#111827" stroke-width="2"></rect><rect x="-18" y="-14" width="14" height="16" rx="3" fill="#dbeafe" stroke="#111827" stroke-width="2"></rect><rect x="2" y="-14" width="14" height="16" rx="3" fill="#dbeafe" stroke="#111827" stroke-width="2"></rect><rect x="22" y="-14" width="14" height="16" rx="3" fill="#dbeafe" stroke="#111827" stroke-width="2"></rect><circle cx="-36" cy="-28" r="8" fill="#111827"></circle><circle cx="36" cy="-28" r="8" fill="#111827"></circle><circle cx="-36" cy="28" r="8" fill="#111827"></circle><circle cx="36" cy="28" r="8" fill="#111827"></circle>`;
  if (kind === 'pedestrian') return `<circle cx="0" cy="-22" r="11" fill="${escapeHtml(color || '#111827')}"></circle><path d="M 0 -10 L 0 18 M -18 0 L 0 -2 L 16 10 M -14 40 L 0 18 L 16 42" stroke="${escapeHtml(color || '#111827')}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" fill="none"></path>`;
  if (kind === 'bicycle') return `<circle cx="-26" cy="18" r="17" fill="none" stroke="#111827" stroke-width="5"></circle><circle cx="30" cy="18" r="17" fill="none" stroke="#111827" stroke-width="5"></circle><path d="M -26 18 L -4 -6 L 14 18 L -2 18 L 8 2 L 26 2" stroke="${escapeHtml(color || '#16a34a')}" stroke-width="6" fill="none" stroke-linecap="round" stroke-linejoin="round"></path><line x1="14" y1="18" x2="30" y2="18" stroke="${escapeHtml(color || '#16a34a')}" stroke-width="6" stroke-linecap="round"></line><line x1="-4" y1="-6" x2="10" y2="-20" stroke="${escapeHtml(color || '#16a34a')}" stroke-width="6" stroke-linecap="round"></line>`;
  if (kind === 'traffic_light') return '<rect x="-8" y="-58" width="16" height="110" rx="6" fill="#111827"></rect><rect x="-22" y="-90" width="44" height="64" rx="10" fill="#1f2937" stroke="#111827" stroke-width="4"></rect><circle cx="0" cy="-74" r="7" fill="#ef4444"></circle><circle cx="0" cy="-58" r="7" fill="#f59e0b"></circle><circle cx="0" cy="-42" r="7" fill="#22c55e"></circle>';
  if (kind === 'tree') return '<rect x="-10" y="6" width="20" height="36" rx="6" fill="#92400e"></rect><circle cx="0" cy="0" r="24" fill="#22c55e" stroke="#15803d" stroke-width="4"></circle><circle cx="-18" cy="8" r="18" fill="#4ade80" stroke="#15803d" stroke-width="3"></circle><circle cx="18" cy="8" r="18" fill="#4ade80" stroke="#15803d" stroke-width="3"></circle>';
  if (kind === 'arrow') {
    const style = props.style || 'straight';
    let path = 'M -70 -16 L 12 -16 L 12 -44 L 92 0 L 12 44 L 12 16 L -70 16 Z';
    if (style === 'left') path = 'M -50 40 L -10 40 L -10 -10 L 30 -10 L 30 -34 L 76 0 L 30 34 L 30 10 L 10 10 L 10 60 L -50 60 Z';
    if (style === 'right') path = 'M 50 40 L 10 40 L 10 -10 L -30 -10 L -30 -34 L -76 0 L -30 34 L -30 10 L -10 10 L -10 60 L 50 60 Z';
    if (style === 'merge') path = 'M -56 58 L -8 58 L -8 28 L 44 28 L 44 2 L 92 42 L 44 82 L 44 56 L 4 56 L 4 88 L -56 88 Z';
    if (style === 'uturn') path = 'M 36 -52 L 82 -18 L 36 16 L 36 -8 L -6 -8 Q -50 -8 -50 36 Q -50 78 -8 78 L 30 78 L 30 56 L 78 92 L 30 128 L 30 102 L -10 102 Q -74 102 -74 38 Q -74 -32 -6 -32 L 36 -32 Z';
    return `<path d="${path}" fill="${escapeHtml(color || '#22c55e')}" stroke="#166534" stroke-width="4" stroke-linejoin="round"></path>`;
  }
  return `<rect x="-70" y="-40" width="140" height="80" rx="14" fill="#e2e8f0" stroke="#64748b" stroke-width="4" stroke-dasharray="10 8"></rect><text x="0" y="6" font-size="16" text-anchor="middle" fill="#334155" font-family="Segoe UI, sans-serif">${text}</text>`;
}
