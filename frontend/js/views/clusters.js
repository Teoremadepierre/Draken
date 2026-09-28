import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, card, closeModal, compact, el, empty, frag, num, openModal,
  pill, scoreChip, table, toast,
} from '../ui.js';

export const meta = { id: 'clusters', icon: 'clusters', group: 'research' };

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';
  const clusters = await api.get(`/projects/${ctx.project.id}/clusters`);

  if (!clusters.length) {
    return card(null, empty(
      es ? 'Todavía no hay clústeres' : 'No clusters yet',
      es ? 'Los clústeres se construyen a partir de tus keywords. Investiga keywords y luego reconstruye los clústeres.'
         : 'Clusters are built from your keywords. Research keywords first, then rebuild.',
      actionButton(es ? 'Reconstruir clústeres' : 'Rebuild clusters',
        () => rebuild(ctx), { primary: true }),
    ));
  }

  const totalVolume = clusters.reduce((a, c) => a + c.total_volume, 0);

  return frag([
    el('div', { class: 'stats' }, [
      el('div', { class: 'stat' }, [
        el('div', { class: 'stat-label', text: es ? 'Clústeres' : 'Clusters' }),
        el('div', { class: 'stat-value', text: num(clusters.length) }),
      ]),
      el('div', { class: 'stat' }, [
        el('div', { class: 'stat-label', text: es ? 'Keywords agrupadas' : 'Keywords grouped' }),
        el('div', { class: 'stat-value', text: num(clusters.reduce((a, c) => a + c.keyword_count, 0)) }),
      ]),
      el('div', { class: 'stat' }, [
        el('div', { class: 'stat-label', text: es ? 'Volumen total' : 'Total volume' }),
        el('div', { class: 'stat-value', text: compact(totalVolume) }),
      ]),
      el('div', { class: 'stat' }, [
        el('div', { class: 'stat-label', text: es ? 'Páginas sin asignar' : 'Unassigned pages' }),
        el('div', { class: 'stat-value', text: num(clusters.filter((c) => !c.target_url).length) }),
        el('div', { class: 'stat-note', text: es ? 'clústeres sin URL objetivo' : 'clusters with no target URL' }),
      ]),
    ]),
    card(null, table([
      { key: 'label', label: es ? 'Clúster' : 'Cluster', render: (r) => el('div', {}, [
        el('span', { class: 'cell-strong', text: r.label }),
        el('div', { class: 'faint small', text: `${es ? 'término principal' : 'head term'}: ${r.head_term}` }),
      ]) },
      { key: 'keyword_count', label: es ? 'Keywords' : 'Keywords', num: true },
      { key: 'total_volume', label: t('label.volume'), num: true, render: (r) => compact(r.total_volume) },
      { key: 'avg_difficulty', label: `${t('label.difficulty')} ø`, num: true,
        render: (r) => scoreChip(r.avg_difficulty, { invert: true }) },
      { key: 'dominant_intent', label: t('label.intent'), render: (r) => pill(r.dominant_intent) },
      { key: 'recommended_page_type', label: es ? 'Tipo de página' : 'Page type',
        render: (r) => el('span', { class: 'small', text: r.recommended_page_type }) },
      { key: 'target_url', label: es ? 'URL objetivo' : 'Target URL', render: (r) =>
        r.target_url
          ? el('a', { href: r.target_url, target: '_blank', rel: 'noopener', class: 'cell-url', text: r.target_url })
          : el('button', {
              class: 'btn btn-ghost btn-sm',
              text: es ? 'Asignar' : 'Assign',
              onClick: (e) => { e.stopPropagation(); assignUrl(ctx, r); },
            }) },
    ], clusters, { onRowClick: (r) => openCluster(ctx, r) })),
    el('p', { class: 'field-hint', text: es
      ? 'Un clúster equivale a una página. Asigna una URL objetivo a cada uno para que el enlazado interno y los anchors apunten al sitio correcto.'
      : 'One cluster equals one page. Assign a target URL to each so internal links and anchors point at the right place.' }),
  ]);
}

