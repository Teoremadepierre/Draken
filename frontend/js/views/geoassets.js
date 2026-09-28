import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, copyToClipboard, download, el, empty, frag, num,
  pill, table, toast,
} from '../ui.js';

export const meta = { id: 'geoassets', icon: 'geo', group: 'ai' };

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';
  const [assets, consistency] = await Promise.all([
    api.get(`/projects/${ctx.project.id}/ai/assets`),
    api.post(`/projects/${ctx.project.id}/ai/entity-consistency`),
  ]);

  const out = frag([]);

  if (assets.profile_gaps?.length) {
    out.append(callout(
      `${es ? 'Rellena estos campos de la ficha para una salida completa' : 'Fill these profile fields for a complete output'}: ${assets.profile_gaps.join(', ')}`,
      'warn',
      es ? 'Ficha incompleta' : 'Incomplete profile',
    ));
  }

  out.append(card('llms.txt', frag([
    el('p', { class: 'card-sub', text: es
      ? 'Un resumen en texto plano de tu entidad para rastreadores de IA. Se publica en la raíz del sitio, igual que robots.txt.'
      : 'A plain-text brief of your entity for AI crawlers. Publish it at your site root, exactly like robots.txt.' }),
    el('pre', { class: 'code', text: assets.llms_txt }),
  ]), {
    actions: [
      actionButton(t('action.copy'), () => copyToClipboard(assets.llms_txt), { small: true }),
      actionButton(t('action.download'), () => download('llms.txt', assets.llms_txt), { small: true }),
    ],
  }));

  out.append(card('JSON-LD (schema.org)', frag([
    el('p', { class: 'card-sub', text: es
      ? `Tipo detectado: ${assets.schema.organization['@type']}. Pega esta etiqueta en el <head> de todas las páginas.`
      : `Detected type: ${assets.schema.organization['@type']}. Paste this tag into the <head> of every page.` }),
    el('pre', { class: 'code', text: assets.schema.script_tag }),
    el('p', { class: 'field-hint', text: assets.schema.install_note }),
  ]), {
    actions: [
      actionButton(t('action.copy'), () => copyToClipboard(assets.schema.script_tag), { small: true }),
      actionButton(t('action.download'), () =>
        download('schema.json', JSON.stringify(assets.schema.graph, null, 2), 'application/json'), { small: true }),
    ],
  }));

  out.append(card(es ? 'Consistencia de entidad (NAP)' : 'Entity consistency (NAP)', frag([
    el('p', { class: 'card-sub', text: es
      ? 'El mismo nombre, dirección y teléfono en todas partes. Las inconsistencias son la razón más habitual de que una entidad local no se consolide en el grafo de conocimiento.'
      : 'The same name, address and phone everywhere. Inconsistency is the most common reason a local entity fails to consolidate in a knowledge graph.' }),
    el('div', { class: 'stats' }, [
      el('div', { class: 'stat' }, [
        el('div', { class: 'stat-label', text: es ? 'Fichas comprobadas' : 'Listings checked' }),
        el('div', { class: 'stat-value is-small', text: num(consistency.listings_checked) }),
      ]),
      el('div', { class: 'stat' }, [
        el('div', { class: 'stat-label', text: es ? 'Consistentes' : 'Consistent' }),
        el('div', { class: 'stat-value is-small', text: num(consistency.consistent_listings) }),
      ]),
      el('div', { class: 'stat' }, [
        el('div', { class: 'stat-label', text: es ? 'Discrepancias' : 'Mismatches' }),
        el('div', { class: 'stat-value is-small', text: num((consistency.mismatches || []).length) }),
      ]),
    ]),
    (consistency.mismatches || []).length
      ? table([
          { key: 'source', label: t('label.source') },
          { key: 'field', label: es ? 'Campo' : 'Field', render: (r) => pill(String(r.field).replace(/_/g, ' ')) },
          { key: 'expected', label: es ? 'Debería ser' : 'Should be' },
          { key: 'found', label: es ? 'Está como' : 'Found as' },
        ], consistency.mismatches)
      : null,
    (consistency.recommendations || []).length
      ? el('ul', { class: 'rec-list' }, consistency.recommendations.map((r) => el('li', { text: r })))
      : null,
  ])));

  out.append(card(es ? 'Checklist de visibilidad en IA' : 'AI visibility checklist', el('ul', { class: 'rec-list' },
    (assets.notes || []).map((n) => el('li', { text: n })).concat([
      el('li', { text: es
        ? 'Publica datos propios (un estudio, un dataset) en tu dominio: es la única forma fiable de que te citen como fuente en lugar de mencionarte de pasada.'
        : 'Publish original data (a study, a dataset) on your own domain: it is the only reliable way to be cited as a source rather than mentioned in passing.' }),
      el('li', { text: es
        ? 'Consigue fichas y reseñas reales en las plataformas de reseñas: los asistentes las usan para responder "el mejor X".'
        : 'Get genuine listings and reviews on review platforms: assistants lean on them to answer "best X".' }),
      el('li', { text: es
        ? 'Un ítem en Wikidata es la palanca de entidad más fuerte, pero necesita referencias independientes verificables primero. Constrúyelas antes de crearlo.'
        : 'A Wikidata item is the strongest entity lever, but it needs verifiable independent references first. Build those before creating it.' }),
    ]))));

  return out;
}

export function actions(ctx) {
  if (!ctx.project) return [];
  const es = ctx.lang === 'es';
  return [
    actionButton(es ? 'Descargar llms.txt' : 'Download llms.txt', async () => {
      const text = await api.getText(`/projects/${ctx.project.id}/ai/assets/llms.txt`);
      download('llms.txt', text);
      toast(es ? 'Súbelo a la raíz de tu sitio como text/plain' : 'Upload it to your site root as text/plain', 'good');
    }, { primary: true }),
    actionButton(t('action.refresh'), () => ctx.reload()),
  ];
}
