import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, barRow, callout, card, closeModal, compact, date, download, el,
  empty, externalLink, frag, hostOf, linkTypePill, num, openModal, pct, pill,
  scoreChip, stat, statusPill, table, toast, truncate,
} from '../ui.js';

export const meta = { id: 'backlinks', icon: 'backlinks', group: 'links' };

const state = { tab: 'profile', q: '', status: '', linkType: '', minAuthority: 0 };

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';
  const { tabs } = await import('../ui.js');

  const out = frag([
    tabs([
      { id: 'profile', label: es ? 'Perfil' : 'Profile' },
      { id: 'links', label: es ? 'Enlaces' : 'Links' },
      { id: 'anchors', label: 'Anchors' },
      { id: 'toxic', label: es ? 'Tóxicos' : 'Toxic' },
      { id: 'competitors', label: es ? 'Competencia' : 'Competitors' },
    ], state.tab, (id) => { state.tab = id; ctx.reload(); }),
  ]);

  if (state.tab === 'profile') out.append(await renderProfile(ctx));
  else if (state.tab === 'links') out.append(await renderLinks(ctx));
  else if (state.tab === 'anchors') out.append(await renderAnchors(ctx));
  else if (state.tab === 'toxic') out.append(await renderToxic(ctx));
  else out.append(await renderCompetitors(ctx));

  return out;
}

async function renderProfile(ctx) {
  const es = ctx.lang === 'es';
  const p = await api.get(`/projects/${ctx.project.id}/backlinks/profile`);

  if (!p.total_links) {
    return card(null, empty(t('empty.noBacklinks'), t('empty.noBacklinksBody'), frag([
      actionButton(t('action.import'), () => openImport(ctx), { primary: true }),
      ' ',
      actionButton(es ? 'Buscar menciones' : 'Discover mentions', () => discover(ctx)),
      ' ',
      actionButton(es ? 'Ver oportunidades' : 'See opportunities', () => ctx.navigate('opportunities')),
    ])));
  }

  const out = frag([
    el('div', { class: 'stats' }, [
      stat(es ? 'Puntuación de autoridad' : 'Authority score', num(p.authority_score, 1)),
      stat(es ? 'Dominios de referencia' : 'Referring domains', num(p.referring_domains)),
      stat(es ? 'Enlaces vivos' : 'Live links', num(p.live_links)),
      stat('Dofollow', num(p.dofollow_links), {
        note: `${pct(p.live_links ? p.dofollow_links / p.live_links : 0)} ${es ? 'del total' : 'of total'}`,
      }),
      stat(es ? 'Autoridad media' : 'Average authority', num(p.avg_domain_authority, 1)),
      stat(es ? 'Perdidos' : 'Lost', num(p.lost_links), { tone: p.lost_links ? 'warn' : null }),
      stat(es ? 'Tóxicos' : 'Toxic', num(p.toxic_links), { tone: p.toxic_links ? 'bad' : null }),
    ]),
  ]);

  if (p.recommendations?.length) {
    out.append(card(es ? 'Recomendaciones' : 'Recommendations',
      el('ul', { class: 'rec-list' }, p.recommendations.map((r) => el('li', { text: r }))),
      { sub: es ? 'Generadas a partir de tu perfil actual, en orden de impacto.' : 'Generated from your current profile, in order of impact.' }));
  }

  out.append(el('div', { class: 'grid grid-2' }, [
    card(es ? 'Velocidad de enlaces' : 'Link velocity',
      (p.velocity || []).some((v) => v.gained || v.lost)
        ? el('div', {}, p.velocity.map((v) => barRow(v.month, v.net,
            Math.max(1, ...p.velocity.map((x) => Math.max(x.gained, x.lost))),
            { formatted: `+${v.gained} / -${v.lost}`, tone: v.net >= 0 ? 'good' : 'bad' })))
        : empty(t('empty.noData'))),
    card(es ? 'Tipos de fuente' : 'Source mix',
      (p.category_mix || []).length
        ? el('div', {}, p.category_mix.map((c) => barRow(
            String(c.category).replace(/_/g, ' '), c.count,
            Math.max(...p.category_mix.map((x) => x.count)))))
        : empty(t('empty.noData')),
      { sub: es
        ? 'Un perfil que viene de un solo tipo de fuente es en sí mismo una huella. Diversifica.'
        : 'A profile from one source type is itself a footprint. Diversify.' }),
  ]));

  out.append(card(es ? 'Principales dominios de referencia' : 'Top referring domains',
    table([
      { key: 'domain', label: t('label.domain'), render: (r) => externalLink(`https://${r.domain}`, r.domain) },
      { key: 'authority', label: t('label.authority'), num: true, render: (r) => scoreChip(r.authority) },
      { key: 'links', label: es ? 'Enlaces' : 'Links', num: true },
      { key: 'dofollow', label: 'Dofollow', num: true },
    ], (p.top_domains || []).slice(0, 40))));

  return out;
}

