import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, compact, el, empty, frag, lineChart, num, pill,
  scoreChip, stat, table, toast,
} from '../ui.js';

export const meta = { id: 'rankings', icon: 'rankings', group: 'research' };

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';
  const [overview, tracked] = await Promise.all([
    api.get(`/projects/${ctx.project.id}/rankings/overview`, { days: 60 }),
    api.get(`/projects/${ctx.project.id}/keywords`, { tracked_only: true, limit: 300 }),
  ]);

  const out = frag([]);
  if (ctx.config.serp_approximate) {
    out.append(callout(t('hint.serpFree'), 'warn', t('msg.approximate')));
  }

  if (!overview.tracked_keywords) {
    out.append(card(null, empty(
      es ? 'No hay keywords seguidas' : 'No tracked keywords',
      es ? 'Marca tus keywords de mayor oportunidad como seguidas en la vista de Palabras clave; después ejecuta el seguimiento.'
         : 'Mark your highest-opportunity keywords as tracked in the Keywords view, then run tracking.',
      actionButton(t('view.keywords'), () => ctx.navigate('keywords'), { primary: true }),
    )));
    return out;
  }

  const dist = overview.distribution || {};
  out.append(el('div', { class: 'stats' }, [
    stat(es ? 'Keywords seguidas' : 'Tracked keywords', num(overview.tracked_keywords)),
    stat(es ? 'Índice de visibilidad' : 'Visibility index', num(overview.visibility_index, 1)),
    stat(es ? 'Tráfico estimado' : 'Estimated traffic', compact(overview.estimated_traffic)),
    stat('Top 3', num(dist.top3 || 0), { tone: 'good' }),
    stat('Top 10', num((dist.top3 || 0) + (dist.top10 || 0))),
    stat(es ? 'A tiro (11-20)' : 'Striking distance', num(dist.top20 || 0), {
      tone: 'warn',
      note: es ? 'el mejor sitio donde invertir' : 'best place to invest',
    }),
  ]));

  const trend = overview.trend || [];
  out.append(card(
    es ? 'Posición media' : 'Average position',
    trend.filter((d) => d.avg_position !== null).length >= 2
      ? lineChart(trend.map((d) => ({ label: d.date.slice(5), value: d.avg_position })),
          { invertY: true, format: (v) => `#${Math.round(v)}` })
      : empty(es ? 'Necesitas al menos dos días de datos' : 'Needs at least two days of data'),
    { sub: overview.last_updated ? `${es ? 'Última captura' : 'Last capture'}: ${overview.last_updated}` : null },
  ));

  const movers = overview.movers || { up: [], down: [] };
  if (movers.up.length || movers.down.length) {
    out.append(el('div', { class: 'grid grid-2' }, [
      card(es ? 'Subidas' : 'Gains', moversTable(movers.up, es, true)),
      card(es ? 'Bajadas' : 'Drops', moversTable(movers.down, es, false)),
    ]));
  }

  out.append(card(es ? 'Keywords seguidas' : 'Tracked keywords', table([
    { key: 'term', label: t('label.keyword'), render: (r) => el('span', { class: 'cell-strong', text: r.term }) },
    { key: 'volume', label: t('label.volume'), num: true, render: (r) => compact(r.volume) },
    { key: 'difficulty', label: 'KD', num: true, render: (r) => scoreChip(r.difficulty, { invert: true }) },
    { key: 'intent', label: t('label.intent'), render: (r) => pill(r.intent) },
    { key: 'serp_features', label: 'SERP', render: (r) =>
      (r.serp_features || []).length
        ? el('div', {}, (r.serp_features || []).slice(0, 3).map((f) => pill(f)))
        : '—' },
  ], tracked)));

  return out;
}

function moversTable(rows, es, up) {
  if (!rows.length) return empty(es ? 'Sin movimientos' : 'No movement');
  return table([
    { key: 'term', label: t('label.keyword') },
    { key: 'previous_position', label: es ? 'Antes' : 'Was', num: true, render: (r) => `#${r.previous_position}` },
    { key: 'position', label: es ? 'Ahora' : 'Now', num: true, render: (r) => `#${r.position}` },
    { key: 'change', label: t('label.change'), num: true, render: (r) =>
      pill(`${r.change > 0 ? '+' : ''}${r.change}`, up ? 'good' : 'bad') },
    { key: 'volume', label: t('label.volume'), num: true, render: (r) => compact(r.volume) },
  ], rows);
}

export function actions(ctx) {
  if (!ctx.project) return [];
  const es = ctx.lang === 'es';
  return [
    actionButton(es ? 'Actualizar posiciones' : 'Update positions', async () => {
      const { job_id } = await api.post(`/projects/${ctx.project.id}/rankings/track`,
        { keyword_ids: [], device: 'desktop' }, { background: true });
      toast(`${t('msg.queued')} #${job_id}`, 'good');
      ctx.watchJob(job_id, (job) => {
        if (job.state === 'succeeded') {
          const r = job.result || {};
          toast(`${r.tracked ?? 0} ${es ? 'keywords, ' : 'keywords, '}+${r.improved ?? 0} / -${r.declined ?? 0}`, 'good', t('msg.done'));
          ctx.reload();
        }
      });
    }, { primary: true }),
    actionButton(t('action.refresh'), () => ctx.reload()),
  ];
}