async function openCluster(ctx, cluster) {
  const es = ctx.lang === 'es';
  const keywords = await api.get(`/projects/${ctx.project.id}/keywords`, {
    cluster_id: cluster.id, limit: 500, sort: 'volume',
  });
  openModal({
    title: cluster.label,
    wide: true,
    body: frag([
      el('dl', { class: 'kv' }, [
        el('dt', { text: es ? 'Tipo de página recomendado' : 'Recommended page type' }),
        el('dd', { text: cluster.recommended_page_type }),
        el('dt', { text: es ? 'Intención dominante' : 'Dominant intent' }),
        el('dd', {}, [pill(cluster.dominant_intent)]),
        el('dt', { text: es ? 'Volumen combinado' : 'Combined volume' }),
        el('dd', { text: compact(cluster.total_volume) }),
        el('dt', { text: es ? 'Dificultad media' : 'Average difficulty' }),
        el('dd', { text: num(cluster.avg_difficulty, 1) }),
      ]),
      el('h3', { style: 'margin:16px 0 8px', text: `${keywords.length} keywords` }),
      table([
        { key: 'term', label: t('label.keyword') },
        { key: 'volume', label: t('label.volume'), num: true, render: (r) => compact(r.volume) },
        { key: 'difficulty', label: 'KD', num: true, render: (r) => scoreChip(r.difficulty, { invert: true }) },
        { key: 'intent', label: t('label.intent'), render: (r) => pill(r.intent) },
      ], keywords),
    ]),
    footer: [el('button', { class: 'btn', text: t('action.close'), onClick: closeModal })],
  });
}

function assignUrl(ctx, cluster) {
  const es = ctx.lang === 'es';
  const input = el('input', {
    class: 'input', value: cluster.target_url || ctx.project.base_url || '',
    placeholder: 'https://…',
  });
  openModal({
    title: es ? 'URL objetivo del clúster' : 'Cluster target URL',
    body: frag([
      el('p', { class: 'field-hint', text: es
        ? 'La página que debe posicionar para este clúster. Se usa como destino por defecto en campañas de enlaces.'
        : 'The page that should rank for this cluster. Used as the default link destination in campaigns.' }),
      el('label', { class: 'field' }, [el('span', { text: t('label.url') }), input]),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.save'), async () => {
        await api.patch(`/projects/${ctx.project.id}/clusters/${cluster.id}`, null, { target_url: input.value.trim() });
        closeModal(); toast(t('msg.saved'), 'good'); ctx.reload();
      }, { primary: true }),
    ],
  });
}

async function rebuild(ctx, threshold = 0.6) {
  const es = ctx.lang === 'es';
  const result = await api.post(`/projects/${ctx.project.id}/clusters/rebuild`, null, { threshold });
  toast(`${result.clusters} ${es ? 'clústeres desde' : 'clusters from'} ${result.keywords} keywords`, 'good');
  if (result.topics?.length) showTopicMap(ctx, result.topics);
  else ctx.reload();
}

function showTopicMap(ctx, topics) {
  const es = ctx.lang === 'es';
  openModal({
    title: es ? 'Mapa de temas' : 'Topic map',
    wide: true,
    body: frag([
      el('p', { class: 'field-hint', text: es
        ? 'Cada tema tiene una página pilar y sus páginas de apoyo. Enlaza cada apoyo al pilar y el pilar a todos ellos.'
        : 'Each topic has a pillar page and its supporting pages. Link every support to the pillar, and the pillar to all of them.' }),
      ...topics.map((topic) => el('div', { class: 'card', style: 'margin-bottom:10px' }, [
        el('div', { class: 'card-head' }, [
          el('h3', { text: topic.topic }),
          el('div', {}, [pill(`${es ? 'volumen' : 'volume'} ${compact(topic.total_volume)}`, 'accent')]),
        ]),
        el('dl', { class: 'kv' }, [
          el('dt', { text: es ? 'Pilar' : 'Pillar' }),
          el('dd', {}, [
            el('strong', { text: topic.pillar.label }), ' ',
            el('span', { class: 'faint small', text: `${topic.pillar.keyword_count} kw · ${topic.pillar.recommended_page_type}` }),
          ]),
          el('dt', { text: es ? 'Apoyo' : 'Supporting' }),
          el('dd', {}, topic.supporting.length
            ? topic.supporting.map((s) => pill(`${s.label} (${s.keyword_count})`))
            : [el('span', { class: 'faint', text: '—' })]),
          el('dt', { text: es ? 'Enlaces internos a crear' : 'Internal links to add' }),
          el('dd', { text: num(topic.internal_links_needed) }),
        ]),
      ])),
    ]),
    footer: [el('button', { class: 'btn', text: t('action.close'), onClick: () => { closeModal(); ctx.reload(); } })],
  });
}

export function actions(ctx) {
  if (!ctx.project) return [];
  const es = ctx.lang === 'es';
  return [
    actionButton(es ? 'Reconstruir' : 'Rebuild', () => rebuild(ctx), { primary: true }),
    actionButton(es ? 'Agrupación fina' : 'Finer grouping', () => rebuild(ctx, 0.75)),
    actionButton(es ? 'Agrupación amplia' : 'Broader grouping', () => rebuild(ctx, 0.45)),
  ];
}
