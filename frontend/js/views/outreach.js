import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, closeModal, copyToClipboard, dateTime, el, empty,
  frag, num, openModal, pill, stat, statusPill, table, toast, truncate,
} from '../ui.js';

export const meta = { id: 'outreach', icon: 'outreach', group: 'links' };

const state = { tab: 'messages', stateFilter: '' };

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';
  const { tabs } = await import('../ui.js');

  const settings = await api.get('/outreach/settings');
  const out = frag([
    tabs([
      { id: 'messages', label: es ? 'Mensajes' : 'Messages' },
      { id: 'templates', label: es ? 'Plantillas' : 'Templates' },
    ], state.tab, (id) => { state.tab = id; ctx.reload(); }),
  ]);

  if (!settings.send_enabled) out.append(callout(settings.note, 'info', t('hint.sendDisabled')));
  else if (!settings.smtp_configured) {
    out.append(callout(es ? 'El envío está activado pero SMTP no está configurado.' : 'Sending is enabled but SMTP is not configured.', 'warn'));
  }

  if (state.tab === 'messages') out.append(await renderMessages(ctx, settings));
  else out.append(await renderTemplates(ctx));

  return out;
}

async function renderMessages(ctx, settings) {
  const es = ctx.lang === 'es';
  const rows = await api.get(`/projects/${ctx.project.id}/outreach/messages`, {
    state: state.stateFilter, limit: 300,
  });

  if (!rows.length) {
    return card(null, empty(
      es ? 'No hay mensajes' : 'No messages',
      es ? 'Selecciona oportunidades en la vista de Oportunidades y usa "Redactar outreach": Draken personaliza cada mensaje con los datos reales de esa página.'
         : 'Select opportunities in the Opportunities view and use "Draft outreach": Draken personalises each message with that page’s real data.',
      actionButton(t('view.opportunities'), () => ctx.navigate('opportunities'), { primary: true }),
    ));
  }

  const byState = rows.reduce((a, r) => { a[r.state] = (a[r.state] || 0) + 1; return a; }, {});
  const needsWork = rows.filter((r) => (r.body || '').includes('[[')).length;

  return frag([
    el('div', { class: 'stats' }, [
      stat(es ? 'Borradores' : 'Drafts', num(byState.draft || 0)),
      stat(es ? 'Enviados' : 'Sent', num(byState.sent || 0), { tone: 'good' }),
      stat(es ? 'Con huecos por rellenar' : 'With gaps to fill', num(needsWork), {
        tone: needsWork ? 'warn' : null,
        note: es ? 'los [[campos]] son tu parte' : 'the [[fields]] are your job',
      }),
    ]),
    table([
      { key: 'to_email', label: es ? 'Para' : 'To', render: (r) =>
        r.to_email || el('span', { class: 'faint small', text: es ? 'sin contacto' : 'no contact' }) },
      { key: 'subject', label: es ? 'Asunto' : 'Subject', render: (r) =>
        el('span', { class: 'cell-wrap', text: truncate(r.subject, 64) }) },
      { key: 'state', label: t('label.status'), render: (r) => statusPill(r.state) },
      { key: 'body', label: '', width: '100px', render: (r) =>
        (r.body || '').includes('[[')
          ? pill(es ? 'incompleto' : 'incomplete', 'warn')
          : pill(es ? 'listo' : 'ready', 'good') },
      { key: 'scheduled_for', label: es ? 'Programado' : 'Scheduled', render: (r) => dateTime(r.scheduled_for) },
    ], rows, { onRowClick: (r) => openMessage(ctx, r, settings) }),
  ]);
}

