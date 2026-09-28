import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, card, closeModal, el, empty, externalLink, frag, num, openModal,
  pill, scoreChip, stat, table, toast, truncate,
} from '../ui.js';

export const meta = { id: 'sources', icon: 'sources', group: 'links' };

const state = { category: '', country: '', q: '', maxEffort: 5, onlyFree: false, onlyDofollow: false, sort: 'authority' };

export async function render(ctx) {
  const es = ctx.lang === 'es';
  const [stats, rows] = await Promise.all([
    api.get('/sources/stats'),
    api.get('/sources', {
      category: state.category, country: state.country, q: state.q,
      max_effort: state.maxEffort, only_free: state.onlyFree,
      only_dofollow: state.onlyDofollow, sort: state.sort, limit: 500,
    }),
  ]);

  const out = frag([
    el('div', { class: 'stats' }, [
      stat(es ? 'Fuentes en catálogo' : 'Sources in catalog', num(stats.total)),
      stat(es ? 'Gratuitas' : 'Free', num(stats.free)),
      stat('Dofollow', num(stats.dofollow), { tone: 'good' }),
      stat(es ? 'Victorias rápidas' : 'Quick wins', num(stats.quick_wins), {
        note: es ? 'esfuerzo ≤2, autoridad ≥60' : 'effort ≤2, authority ≥60',
      }),
      stat(es ? 'Señal para IA' : 'AI training signal', num(stats.ai_training_signal), {
        note: es ? 'corpus que citan los asistentes' : 'corpora assistants cite',
      }),
      stat(es ? 'Países cubiertos' : 'Countries covered', num(stats.countries_covered)),
    ]),
    filters(ctx, stats),
  ]);

  out.append(card(es ? 'Reparto por categoría' : 'Breakdown by category',
    el('div', {}, (stats.by_category || []).map((c) => {
      const max = Math.max(...stats.by_category.map((x) => x.count));
      return el('div', { class: 'bar-row' }, [
        el('button', {
          class: 'bar-label',
          style: 'background:none;border:0;color:var(--accent-text);cursor:pointer;text-align:left;font:inherit;padding:0',
          text: String(c.category).replace(/_/g, ' '),
          onClick: () => { state.category = c.category; ctx.reload(); },
        }),
        el('div', { class: 'bar-track' }, [
          el('div', { class: 'bar-fill', style: `width:${(c.count / max) * 100}%` }),
        ]),
        el('div', { class: 'bar-value', text: `${c.count} · DA ø${num(c.avg_authority, 0)}` }),
      ]);
    }))));

  if (!rows.length) {
    out.append(card(null, empty(es ? 'Sin resultados' : 'No matches')));
    return out;
  }

  out.append(table([
    { key: 'name', label: t('label.source'), render: (r) => el('div', {}, [
      el('span', { class: 'cell-strong', text: r.name }),
      el('div', { class: 'faint small', text: r.domain }),
    ]) },
    { key: 'category', label: t('label.category'), render: (r) =>
      pill(String(r.category).replace(/_/g, ' ')) },
    { key: 'authority', label: t('label.authority'), num: true, render: (r) => scoreChip(r.authority) },
    { key: 'link_type', label: t('label.type'), render: (r) =>
      pill(r.link_type, r.link_type === 'dofollow' ? 'good' : r.link_type === 'unknown' ? '' : 'warn') },
    { key: 'effort', label: t('label.effort'), num: true, render: (r) =>
      pill('•'.repeat(r.effort), r.effort <= 2 ? 'good' : r.effort >= 4 ? 'warn' : '') },
    { key: 'llm_citation_weight', label: es ? 'Peso IA' : 'AI weight', num: true, render: (r) =>
      r.llm_citation_weight ? scoreChip(r.llm_citation_weight * 100) : '—' },
    { key: 'countries', label: es ? 'Países' : 'Countries', render: (r) =>
      el('span', { class: 'small faint', text: (r.countries || []).includes('*') ? (es ? 'global' : 'global') : (r.countries || []).slice(0, 4).join(', ') }) },
  ], rows, { onRowClick: (r) => openSource(ctx, r) }));

  out.append(el('p', { class: 'field-hint', text: es
    ? `${rows.length} fuentes. Editables en data/seeds/link_sources.json: añade las tuyas y pulsa "Recargar catálogo".`
    : `${rows.length} sources. Editable in data/seeds/link_sources.json: add your own and hit "Reload catalog".` }));

  return out;
}

