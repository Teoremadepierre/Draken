import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, barRow, callout, card, closeModal, dateTime, el, empty,
  externalLink, frag, lineChart, num, openModal, pct, pill, scoreChip, stat,
  table, toast, truncate,
} from '../ui.js';

export const meta = { id: 'aivisibility', icon: 'ai', group: 'ai' };

const state = { tab: 'summary' };

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';
  const { tabs } = await import('../ui.js');

  const out = frag([
    tabs([
      { id: 'summary', label: es ? 'Resumen' : 'Summary' },
      { id: 'prompts', label: es ? 'Preguntas' : 'Prompts' },
      { id: 'runs', label: es ? 'Respuestas' : 'Answers' },
    ], state.tab, (id) => { state.tab = id; ctx.reload(); }),
  ]);

  const engines = await api.get(`/projects/${ctx.project.id}/ai/engines`);
  if (!engines.any_configured) {
    out.append(callout(engines.setup_hint, 'warn', t('hint.noAiKeys')));
  }

  if (state.tab === 'summary') out.append(await renderSummary(ctx, engines));
  else if (state.tab === 'prompts') out.append(await renderPrompts(ctx));
  else out.append(await renderRuns(ctx));

  return out;
}

async function renderSummary(ctx, engines) {
  const es = ctx.lang === 'es';
  const s = await api.get(`/projects/${ctx.project.id}/ai/summary`);

  const out = frag([
    el('div', { class: 'stats' }, [
      stat(es ? 'Preguntas seguidas' : 'Prompts tracked', num(s.prompts_tracked)),
      stat(es ? 'Respuestas medidas' : 'Answers measured', num(s.runs)),
      stat(es ? 'Tasa de mención' : 'Mention rate', pct(s.mention_rate), {
        tone: s.mention_rate >= 0.4 ? 'good' : s.mention_rate > 0.1 ? 'warn' : 'bad',
      }),
      stat(es ? 'Tasa de cita' : 'Citation rate', pct(s.citation_rate), {
        note: es ? 'tu dominio como fuente' : 'your domain as a source',
      }),
      stat(es ? 'Puntuación media' : 'Average score', num(s.avg_visibility_score, 1)),
      stat(es ? 'Cuota de voz' : 'Share of voice', pct(s.share_of_voice)),
    ]),
  ]);

  if (s.recommendations?.length) {
    out.append(card(es ? 'Qué mover' : 'What to move',
      el('ul', { class: 'rec-list' }, s.recommendations.map((r) => el('li', { text: r })))));
  }

  const grid = el('div', { class: 'grid grid-2' });

  grid.append(card(es ? 'Por motor' : 'By engine',
    (s.by_engine || []).length
      ? table([
          { key: 'engine', label: t('label.engine'), render: (r) => pill(r.engine, 'accent') },
          { key: 'runs', label: es ? 'Respuestas' : 'Answers', num: true },
          { key: 'mention_rate', label: es ? 'Mención' : 'Mention', num: true, render: (r) => pct(r.mention_rate) },
          { key: 'citation_rate', label: es ? 'Cita' : 'Citation', num: true, render: (r) => pct(r.citation_rate) },
          { key: 'avg_visibility_score', label: t('label.score'), num: true,
            render: (r) => scoreChip(r.avg_visibility_score) },
        ], s.by_engine)
      : empty(es ? 'Sin ejecuciones todavía' : 'No runs yet')));

  grid.append(card(es ? 'Competidores mencionados' : 'Competitors mentioned',
    (s.competitor_share || []).length
      ? el('div', {}, s.competitor_share.map((c) => barRow(
          c.competitor, c.share * 100, 100,
          { formatted: pct(c.share), tone: c.share > s.mention_rate ? 'bad' : '' })))
      : empty(es ? 'Ninguno detectado' : 'None detected'),
    { sub: es
      ? 'En rojo, quienes salen más que tú en tu propio conjunto de preguntas.'
      : 'In red, those named more often than you in your own prompt set.' }));

  if ((s.trend || []).length >= 2) {
    grid.append(card(es ? 'Evolución' : 'Trend',
      lineChart(s.trend.map((d) => ({ label: d.date.slice(5), value: d.avg_visibility_score })),
        { format: (v) => num(v, 1) })));
  }

  grid.append(card(es ? 'Dominios que citan los motores' : 'Domains the engines cite',
    (s.top_cited_domains || []).length
      ? table([
          { key: 'domain', label: t('label.domain'), render: (r) => externalLink(`https://${r.domain}`, r.domain) },
          { key: 'citations', label: es ? 'Citas' : 'Citations', num: true },
        ], s.top_cited_domains.slice(0, 20))
      : empty(es ? 'Sin citas registradas' : 'No citations recorded'),
    { sub: es
      ? 'Esta es tu lista de objetivos de enlaces para IA: consigue estar en estas fuentes y aparecerás en las respuestas.'
      : 'This is your AI link-target list: get onto these sources and you show up in the answers.' }));

  out.append(grid);

  if ((s.uncovered_prompts || []).length) {
    out.append(card(es ? 'Preguntas donde no apareces' : 'Prompts where you do not appear',
      table([
        { key: 'prompt', label: t('label.prompt'), render: (r) => el('span', { class: 'cell-wrap', text: r.prompt }) },
        { key: 'category', label: t('label.category'), render: (r) => pill(r.category) },
        { key: 'priority', label: es ? 'Prioridad' : 'Priority', num: true },
      ], s.uncovered_prompts),
      { sub: es
        ? 'Empieza por las de prioridad 1: son consultas de descubrimiento, donde se decide la compra.'
        : 'Start with priority 1: those are discovery queries, where the decision gets made.' }));
  }

  return out;
}

