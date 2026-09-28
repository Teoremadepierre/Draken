// DOM and formatting primitives shared by every view.

import { t } from './i18n.js';

// --- element construction -------------------------------------------------

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function frag(children) {
  const f = document.createDocumentFragment();
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    f.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return f;
}

export function clear(node) {
  node.replaceChildren();
  return node;
}

export function icon(path, size = 16) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = `<path d="${path}" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`;
  return svg;
}

export const ICONS = {
  start: 'M12 3l1.9 5.8h6.1l-4.9 3.6 1.9 5.8-5-3.6-5 3.6 1.9-5.8L4 8.8h6.1L12 3Z',
  scan: 'M3 8V5a2 2 0 0 1 2-2h3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3M7 12h10',
  datasources: 'M12 7c4.4 0 8-1.1 8-2.5S16.4 2 12 2 4 3.1 4 4.5 7.6 7 12 7Zm8-2.5v15c0 1.4-3.6 2.5-8 2.5s-8-1.1-8-2.5v-15M20 12c0 1.4-3.6 2.5-8 2.5S4 13.4 4 12',
  dashboard: 'M4 13h7V4H4v9Zm9 7h7v-9h-7v9ZM4 20h7v-5H4v5Zm9-11h7V4h-7v5Z',
  keywords: 'M10 4a6 6 0 1 0 4.2 10.3l4.5 4.5 1.4-1.4-4.5-4.5A6 6 0 0 0 10 4Z',
  clusters: 'M7 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm10 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm0 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM7 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm5-9a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm0 0v0M8.6 6.4l2 2m4.8-2-2 2m2 9.2-2-2m-2.8 2 2-2',
  rankings: 'M4 19V5m0 14h16M8 19v-6m4 6V9m4 10v-8',
  gap: 'M8 4v16M16 4v16M3 9h5m8 6h5',
  audit: 'M9 11l3 3 5-6M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z',
  onpage: 'M14 3v5h5M6 3h8l5 5v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm2 10h8M8 17h5',
  backlinks: 'M9.5 14.5 5 19m5-9.5L14.5 5M8 16a4 4 0 0 1 0-5.7l2-2a4 4 0 0 1 5.7 5.7l-.6.6m-6.2 0-.6.6a4 4 0 0 0 5.7 5.7l2-2A4 4 0 0 0 16 15',
  opportunities: 'M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5L12 3Z',
  sources: 'M4 6h16M4 12h16M4 18h10',
  submissions: 'M4 5h16v14H4zM8 9h8M8 13h8M8 17h4',
  outreach: 'M4 6h16v12H4zM4 7l8 6 8-6',
  campaigns: 'M4 11l14-6v14L4 13v-2Zm0 0H3v2h1m3 1v4h3v-3',
  ai: 'M12 3v3m0 12v3M3 12h3m12 0h3M6.3 6.3l2.1 2.1m7.3 7.3 2.1 2.1m0-11.5-2.1 2.1M8.4 15.6l-2.1 2.1M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6Z',
  geo: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 0c2.5 2.3 4 5.5 4 9s-1.5 6.7-4 9c-2.5-2.3-4-5.5-4-9s1.5-6.7 4-9ZM3.5 9h17M3.5 15h17',
  profile: 'M4 20v-1a6 6 0 0 1 12 0v1M10 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm8 9v-1a5 5 0 0 0-3-4.6',
  jobs: 'M12 7v5l3 2M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-2-1.2L14.5 3h-4l-.4 2.6a7.5 7.5 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7.5 7.5 0 0 0 2 1.2l.4 2.6h4l.4-2.6a7.5 7.5 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.06-.4.1-.8.1-1.2Z',
};

// --- formatting -----------------------------------------------------------

export function num(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function compact(value) {
  if (value === null || value === undefined) return '—';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  if (Math.abs(n) >= 1000) {
    return n.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 1 });
  }
  return num(n);
}