async function renderTemplates(ctx) {
  const es = ctx.lang === 'es';
  const data = await api.get('/outreach/templates');
  return frag([
    el('p', { class: 'field-hint', text: es
      ? `${data.templates.length} plantillas integradas, editables en data/seeds/outreach_templates.json. Las variables {{así}} se rellenan con los datos del proyecto y de la oportunidad.`
      : `${data.templates.length} built-in templates, editable in data/seeds/outreach_templates.json. {{Variables}} are filled from project and opportunity data.` }),
    ...data.templates.map((tpl) => card(tpl.name, frag([
      el('div', { style: 'display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px' }, [
        pill(tpl.tactic.replace(/_/g, ' '), 'accent'),
        pill(tpl.language),
        pill(`${es ? 'paso' : 'step'} ${tpl.step_number}`),
        tpl.delay_days ? pill(`+${tpl.delay_days}d`) : null,
      ]),
      el('dl', { class: 'kv' }, [
        el('dt', { text: es ? 'Asunto' : 'Subject' }), el('dd', { text: tpl.subject }),
      ]),
      el('pre', { class: 'code wrap', style: 'margin-top:10px', text: tpl.body }),
      (tpl.variables || []).length
        ? el('div', { style: 'margin-top:8px' }, (tpl.variables || []).map((v) => pill(v))) : null,
    ]), {
      actions: [actionButton(t('action.copy'), () => copyToClipboard(`${tpl.subject}\n\n${tpl.body}`), { small: true })],
    })),
  ]);
}

function openMessage(ctx, message, settings) {
  const es = ctx.lang === 'es';
  const to = el('input', { class: 'input', value: message.to_email || '' });
  const subject = el('input', { class: 'input', value: message.subject || '' });
  const body = el('textarea', { class: 'textarea', style: 'min-height:260px' });
  body.value = message.body || '';

  const gaps = (message.body || '').match(/\[\[[a-z_]+\]\]/gi) || [];

  openModal({
    title: es ? 'Mensaje de outreach' : 'Outreach message',
    wide: true,
    body: frag([
      gaps.length
        ? el('div', { class: 'callout callout-warn' }, [
            el('div', {}, [
              el('strong', { text: es ? 'Rellena estos huecos antes de enviar' : 'Fill these gaps before sending' }),
              el('div', {}, gaps.map((g) => pill(g.replace(/\[|\]/g, '')))),
              el('p', { class: 'small', style: 'margin:6px 0 0', text: es
                ? 'El detalle concreto en estos campos es toda la diferencia entre un email que funciona y uno que se ignora.'
                : 'The specific detail in these fields is the whole difference between an email that works and one that gets ignored.' }),
            ]),
          ])
        : null,
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: es ? 'Para' : 'To' }), to]),
      ]),
      el('label', { class: 'field' }, [el('span', { text: es ? 'Asunto' : 'Subject' }), subject]),
      el('label', { class: 'field' }, [el('span', { text: es ? 'Cuerpo' : 'Body' }), body]),
      message.error ? el('div', { class: 'callout callout-warn' }, [el('div', { text: message.error })]) : null,
    ]),
    footer: [
      actionButton(t('action.copy'), () => copyToClipboard(`${subject.value}\n\n${body.value}`)),
      actionButton(t('action.save'), async () => {
        await api.patch(`/projects/${ctx.project.id}/outreach/messages/${message.id}`, null, {
          to_email: to.value, subject: subject.value, body: body.value,
        });
        toast(t('msg.saved'), 'good');
      }),
      settings.send_enabled
        ? actionButton(es ? 'Enviar' : 'Send', async () => {
            await api.patch(`/projects/${ctx.project.id}/outreach/messages/${message.id}`, null, {
              to_email: to.value, subject: subject.value, body: body.value,
            });
            const r = await api.post(`/projects/${ctx.project.id}/outreach/messages/${message.id}/send`);
            toast(r.detail, r.sent ? 'good' : 'bad');
            if (r.sent) { closeModal(); ctx.reload(); }
          }, { primary: true })
        : el('span', { class: 'field-hint', text: t('hint.sendDisabled') }),
      el('button', { class: 'btn', text: t('action.close'), onClick: closeModal }),
    ].filter(Boolean),
  });
}

export function actions(ctx) {
  if (!ctx.project) return [];
  const es = ctx.lang === 'es';
  return [
    actionButton(es ? 'Ir a oportunidades' : 'Go to opportunities',
      () => ctx.navigate('opportunities'), { primary: true }),
    actionButton(t('action.refresh'), () => ctx.reload()),
  ];
}
