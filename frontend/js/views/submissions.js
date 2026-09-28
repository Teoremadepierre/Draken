import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, closeModal, copyToClipboard, dateTime, el, empty,
  externalLink, frag, num, openModal, pill, stat, statusPill, table, toast,
} from '../ui.js';

export const meta = { id: 'submissions', icon: 'submissions', group: 'links' };

const state = { stateFilter: '' };
let selection = [];

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';

  const [rows, settings, completeness] = await Promise.all([
    api.get(`/projects/${ctx.project.id}/submissions`, { state: state.stateFilter, limit: 300 }),
    api.get(`/projects/${ctx.project.id}/submissions/settings`),
    api.get(`/projects/${ctx.project.id}/profile/completeness`),
  ]);

  const out = frag([]);

  if (settings.dry_run) out.append(callout(t('hint.dryRun'), 'warn', es ? 'Simulación' : 'Dry run'));
  out.append(callout(settings.note, 'info'));

  if (!completeness.ready_for_submissions) {
    out.append(callout(
      `${es ? 'Ficha de empresa al' : 'Business profile is'} ${Math.round(completeness.completeness * 100)}%. ${completeness.note}`,
      'warn',
      es ? 'Completa la ficha primero' : 'Complete the profile first',
    ));
    out.append(card(null, empty(
      es ? 'Faltan datos de empresa' : 'Business data missing',
      `${es ? 'Campos pendientes' : 'Missing fields'}: ${completeness.missing_fields.join(', ')}`,
      actionButton(t('view.profile'), () => ctx.navigate('profile'), { primary: true }),
    )));
    return out;
  }

  const byState = rows.reduce((acc, r) => { acc[r.state] = (acc[r.state] || 0) + 1; return acc; }, {});
  out.append(el('div', { class: 'stats' }, [
    stat(es ? 'Total' : 'Total', num(rows.length)),
    stat(es ? 'Esperando aprobación' : 'Awaiting approval', num(byState.awaiting_approval || 0), {
      tone: byState.awaiting_approval ? 'warn' : null,
    }),
    stat(es ? 'Aprobados' : 'Approved', num(byState.approved || 0)),
    stat(es ? 'Manual pendiente' : 'Manual pending', num(byState.manual_required || 0)),
    stat(es ? 'Enviados' : 'Submitted', num(byState.submitted || 0)),
    stat(es ? 'Verificados' : 'Verified', num(byState.verified || 0), { tone: 'good' }),
  ]));

  const filter = el('select', { class: 'select' }, [
    el('option', { value: '', text: es ? 'Cualquier estado' : 'Any state' }),
    ...['draft', 'awaiting_approval', 'approved', 'manual_required', 'submitted', 'verified', 'failed']
      .map((v) => el('option', { value: v, text: v.replace(/_/g, ' '), selected: state.stateFilter === v })),
  ]);
  filter.addEventListener('change', () => { state.stateFilter = filter.value; ctx.reload(); });
  out.append(el('div', { class: 'filters' }, [
    filter,
    el('span', { class: 'field-hint', text: es
      ? `Límites: ${settings.per_domain_daily_cap}/dominio/día, ${settings.global_daily_cap}/día en total`
      : `Caps: ${settings.per_domain_daily_cap}/domain/day, ${settings.global_daily_cap}/day overall` }),
  ]));
  out.append(el('div', { id: 'sub-selection' }));

  if (!rows.length) {
    out.append(card(null, empty(
      t('empty.noSubmissions'), t('empty.noSubmissionsBody'),
      actionButton(es ? 'Ir a oportunidades' : 'Go to opportunities',
        () => ctx.navigate('opportunities'), { primary: true }),
    )));
    return out;
  }

  out.append(table([
    { key: 'id', label: '#', num: true, width: '54px' },
    { key: 'state', label: t('label.status'), render: (r) => statusPill(r.state) },
    { key: 'method', label: es ? 'Método' : 'Method', render: (r) => pill(r.method.replace(/_/g, ' ')) },
    { key: 'payload', label: es ? 'Campos listos' : 'Fields ready', render: (r) => {
      const fields = Object.keys(r.payload?.fields || {}).length;
      const missing = (r.payload?.missing || []).length;
      return el('span', {}, [
        pill(`${fields} ok`, 'good'),
        missing ? pill(`${missing} ${es ? 'faltan' : 'missing'}`, 'warn') : null,
      ]);
    } },
    { key: 'live_url', label: es ? 'URL publicada' : 'Live URL', render: (r) =>
      r.live_url ? externalLink(r.live_url) : el('button', {
        class: 'btn btn-ghost btn-sm',
        text: es ? 'Registrar' : 'Record',
        onClick: (e) => { e.stopPropagation(); recordLiveUrl(ctx, r); },
      }) },
    { key: 'dry_run', label: es ? 'Simulado' : 'Dry run', render: (r) =>
      r.dry_run ? pill(es ? 'sí' : 'yes', 'warn') : pill(es ? 'real' : 'real', 'good') },
    { key: 'created_at', label: t('label.date'), render: (r) => dateTime(r.created_at) },
  ], rows, {
    selectable: true,
    onSelectionChange: (ids) => { selection = ids; renderSelectionBar(ctx); },
    onRowClick: (r) => openSubmission(ctx, r),
  }));

  return out;
}

