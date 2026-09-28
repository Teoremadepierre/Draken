import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, closeModal, el, empty, externalLink, frag, num,
  openModal, pct, pill, scoreChip, stat, statusPill, table, toast, truncate,
} from '../ui.js';

export const meta = { id: 'opportunities', icon: 'opportunities', group: 'links' };

const state = { status: '', tactic: '', minScore: 0, maxEffort: 5, q: '', sort: 'score' };
let selection = [];

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';

  const [rows, pipeline] = await Promise.all([
    api.get(`/projects/${ctx.project.id}/opportunities`, {
      status: state.status, tactic: state.tactic, min_score: state.minScore,
      max_effort: state.maxEffort, q: state.q, sort: state.sort, limit: 500,
    }),
    api.get(`/projects/${ctx.project.id}/opportunities/pipeline`),
  ]);

  const out = frag([
    el('div', { class: 'stats' }, [
      stat(es ? 'Total' : 'Total', num(pipeline.total)),
      stat(es ? 'Alta prioridad' : 'High priority', num(pipeline.high_priority), {
        note: es ? 'puntuación ≥ 60' : 'score ≥ 60',
      }),
      stat(es ? 'Victorias rápidas' : 'Quick wins', num(pipeline.quick_wins), {
        note: es ? 'buena puntuación, poco esfuerzo' : 'good score, low effort',
        tone: 'good',
      }),
      stat(es ? 'Ganados' : 'Won', num(pipeline.won), { tone: 'good' }),
      stat(es ? 'Conversión' : 'Conversion', pct(pipeline.conversion_rate, 1)),
      stat(es ? 'Puntuación media' : 'Average score', num(pipeline.avg_score, 1)),
    ]),
    filters(ctx),
    el('div', { id: 'opp-selection' }),
  ]);

  if (!rows.length) {
    out.append(card(null, empty(
      es ? 'No hay oportunidades con estos filtros' : 'No opportunities match these filters',
      es ? 'Genera la cola desde el catálogo de 355 fuentes, o busca enlaces de la competencia.'
         : 'Generate the queue from the 355-source catalog, or prospect competitor links.',
      actionButton(t('action.generate'), () => openGenerate(ctx), { primary: true }),
    )));
    return out;
  }

  out.append(table([
    { key: 'target_domain', label: es ? 'Dónde' : 'Where', render: (r) => el('div', {}, [
      el('span', { class: 'cell-strong', text: r.target_domain }),
      el('div', { class: 'faint small', text: String(r.tactic).replace(/_/g, ' ') }),
    ]) },
    { key: 'score', label: t('label.score'), num: true, render: (r) => scoreChip(r.score) },
    { key: 'authority', label: t('label.authority'), num: true, render: (r) => scoreChip(r.authority) },
    { key: 'relevance', label: es ? 'Relevancia' : 'Relevance', num: true, render: (r) => scoreChip(r.relevance) },
    { key: 'effort', label: t('label.effort'), num: true, render: (r) =>
      pill('•'.repeat(r.effort), r.effort <= 2 ? 'good' : r.effort >= 4 ? 'warn' : '') },
    { key: 'competitor_links', label: es ? 'Comp.' : 'Comp.', num: true, render: (r) =>
      r.competitor_links ? pill(num(r.competitor_links), 'teal') : '—' },
    { key: 'suggested_anchor', label: t('label.anchor'), render: (r) =>
      el('span', { class: 'small', text: truncate(r.suggested_anchor, 26) }) },
    { key: 'status', label: t('label.status'), render: (r) => statusPill(r.status) },
  ], rows, {
    selectable: true,
    onSelectionChange: (ids) => { selection = ids; renderSelectionBar(ctx); },
    onRowClick: (r) => openOpportunity(ctx, r),
  }));

  out.append(el('p', { class: 'field-hint', text: es
    ? `${rows.length} oportunidades. Empieza por las de esfuerzo 1-2: son la base del perfil y se completan en una tarde.`
    : `${rows.length} opportunities. Start with effort 1-2: they are the profile foundation and take an afternoon.` }));

  return out;
}