export function pct(value, digits = 0) {
  if (value === null || value === undefined) return '—';
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export function money(value) {
  if (value === null || value === undefined) return '—';
  return `$${Number(value).toFixed(2)}`;
}

export function date(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function dateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function hostOf(url) {
  try { return new URL(url).host.replace(/^www\./, ''); } catch { return url || '—'; }
}

export function truncate(text, max = 90) {
  const s = String(text ?? '');
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

// --- small components ----------------------------------------------------

export function pill(text, tone = '') {
  return el('span', { class: `pill${tone ? ` pill-${tone}` : ''}`, text });
}

/** Difficulty, toxicity, spam: low is good. */
export function scoreChip(value, { invert = false } = {}) {
  if (value === null || value === undefined) return el('span', { class: 'faint', text: '—' });
  const n = Number(value);
  const good = invert ? n < 30 : n >= 60;
  const bad = invert ? n >= 65 : n < 25;
  const tone = good ? 'good' : bad ? 'bad' : 'warn';
  const colors = {
    good: ['var(--good-soft)', 'var(--good)'],
    warn: ['var(--warn-soft)', 'var(--warn)'],
    bad: ['var(--bad-soft)', 'var(--bad)'],
  }[tone];
  return el('span', {
    class: 'score-chip',
    style: `background:${colors[0]};color:${colors[1]}`,
    text: num(n, Number.isInteger(n) ? 0 : 1),
  });
}

export function meter(value, max = 100, tone = '') {
  const width = Math.max(0, Math.min(100, (Number(value) / max) * 100));
  return el('div', { class: `meter${tone ? ` ${tone}` : ''}` }, [
    el('span', { style: `width:${width}%` }),
  ]);
}

export function stat(label, value, { note, delta, small, tone } = {}) {
  const children = [
    el('div', { class: 'stat-label', text: label }),
    el('div', { class: `stat-value${small ? ' is-small' : ''}`, style: tone ? `color:var(--${tone})` : null, text: value }),
  ];
  if (delta !== undefined && delta !== null && delta !== 0) {
    const up = Number(delta) > 0;
    children.push(el('div', { class: `stat-delta ${up ? 'up' : 'down'}`, text: `${up ? '▲' : '▼'} ${Math.abs(delta)}` }));
  }
  if (note) children.push(el('div', { class: 'stat-note', text: note }));
  return el('div', { class: 'stat' }, children);
}

export function card(title, children, { sub, actions } = {}) {
  const parts = [];
  if (title || actions) {
    parts.push(el('div', { class: 'card-head' }, [
      title ? el('h2', { text: title }) : el('span'),
      actions ? el('div', { class: 'row-actions' }, actions) : null,
    ]));
  }
  if (sub) parts.push(el('p', { class: 'card-sub', text: sub }));
  return el('div', { class: 'card' }, parts.concat([].concat(children)));
}

export function callout(text, tone = 'info', title = '') {
  return el('div', { class: `callout callout-${tone}` }, [
    el('div', {}, [title ? el('strong', { text: title }) : null, text]),
  ]);
}

export function empty(title, body, action) {
  return el('div', { class: 'empty' }, [
    el('h3', { text: title }),
    body ? el('p', { text: body }) : null,
    action || null,
  ]);
}

export function skeleton(rows = 4) {
  return el('div', { class: 'card' }, Array.from({ length: rows }, (_, i) =>
    el('div', { class: 'skeleton', style: `width:${100 - i * 9}%` })));
}

export function loading() {
  return frag([skeleton(3), skeleton(5)]);
}

export function tabs(items, active, onSelect) {
  return el('div', { class: 'tabs' }, items.map((item) =>
    el('button', {
      class: `tab${item.id === active ? ' is-active' : ''}`,
      text: item.label,
      onClick: () => onSelect(item.id),
    })));
}

export function barRow(label, value, max, { formatted, tone, targetPct } = {}) {
  const width = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  const track = el('div', { class: 'bar-track' }, [
    el('div', { class: 'bar-fill', style: `width:${width}%${tone ? `;background:var(--${tone})` : ''}` }),
  ]);
  if (targetPct !== undefined) {
    track.append(el('div', { class: 'bar-target', style: `left:${Math.min(100, targetPct)}%` }));
  }
  return el('div', { class: 'bar-row' }, [
    el('div', { class: 'bar-label', text: label }),
    track,
    el('div', { class: 'bar-value', text: formatted ?? num(value) }),
  ]);
}

// --- tables --------------------------------------------------------------

/**
 * columns: [{ key, label, num?, render?(row), width?, sortable? }]
 * options: { rowKey, onRowClick, selectable, onSelectionChange, emptyNode }
 */
export function table(columns, rows, options = {}) {
  const { onRowClick, selectable, onSelectionChange, emptyNode, rowKey = (r) => r.id } = options;
  if (!rows || !rows.length) {
    return emptyNode || empty(t('empty.noData'));
  }

  const selected = new Set();
  const head = el('tr', {}, [
    selectable ? el('th', { style: 'width:28px' }, [
      el('input', {
        type: 'checkbox',
        'aria-label': t('action.selectAll'),
        onChange: (e) => {
          const on = e.target.checked;
          selected.clear();
          if (on) rows.forEach((r) => selected.add(rowKey(r)));
          body.querySelectorAll('input[type=checkbox]').forEach((cb) => { cb.checked = on; });
          onSelectionChange?.([...selected]);
        },
      }),
    ]) : null,
    ...columns.map((c) => el('th', {
      class: c.num ? 'num' : '',
      style: c.width ? `width:${c.width}` : null,
      text: c.label,
    })),
  ]);

  const body = el('tbody', {}, rows.map((row) => {
    const tr = el('tr', {
      class: onRowClick ? 'is-clickable' : '',
      style: onRowClick ? 'cursor:pointer' : null,
    }, [
      selectable ? el('td', {}, [
        el('input', {
          type: 'checkbox',
          'aria-label': 'select row',
          onClick: (e) => e.stopPropagation(),
          onChange: (e) => {
            if (e.target.checked) selected.add(rowKey(row));
            else selected.delete(rowKey(row));
            onSelectionChange?.([...selected]);
          },
        }),
      ]) : null,
      ...columns.map((c) => {
        const content = c.render ? c.render(row) : row[c.key];
        const td = el('td', { class: c.num ? 'num' : '' });
        if (content instanceof Node) td.append(content);
        else td.textContent = content === null || content === undefined || content === '' ? '—' : String(content);
        return td;
      }),
    ]);
    if (onRowClick) tr.addEventListener('click', () => onRowClick(row));
    return tr;
  }));

  return el('div', { class: 'table-wrap' }, [
    el('table', {}, [el('thead', {}, [head]), body]),
  ]);
}

// --- charts (inline SVG, no dependencies) --------------------------------

const SVG_NS = 'http://www.w3.org/2000/svg';

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  return node;
}

/**
 * Line chart. points: [{ label, value }]. Null values create gaps.
 * invertY: for rank charts, where 1 is best and belongs at the top.
 */
export function lineChart(points, { height = 170, invertY = false, format = num } = {}) {
  const valid = points.filter((p) => p.value !== null && p.value !== undefined);
  if (valid.length < 2) {
    return empty(t('empty.noData'), null);
  }
  const W = 640;
  const H = height;
  const pad = { top: 12, right: 12, bottom: 24, left: 42 };
  const innerW = W - pad.left - pad.right;
  const innerH = H - pad.top - pad.bottom;

  const values = valid.map((p) => Number(p.value));
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) { min = Math.max(0, min - 1); max = max + 1; }
  const span = max - min;

  const x = (i) => pad.left + (points.length === 1 ? innerW / 2 : (i / (points.length - 1)) * innerW);
  const y = (v) => {
    const ratio = (Number(v) - min) / span;
    return pad.top + (invertY ? ratio : 1 - ratio) * innerH;
  };

  const svg = svgEl('svg', {
    class: 'chart', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none',
    role: 'img', style: `height:${H}px`,
  });

  // horizontal gridlines + y labels
  for (let i = 0; i <= 3; i += 1) {
    const value = min + (span * i) / 3;
    const gy = y(value);
    svg.append(svgEl('line', { class: 'grid-line', x1: pad.left, x2: W - pad.right, y1: gy, y2: gy }));
    const label = svgEl('text', { class: 'axis-text', x: pad.left - 6, y: gy + 3, 'text-anchor': 'end' });
    label.textContent = format(value);
    svg.append(label);
  }

  // segments, broken across gaps
  let path = '';
  let open = false;
  points.forEach((p, i) => {
    if (p.value === null || p.value === undefined) { open = false; return; }
    path += `${open ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`;
    open = true;
  });
  svg.append(svgEl('path', { class: 'series-line', d: path }));

  points.forEach((p, i) => {
    if (p.value === null || p.value === undefined) return;
    const dot = svgEl('circle', { class: 'series-dot', cx: x(i), cy: y(p.value), r: 2.6 });
    const title = svgEl('title');
    title.textContent = `${p.label}: ${format(p.value)}`;
    dot.append(title);
    svg.append(dot);
  });

  // x labels: first, middle, last
  [0, Math.floor((points.length - 1) / 2), points.length - 1].forEach((i, n, arr) => {
    if (arr.indexOf(i) !== n) return;
    const label = svgEl('text', {
      class: 'axis-text', x: x(i), y: H - 6,
      'text-anchor': i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle',
    });
    label.textContent = points[i].label;
    svg.append(label);
  });

  return svg;
}

/** Grouped/simple bar chart. bars: [{ label, value, tone? }] */
export function barChart(bars, { height = 170, format = num } = {}) {
  if (!bars || !bars.length) return empty(t('empty.noData'), null);
  const W = 640;
  const H = height;
  const pad = { top: 12, right: 12, bottom: 26, left: 42 };
  const innerW = W - pad.left - pad.right;
  const innerH = H - pad.top - pad.bottom;
  const max = Math.max(...bars.map((b) => Math.abs(Number(b.value) || 0)), 1);
  const slot = innerW / bars.length;
  const barW = Math.max(3, Math.min(38, slot * 0.62));

  const svg = svgEl('svg', {
    class: 'chart', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none',
    role: 'img', style: `height:${H}px`,
  });

  for (let i = 0; i <= 3; i += 1) {
    const value = (max * i) / 3;
    const gy = pad.top + innerH - (value / max) * innerH;
    svg.append(svgEl('line', { class: 'grid-line', x1: pad.left, x2: W - pad.right, y1: gy, y2: gy }));
    const label = svgEl('text', { class: 'axis-text', x: pad.left - 6, y: gy + 3, 'text-anchor': 'end' });
    label.textContent = format(value);
    svg.append(label);
  }

  bars.forEach((bar, i) => {
    const value = Number(bar.value) || 0;
    const h = (Math.abs(value) / max) * innerH;
    const bx = pad.left + slot * i + (slot - barW) / 2;
    const rect = svgEl('rect', {
      class: 'series-bar', x: bx, y: pad.top + innerH - h,
      width: barW, height: Math.max(1, h), rx: 3,
      fill: bar.tone ? `var(--${bar.tone})` : null,
    });
    const title = svgEl('title');
    title.textContent = `${bar.label}: ${format(value)}`;
    rect.append(title);
    svg.append(rect);

    if (bars.length <= 14) {
      const label = svgEl('text', {
        class: 'axis-text', x: bx + barW / 2, y: H - 8, 'text-anchor': 'middle',
      });
      label.textContent = bar.label;
      svg.append(label);
    }
  });

  return svg;
}

// --- toasts & modal ------------------------------------------------------

export function toast(message, tone = '', title = '') {
  const host = document.getElementById('toasts');
  const node = el('div', { class: `toast${tone ? ` toast-${tone}` : ''}` }, [
    title ? el('strong', { text: title }) : null,
    el('div', { text: message }),
  ]);
  host.append(node);
  setTimeout(() => {
    node.style.opacity = '0';
    node.style.transition = 'opacity .2s';
    setTimeout(() => node.remove(), 220);
  }, tone === 'bad' ? 7000 : 4200);
}

let modalOnClose = null;

export function openModal({ title, body, footer, wide }) {
  const backdrop = document.getElementById('modal-backdrop');
  const dialog = backdrop.querySelector('.modal');
  dialog.classList.toggle('is-wide', Boolean(wide));
  document.getElementById('modal-title').textContent = title || '';
  clear(document.getElementById('modal-body')).append(body instanceof Node ? body : document.createTextNode(String(body ?? '')));
  const foot = clear(document.getElementById('modal-foot'));
  if (footer) foot.append(frag(footer));
  backdrop.hidden = false;
  document.body.style.overflow = 'hidden';
}

export function closeModal() {
  document.getElementById('modal-backdrop').hidden = true;
  document.body.style.overflow = '';
  modalOnClose?.();
  modalOnClose = null;
}

export function confirmDialog(message, onConfirm, { danger = true, title } = {}) {
  openModal({
    title: title || t('action.delete'),
    body: el('p', { text: message }),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      el('button', {
        class: `btn ${danger ? 'btn-danger' : 'btn-primary'}`,
        text: t('action.delete'),
        onClick: async () => { closeModal(); await onConfirm(); },
      }),
    ],
  });
}

