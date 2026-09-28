import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, closeModal, compact, el, empty, frag, money, num,
  openModal, pill, scoreChip, table, toast,
} from '../ui.js';

export const meta = { id: 'keywords', icon: 'keywords', group: 'research' };

const state = { q: '', intent: '', sort: 'opportunity', maxDifficulty: 100, minVolume: 0, tracked: false };
let selection = [];

export async function render(ctx) {
  const { project } = ctx;
  if (!project) return ctx.noProject();

  const rows = await api.get(`/projects/${project.id}/keywords`, {
    q: state.q, intent: state.intent, sort: state.sort,
    max_difficulty: state.maxDifficulty, min_volume: state.minVolume,
    tracked_only: state.tracked, limit: 500,
  });

  const out = frag([filters(ctx), selectionBar(ctx)]);

  if (!rows.length && !state.q && !state.intent) {
    out.append(card(null, empty(
      t('empty.noKeywords'), t('empty.noKeywordsBody'),
      actionButton(ctx.lang === 'es' ? 'Investigar keywords' : 'Research keywords',
        () => openResearch(ctx), { primary: true }),
    )));
    return out;
  }

  const es = ctx.lang === 'es';
  out.append(table([
    { key: 'term', label: t('label.keyword'), render: (r) => el('div', {}, [
      el('span', { class: 'cell-strong', text: r.term }),
      r.is_question ? el('span', { class: 'pill', style: 'margin-left:6px', text: '?' }) : null,
      r.is_branded ? pill(es ? 'marca' : 'brand', 'accent') : null,
    ]) },
    { key: 'volume', label: t('label.volume'), num: true, render: (r) => el('span', {
      title: `${es ? 'Confianza' : 'Confidence'}: ${Math.round(r.volume_confidence * 100)}%`,
      text: compact(r.volume),
    }) },
    { key: 'difficulty', label: t('label.difficulty'), num: true,
      render: (r) => scoreChip(r.difficulty, { invert: true }) },
    { key: 'opportunity_score', label: t('label.opportunity'), num: true,
      render: (r) => scoreChip(r.opportunity_score) },
    { key: 'intent', label: t('label.intent'), render: (r) => pill(r.intent, INTENT_TONE[r.intent] || '') },
    { key: 'cpc', label: t('label.cpc'), num: true, render: (r) => money(r.cpc) },
    { key: 'parent_topic', label: es ? 'Clúster' : 'Cluster',
      render: (r) => r.parent_topic ? el('span', { class: 'faint small', text: r.parent_topic }) : '—' },
    { key: 'is_tracked', label: es ? 'Seguida' : 'Tracked', render: (r) =>
      el('input', {
        type: 'checkbox', checked: r.is_tracked,
        'aria-label': 'track',
        onClick: (e) => e.stopPropagation(),
        onChange: async (e) => {
          await api.patch(`/projects/${project.id}/keywords/${r.id}`, null, { is_tracked: e.target.checked });
          toast(t('msg.saved'), 'good');
        },
      }) },
  ], rows, {
    selectable: true,
    onSelectionChange: (ids) => { selection = ids; renderSelectionBar(ctx); },
    onRowClick: (r) => openKeyword(ctx, r),
  }));

  out.append(el('p', { class: 'field-hint', style: 'margin-top:10px', text: es
    ? `${rows.length} keyword(s). El volumen es una estimación explicable, no un dato de proveedor: se usa para ordenar, no para presupuestar.`
    : `${rows.length} keyword(s). Volume is an explainable estimate, not provider data: use it to rank, not to budget.` }));

  return out;
}

const INTENT_TONE = {
  transactional: 'good', commercial: 'teal', local: 'info',
  informational: '', navigational: 'warn',
};