async function renderLinks(ctx) {
  const es = ctx.lang === 'es';
  const rows = await api.get(`/projects/${ctx.project.id}/backlinks`, {
    q: state.q, status: state.status, link_type: state.linkType,
    min_authority: state.minAuthority, limit: 500,
  });

  const search = el('input', { class: 'input grow', type: 'search', placeholder: t('label.domain'), value: state.q });
  let timer;
  search.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => { state.q = search.value.trim(); ctx.reload(); }, 300);
  });

  const statusSel = el('select', { class: 'select' }, [
    el('option', { value: '', text: es ? 'Cualquier estado' : 'Any status' }),
    ...['live', 'lost', 'broken', 'pending'].map((v) =>
      el('option', { value: v, text: v, selected: state.status === v })),
  ]);
  statusSel.addEventListener('change', () => { state.status = statusSel.value; ctx.reload(); });

  const typeSel = el('select', { class: 'select' }, [
    el('option', { value: '', text: es ? 'Cualquier tipo' : 'Any type' }),
    ...['dofollow', 'nofollow', 'ugc', 'sponsored', 'unknown'].map((v) =>
      el('option', { value: v, text: v, selected: state.linkType === v })),
  ]);
  typeSel.addEventListener('change', () => { state.linkType = typeSel.value; ctx.reload(); });

  return frag([
    el('div', { class: 'filters' }, [search, statusSel, typeSel]),
    table([
      { key: 'source_domain', label: es ? 'Dominio origen' : 'Source domain', render: (r) => el('div', {}, [
        externalLink(r.source_url, r.source_domain),
        el('div', { class: 'faint small cell-url', title: r.source_url,
          text: truncate(r.source_url.replace(/^https?:\/\/[^/]+/, '') || '/', 60) }),
      ]) },
      { key: 'anchor_text', label: t('label.anchor'), render: (r) =>
        r.anchor_text ? el('span', { class: 'small', text: truncate(r.anchor_text, 46) })
                      : el('span', { class: 'faint small', text: es ? '(imagen / vacío)' : '(image / empty)' }) },
      { key: 'link_type', label: t('label.type'), render: (r) => linkTypePill(r.link_type) },
      { key: 'domain_authority', label: t('label.authority'), num: true, render: (r) => scoreChip(r.domain_authority) },
      { key: 'toxicity_score', label: es ? 'Toxicidad' : 'Toxicity', num: true,
        render: (r) => scoreChip(r.toxicity_score, { invert: true }) },
      { key: 'status', label: t('label.status'), render: (r) => statusPill(r.status) },
      { key: 'first_seen', label: es ? 'Visto' : 'Seen', render: (r) => date(r.first_seen) },
    ], rows, { onRowClick: (r) => openLink(ctx, r) }),
    el('p', { class: 'field-hint', text: `${rows.length} ${es ? 'enlaces' : 'links'}` }),
  ]);
}

