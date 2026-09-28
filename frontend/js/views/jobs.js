import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, card, closeModal, dateTime, el, empty, frag, meter, num,
  openModal, pill, statusPill, table, toast, truncate,
} from '../ui.js';

export const meta = { id: 'jobs', icon: 'jobs', group: 'system' };

export async function render(ctx) {
  const es = ctx.lang === 'es';
  const [jobs, kinds, activity] = await Promise.all([
    api.get('/jobs', { project_id: ctx.project?.id, limit: 60 }),
    api.get('/jobs/kinds'),
    ctx.project ? api.get(`/projects/${ctx.project.id}/activity`, { limit: 80 }) : Promise.resolve([]),
  ]);

  const out = frag([]);

  out.append(card(es ? 'Lanzar una tarea' : 'Run a job', frag([
    el('p', { class: 'card-sub', text: es
      ? 'Cualquier módulo se puede ejecutar en segundo plano. Lo mismo está disponible por CLI para cron.'
      : 'Any module can run in the background. The same is available over the CLI for cron.' }),
    el('div', { style: 'display:flex;flex-wrap:wrap;gap:6px' }, (kinds.kinds || []).map((kind) =>
      actionButton(kind.replace(/_/g, ' '), async () => {
        if (!ctx.project) { toast(es ? 'Elige un proyecto primero' : 'Pick a project first', 'bad'); return; }
        const r = await api.post(`/projects/${ctx.project.id}/jobs/${kind}`, {});
        toast(`${t('msg.queued')} #${r.job_id}`, 'good');
        ctx.watchJob(r.job_id, (j) => { if (j.state === 'succeeded') ctx.reload(); });
      }, { small: true }))),
  ])));

  out.append(card(es ? 'Tareas recientes' : 'Recent jobs',
    jobs.length
      ? table([
          { key: 'id', label: '#', num: true, width: '54px' },
          { key: 'kind', label: es ? 'Tipo' : 'Kind', render: (r) => pill(r.kind.replace(/_/g, ' ')) },
          { key: 'state', label: t('label.status'), render: (r) => statusPill(r.state) },
          { key: 'progress', label: t('label.progress'), render: (r) =>
            r.state === 'running' ? meter(r.progress * 100) : el('span', { class: 'faint small', text: r.message || '—' }) },
          { key: 'created_at', label: es ? 'Creada' : 'Created', render: (r) => dateTime(r.created_at) },
          { key: 'finished_at', label: es ? 'Terminada' : 'Finished', render: (r) => dateTime(r.finished_at) },
        ], jobs, { onRowClick: (r) => openJob(ctx, r) })
      : empty(es ? 'Ninguna tarea todavía' : 'No jobs yet'),
    { actions: [actionButton(t('action.refresh'), () => ctx.reload(), { small: true })] }));

  if (activity.length) {
    out.append(card(es ? 'Registro de actividad' : 'Activity log',
      table([
        { key: 'created_at', label: t('label.date'), render: (r) => dateTime(r.created_at) },
        { key: 'actor', label: es ? 'Actor' : 'Actor', render: (r) => pill(r.actor) },
        { key: 'action', label: es ? 'Acción' : 'Action', render: (r) => r.action },
        { key: 'detail', label: t('label.details'), render: (r) =>
          el('span', { class: 'mono small cell-wrap', text: truncate(JSON.stringify(r.detail || {}), 70) }) },
      ], activity),
      { sub: es
        ? 'Todo lo que Draken hace hacia fuera queda registrado aquí: qué se envió, a dónde y con qué resultado.'
        : 'Everything Draken does to the outside world is recorded here: what was sent, where, and with what result.' }));
  }

  return out;
}

function openJob(ctx, job) {
  const es = ctx.lang === 'es';
  openModal({
    title: `${job.kind.replace(/_/g, ' ')} #${job.id}`,
    wide: true,
    body: frag([
      el('div', { style: 'display:flex;gap:6px;margin-bottom:12px' }, [
        statusPill(job.state),
        job.message ? pill(job.message) : null,
      ]),
      el('dl', { class: 'kv' }, [
        el('dt', { text: es ? 'Creada' : 'Created' }), el('dd', { text: dateTime(job.created_at) }),
        el('dt', { text: es ? 'Iniciada' : 'Started' }), el('dd', { text: dateTime(job.started_at) }),
        el('dt', { text: es ? 'Terminada' : 'Finished' }), el('dd', { text: dateTime(job.finished_at) }),
      ]),
      Object.keys(job.params || {}).length
        ? frag([
            el('h3', { style: 'margin:14px 0 6px', text: es ? 'Parámetros' : 'Params' }),
            el('pre', { class: 'code', text: JSON.stringify(job.params, null, 2) }),
          ])
        : null,
      Object.keys(job.result || {}).length
        ? frag([
            el('h3', { style: 'margin:14px 0 6px', text: es ? 'Resultado' : 'Result' }),
            el('pre', { class: 'code', text: JSON.stringify(job.result, null, 2) }),
          ])
        : null,
      job.error
        ? frag([
            el('h3', { style: 'margin:14px 0 6px', text: t('msg.error') }),
            el('pre', { class: 'code wrap', text: job.error }),
          ])
        : null,
    ]),
    footer: [
      ['pending', 'running'].includes(job.state)
        ? actionButton(t('action.cancel'), async () => {
            await api.post(`/jobs/${job.id}/cancel`);
            closeModal(); toast(t('msg.saved'), 'good'); ctx.reload();
          })
        : null,
      el('button', { class: 'btn', text: t('action.close'), onClick: closeModal }),
    ].filter(Boolean),
  });
}

export function actions(ctx) {
  return [actionButton(t('action.refresh'), () => ctx.reload())];
}