function filters(ctx) {
  const es = ctx.lang === 'es';
  const bar = el('div', { class: 'filters' });
  const search = el('input', {
    class: 'input grow', type: 'search', placeholder: t('action.search'), value: state.q,
  });
  let timer;
  search.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.q = search.value.trim(); ctx.reload(); }, 300);
  });
  bar.append(search);

  const intent = el('select', { class: 'select' }, [
    el('option', { value: '', text: es ? 'Toda intención' : 'Any intent' }),
    ...['transactional', 'commercial', 'local', 'informational', 'navigational'].map((v) =>
      el('option', { value: v, text: v, selected: state.intent === v })),
  ]);
  intent.addEventListener('change', () => { state.intent = intent.value; ctx.reload(); });
  bar.append(intent);

  const sort = el('select', { class: 'select' }, [
    ['opportunity', es ? 'Por oportunidad' : 'By opportunity'],
    ['volume', es ? 'Por volumen' : 'By volume'],
    ['difficulty', es ? 'Por dificultad' : 'By difficulty'],
    ['term', es ? 'Alfabético' : 'Alphabetical'],
  ].map(([v, label]) => el('option', { value: v, text: label, selected: state.sort === v })));
  sort.addEventListener('change', () => { state.sort = sort.value; ctx.reload(); });
  bar.append(sort);

  const diff = el('select', { class: 'select' }, [
    [100, es ? 'Cualquier dificultad' : 'Any difficulty'],
    [30, 'KD ≤ 30'], [50, 'KD ≤ 50'], [70, 'KD ≤ 70'],
  ].map(([v, label]) => el('option', { value: v, text: label, selected: Number(state.maxDifficulty) === v })));
  diff.addEventListener('change', () => { state.maxDifficulty = Number(diff.value); ctx.reload(); });
  bar.append(diff);

  const trackedToggle = el('label', { class: 'checkbox' }, [
    el('input', {
      type: 'checkbox', checked: state.tracked,
      onChange: (e) => { state.tracked = e.target.checked; ctx.reload(); },
    }),
    es ? 'Solo seguidas' : 'Tracked only',
  ]);
  bar.append(trackedToggle);
  return bar;
}

function selectionBar(ctx) {
  const host = el('div', { id: 'kw-selection' });
  return host;
}

function renderSelectionBar(ctx) {
  const host = document.getElementById('kw-selection');
  if (!host) return;
  host.replaceChildren();
  if (!selection.length) return;
  const es = ctx.lang === 'es';
  host.append(el('div', { class: 'filters' }, [
    el('strong', { text: `${selection.length} ${t('label.selected')}` }),
    actionButton(es ? 'Seguir' : 'Track', async () => {
      const r = await api.post(`/projects/${ctx.project.id}/keywords/track-bulk`, selection, { tracked: true });
      toast(`${r.updated} ${es ? 'actualizadas' : 'updated'}`, 'good');
      ctx.reload();
    }, { small: true, primary: true }),
    actionButton(es ? 'Dejar de seguir' : 'Untrack', async () => {
      const r = await api.post(`/projects/${ctx.project.id}/keywords/track-bulk`, selection, { tracked: false });
      toast(`${r.updated} ${es ? 'actualizadas' : 'updated'}`, 'good');
      ctx.reload();
    }, { small: true }),
    actionButton(t('action.export'), () => exportCsv(ctx), { small: true }),
  ]));
}

async function exportCsv(ctx) {
  const rows = await api.get(`/projects/${ctx.project.id}/keywords`, { limit: 5000, sort: state.sort });
  const picked = selection.length ? rows.filter((r) => selection.includes(r.id)) : rows;
  const header = ['term', 'volume', 'difficulty', 'opportunity_score', 'intent', 'cpc', 'parent_topic', 'is_tracked'];
  const csv = [header.join(',')].concat(picked.map((r) =>
    header.map((k) => `"${String(r[k] ?? '').replace(/"/g, '""')}"`).join(','))).join('\n');
  const { download } = await import('../ui.js');
  download(`keywords-${ctx.project.domain}.csv`, csv, 'text/csv');
}