function renderSelectionBar(ctx) {
  const host = document.getElementById('sub-selection');
  if (!host) return;
  host.replaceChildren();
  if (!selection.length) return;
  const es = ctx.lang === 'es';
  host.append(el('div', { class: 'filters' }, [
    el('strong', { text: `${selection.length} ${t('label.selected')}` }),
    actionButton(t('action.approve'), async () => {
      const r = await api.post(`/projects/${ctx.project.id}/submissions/approve`, {
        submission_ids: selection, approved_by: 'operator',
      });
      (r.messages || []).forEach((m) => toast(m, 'good'));
      ctx.reload();
    }, { small: true, primary: true }),
    actionButton(t('action.run'), async () => {
      const r = await api.post(`/projects/${ctx.project.id}/submissions/run`, {
        submission_ids: selection, limit: selection.length, dry_run: null,
      });
      toast(`${t('msg.queued')} #${r.job_id}${r.dry_run ? ` · ${es ? 'simulación' : 'dry run'}` : ''}`, 'good');
      ctx.watchJob(r.job_id, (j) => {
        if (j.state === 'succeeded') {
          (j.result?.messages || []).forEach((m) => toast(m, 'good'));
          ctx.reload();
        }
      });
    }, { small: true }),
  ]));
}

async function openSubmission(ctx, submission) {
  const es = ctx.lang === 'es';
  const brief = submission.rendered_instructions || '';
  openModal({
    title: `${es ? 'Envío' : 'Submission'} #${submission.id}`,
    wide: true,
    body: frag([
      el('div', { style: 'display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap' }, [
        statusPill(submission.state),
        pill(submission.method.replace(/_/g, ' ')),
        submission.dry_run ? pill(es ? 'simulación' : 'dry run', 'warn') : null,
        submission.attempts ? pill(`${submission.attempts} ${es ? 'intentos' : 'attempts'}`) : null,
      ]),
      (submission.payload?.warnings || []).length
        ? el('div', { class: 'callout callout-warn' }, [
            el('div', {}, [
              el('strong', { text: es ? 'Ten en cuenta' : 'Note' }),
              el('ul', { style: 'margin:4px 0 0;padding-left:18px' },
                submission.payload.warnings.map((w) => el('li', { text: w }))),
            ]),
          ])
        : null,
      submission.error ? el('div', { class: 'callout callout-warn' }, [
        el('div', {}, [el('strong', { text: t('msg.error') }), submission.error]),
      ]) : null,
      el('h3', { style: 'margin:6px 0 8px', text: es ? 'Guion listo para pegar' : 'Paste-ready brief' }),
      el('pre', { class: 'code wrap', text: brief }),
      submission.response_excerpt
        ? frag([
            el('h3', { style: 'margin:14px 0 8px', text: es ? 'Respuesta' : 'Response' }),
            el('pre', { class: 'code wrap', text: submission.response_excerpt }),
          ])
        : null,
    ]),
    footer: [
      actionButton(t('action.copy'), () => copyToClipboard(brief), { small: false }),
      submission.payload?.target_url
        ? el('a', {
            class: 'btn', href: submission.payload.target_url, target: '_blank', rel: 'noopener',
            text: es ? 'Abrir formulario' : 'Open form',
          })
        : null,
      ['draft', 'awaiting_approval'].includes(submission.state)
        ? actionButton(t('action.approve'), async () => {
            await api.post(`/projects/${ctx.project.id}/submissions/approve`, {
              submission_ids: [submission.id], approved_by: 'operator',
            });
            closeModal(); toast(t('msg.saved'), 'good'); ctx.reload();
          }, { primary: true })
        : null,
      !submission.live_url
        ? actionButton(es ? 'Registrar URL' : 'Record URL', () => { closeModal(); recordLiveUrl(ctx, submission); })
        : null,
      el('button', { class: 'btn', text: t('action.close'), onClick: closeModal }),
    ].filter(Boolean),
  });
}