function filters(ctx, stats) {
  const es = ctx.lang === 'es';
  const bar = el('div', { class: 'filters' });

  const search = el('input', { class: 'input grow', type: 'search', placeholder: t('action.search'), value: state.q });
  let timer;
  search.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.q = search.value.trim(); ctx.reload(); }, 300);
  });
  bar.append(search);

  const cat = el('select', { class: 'select' }, [
    el('option', { value: '', text: es ? 'Todas las categorías' : 'All categories' }),
    ...(stats.by_category || []).map((c) =>
      el('option', { value: c.category, text: `${String(c.category).replace(/_/g, ' ')} (${c.count})`, selected: state.category === c.category })),
  ]);
  cat.addEventListener('change', () => { state.category = cat.value; ctx.reload(); });
  bar.append(cat);

  const country = el('input', {
    class: 'input', style: 'max-width:90px', placeholder: es ? 'País' : 'Country', value: state.country,
  });
  country.addEventListener('change', () => { state.country = country.value.trim().toUpperCase(); ctx.reload(); });
  bar.append(country);

  const effort = el('select', { class: 'select' },
    [[5, es ? 'Cualquier esfuerzo' : 'Any effort'], [2, es ? 'Fácil (≤2)' : 'Easy (≤2)'], [3, '≤3']]
      .map(([v, label]) => el('option', { value: v, text: label, selected: Number(state.maxEffort) === v })));
  effort.addEventListener('change', () => { state.maxEffort = Number(effort.value); ctx.reload(); });
  bar.append(effort);

  bar.append(el('label', { class: 'checkbox' }, [
    el('input', { type: 'checkbox', checked: state.onlyDofollow,
      onChange: (e) => { state.onlyDofollow = e.target.checked; ctx.reload(); } }),
    'dofollow',
  ]));
  bar.append(el('label', { class: 'checkbox' }, [
    el('input', { type: 'checkbox', checked: state.onlyFree,
      onChange: (e) => { state.onlyFree = e.target.checked; ctx.reload(); } }),
    es ? 'gratis' : 'free',
  ]));

  const sort = el('select', { class: 'select' },
    [['authority', es ? 'Por autoridad' : 'By authority'], ['effort', es ? 'Por esfuerzo' : 'By effort'],
     ['llm', es ? 'Por peso en IA' : 'By AI weight'], ['name', es ? 'Por nombre' : 'By name']]
      .map(([v, label]) => el('option', { value: v, text: label, selected: state.sort === v })));
  sort.addEventListener('change', () => { state.sort = sort.value; ctx.reload(); });
  bar.append(sort);

  if (state.category || state.country || state.q) {
    bar.append(actionButton(t('action.clear'), () => {
      Object.assign(state, { category: '', country: '', q: '', maxEffort: 5, onlyFree: false, onlyDofollow: false });
      ctx.reload();
    }, { small: true }));
  }

  return bar;
}