async function renderAnchors(ctx) {
  const es = ctx.lang === 'es';
  const p = await api.get(`/projects/${ctx.project.id}/backlinks/profile`);
  if (!p.live_links) return card(null, empty(t('empty.noBacklinks'), t('empty.noBacklinksBody')));

  const out = frag([]);
  if (p.anchor_health?.warnings?.length) {
    p.anchor_health.warnings.forEach((w) => out.append(callout(w, 'warn', es ? 'Riesgo' : 'Risk')));
  }

  out.append(card(es ? 'Distribución de anchors' : 'Anchor distribution',
    frag([
      el('p', { class: 'card-sub', text: es
        ? 'La marca gris marca el máximo saludable. Pasarse en anchors de coincidencia exacta es la señal de manipulación más fácil de detectar.'
        : 'The grey mark is the healthy maximum. Over-doing exact-match anchors is the easiest manipulation signal to spot.' }),
      ...p.anchor_distribution.map((row) => el('div', {}, [
        barRow(
          String(row.bucket).replace(/_/g, ' '),
          row.share * 100, 100,
          {
            formatted: `${(row.share * 100).toFixed(0)}% (${row.count})`,
            tone: row.verdict === 'healthy' ? 'good' : row.verdict === 'too_high' ? 'bad' : 'warn',
            targetPct: row.target_max * 100,
          },
        ),
        el('div', { class: 'field-hint', style: 'margin:-4px 0 8px 142px' , text:
          `${es ? 'rango sano' : 'healthy range'} ${(row.target_min * 100).toFixed(0)}–${(row.target_max * 100).toFixed(0)}% · ${row.verdict.replace(/_/g, ' ')}` }),
      ])),
    ])));

  out.append(el('div', { class: 'grid grid-2' }, [
    card(es ? 'Anchors más frecuentes' : 'Most common anchors',
      table([
        { key: 'anchor', label: t('label.anchor') },
        { key: 'count', label: t('label.count'), num: true },
      ], p.anchor_health.most_common || [])),
    card(es ? 'Diversidad' : 'Diversity', el('dl', { class: 'kv' }, [
      el('dt', { text: es ? 'Anchors únicos' : 'Unique anchors' }),
      el('dd', { text: num(p.anchor_health.unique_anchors) }),
      el('dt', { text: es ? 'Ratio de diversidad' : 'Diversity ratio' }),
      el('dd', { text: num(p.anchor_health.diversity, 2) }),
      el('dt', { text: es ? 'Enlaces vivos' : 'Live links' }), el('dd', { text: num(p.live_links) }),
    ]), {
      sub: es
        ? 'Un ratio muy bajo con muchos enlaces significa que todos usan el mismo texto: poco natural.'
        : 'A very low ratio with many links means they all use the same text, which is not natural.',
    }),
  ]));

  return out;
}

async function renderToxic(ctx) {
  const es = ctx.lang === 'es';
  const data = await api.get(`/projects/${ctx.project.id}/backlinks/toxic`, { threshold: 40 });

  const out = frag([callout(data.guidance, 'info')]);
  if (!data.count) {
    out.append(card(null, empty(
      es ? 'Ningún enlace preocupante' : 'No links of concern',
      es ? 'Nada supera el umbral de toxicidad. Vuelve a comprobarlo tras cada campaña.'
         : 'Nothing is above the toxicity threshold. Re-check after each campaign.',
    )));
    return out;
  }

  out.append(card(`${data.count} ${es ? 'enlaces marcados' : 'flagged links'}`, table([
    { key: 'source_domain', label: t('label.domain'), render: (r) => externalLink(r.source_url, r.source_domain) },
    { key: 'anchor_text', label: t('label.anchor'), render: (r) => truncate(r.anchor_text, 34) || '—' },
    { key: 'link_type', label: t('label.type'), render: (r) => linkTypePill(r.link_type) },
    { key: 'domain_authority', label: t('label.authority'), num: true, render: (r) => scoreChip(r.domain_authority) },
    { key: 'toxicity_score', label: es ? 'Toxicidad' : 'Toxicity', num: true,
      render: (r) => scoreChip(r.toxicity_score, { invert: true }) },
    { key: 'recommended_action', label: es ? 'Acción' : 'Action', render: (r) =>
      pill(String(r.recommended_action).replace(/_/g, ' '),
        r.recommended_action === 'disavow' ? 'bad' : r.recommended_action === 'request_removal' ? 'warn' : '') },
    { key: 'reasons', label: es ? 'Por qué' : 'Why', render: (r) =>
      el('div', { class: 'small faint cell-wrap' }, (r.reasons || []).slice(0, 2).join(' · ') || '—') },
  ], data.links), {
    actions: [actionButton(es ? 'Descargar disavow' : 'Download disavow', async () => {
      const text = await api.getText(`/projects/${ctx.project.id}/backlinks/disavow`, { threshold: 70 });
      download(`disavow-${ctx.project.domain}.txt`, text);
      toast(es ? 'Revisa cada línea antes de subirlo' : 'Review every line before uploading', 'warn');
    }, { small: true })],
  }));

  return out;
}