function openResearch(ctx) {
  const es = ctx.lang === 'es';
  const seeds = el('textarea', {
    class: 'textarea', style: 'min-height:70px',
    placeholder: es ? 'software seo\nherramienta de keywords' : 'seo software\nkeyword tool',
  });
  const maxResults = el('input', { class: 'input', type: 'number', value: 400, min: 20, max: 5000 });
  const country = el('input', { class: 'input', value: ctx.project.country });
  const language = el('input', { class: 'input', value: ctx.project.language });
  const questions = el('input', { type: 'checkbox', checked: true });
  const modifiers = el('input', { type: 'checkbox', checked: true });
  const soup = el('input', { type: 'checkbox' });
  const live = el('input', { type: 'checkbox', checked: true });

  const body = frag([
    el('p', { class: 'field-hint', text: es
      ? 'Dos a cinco semillas funcionan mejor que veinte: son las palabras que escribiría un cliente, una por línea.'
      : 'Two to five seeds beat twenty: the words a customer would actually type, one per line.' }),
    el('label', { class: 'field' }, [el('span', { text: es ? 'Semillas' : 'Seed terms' }), seeds]),
    el('div', { class: 'field-row' }, [
      el('label', { class: 'field' }, [el('span', { text: t('label.country') }), country]),
      el('label', { class: 'field' }, [el('span', { text: t('label.language') }), language]),
      el('label', { class: 'field' }, [el('span', { text: es ? 'Máx. resultados' : 'Max results' }), maxResults]),
    ]),
    el('label', { class: 'checkbox', style: 'margin-bottom:6px' }, [modifiers, es ? 'Añadir modificadores comerciales y locales' : 'Add commercial and local modifiers']),
    el('label', { class: 'checkbox', style: 'margin-bottom:6px' }, [questions, es ? 'Añadir preguntas' : 'Add questions']),
    el('label', { class: 'checkbox', style: 'margin-bottom:6px' }, [soup, es ? 'Alphabet soup (a-z) — muchas más consultas' : 'Alphabet soup (a-z) — many more queries']),
    el('label', { class: 'checkbox' }, [live, es ? 'Consultar autocompletado en vivo' : 'Query live autocomplete']),
    el('p', { class: 'field-hint', text: es
      ? 'Si tu red bloquea los endpoints de autocompletado, desactiva la última opción: Draken seguirá generando y puntuando variantes.'
      : 'If your network blocks the autocomplete endpoints, turn the last option off: Draken still generates and scores variants.' }),
  ]);

  openModal({
    title: es ? 'Investigar keywords' : 'Research keywords',
    body,
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.run'), async () => {
        const list = seeds.value.split('\n').map((s) => s.trim()).filter(Boolean);
        if (!list.length) { toast(es ? 'Añade al menos una semilla' : 'Add at least one seed', 'bad'); return; }
        const payload = {
          seeds: list, country: country.value, language: language.value,
          include_questions: questions.checked, include_modifiers: modifiers.checked,
          include_alphabet_soup: soup.checked, max_results: Number(maxResults.value),
          persist: true, use_live_suggest: live.checked,
        };
        closeModal();
        toast(es ? 'Investigando…' : 'Researching…');
        const { job_id } = await api.post(
          `/projects/${ctx.project.id}/keywords/research`, payload, { background: true });
        ctx.watchJob(job_id, (job) => {
          if (job.state === 'succeeded') {
            const r = job.result || {};
            toast(`${r.created ?? 0} ${es ? 'keywords nuevas' : 'new keywords'}, ${r.clustering?.clusters ?? 0} ${es ? 'clústeres' : 'clusters'}`, 'good', t('msg.done'));
            ctx.reload();
          }
        });
      }, { primary: true }),
    ],
  });
}