async function renderPrompts(ctx) {
  const es = ctx.lang === 'es';
  const prompts = await api.get(`/projects/${ctx.project.id}/ai/prompts`);

  if (!prompts.length) {
    return card(null, empty(
      t('empty.noPrompts'), t('empty.noPromptsBody'),
      actionButton(t('action.generate'), () => generate(ctx), { primary: true }),
    ));
  }

  return frag([
    table([
      { key: 'prompt', label: t('label.prompt'), render: (r) => el('span', { class: 'cell-wrap', text: r.prompt }) },
      { key: 'category', label: t('label.category'), render: (r) => pill(r.category) },
      { key: 'intent', label: t('label.intent'), render: (r) => pill(r.intent) },
      { key: 'language', label: t('label.language'), render: (r) => pill(r.language) },
      { key: 'priority', label: es ? 'Prioridad' : 'Priority', num: true },
      { key: 'id', label: '', width: '48px', render: (r) => el('button', {
        class: 'btn btn-ghost btn-sm', text: '×', title: t('action.delete'),
        onClick: async (e) => {
          e.stopPropagation();
          await api.del(`/projects/${ctx.project.id}/ai/prompts/${r.id}`);
          toast(t('msg.deleted'), 'good'); ctx.reload();
        },
      }) },
    ], prompts),
    el('p', { class: 'field-hint', text: es
      ? `${prompts.length} preguntas. Son las que escribiría un cliente real, no consultas de marca: si solo mides "¿qué es X?", siempre parecerás visible.`
      : `${prompts.length} prompts. These are what a real buyer types, not brand queries: if you only measure "what is X?", you will always look visible.` }),
  ]);
}

async function renderRuns(ctx) {
  const es = ctx.lang === 'es';
  const runs = await api.get(`/projects/${ctx.project.id}/ai/runs`, { limit: 200 });

  if (!runs.length) {
    return card(null, empty(
      es ? 'Sin respuestas registradas' : 'No answers recorded',
      es ? 'Ejecuta el conjunto de preguntas contra los motores configurados para obtener una línea base.'
         : 'Run the prompt set against the configured engines to get a baseline.',
    ));
  }

  return table([
    { key: 'engine', label: t('label.engine'), render: (r) => pill(r.engine, 'accent') },
    { key: 'brand_mentioned', label: t('label.mentioned'), render: (r) =>
      r.brand_mentioned ? pill(r.brand_position ? `#${r.brand_position}` : '✓', 'good') : pill('—', 'bad') },
    { key: 'domain_cited', label: t('label.cited'), render: (r) =>
      r.domain_cited ? pill('✓', 'good') : pill('—') },
    { key: 'competitors_mentioned', label: es ? 'Competencia' : 'Competitors', render: (r) =>
      (r.competitors_mentioned || []).length
        ? el('span', { class: 'small faint', text: truncate((r.competitors_mentioned || []).join(', '), 34) })
        : '—' },
    { key: 'sentiment', label: t('label.sentiment'), render: (r) =>
      pill(r.sentiment, r.sentiment === 'positive' ? 'good' : r.sentiment === 'negative' ? 'bad' : '') },
    { key: 'visibility_score', label: t('label.score'), num: true, render: (r) => scoreChip(r.visibility_score) },
    { key: 'captured_at', label: t('label.date'), render: (r) => dateTime(r.captured_at) },
  ], runs, { onRowClick: (r) => openRun(ctx, r) });
}