function filters(ctx) {
  const es = ctx.lang === 'es';
  const bar = el('div', { class: 'filters' });

  const search = el('input', { class: 'input grow', type: 'search', placeholder: t('label.domain'), value: state.q });
  let timer;
  search.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.q = search.value.trim(); ctx.reload(); }, 300);
  });
  bar.append(search);

  const statusSel = el('select', { class: 'select' }, [
    el('option', { value: '', text: es ? 'Cualquier estado' : 'Any status' }),
    ...['new', 'qualified', 'queued', 'in_progress', 'submitted', 'awaiting_review', 'won', 'rejected', 'skipped']
      .map((v) => el('option', { value: v, text: v.replace(/_/g, ' '), selected: state.status === v })),
  ]);
  statusSel.addEventListener('change', () => { state.status = statusSel.value; ctx.reload(); });
  bar.append(statusSel);

  const effort = el('select', { class: 'select' }, [
    [5, es ? 'Cualquier esfuerzo' : 'Any effort'],
    [1, es ? 'Trivial (1)' : 'Trivial (1)'],
    [2, es ? 'Fácil (≤2)' : 'Easy (≤2)'],
    [3, es ? 'Medio (≤3)' : 'Medium (≤3)'],
  ].map(([v, label]) => el('option', { value: v, text: label, selected: Number(state.maxEffort) === v })));
  effort.addEventListener('change', () => { state.maxEffort = Number(effort.value); ctx.reload(); });
  bar.append(effort);

  const score = el('select', { class: 'select' }, [
    [0, es ? 'Cualquier puntuación' : 'Any score'], [40, '≥ 40'], [60, '≥ 60'], [75, '≥ 75'],
  ].map(([v, label]) => el('option', { value: v, text: label, selected: Number(state.minScore) === v })));
  score.addEventListener('change', () => { state.minScore = Number(score.value); ctx.reload(); });
  bar.append(score);

  return bar;
}

function renderSelectionBar(ctx) {
  const host = document.getElementById('opp-selection');
  if (!host) return;
  host.replaceChildren();
  if (!selection.length) return;
  const es = ctx.lang === 'es';
  host.append(el('div', { class: 'filters' }, [
    el('strong', { text: `${selection.length} ${t('label.selected')}` }),
    actionButton(es ? 'Preparar envíos' : 'Prepare submissions', async () => {
      const r = await api.post(`/projects/${ctx.project.id}/submissions/prepare`, {
        opportunity_ids: selection, limit: selection.length, auto_approve: false,
      });
      (r.messages || []).forEach((m) => toast(m, r.prepared ? 'good' : 'warn'));
      if (r.prepared) ctx.navigate('submissions');
      else ctx.reload();
    }, { small: true, primary: true }),
    actionButton(es ? 'Redactar outreach' : 'Draft outreach', async () => {
      const r = await api.post(`/projects/${ctx.project.id}/outreach/draft`, {
        opportunity_ids: selection, tactic: 'resource_page',
      });
      toast(`${r.drafted} ${es ? 'borradores' : 'drafts'}`, 'good');
      ctx.navigate('outreach');
    }, { small: true }),
    actionButton(es ? 'Buscar contactos' : 'Find contacts', async () => {
      const r = await api.post(`/projects/${ctx.project.id}/outreach/find-contacts`, selection);
      toast(`${r.found} / ${r.checked} ${es ? 'contactos encontrados' : 'contacts found'}`, 'good');
      ctx.reload();
    }, { small: true }),
    actionButton(es ? 'Marcar cualificadas' : 'Mark qualified', async () => {
      for (const id of selection) {
        await api.patch(`/projects/${ctx.project.id}/opportunities/${id}`, { status: 'qualified' });
      }
      toast(t('msg.saved'), 'good');
      ctx.reload();
    }, { small: true }),
    actionButton(es ? 'Descartar' : 'Skip', async () => {
      for (const id of selection) {
        await api.patch(`/projects/${ctx.project.id}/opportunities/${id}`, { status: 'skipped' });
      }
      toast(t('msg.saved'), 'good');
      ctx.reload();
    }, { small: true }),
  ]));
}

