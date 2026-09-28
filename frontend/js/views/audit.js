import { api, pollJob } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, card, closeModal, compact, el, empty, externalLink, frag, num,
  openModal, pill, scoreChip, stat, table, toast, TONE_BY_SEVERITY, truncate,
} from '../ui.js';

export const meta = { id: 'audit', icon: 'audit', group: 'site' };

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';
  const latest = await api.get(`/projects/${ctx.project.id}/audits/latest`);

  if (!latest.audit) {
    return card(null, empty(
      t('empty.noAudit'), t('empty.noAuditBody'),
      actionButton(es ? 'Auditar ahora' : 'Audit now', () => startAudit(ctx), { primary: true }),
    ));
  }

  const audit = latest.audit;
  const summary = audit.summary || {};
  const issues = latest.issues || [];

  if (audit.state === 'running' || audit.state === 'pending') {
    return card(null, empty(
      es ? 'Auditoría en curso' : 'Audit in progress',
      es ? 'El rastreo está en marcha. Esta vista se actualizará al terminar.'
         : 'The crawl is running. This view refreshes when it finishes.',
      actionButton(t('action.refresh'), () => ctx.reload()),
    ));
  }
  if (audit.state === 'failed') {
    return card(null, frag([
      empty(es ? 'La auditoría falló' : 'The audit failed', audit.error,
        actionButton(t('action.retry'), () => startAudit(ctx), { primary: true })),
    ]));
  }

  const out = frag([]);
  out.append(el('div', { class: 'stats' }, [
    stat(es ? 'Salud' : 'Health', num(audit.health_score, 1), {
      tone: audit.health_score >= 80 ? 'good' : audit.health_score >= 55 ? 'warn' : 'bad',
    }),
    stat(es ? 'Páginas rastreadas' : 'Pages crawled', num(audit.pages_crawled)),
    stat(es ? 'Indexables' : 'Indexable', num(summary.indexable_pages)),
    stat(es ? 'Roto (4xx/5xx)' : 'Broken (4xx/5xx)', num(summary.broken_pages), {
      tone: summary.broken_pages ? 'bad' : null,
    }),
    stat(es ? 'Con datos estructurados' : 'With structured data',
      `${num(summary.pages_with_schema)} / ${num(summary.html_pages)}`, { small: true }),
    stat(es ? 'Preparación IA ø' : 'AI readiness ø', num(summary.avg_ai_readiness, 1), {
      note: es ? 'qué tan citable es cada página' : 'how quotable each page is',
    }),
  ]));

  out.append(el('div', { class: 'grid grid-4', style: 'margin-bottom:16px' },
    ['critical', 'error', 'warning', 'notice'].map((sev) =>
      el('div', { class: 'stat' }, [
        el('div', { class: 'stat-label' }, [pill(sev, TONE_BY_SEVERITY[sev])]),
        el('div', { class: 'stat-value', text: num(audit.issue_counts?.[sev] || 0) }),
      ]))));

  out.append(card(es ? 'Problemas detectados' : 'Issues found',
    issues.length
      ? table([
          { key: 'severity', label: t('label.severity'), width: '90px',
            render: (r) => pill(r.severity, TONE_BY_SEVERITY[r.severity]) },
          { key: 'title', label: t('label.issue'), render: (r) => el('div', {}, [
            el('span', { class: 'cell-strong', text: r.title }),
            el('div', { class: 'faint small cell-wrap', text: truncate(r.description, 130) }),
          ]) },
          { key: 'category', label: t('label.category'), render: (r) => pill(r.category) },
          { key: 'count', label: t('label.count'), num: true },
        ], issues, { onRowClick: (r) => openIssue(ctx, audit.id, r) })
      : el('p', { class: 'muted', text: es ? 'Ningún problema detectado.' : 'No issues found.' }),
    { sub: es
      ? 'Agrupado por tipo: pulsa una fila para ver todas las URLs afectadas y cómo arreglarlo.'
      : 'Grouped by type: click a row for every affected URL and how to fix it.' }));

  out.append(card(es ? 'Detalles del rastreo' : 'Crawl detail', el('dl', { class: 'kv' }, [
    el('dt', { text: 'robots.txt' }),
    el('dd', {}, [summary.robots_txt ? pill(es ? 'encontrado' : 'found', 'good') : pill(es ? 'ausente' : 'missing', 'warn')]),
    el('dt', { text: es ? 'URLs en sitemap' : 'Sitemap URLs' }), el('dd', { text: num(summary.sitemap_urls) }),
    el('dt', { text: es ? 'Palabras por página ø' : 'Words per page ø' }), el('dd', { text: num(summary.avg_word_count) }),
    el('dt', { text: es ? 'Respuesta ø' : 'Response ø' }), el('dd', { text: `${num(summary.avg_response_ms)} ms` }),
    el('dt', { text: es ? 'Redirecciones' : 'Redirects' }), el('dd', { text: num(summary.redirects) }),
    el('dt', { text: es ? 'Dominios externos enlazados' : 'External domains linked' }),
    el('dd', { text: num(summary.external_domains) }),
  ]), {
    actions: [actionButton(es ? 'Ver páginas' : 'View pages', () => openPages(ctx, audit.id), { small: true })],
  }));

  return out;
}