async function renderCompetitors(ctx) {
  const es = ctx.lang === 'es';
  const data = await api.get(`/projects/${ctx.project.id}/backlinks/competitors`);

  const out = frag([callout(data.note, 'info')]);

  if (!data.competitors.length) {
    out.append(card(null, empty(
      es ? 'Sin datos de competencia' : 'No competitor data',
      es ? 'Añade dominios de competidores al proyecto y lanza el prospecting: Draken buscará quién les enlaza y a ti no.'
         : 'Add competitor domains to the project and run prospecting: Draken finds who links to them but not to you.',
      actionButton(es ? 'Buscar enlaces de competencia' : 'Prospect competitor links', async () => {
        const { job_id } = await api.post(`/projects/${ctx.project.id}/opportunities/prospect-competitors`);
        toast(`${t('msg.queued')} #${job_id}`, 'good');
        ctx.watchJob(job_id, (j) => { if (j.state === 'succeeded') ctx.reload(); });
      }, { primary: true }),
    )));
    return out;
  }

  out.append(card(es ? 'Comparativa' : 'Comparison', table([
    { key: 'domain', label: es ? 'Competidor' : 'Competitor' },
    { key: 'referring_domains_found', label: es ? 'Dominios hallados' : 'Domains found', num: true },
    { key: 'shared_with_us', label: es ? 'Compartidos' : 'Shared', num: true },
    { key: 'gap', label: 'Gap', num: true, render: (r) => pill(num(r.gap), r.gap ? 'warn' : 'good') },
  ], data.competitors), {
    sub: `${es ? 'Tus dominios de referencia' : 'Your referring domains'}: ${num(data.own_referring_domains)}`,
  }));

  out.append(card(es ? 'Link intersect: enlazan a la competencia pero no a ti' : 'Link intersect: they link to competitors, not to you',
    table([
      { key: 'domain', label: t('label.domain'), render: (r) => externalLink(`https://${r.domain}`, r.domain) },
      { key: 'competitors_linking', label: es ? 'Competidores' : 'Competitors', num: true, render: (r) =>
        pill(num(r.competitors_linking), r.competitors_linking >= 2 ? 'good' : '') },
      { key: 'authority', label: t('label.authority'), num: true, render: (r) => scoreChip(r.authority) },
    ], data.link_intersect || []),
    { sub: es
      ? 'Dos o más competidores enlazando desde el mismo dominio es la prueba más fuerte de que ese enlace es alcanzable para ti.'
      : 'Two or more competitors linked from the same domain is the strongest proof that link is obtainable for you.' }));

  return out;
}

function openLink(ctx, link) {
  const es = ctx.lang === 'es';
  openModal({
    title: link.source_domain,
    body: frag([
      el('dl', { class: 'kv' }, [
        el('dt', { text: es ? 'URL origen' : 'Source URL' }), el('dd', {}, [externalLink(link.source_url)]),
        el('dt', { text: es ? 'URL destino' : 'Target URL' }), el('dd', { text: link.target_url || '—' }),
        el('dt', { text: t('label.anchor') }), el('dd', { text: link.anchor_text || (es ? '(vacío)' : '(empty)') }),
        el('dt', { text: t('label.type') }), el('dd', {}, [linkTypePill(link.link_type)]),
        el('dt', { text: t('label.status') }), el('dd', {}, [statusPill(link.status)]),
        el('dt', { text: t('label.authority') }), el('dd', { text: num(link.domain_authority, 1) }),
        el('dt', { text: es ? 'Toxicidad' : 'Toxicity' }), el('dd', { text: num(link.toxicity_score, 1) }),
        el('dt', { text: es ? 'Descubierto vía' : 'Discovered via' }), el('dd', { text: link.discovered_via }),
        el('dt', { text: es ? 'Primera vez' : 'First seen' }), el('dd', { text: date(link.first_seen) }),
        el('dt', { text: es ? 'Última comprobación' : 'Last checked' }), el('dd', { text: date(link.last_checked) }),
      ]),
      (link.toxicity_reasons || []).length
        ? frag([
            el('h3', { style: 'margin:14px 0 6px', text: es ? 'Motivos de toxicidad' : 'Toxicity reasons' }),
            el('ul', { class: 'rec-list' }, link.toxicity_reasons.map((r) => el('li', { text: r }))),
          ])
        : null,
    ]),
    footer: [
      el('button', { class: 'btn btn-danger', text: t('action.delete'), onClick: async () => {
        await api.del(`/projects/${ctx.project.id}/backlinks/${link.id}`);
        closeModal(); toast(t('msg.deleted'), 'good'); ctx.reload();
      } }),
      el('button', { class: 'btn', text: t('action.close'), onClick: closeModal }),
    ],
  });
}