export function initOverlays() {
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.getElementById('modal-backdrop').addEventListener('click', (e) => {
    if (e.target.id === 'modal-backdrop') closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !document.getElementById('modal-backdrop').hidden) closeModal();
  });
}

// --- helpers -------------------------------------------------------------

/** Wraps a click handler so the button shows a spinner and cannot double-fire. */
export function busy(button, fn) {
  return async (event) => {
    const node = button instanceof HTMLElement ? button : event.currentTarget;
    node.classList.add('is-busy');
    node.disabled = true;
    try {
      await fn(event);
    } finally {
      node.classList.remove('is-busy');
      node.disabled = false;
    }
  };
}

export function actionButton(label, onClick, { primary, small, iconPath } = {}) {
  const btn = el('button', {
    class: `btn${primary ? ' btn-primary' : ''}${small ? ' btn-sm' : ''}`,
  }, [iconPath ? icon(iconPath, small ? 14 : 16) : null, label]);
  btn.addEventListener('click', busy(btn, onClick));
  return btn;
}

export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast(t('action.copied'), 'good');
  } catch {
    // Clipboard API needs a secure context; fall back to a selectable textarea.
    const area = el('textarea', { class: 'textarea', style: 'height:220px' });
    area.value = text;
    openModal({ title: t('action.copy'), body: area });
    area.select();
  }
}

export function download(filename, content, type = 'text/plain') {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const TONE_BY_SEVERITY = {
  critical: 'bad', error: 'bad', warning: 'warn', notice: 'info',
};

export const TONE_BY_STATUS = {
  live: 'good', won: 'good', verified: 'good', succeeded: 'good', approved: 'good',
  lost: 'bad', broken: 'bad', failed: 'bad', rejected: 'bad',
  pending: 'info', queued: 'info', running: 'info', new: 'info', draft: '',
  awaiting_approval: 'warn', awaiting_review: 'warn', in_progress: 'warn',
  submitted: 'accent', manual_required: 'warn', qualified: 'teal', skipped: '',
};

export function statusPill(status) {
  return pill(String(status || '').replace(/_/g, ' '), TONE_BY_STATUS[status] ?? '');
}

export function linkTypePill(type) {
  const tone = type === 'dofollow' ? 'good' : type === 'unknown' ? '' : 'warn';
  return pill(type || '—', tone);
}

export function externalLink(url, label) {
  return el('a', {
    href: url, target: '_blank', rel: 'noopener noreferrer',
    class: 'cell-url', title: url, text: label ?? url,
  });
}