function openSource(ctx, source) {
  const es = ctx.lang === 'es';
  openModal({
    title: source.name,
    body: frag([
      el('div', { class: 'stats' }, [
        stat(t('label.authority'), num(source.authority, 0)),
        stat(t('label.effort'), `${source.effort}/5`),
        stat(es ? 'Peso IA' : 'AI weight', num((source.llm_citation_weight || 0) * 100, 0)),
      ]),
      el('dl', { class: 'kv' }, [
        el('dt', { text: t('label.domain') }), el('dd', {}, [externalLink(`https://${source.domain}`, source.domain)]),
        el('dt', { text: es ? 'URL de envío' : 'Submit URL' }), el('dd', {}, [externalLink(source.submit_url)]),
        el('dt', { text: t('label.category') }), el('dd', {}, [pill(String(source.category).replace(/_/g, ' '))]),
        el('dt', { text: t('label.type') }), el('dd', {}, [pill(source.link_type, source.link_type === 'dofollow' ? 'good' : 'warn')]),
        el('dt', { text: es ? 'Gratis' : 'Free' }), el('dd', {}, [pill(source.is_free ? (es ? 'sí' : 'yes') : (es ? 'no' : 'no'), source.is_free ? 'good' : 'warn')]),
        el('dt', { text: es ? 'Requiere cuenta' : 'Requires account' }),
        el('dd', { text: source.requires_account ? (es ? 'sí' : 'yes') : (es ? 'no' : 'no') }),
        el('dt', { text: es ? 'Automatizable' : 'Automatable' }),
        el('dd', {}, [pill(source.automatable ? (es ? 'sí' : 'yes') : (es ? 'no' : 'no'), source.automatable ? 'good' : '')]),
        el('dt', { text: es ? 'Señal de entrenamiento IA' : 'AI training signal' }),
        el('dd', { text: source.ai_training_signal ? (es ? 'sí' : 'yes') : (es ? 'no' : 'no') }),
        el('dt', { text: es ? 'Países' : 'Countries' }),
        el('dd', { text: (source.countries || []).join(', ') || '—' }),
        el('dt', { text: es ? 'Sectores' : 'Industries' }),
        el('dd', { text: (source.industries || []).join(', ') || '—' }),
        source.required_fields?.length ? el('dt', { text: es ? 'Campos requeridos' : 'Required fields' }) : null,
        source.required_fields?.length
          ? el('dd', {}, source.required_fields.map((f) => pill(String(f).replace(/_/g, ' ')))) : null,
        source.guidelines_url ? el('dt', { text: es ? 'Normas' : 'Guidelines' }) : null,
        source.guidelines_url ? el('dd', {}, [externalLink(source.guidelines_url)]) : null,
        source.tags?.length ? el('dt', { text: 'Tags' }) : null,
        source.tags?.length ? el('dd', {}, source.tags.map((tag) => pill(tag))) : null,
      ]),
      source.notes ? el('div', { class: 'callout callout-info' }, [
        el('div', {}, [el('strong', { text: es ? 'Cómo abordarlo' : 'How to approach it' }), source.notes]),
      ]) : null,
    ]),
    footer: [el('button', { class: 'btn', text: t('action.close'), onClick: closeModal })],
  });
}

async function showPlaybook(ctx) {
  const es = ctx.lang === 'es';
  const data = await api.get('/sources/playbook');
  openModal({
    title: es ? 'Tácticas que no son un formulario' : 'Tactics that are not a form',
    wide: true,
    body: frag([
      el('p', { class: 'field-hint', text: es
        ? 'Estas tácticas no tienen una URL de envío: se prospectan. Son las que consiguen enlaces que no puedes simplemente solicitar, y las que más rinden a medio plazo.'
        : 'These have no submit URL: they are prospected. They earn the links you cannot simply request, and they pay the most over time.' }),
      ...data.tactics.map((tac) => el('div', { class: 'card', style: 'margin-bottom:10px' }, [
        el('div', { class: 'card-head' }, [
          el('h3', { text: tac.name }),
          el('div', { class: 'row-actions' }, [
            pill(`${es ? 'esfuerzo' : 'effort'} ${tac.effort}/5`, tac.effort <= 2 ? 'good' : tac.effort >= 4 ? 'warn' : ''),
            pill(tac.link_type, tac.link_type === 'dofollow' ? 'good' : ''),
          ]),
        ]),
        el('p', { class: 'small', text: tac.notes }),
        (tac.tags || []).length ? el('div', {}, tac.tags.map((tg) => pill(tg))) : null,
      ])),
    ]),
    footer: [el('button', { class: 'btn', text: t('action.close'), onClick: closeModal })],
  });
}

export function actions(ctx) {
  const es = ctx.lang === 'es';
  return [
    actionButton(es ? 'Tácticas' : 'Tactics', () => showPlaybook(ctx), { primary: true }),
    actionButton(es ? 'Recargar catálogo' : 'Reload catalog', async () => {
      const r = await api.post('/sources/sync');
      toast(`${r.total} ${es ? 'fuentes' : 'sources'} (${r.created} ${es ? 'nuevas' : 'new'})`, 'good');
      ctx.reload();
    }),
  ];
}