function openImport(ctx) {
  const es = ctx.lang === 'es';
  const area = el('textarea', {
    class: 'textarea', style: 'min-height:190px',
    placeholder: 'Referring Page URL,Anchor,Domain Rating,Type\nhttps://site.example/post,Acme,64,dofollow',
  });
  const verify = el('input', { type: 'checkbox' });
  openModal({
    title: es ? 'Importar backlinks' : 'Import backlinks',
    wide: true,
    body: frag([
      el('p', { class: 'field-hint', text: es
        ? 'Pega el CSV tal cual salga de Search Console, Ahrefs, Semrush o cualquier otra herramienta. Los nombres de columna se reconocen de forma flexible y el separador puede ser coma, punto y coma o tabulador.'
        : 'Paste the CSV exactly as your tool exports it (Search Console, Ahrefs, Semrush, anything). Column names are matched loosely and the delimiter can be a comma, semicolon or tab.' }),
      el('label', { class: 'field' }, [el('span', { text: 'CSV' }), area]),
      el('label', { class: 'checkbox' }, [verify, es
        ? 'Verificar cada enlace visitando la página (más lento, pero es el dato real)'
        : 'Verify each link by fetching the page (slower, but it is the real data)']),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.import'), async () => {
        if (!area.value.trim()) return;
        const r = await api.post(`/projects/${ctx.project.id}/backlinks/import`,
          { csv_text: area.value, rows: [], discovered_via: 'import' },
          { verify: verify.checked });
        closeModal();
        toast(`${r.imported} ${es ? 'importados' : 'imported'}, ${r.updated} ${es ? 'actualizados' : 'updated'}`, 'good');
        ctx.reload();
      }, { primary: true }),
    ],
  });
}

function openAdd(ctx) {
  const es = ctx.lang === 'es';
  const url = el('input', { class: 'input', placeholder: 'https://site.example/post' });
  const anchor = el('input', { class: 'input' });
  const type = el('select', { class: 'select' }, ['dofollow', 'nofollow', 'ugc', 'sponsored', 'unknown']
    .map((v) => el('option', { value: v, text: v })));
  const authority = el('input', { class: 'input', type: 'number', value: 0, min: 0, max: 100 });
  openModal({
    title: es ? 'Registrar un enlace' : 'Record a link',
    body: frag([
      el('label', { class: 'field' }, [el('span', { text: es ? 'URL origen' : 'Source URL' }), url]),
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: t('label.anchor') }), anchor]),
        el('label', { class: 'field' }, [el('span', { text: t('label.type') }), type]),
        el('label', { class: 'field' }, [el('span', { text: t('label.authority') }), authority]),
      ]),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.add'), async () => {
        await api.post(`/projects/${ctx.project.id}/backlinks`, null, {
          source_url: url.value.trim(), anchor_text: anchor.value,
          link_type: type.value, domain_authority: Number(authority.value),
        });
        closeModal(); toast(t('msg.saved'), 'good'); ctx.reload();
      }, { primary: true }),
    ],
  });
}

async function discover(ctx) {
  const { job_id } = await api.post(`/projects/${ctx.project.id}/backlinks/discover`);
  toast(`${t('msg.queued')} #${job_id}`, 'good');
  ctx.watchJob(job_id, (j) => { if (j.state === 'succeeded') ctx.reload(); });
}

export function actions(ctx) {
  if (!ctx.project) return [];
  const es = ctx.lang === 'es';
  return [
    actionButton(t('action.import'), () => openImport(ctx), { primary: true }),
    actionButton(t('action.add'), () => openAdd(ctx)),
    actionButton(es ? 'Descubrir' : 'Discover', () => discover(ctx)),
    actionButton(es ? 'Re-verificar' : 'Re-check', async () => {
      const { job_id } = await api.post(`/projects/${ctx.project.id}/backlinks/recheck`, null, { limit: 200 });
      toast(`${t('msg.queued')} #${job_id}`, 'good');
      ctx.watchJob(job_id, (j) => {
        if (j.state === 'succeeded') {
          const r = j.result || {};
          toast(`${r.still_live ?? 0} ${es ? 'vivos' : 'live'}, ${r.newly_lost ?? 0} ${es ? 'perdidos' : 'lost'}`, 'good');
          ctx.reload();
        }
      });
    }),
  ];
}
