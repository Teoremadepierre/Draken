// The two pages that work without an account: a shared read-only report, and
// accepting an invitation. Rendered into the same shell as the app.

import { api, setToken } from './api.js';
import { getLang, t } from './i18n.js';
import {
  actionButton, callout, card, copyToClipboard, el, frag, num, pct, pill,
  scoreChip, stat, table, toast, truncate,
} from './ui.js';

export function publicRoute() {
  const path = window.location.pathname;
  if (path.startsWith('/shared/')) return { kind: 'shared', token: path.slice(8) };
  if (path.startsWith('/invite/')) return { kind: 'invite', token: path.slice(8) };
  return null;
}

function shell(children) {
  document.getElementById('login').hidden = true;
  const app = document.getElementById('app');
  app.hidden = false;
  document.getElementById('sidebar').hidden = true;
  document.getElementById('nav-toggle').hidden = true;
  const view = document.getElementById('view');
  view.replaceChildren(children);
  return view;
}

// --- shared report -------------------------------------------------------

export async function renderShared(token) {
  const es = getLang() === 'es';
  document.getElementById('view-title').textContent = es ? 'Informe compartido' : 'Shared report';
  document.getElementById('view-sub').textContent = '';
  document.getElementById('view-actions').replaceChildren();

  let data;
  try {
    data = await api.get(`/shared/${token}`);
  } catch (error) {
    shell(card(t('msg.error'), el('p', {
      text: error.status === 404
        ? (es ? 'Este enlace no es válido o ha caducado.' : 'This link is not valid or has expired.')
        : error.message,
    })));
    return;
  }

  const r = data.report;
  document.getElementById('view-title').textContent = r.project.name;
  document.getElementById('view-sub').textContent =
    `${r.project.domain} · ${data.label}`;

  const s = r.scores;
  const out = frag([
    callout(es
      ? 'Informe de solo lectura. No puedes modificar nada desde aquí, y no lleva ninguna clave.'
      : 'Read-only report. Nothing can be changed from here, and it carries no keys.',
      'info'),
    el('div', { class: 'stats' }, [
      stat(es ? 'Puntuación global' : 'Overall', num(s.overall, 1)),
      stat(es ? 'Salud técnica' : 'Site health', s.site_health === null ? '—' : num(s.site_health, 1)),
      stat(es ? 'Autoridad de enlaces' : 'Link authority', num(s.link_authority, 1)),
      stat(es ? 'Visibilidad IA' : 'AI visibility', num(s.ai_visibility, 1)),
    ]),
  ]);

  if (r.headline) {
    out.append(card(es ? 'Resumen' : 'Summary', el('dl', { class: 'kv' },
      Object.entries(r.headline).flatMap(([k, v]) => [
        el('dt', { text: k.replace(/_/g, ' ') }),
        el('dd', { text: typeof v === 'number' && v < 1 && v > 0 ? pct(v) : num(v) }),
      ]))));
  }

  if (r.fixes?.length) {
    out.append(card(es ? 'Qué arreglar' : 'What to fix', table([
      { key: 'priority', label: '#', num: true, width: '48px' },
      { key: 'severity', label: t('label.severity'), render: (x) =>
        pill(x.severity, { critical: 'bad', error: 'bad', warning: 'warn' }[x.severity] || 'info') },
      { key: 'title', label: es ? 'Problema' : 'Issue', render: (x) => el('div', {}, [
        el('span', { class: 'cell-strong', text: x.title }),
        el('div', { class: 'faint small cell-wrap', text: truncate(x.how, 130) }),
      ]) },
      { key: 'affected', label: es ? 'Afecta a' : 'Affects', num: true },
    ], r.fixes)));
  }

  if (r.backlinks) {
    const b = r.backlinks.summary;
    out.append(card(es ? 'Backlinks disponibles ahora' : 'Backlinks available now', frag([
      el('div', { class: 'grid grid-4' }, [
        stat(es ? 'Disponibles' : 'Available', num(b.available_now)),
        stat('Dofollow', num(b.dofollow_now)),
        stat(es ? 'Autoridad media' : 'Avg authority', num(b.avg_authority_now, 1)),
        stat(es ? 'Horas' : 'Hours', num(b.estimated_hours, 1)),
      ]),
      table([
        { key: 'name', label: es ? 'Dónde' : 'Where' },
        { key: 'authority', label: es ? 'Autoridad' : 'Authority', num: true,
          render: (x) => scoreChip(x.authority) },
        { key: 'link_type', label: t('label.type'), render: (x) =>
          pill(x.link_type, x.link_type === 'dofollow' ? 'good' : '') },
        { key: 'effort', label: es ? 'Esfuerzo' : 'Effort', num: true },
      ], (r.backlinks.now || []).slice(0, 40)),
    ])));
  }

  if (data.ai_brief) {
    out.append(card(es ? 'Trabájalo con tu propia IA' : 'Work it with your own AI', frag([
      el('p', { class: 'card-sub', text: data.ai_brief_note || '' }),
      el('pre', { class: 'code wrap', style: 'max-height:300px', text: data.ai_brief }),
      el('div', { style: 'display:flex;gap:8px;flex-wrap:wrap' }, [
        actionButton(es ? 'Copiar informe' : 'Copy brief',
          () => copyToClipboard(data.ai_brief), { primary: true }),
        el('a', { class: 'btn', href: 'https://claude.ai/new', target: '_blank', rel: 'noopener',
                  text: es ? 'Abrir Claude' : 'Open Claude' }),
        el('a', { class: 'btn', href: 'https://chatgpt.com/', target: '_blank', rel: 'noopener',
                  text: 'ChatGPT' }),
      ]),
    ])));
  }

  shell(out);
}

// --- invitation ----------------------------------------------------------

export function renderInvite(token) {
  const es = getLang() === 'es';
  document.getElementById('view-title').textContent = es ? 'Únete a Draken' : 'Join Draken';
  document.getElementById('view-sub').textContent = '';
  document.getElementById('view-actions').replaceChildren();

  const password = el('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
  const confirm = el('input', { class: 'input', type: 'password', autocomplete: 'new-password' });
  const error = el('p', { class: 'login-error', hidden: true });

  const form = card(es ? 'Elige tu contraseña' : 'Choose your password', frag([
    el('p', { class: 'card-sub', text: es
      ? 'Este enlace funciona una sola vez. Al terminar entrarás directamente.'
      : 'This link works once. You will be signed in straight after.' }),
    el('label', { class: 'field' }, [
      el('span', { text: es ? 'Contraseña (mínimo 8 caracteres)' : 'Password (at least 8 characters)' }),
      password,
    ]),
    el('label', { class: 'field' }, [
      el('span', { text: es ? 'Repítela' : 'Repeat it' }), confirm,
    ]),
    error,
    actionButton(es ? 'Entrar' : 'Sign in', async () => {
      error.hidden = true;
      if (password.value.length < 8) {
        error.textContent = es ? 'Mínimo 8 caracteres.' : 'At least 8 characters.';
        error.hidden = false;
        return;
      }
      if (password.value !== confirm.value) {
        error.textContent = es ? 'No coinciden.' : 'They do not match.';
        error.hidden = false;
        return;
      }
      try {
        const r = await api.post('/users/accept-invite', { token, password: password.value });
        setToken(r.token);
        toast(es ? `Bienvenido, ${r.username}` : `Welcome, ${r.username}`, 'good');
        window.location.href = '/#start';
      } catch (err) {
        error.textContent = err.message;
        error.hidden = false;
      }
    }, { primary: true }),
  ]));

  shell(el('div', { style: 'max-width:440px;margin:40px auto' }, [form]));
}