function openRun(ctx, run) {
  const es = ctx.lang === 'es';
  openModal({
    title: `${run.engine} · ${run.model || ''}`,
    wide: true,
    body: frag([
      el('div', { style: 'display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px' }, [
        run.brand_mentioned ? pill(`${es ? 'mencionado' : 'mentioned'}${run.brand_position ? ` #${run.brand_position}` : ''}`, 'good') : pill(es ? 'no mencionado' : 'not mentioned', 'bad'),
        run.domain_cited ? pill(es ? 'dominio citado' : 'domain cited', 'good') : null,
        pill(run.sentiment, run.sentiment === 'positive' ? 'good' : run.sentiment === 'negative' ? 'bad' : ''),
        pill(`${es ? 'puntuación' : 'score'} ${num(run.visibility_score, 1)}`, 'accent'),
      ]),
      run.error ? el('div', { class: 'callout callout-warn' }, [el('div', { text: run.error })]) : null,
      el('h3', { style: 'margin:6px 0 8px', text: es ? 'Respuesta completa' : 'Full answer' }),
      el('pre', { class: 'code wrap', text: run.answer || '—' }),
      (run.citations || []).length
        ? frag([
            el('h3', { style: 'margin:14px 0 8px', text: es ? 'Fuentes citadas' : 'Cited sources' }),
            el('ul', { style: 'margin:0;padding-left:18px' },
              run.citations.map((c) => el('li', {}, [externalLink(c)]))),
          ])
        : null,
    ]),
    footer: [el('button', { class: 'btn', text: t('action.close'), onClick: closeModal })],
  });
}

function generate(ctx) {
  const es = ctx.lang === 'es';
  const limit = el('input', { class: 'input', type: 'number', value: 40, min: 5, max: 200 });
  const fromKeywords = el('input', { type: 'checkbox', checked: true });
  const topics = el('textarea', { class: 'textarea', style: 'min-height:60px',
    placeholder: es ? 'temas extra, uno por línea' : 'extra topics, one per line' });
  openModal({
    title: es ? 'Generar conjunto de preguntas' : 'Generate prompt set',
    body: frag([
      el('p', { class: 'field-hint', text: es
        ? 'Se construyen a partir de tu sector, tu ficha de empresa, tus competidores y tus keywords de mayor oportunidad.'
        : 'Built from your industry, business profile, competitors and highest-opportunity keywords.' }),
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: es ? 'Cuántas' : 'How many' }), limit]),
      ]),
      el('label', { class: 'checkbox', style: 'margin-bottom:10px' }, [fromKeywords,
        es ? 'Derivar preguntas de mis keywords' : 'Derive prompts from my keywords']),
      el('label', { class: 'field' }, [el('span', { text: es ? 'Temas adicionales' : 'Extra topics' }), topics]),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.generate'), async () => {
        const r = await api.post(`/projects/${ctx.project.id}/ai/prompts/generate`, {
          from_keywords: fromKeywords.checked,
          limit: Number(limit.value),
          extra_topics: topics.value.split('\n').map((s) => s.trim()).filter(Boolean),
        });
        closeModal();
        toast(`${r.created} ${es ? 'preguntas nuevas' : 'new prompts'}`, 'good');
        state.tab = 'prompts';
        ctx.reload();
      }, { primary: true }),
    ],
  });
}

export function actions(ctx) {
  if (!ctx.project) return [];
  const es = ctx.lang === 'es';
  return [
    actionButton(t('action.generate'), () => generate(ctx), { primary: true }),
    actionButton(es ? 'Medir ahora' : 'Measure now', async () => {
      try {
        const r = await api.post(`/projects/${ctx.project.id}/ai/run`, {
          engines: [], prompt_ids: [], limit: 20,
        });
        toast(`${t('msg.queued')} #${r.job_id}`, 'good');
        ctx.watchJob(r.job_id, (j) => {
          if (j.state === 'succeeded') {
            toast(`${j.result?.runs ?? 0} ${es ? 'respuestas medidas' : 'answers measured'}`, 'good', t('msg.done'));
            state.tab = 'summary';
            ctx.reload();
          }
        });
      } catch (e) {
        toast(e.message, 'bad', t('msg.error'));
      }
    }),
    actionButton(t('view.geoassets'), () => ctx.navigate('geoassets')),
  ];
}
