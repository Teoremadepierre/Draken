import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, barRow, callout, card, compact, dateTime, el, empty, frag,
  lineChart, num, pct, pill, scoreChip, stat, statusPill, toast,
} from '../ui.js';

export const meta = { id: 'dashboard', icon: 'dashboard', group: 'overview' };

export async function render(ctx) {
  const { project, navigate } = ctx;
  if (!project) return ctx.noProject();

  const data = await api.get(`/projects/${project.id}/overview`);
  const out = frag([]);

  // --- deployment caveats, stated up front rather than buried -------------
  if (ctx.config.serp_approximate) {
    out.append(callout(t('hint.serpFree'), 'warn', t('msg.approximate')));
  }
  if (!Object.values(ctx.config.ai_engines_configured || {}).some(Boolean)) {
    out.append(callout(t('hint.noAiKeys'), 'info'));
  }

  // --- headline numbers ---------------------------------------------------
  const c = data.counts;
  const lp = data.link_profile;
  const health = data.site_health;
  out.append(el('div', { class: 'stats' }, [
    stat(t('label.authority'), num(lp.authority_score, 1), {
      note: `${num(lp.referring_domains)} ${ctx.lang === 'es' ? 'dominios de referencia' : 'referring domains'}`,
    }),
    stat(ctx.lang === 'es' ? 'Salud del sitio' : 'Site health',
      health.score === null ? '—' : num(health.score, 1), {
        note: health.pages_crawled ? `${num(health.pages_crawled)} ${t('label.pages').toLowerCase()}` : t('empty.noData'),
        tone: health.score === null ? null : health.score >= 80 ? 'good' : health.score >= 55 ? 'warn' : 'bad',
      }),
    stat(ctx.lang === 'es' ? 'Visibilidad' : 'Visibility', num(data.rankings.visibility_index, 1), {
      note: `${num(c.tracked_keywords)} ${ctx.lang === 'es' ? 'keywords seguidas' : 'tracked keywords'}`,
    }),
    stat(ctx.lang === 'es' ? 'Tráfico estimado' : 'Est. traffic', compact(data.rankings.estimated_traffic), {
      note: ctx.lang === 'es' ? 'visitas/mes desde posiciones' : 'visits/mo from positions',
    }),
    stat(ctx.lang === 'es' ? 'Menciones IA' : 'AI mentions', pct(data.ai_visibility.mention_rate), {
      note: `${ctx.lang === 'es' ? 'citas' : 'citations'} ${pct(data.ai_visibility.citation_rate)}`,
    }),
    stat(ctx.lang === 'es' ? 'Enlaces ganados' : 'Links won', num(c.links_won), {
      note: `${num(c.opportunities)} ${ctx.lang === 'es' ? 'oportunidades' : 'opportunities'}`,
    }),
  ]));

  // --- next actions: the point of the whole screen ------------------------
  if (data.next_actions?.length) {
    out.append(card(
      ctx.lang === 'es' ? 'Qué hacer ahora' : 'What to do next',
      el('ul', { class: 'action-list' }, data.next_actions.map((a) =>
        el('li', {}, [
          el('div', { class: 'action-area', text: a.area }),
          el('div', {}, [
            a.action,
            ' ',
            el('button', {
              class: 'btn btn-ghost btn-sm',
              text: t('action.view'),
              onClick: () => navigate(AREA_ROUTES[a.area] || 'dashboard'),
            }),
          ]),
        ]))),
      { sub: ctx.lang === 'es'
        ? 'Ordenado por impacto. Cada módulo aporta lo que ha detectado.'
        : 'Ordered by impact. Each module contributes what it found.' },
    ));
  }

  // --- charts ------------------------------------------------------------
  const grid = el('div', { class: 'grid grid-2' });

  const trend = data.rankings.trend || [];
  grid.append(card(
    ctx.lang === 'es' ? 'Visibilidad en el tiempo' : 'Visibility over time',
    trend.length >= 2
      ? lineChart(trend.map((d) => ({ label: d.date.slice(5), value: d.visibility })), { format: (v) => num(v, 1) })
      : empty(t('empty.noData'), ctx.lang === 'es'
        ? 'Marca keywords como seguidas y ejecuta el seguimiento de posiciones varios días para ver la tendencia.'
        : 'Track some keywords and run rank tracking on several days to build a trend.'),
  ));

  const velocity = lp.velocity || [];
  grid.append(card(
    ctx.lang === 'es' ? 'Enlaces ganados y perdidos' : 'Links gained and lost',
    velocity.some((v) => v.gained || v.lost)
      ? el('div', {}, velocity.map((v) => barRow(
          v.month,
          v.net,
          Math.max(1, ...velocity.map((x) => Math.max(Math.abs(x.gained), Math.abs(x.lost)))),
          { formatted: `+${v.gained} / -${v.lost}`, tone: v.net >= 0 ? 'good' : 'bad' },
        )))
      : empty(t('empty.noBacklinks'), t('empty.noBacklinksBody')),
  ));

  const dist = data.rankings.distribution || {};
  const distTotal = Object.values(dist).reduce((a, b) => a + b, 0);
  grid.append(card(
    ctx.lang === 'es' ? 'Distribución de posiciones' : 'Position distribution',
    distTotal
      ? el('div', {}, [
          barRow('1-3', dist.top3 || 0, distTotal, { tone: 'good' }),
          barRow('4-10', dist.top10 || 0, distTotal, { tone: 'teal' }),
          barRow('11-20', dist.top20 || 0, distTotal, { tone: 'warn' }),
          barRow('21-50', dist.top50 || 0, distTotal),
          barRow('50+', dist.beyond || 0, distTotal),
          barRow(ctx.lang === 'es' ? 'Sin posición' : 'Unranked', dist.unranked || 0, distTotal, { tone: 'bad' }),
          dist.top20 ? el('p', { class: 'field-hint', text: ctx.lang === 'es'
            ? `${dist.top20} keyword(s) en posiciones 11-20: es donde un cambio pequeño rinde más.`
            : `${dist.top20} keyword(s) at 11-20 - the cheapest wins on the board.` }) : null,
        ])
      : empty(t('empty.noData')),
  ));

  const pipeline = data.pipeline || {};
  grid.append(card(
    ctx.lang === 'es' ? 'Pipeline de enlaces' : 'Link pipeline',
    Object.keys(pipeline.by_status || {}).length
      ? el('div', {}, [
          ...Object.entries(pipeline.by_status).map(([status, n]) =>
            barRow(String(status).replace(/_/g, ' '), n, pipeline.total || 1)),
          el('div', { class: 'grid grid-3', style: 'margin-top:12px' }, [
            stat(ctx.lang === 'es' ? 'Alta prioridad' : 'High priority', num(pipeline.high_priority), { small: true }),
            stat(ctx.lang === 'es' ? 'Victorias rápidas' : 'Quick wins', num(pipeline.quick_wins), { small: true }),
            stat(ctx.lang === 'es' ? 'Conversión' : 'Conversion', pct(pipeline.conversion_rate, 1), { small: true }),
          ]),
        ])
      : empty(t('empty.noData')),
  ));

  out.append(grid);

  // --- movers & issues ---------------------------------------------------
  const lower = el('div', { class: 'grid grid-2' });

  const movers = data.rankings.movers || { up: [], down: [] };
  if (movers.up.length || movers.down.length) {
    lower.append(card(
      ctx.lang === 'es' ? 'Mayores movimientos' : 'Biggest movers',
      el('div', {}, [
        ...movers.up.slice(0, 5).map((m) => moverRow(m, true)),
        ...movers.down.slice(0, 5).map((m) => moverRow(m, false)),
      ]),
    ));
  }

  if (Object.keys(health.issue_counts || {}).length) {
    lower.append(card(
      ctx.lang === 'es' ? 'Problemas del sitio' : 'Site issues',
      frag([
        el('div', { class: 'grid grid-4' }, ['critical', 'error', 'warning', 'notice'].map((sev) =>
          stat(sev, num(health.issue_counts[sev] || 0), {
            small: true,
            tone: sev === 'critical' || sev === 'error' ? 'bad' : sev === 'warning' ? 'warn' : null,
          }))),
        el('p', { class: 'field-hint', style: 'margin-top:10px' }, [
          `${ctx.lang === 'es' ? 'Última auditoría' : 'Last audit'}: ${dateTime(health.last_run)}`,
        ]),
        actionButton(t('action.view'), () => navigate('audit'), { small: true }),
      ]),
    ));
  }

  if (lp.anchor_warnings?.length) {
    lower.append(card(
      ctx.lang === 'es' ? 'Riesgo de anchors' : 'Anchor risk',
      el('ul', { class: 'rec-list' }, lp.anchor_warnings.map((w) => el('li', { text: w }))),
    ));
  }

  const engines = data.ai_visibility.by_engine || [];
  if (engines.length) {
    lower.append(card(
      ctx.lang === 'es' ? 'Visibilidad por motor de IA' : 'Visibility by AI engine',
      el('div', {}, engines.map((e) => el('div', { class: 'bar-row' }, [
        el('div', { class: 'bar-label' }, [pill(e.engine, 'accent')]),
        el('div', { class: 'bar-track' }, [
          el('div', { class: 'bar-fill', style: `width:${Math.min(100, e.avg_visibility_score)}%` }),
        ]),
        el('div', { class: 'bar-value', text: num(e.avg_visibility_score, 1) }),
      ]))),
      { sub: `${ctx.lang === 'es' ? 'Competidores más citados' : 'Most-cited competitors'}: ${
        (data.ai_visibility.competitor_share || []).map((cs) => cs.competitor).join(', ') || '—'}` },
    ));
  }

  out.append(lower);
  return out;
}

const AREA_ROUTES = {
  backlinks: 'opportunities',
  site: 'audit',
  keywords: 'keywords',
  'ai-visibility': 'aivisibility',
  submissions: 'submissions',
};

function moverRow(m, up) {
  return el('div', { class: 'bar-row' }, [
    el('div', { class: 'bar-label', style: 'flex-basis:auto;flex:1', title: m.term }, [m.term]),
    el('div', { style: 'flex:0 0 auto' }, [
      pill(`${m.previous_position} → ${m.position}`, up ? 'good' : 'bad'),
    ]),
    el('div', { class: 'bar-value', text: `${up ? '+' : ''}${m.change}` }),
  ]);
}

export function actions(ctx) {
  if (!ctx.project) return [];
  return [
    actionButton(ctx.lang === 'es' ? 'Barrido completo' : 'Full sweep', async () => {
      const { job_id } = await api.post(`/projects/${ctx.project.id}/jobs/full_sweep`, {});
      toast(`${t('msg.queued')} #${job_id}. ${t('msg.jobRunning')}`, 'good');
      ctx.watchJob(job_id);
    }, { primary: true }),
    actionButton(t('action.refresh'), () => ctx.reload()),
  ];
}