function openAdd(ctx) {
  const es = ctx.lang === 'es';
  const area = el('textarea', { class: 'textarea', placeholder: es ? 'una keyword por línea' : 'one keyword per line' });
  const track = el('input', { type: 'checkbox', checked: true });
  openModal({
    title: es ? 'Añadir keywords manualmente' : 'Add keywords manually',
    body: frag([
      el('label', { class: 'field' }, [el('span', { text: t('label.keyword') }), area]),
      el('label', { class: 'checkbox' }, [track, es ? 'Seguir posiciones' : 'Track positions']),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.add'), async () => {
        const terms = area.value.split('\n').map((s) => s.trim()).filter(Boolean);
        if (!terms.length) return;
        const r = await api.post(`/projects/${ctx.project.id}/keywords`, {
          terms, country: ctx.project.country, track: track.checked,
        });
        closeModal();
        toast(`${r.created} ${es ? 'añadidas' : 'added'}, ${r.skipped} ${es ? 'ya existían' : 'already present'}`, 'good');
        ctx.reload();
      }, { primary: true }),
    ],
  });
}

async function openKeyword(ctx, row) {
  const es = ctx.lang === 'es';
  const history = await api.get(`/projects/${ctx.project.id}/keywords/${row.id}/history`);
  const { lineChart } = await import('../ui.js');
  openModal({
    title: row.term,
    wide: true,
    body: frag([
      el('div', { class: 'stats' }, [
        statTile(t('label.volume'), compact(row.volume)),
        statTile(t('label.difficulty'), num(row.difficulty, 1)),
        statTile(t('label.opportunity'), num(row.opportunity_score, 1)),
        statTile(t('label.cpc'), money(row.cpc)),
      ]),
      el('dl', { class: 'kv' }, [
        el('dt', { text: t('label.intent') }), el('dd', {}, [pill(row.intent)]),
        el('dt', { text: es ? 'Palabras' : 'Words' }), el('dd', { text: num(row.word_count) }),
        el('dt', { text: es ? 'Confianza del volumen' : 'Volume confidence' }),
        el('dd', { text: `${Math.round(row.volume_confidence * 100)}%` }),
        el('dt', { text: es ? 'Clúster' : 'Cluster' }), el('dd', { text: row.parent_topic || '—' }),
        el('dt', { text: es ? 'Origen' : 'Source' }), el('dd', { text: row.source }),
        el('dt', { text: 'SERP features' }),
        el('dd', {}, (row.serp_features || []).length
          ? (row.serp_features || []).map((f) => pill(f)) : ['—']),
      ]),
      el('h3', { style: 'margin:16px 0 8px', text: es ? 'Histórico de posición' : 'Position history' }),
      history.length >= 2
        ? lineChart(history.map((h) => ({ label: String(h.captured_on).slice(5), value: h.position })),
            { invertY: true, format: (v) => `#${Math.round(v)}` })
        : el('p', { class: 'muted', text: es
            ? 'Aún no hay histórico. Márcala como seguida y ejecuta el seguimiento de posiciones.'
            : 'No history yet. Track it and run rank tracking.' }),
    ]),
    footer: [
      el('button', { class: 'btn btn-danger', text: t('action.delete'), onClick: async () => {
        await api.del(`/projects/${ctx.project.id}/keywords/${row.id}`);
        closeModal(); toast(t('msg.deleted'), 'good'); ctx.reload();
      } }),
      el('button', { class: 'btn', text: t('action.close'), onClick: closeModal }),
    ],
  });
}

function statTile(label, value) {
  return el('div', { class: 'stat' }, [
    el('div', { class: 'stat-label', text: label }),
    el('div', { class: 'stat-value is-small', text: value }),
  ]);
}

export function actions(ctx) {
  if (!ctx.project) return [];
  const es = ctx.lang === 'es';
  return [
    actionButton(es ? 'Investigar' : 'Research', () => openResearch(ctx), { primary: true }),
    actionButton(t('action.add'), () => openAdd(ctx)),
    actionButton(t('action.export'), () => exportCsv(ctx)),
  ];
}
