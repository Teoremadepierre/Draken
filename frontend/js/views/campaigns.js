import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, barRow, card, closeModal, confirmDialog, date, el, empty, frag,
  num, openModal, pill, stat, table, toast,
} from '../ui.js';

export const meta = { id: 'campaigns', icon: 'campaigns', group: 'links' };

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';
  const campaigns = await api.get(`/projects/${ctx.project.id}/campaigns`);

  if (!campaigns.length) {
    return card(null, empty(
      es ? 'No hay campañas' : 'No campaigns',
      es ? 'Una campaña agrupa oportunidades con un objetivo concreto y un plan de anchors, para no improvisar el perfil de enlaces.'
         : 'A campaign groups opportunities behind one goal and an anchor plan, so the link profile is not improvised.',
      actionButton(t('action.create'), () => openCreate(ctx), { primary: true }),
    ));
  }

  const out = frag([]);
  for (const campaign of campaigns) {
    const progress = await api.get(`/projects/${ctx.project.id}/campaigns/${campaign.id}/progress`);
    out.append(card(campaign.name, frag([
      campaign.goal ? el('p', { class: 'card-sub', text: campaign.goal }) : null,
      el('div', { class: 'stats' }, [
        stat(es ? 'Objetivo mensual' : 'Monthly target', num(progress.monthly_link_target)),
        stat(es ? 'Ganados' : 'Won', num(progress.won), { tone: 'good' }),
        stat(es ? 'En marcha' : 'In flight', num(progress.in_flight)),
        stat(es ? 'Faltan' : 'Remaining', num(progress.remaining_to_target), {
          tone: progress.remaining_to_target ? 'warn' : 'good',
        }),
        stat(es ? 'Autoridad media ganada' : 'Avg won authority', num(progress.avg_won_authority, 1)),
      ]),
      barRow(es ? 'Progreso' : 'Progress', progress.won, Math.max(1, progress.monthly_link_target), {
        formatted: `${progress.won} / ${progress.monthly_link_target}`,
        tone: progress.won >= progress.monthly_link_target ? 'good' : 'accent',
      }),
      Object.keys(campaign.anchor_plan || {}).length
        ? frag([
            el('h3', { style: 'margin:14px 0 8px', text: es ? 'Plan de anchors' : 'Anchor plan' }),
            ...Object.entries(campaign.anchor_plan).map(([bucket, share]) =>
              barRow(bucket.replace(/_/g, ' '), share * 100, 100, { formatted: `${(share * 100).toFixed(0)}%` })),
          ])
        : null,
      Object.keys(progress.by_tactic || {}).length
        ? frag([
            el('h3', { style: 'margin:14px 0 8px', text: es ? 'Por táctica' : 'By tactic' }),
            el('div', {}, Object.entries(progress.by_tactic).map(([tac, n]) =>
              pill(`${tac.replace(/_/g, ' ')} · ${n}`))),
          ])
        : null,
      el('dl', { class: 'kv', style: 'margin-top:14px' }, [
        campaign.tactics?.length ? el('dt', { text: es ? 'Tácticas' : 'Tactics' }) : null,
        campaign.tactics?.length ? el('dd', {}, campaign.tactics.map((x) => pill(x))) : null,
        campaign.landing_urls?.length ? el('dt', { text: es ? 'Destinos' : 'Landing URLs' }) : null,
        campaign.landing_urls?.length ? el('dd', { text: campaign.landing_urls.join(', ') }) : null,
        campaign.starts_on ? el('dt', { text: es ? 'Empieza' : 'Starts' }) : null,
        campaign.starts_on ? el('dd', { text: date(campaign.starts_on) }) : null,
      ]),
    ]), {
      actions: [
        pill(campaign.state, campaign.state === 'active' ? 'good' : ''),
        actionButton(t('action.delete'), () => confirmDialog(t('msg.confirmDelete'), async () => {
          await api.del(`/projects/${ctx.project.id}/campaigns/${campaign.id}`);
          toast(t('msg.deleted'), 'good'); ctx.reload();
        }), { small: true }),
      ],
    }));
  }
  return out;
}

function openCreate(ctx) {
  const es = ctx.lang === 'es';
  const name = el('input', { class: 'input', placeholder: es ? 'Q4 base de citaciones' : 'Q4 citation foundation' });
  const goal = el('input', { class: 'input', placeholder: es ? '30 dominios de referencia nuevos' : '30 new referring domains' });
  const target = el('input', { class: 'input', type: 'number', value: 20, min: 1 });
  const tactics = el('input', { class: 'input', placeholder: 'directory, local_citation, review_platform' });
  const landing = el('input', { class: 'input', value: ctx.project.base_url || '' });

  openModal({
    title: es ? 'Nueva campaña' : 'New campaign',
    body: frag([
      el('label', { class: 'field' }, [el('span', { text: t('label.name') }), name]),
      el('label', { class: 'field' }, [el('span', { text: es ? 'Objetivo' : 'Goal' }), goal]),
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: es ? 'Enlaces/mes' : 'Links/month' }), target]),
        el('label', { class: 'field' }, [el('span', { text: es ? 'Tácticas (coma)' : 'Tactics (comma)' }), tactics]),
      ]),
      el('label', { class: 'field' }, [el('span', { text: es ? 'URL de destino' : 'Landing URL' }), landing]),
      el('p', { class: 'field-hint', text: es
        ? 'El plan de anchors por defecto (55% marca, 15% URL, 12% genérico, 13% parcial, 5% exacto) es un reparto que no llama la atención. Ajústalo solo si sabes por qué.'
        : 'The default anchor plan (55% brand, 15% naked URL, 12% generic, 13% partial, 5% exact) is a mix that does not draw attention. Change it only if you know why.' }),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.create'), async () => {
        if (!name.value.trim()) return;
        await api.post(`/projects/${ctx.project.id}/campaigns`, {
          name: name.value.trim(), goal: goal.value,
          tactics: tactics.value.split(',').map((s) => s.trim()).filter(Boolean),
          target_keywords: [],
          landing_urls: landing.value ? [landing.value.trim()] : [],
          monthly_link_target: Number(target.value),
        });
        closeModal(); toast(t('msg.saved'), 'good'); ctx.reload();
      }, { primary: true }),
    ],
  });
}

export function actions(ctx) {
  if (!ctx.project) return [];
  return [actionButton(t('action.create'), () => openCreate(ctx), { primary: true })];
}