function recordLiveUrl(ctx, submission) {
  const es = ctx.lang === 'es';
  const input = el('input', { class: 'input', placeholder: 'https://directorio.example/tu-ficha' });
  const won = el('input', { type: 'checkbox', checked: true });
  openModal({
    title: es ? 'URL de la ficha publicada' : 'Published listing URL',
    body: frag([
      el('p', { class: 'field-hint', text: es
        ? 'Pega la URL donde ya aparece tu ficha. Draken la verificará, leerá el anchor y el rel reales, y la añadirá a tu perfil de enlaces.'
        : 'Paste the URL where your listing is live. Draken verifies it, reads the real anchor and rel, and adds it to your link profile.' }),
      el('label', { class: 'field' }, [el('span', { text: t('label.url') }), input]),
      el('label', { class: 'checkbox' }, [won, es ? 'Marcar la oportunidad como ganada' : 'Mark the opportunity as won']),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.save'), async () => {
        if (!input.value.trim()) return;
        await api.post(`/projects/${ctx.project.id}/submissions/${submission.id}/live-url`, null, {
          live_url: input.value.trim(), mark_won: won.checked,
        });
        closeModal(); toast(t('msg.saved'), 'good'); ctx.reload();
      }, { primary: true }),
    ],
  });
}

export function actions(ctx) {
  if (!ctx.project) return [];
  const es = ctx.lang === 'es';
  return [
    actionButton(t('action.prepare'), async () => {
      const r = await api.post(`/projects/${ctx.project.id}/submissions/prepare`, {
        opportunity_ids: [], limit: 25, auto_approve: false,
      });
      (r.messages || []).forEach((m) => toast(m, r.prepared ? 'good' : 'warn'));
      ctx.reload();
    }, { primary: true }),
    actionButton(t('action.run'), async () => {
      const r = await api.post(`/projects/${ctx.project.id}/submissions/run`, {
        submission_ids: [], limit: 10, dry_run: null,
      });
      toast(`${t('msg.queued')} #${r.job_id}${r.dry_run ? ` · ${es ? 'simulación' : 'dry run'}` : ''}`, 'good');
      ctx.watchJob(r.job_id, (j) => {
        if (j.state === 'succeeded') {
          (j.result?.messages || []).forEach((m) => toast(m, 'good'));
          ctx.reload();
        }
      });
    }),
    actionButton(t('action.verify'), async () => {
      const r = await api.post(`/projects/${ctx.project.id}/submissions/verify`, null, { limit: 25 });
      toast(`${t('msg.queued')} #${r.job_id}`, 'good');
      ctx.watchJob(r.job_id, (j) => {
        if (j.state === 'succeeded') {
          (j.result?.messages || []).forEach((m) => toast(m, 'good'));
          ctx.reload();
        }
      });
    }),
  ];
}