async function openOpportunity(ctx, row) {
  const es = ctx.lang === 'es';
  const detail = await api.get(`/projects/${ctx.project.id}/opportunities/${row.id}`);
  const opp = detail.opportunity;
  const source = detail.source;
  const bd = opp.score_breakdown || {};

  const statusSel = el('select', { class: 'select' },
    ['new', 'qualified', 'queued', 'in_progress', 'submitted', 'awaiting_review', 'won', 'rejected', 'skipped']
      .map((v) => el('option', { value: v, text: v.replace(/_/g, ' '), selected: opp.status === v })));
  const anchor = el('input', { class: 'input', value: opp.suggested_anchor });
  const landing = el('input', { class: 'input', value: opp.landing_url });
  const notes = el('textarea', { class: 'textarea', style: 'min-height:70px' });
  notes.value = opp.notes || '';

  openModal({
    title: opp.target_domain,
    wide: true,
    body: frag([
      el('div', { class: 'stats' }, [
        stat(t('label.score'), num(opp.score, 1)),
        stat(t('label.authority'), num(opp.authority, 1)),
        stat(es ? 'Relevancia' : 'Relevance', num(opp.relevance, 1)),
        stat(t('label.effort'), `${opp.effort}/5`),
      ]),

      el('h3', { style: 'margin:6px 0 8px', text: es ? 'Cómo se calcula la puntuación' : 'How the score is calculated' }),
      el('div', {}, [
        ['authority', es ? 'Autoridad' : 'Authority'],
        ['relevance', es ? 'Relevancia' : 'Relevance'],
        ['ease', es ? 'Facilidad' : 'Ease'],
        ['follow', es ? 'Transfiere equity' : 'Passes equity'],
        ['evidence', es ? 'Evidencia (competencia)' : 'Evidence (competitors)'],
      ].map(([key, label]) => {
        const value = bd[key] ?? 0;
        const weight = bd.weights?.[key];
        return el('div', { class: 'bar-row' }, [
          el('div', { class: 'bar-label', text: label }),
          el('div', { class: 'bar-track' }, [
            el('div', { class: 'bar-fill', style: `width:${Math.min(100, value * 100)}%` }),
          ]),
          el('div', { class: 'bar-value', text: `${(value * 100).toFixed(0)}%${weight ? ` ×${weight}` : ''}` }),
        ]);
      })),
      bd.geo_bonus ? el('p', { class: 'field-hint', text:
        `${es ? 'Bonus de visibilidad IA' : 'AI visibility bonus'}: +${num(bd.geo_bonus, 1)} ${es ? '(esta fuente aparece a menudo como cita en respuestas de asistentes)' : '(this source often appears as a citation in assistant answers)'}` }) : null,

      el('h3', { style: 'margin:16px 0 8px', text: es ? 'Detalles' : 'Details' }),
      el('dl', { class: 'kv' }, [
        el('dt', { text: t('label.tactic') }), el('dd', {}, [pill(String(opp.tactic).replace(/_/g, ' '))]),
        el('dt', { text: es ? 'URL de envío' : 'Submit URL' }),
        el('dd', {}, [opp.target_url ? externalLink(opp.target_url) : '—']),
        el('dt', { text: es ? 'Descubierto vía' : 'Discovered via' }), el('dd', { text: opp.discovered_via }),
        source ? el('dt', { text: t('label.type') }) : null,
        source ? el('dd', {}, [pill(source.link_type, source.link_type === 'dofollow' ? 'good' : 'warn')]) : null,
        source?.required_fields?.length ? el('dt', { text: es ? 'Campos requeridos' : 'Required fields' }) : null,
        source?.required_fields?.length
          ? el('dd', {}, source.required_fields.map((f) => pill(f.replace(/_/g, ' ')))) : null,
        source?.guidelines_url ? el('dt', { text: es ? 'Normas' : 'Guidelines' }) : null,
        source?.guidelines_url ? el('dd', {}, [externalLink(source.guidelines_url)]) : null,
        opp.contact_email ? el('dt', { text: 'Email' }) : null,
        opp.contact_email ? el('dd', { text: opp.contact_email }) : null,
      ]),

      opp.notes || source?.notes
        ? el('div', { class: 'callout callout-info' }, [
            el('div', {}, [
              el('strong', { text: es ? 'Cómo abordarlo' : 'How to approach it' }),
              opp.notes || source?.notes,
            ]),
          ])
        : null,

      el('h3', { style: 'margin:16px 0 8px', text: es ? 'Actualizar' : 'Update' }),
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: t('label.status') }), statusSel]),
        el('label', { class: 'field' }, [el('span', { text: es ? 'Anchor sugerido' : 'Suggested anchor' }), anchor]),
      ]),
      el('label', { class: 'field' }, [el('span', { text: es ? 'URL de destino' : 'Landing URL' }), landing]),
      el('label', { class: 'field' }, [el('span', { text: t('label.notes') }), notes]),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.close'), onClick: closeModal }),
      actionButton(t('action.save'), async () => {
        await api.patch(`/projects/${ctx.project.id}/opportunities/${opp.id}`, {
          status: statusSel.value, notes: notes.value,
          suggested_anchor: anchor.value, landing_url: landing.value,
        });
        closeModal(); toast(t('msg.saved'), 'good'); ctx.reload();
      }, { primary: true }),
    ],
  });
}