async function openIssue(ctx, auditId, issue) {
  const es = ctx.lang === 'es';
  const detail = await api.get(`/projects/${ctx.project.id}/audits/${auditId}/issues/${issue.code}`);
  openModal({
    title: issue.title,
    wide: true,
    body: frag([
      el('div', { style: 'display:flex;gap:6px;margin-bottom:12px' }, [
        pill(detail.severity, TONE_BY_SEVERITY[detail.severity]),
        pill(detail.category),
        pill(`${detail.count} ${es ? 'afectadas' : 'affected'}`, 'accent'),
      ]),
      el('p', { text: detail.description }),
      el('div', { class: 'callout callout-good' }, [
        el('div', {}, [el('strong', { text: es ? 'Cómo arreglarlo' : 'How to fix it' }), detail.how_to_fix]),
      ]),
      el('h3', { style: 'margin:14px 0 8px', text: t('label.url') }),
      table([
        { key: 'url', label: t('label.url'), render: (r) => r.url ? externalLink(r.url) : '—' },
        { key: 'detail', label: t('label.details'), render: (r) =>
          Object.keys(r.detail || {}).length
            ? el('span', { class: 'mono small', text: truncate(JSON.stringify(r.detail), 90) })
            : '—' },
      ], detail.urls || []),
    ]),
    footer: [el('button', { class: 'btn', text: t('action.close'), onClick: closeModal })],
  });
}

async function openPages(ctx, auditId) {
  const es = ctx.lang === 'es';
  const pages = await api.get(`/projects/${ctx.project.id}/audits/${auditId}/pages`, {
    sort: 'inlinks', limit: 500,
  });
  openModal({
    title: es ? 'Páginas rastreadas' : 'Crawled pages',
    wide: true,
    body: table([
      { key: 'url', label: t('label.url'), render: (r) => externalLink(r.url, r.url.replace(/^https?:\/\/[^/]+/, '') || '/') },
      { key: 'status_code', label: es ? 'Código' : 'Status', num: true, render: (r) =>
        pill(r.status_code, r.status_code >= 400 ? 'bad' : r.status_code >= 300 ? 'warn' : 'good') },
      { key: 'title', label: es ? 'Título' : 'Title', render: (r) =>
        el('span', { class: 'small cell-url', title: r.title, text: r.title || '—' }) },
      { key: 'word_count', label: es ? 'Palabras' : 'Words', num: true },
      { key: 'inlinks', label: es ? 'Enlaces entrantes' : 'Inlinks', num: true },
      { key: 'depth', label: es ? 'Profundidad' : 'Depth', num: true },
      { key: 'has_schema', label: 'Schema', render: (r) =>
        r.has_schema ? pill('✓', 'good') : pill('—') },
      { key: 'ai_readiness', label: 'IA', num: true, render: (r) => scoreChip(r.ai_readiness) },
    ], pages),
    footer: [el('button', { class: 'btn', text: t('action.close'), onClick: closeModal })],
  });
}

function startAudit(ctx) {
  const es = ctx.lang === 'es';
  const maxPages = el('input', { class: 'input', type: 'number', value: 200, min: 1, max: 5000 });
  const maxDepth = el('input', { class: 'input', type: 'number', value: 4, min: 1, max: 10 });
  openModal({
    title: es ? 'Nueva auditoría' : 'New audit',
    body: frag([
      el('p', { class: 'field-hint', text: es
        ? `Se rastreará ${ctx.project.base_url || ctx.project.domain} respetando robots.txt y el crawl-delay que declare.`
        : `Will crawl ${ctx.project.base_url || ctx.project.domain}, respecting robots.txt and any declared crawl-delay.` }),
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: es ? 'Máx. páginas' : 'Max pages' }), maxPages]),
        el('label', { class: 'field' }, [el('span', { text: es ? 'Profundidad máx.' : 'Max depth' }), maxDepth]),
      ]),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.run'), async () => {
        const { job_id } = await api.post(`/projects/${ctx.project.id}/audits`, {
          max_pages: Number(maxPages.value), max_depth: Number(maxDepth.value),
          include_external_check: false,
        });
        closeModal();
        toast(`${t('msg.queued')} #${job_id}. ${t('msg.jobRunning')}`, 'good');
        ctx.watchJob(job_id, (job) => {
          if (job.state === 'succeeded') {
            toast(`${job.result?.pages_crawled ?? 0} ${es ? 'páginas, salud' : 'pages, health'} ${num(job.result?.health_score ?? 0, 1)}`, 'good', t('msg.done'));
            ctx.reload();
          }
        });
      }, { primary: true }),
    ],
  });
}

export function actions(ctx) {
  if (!ctx.project) return [];
  const es = ctx.lang === 'es';
  return [
    actionButton(es ? 'Nueva auditoría' : 'New audit', () => startAudit(ctx), { primary: true }),
    actionButton(es ? 'Historial' : 'History', async () => {
      const audits = await api.get(`/projects/${ctx.project.id}/audits`);
      openModal({
        title: es ? 'Auditorías anteriores' : 'Past audits',
        body: table([
          { key: 'id', label: '#', num: true },
          { key: 'finished_at', label: t('label.date'), render: (r) =>
            new Date(r.finished_at || r.created_at).toLocaleString() },
          { key: 'pages_crawled', label: t('label.pages'), num: true },
          { key: 'health_score', label: es ? 'Salud' : 'Health', num: true, render: (r) => scoreChip(r.health_score) },
          { key: 'state', label: t('label.status'), render: (r) => pill(r.state) },
        ], audits),
        footer: [el('button', { class: 'btn', text: t('action.close'), onClick: closeModal })],
      });
    }),
    actionButton(t('action.refresh'), () => ctx.reload()),
  ];
}