function openGenerate(ctx) {
  const es = ctx.lang === 'es';
  const maxEffort = el('select', { class: 'select' },
    [5, 4, 3, 2, 1].map((v) => el('option', { value: v, text: `≤ ${v}`, selected: v === 5 })));
  const limit = el('input', { class: 'input', type: 'number', value: 250, min: 10, max: 2000 });
  const onlyFree = el('input', { type: 'checkbox', checked: true });
  const onlyDofollow = el('input', { type: 'checkbox' });
  const includeAi = el('input', { type: 'checkbox', checked: true });
  const country = el('input', { class: 'input', value: ctx.project.country });

  openModal({
    title: es ? 'Generar oportunidades' : 'Generate opportunities',
    body: frag([
      el('p', { class: 'field-hint', text: es
        ? 'Draken puntúa las 355 fuentes del catálogo para este proyecto concreto: país, idioma, sector, lo que ya tienes y el peso de citación en IA.'
        : 'Draken scores all 355 catalog sources for this specific project: country, language, industry, what you already have, and AI citation weight.' }),
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: t('label.effort') }), maxEffort]),
        el('label', { class: 'field' }, [el('span', { text: t('label.country') }), country]),
        el('label', { class: 'field' }, [el('span', { text: es ? 'Máximo' : 'Limit' }), limit]),
      ]),
      el('label', { class: 'checkbox', style: 'margin-bottom:6px' }, [onlyFree, es ? 'Solo fuentes gratuitas' : 'Free sources only']),
      el('label', { class: 'checkbox', style: 'margin-bottom:6px' }, [onlyDofollow, es ? 'Solo dofollow' : 'Dofollow only']),
      el('label', { class: 'checkbox' }, [includeAi, es ? 'Incluir fuentes de datos/IA (alta citación en asistentes)' : 'Include dataset/AI sources (high assistant citation)']),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.generate'), async () => {
        const r = await api.post(`/projects/${ctx.project.id}/opportunities/generate`, {
          categories: [], countries: country.value ? [country.value] : [],
          max_effort: Number(maxEffort.value), only_free: onlyFree.checked,
          only_dofollow: onlyDofollow.checked, include_ai_sources: includeAi.checked,
          limit: Number(limit.value),
        });
        closeModal();
        toast(`${r.created} ${es ? 'nuevas' : 'new'}, ${r.already_present} ${es ? 'ya existían' : 'already present'}`, 'good');
        ctx.reload();
      }, { primary: true }),
    ],
  });
}

export function actions(ctx) {
  if (!ctx.project) return [];
  const es = ctx.lang === 'es';
  return [
    actionButton(t('action.generate'), () => openGenerate(ctx), { primary: true }),
    actionButton(es ? 'Menciones sin enlace' : 'Unlinked mentions', async () => {
      const { job_id } = await api.post(`/projects/${ctx.project.id}/opportunities/prospect-mentions`);
      toast(`${t('msg.queued')} #${job_id}`, 'good');
      ctx.watchJob(job_id, (j) => {
        if (j.state === 'succeeded') {
          toast(`${j.result?.created ?? 0} ${es ? 'encontradas' : 'found'}`, 'good');
          ctx.reload();
        }
      });
    }),
    actionButton(es ? 'Link intersect' : 'Link intersect', async () => {
      const { job_id } = await api.post(`/projects/${ctx.project.id}/opportunities/prospect-competitors`);
      toast(`${t('msg.queued')} #${job_id}`, 'good');
      ctx.watchJob(job_id, (j) => {
        if (j.state === 'succeeded') {
          toast(`${j.result?.created ?? 0} ${es ? 'nuevas' : 'new'}`, 'good');
          ctx.reload();
        }
      });
    }),
  ];
}
