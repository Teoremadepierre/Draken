import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, closeModal, copyToClipboard, el, empty,
  externalLink, frag, meter, num, openModal, pct, pill, scoreChip, stat, table,
  toast, truncate,
} from '../ui.js';

export const meta = { id: 'scan', icon: 'scan', group: 'overview' };

const state = { report: null, tab: 'fixes', scanning: false, jobId: null };

export async function render(ctx) {
  const es = ctx.lang === 'es';

  // No project yet: this view *is* the starting point.
  if (!ctx.project) return scanForm(ctx, { standalone: true });

  if (!state.report) {
    try {
      state.report = await api.get(`/scan/${ctx.project.id}/report`);
    } catch {
      state.report = null;
    }
  }
  const report = state.report;

  const out = frag([scanForm(ctx, { standalone: false })]);

  if (!report || !report.scanned_at) {
    out.append(card(null, empty(
      es ? 'Este proyecto todavía no se ha escaneado' : 'This project has not been scanned yet',
      es ? 'Pulsa "Escanear ahora": Draken audita el sitio, busca tus enlaces, calcula qué backlinks puedes conseguir y mide cómo te ven los asistentes de IA. Tarda uno o dos minutos.'
         : 'Hit "Scan now": Draken audits the site, finds your links, works out which backlinks you can get, and measures how AI assistants see you. One or two minutes.',
    )));
    return out;
  }

  out.append(scoreBoard(ctx, report));
  out.append(dataQualityBanner(ctx, report));

  const { tabs } = await import('../ui.js');
  out.append(tabs([
    { id: 'fixes', label: es ? `Qué arreglar (${report.fixes.length})` : `What to fix (${report.fixes.length})` },
    { id: 'links', label: es ? `Backlinks ya (${report.backlinks.summary.available_now})` : `Backlinks now (${report.backlinks.summary.available_now})` },
    { id: 'ai', label: es ? 'Visibilidad IA' : 'AI visibility' },
    { id: 'share', label: es ? 'Compartir' : 'Share' },
  ], state.tab, (id) => { state.tab = id; ctx.reload(); }));

  if (state.tab === 'fixes') out.append(fixesTab(ctx, report));
  else if (state.tab === 'links') out.append(linksTab(ctx, report));
  else if (state.tab === 'ai') out.append(aiTab(ctx, report));
  else out.append(await shareTab(ctx));

  return out;
}

// --- the input -----------------------------------------------------------

function scanForm(ctx, { standalone }) {
  const es = ctx.lang === 'es';
  const input = el('input', {
    class: 'input', type: 'url', style: 'font-size:15px;padding:11px 13px',
    placeholder: 'https://tudominio.com',
    value: ctx.project ? (ctx.project.base_url || `https://${ctx.project.domain}`) : '',
  });
  const pages = el('select', { class: 'select' },
    [[60, es ? 'Rápido (60 págs)' : 'Quick (60 pages)'],
     [150, es ? 'Normal (150 págs)' : 'Normal (150 pages)'],
     [500, es ? 'Profundo (500 págs)' : 'Deep (500 pages)']]
      .map(([v, label]) => el('option', { value: v, text: label, selected: v === 150 })));

  const go = actionButton(
    es ? 'Escanear ahora' : 'Scan now',
    async () => {
      const url = input.value.trim();
      if (!url) { toast(es ? 'Pon una URL' : 'Enter a URL', 'bad'); return; }
      state.scanning = true;
      const res = await api.post('/scan', {
        url, name: '', max_pages: Number(pages.value), deep: Number(pages.value) > 200, seeds: [],
      });
      state.jobId = res.job_id;
      state.report = null;
      toast(
        es ? `Escaneando ${res.domain}… uno o dos minutos.` : `Scanning ${res.domain}… one or two minutes.`,
        'good',
      );
      if (res.project_created) await ctx.refreshProjects();
      ctx.watchJob(res.job_id, (job) => {
        state.scanning = false;
        if (job.state === 'succeeded') {
          toast(es ? 'Escaneo terminado' : 'Scan finished', 'good', t('msg.done'));
          localStorage.setItem('draken_project', res.project_id);
          ctx.refreshProjects().then(() => ctx.reload());
        }
      });
      ctx.reload();
    },
    { primary: true },
  );

  const body = frag([
    standalone ? el('h2', { style: 'margin-bottom:6px', text: es ? 'Escanea un sitio web' : 'Scan a website' }) : null,
    el('p', { class: 'card-sub', text: es
      ? 'Pega la URL y listo. Draken audita el sitio, busca tus enlaces actuales, calcula qué backlinks puedes conseguir y con qué autoridad, y mide cómo te describen los asistentes de IA.'
      : 'Paste the URL. Draken audits the site, finds your current links, works out which backlinks you can get and at what authority, and measures how AI assistants describe you.' }),
    el('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end' }, [
      el('div', { style: 'flex:1;min-width:240px' }, [input]),
      pages,
      go,
    ]),
    state.scanning
      ? el('div', { style: 'margin-top:12px' }, [
          meter(50),
          el('p', { class: 'field-hint', text: es
            ? 'Auditando páginas, buscando enlaces, puntuando oportunidades… puedes seguir usando el resto de la app.'
            : 'Auditing pages, finding links, scoring opportunities… you can keep using the rest of the app.' }),
        ])
      : null,
  ]);

  return standalone
    ? el('div', { class: 'card', style: 'max-width:760px;margin:40px auto' }, [body])
    : card(null, body);
}

// --- scores --------------------------------------------------------------

function scoreBoard(ctx, report) {
  const es = ctx.lang === 'es';
  const s = report.scores;
  const h = report.headline;
  const tone = (v) => (v === null ? null : v >= 75 ? 'good' : v >= 45 ? 'warn' : 'bad');

  return frag([
    el('div', { class: 'stats' }, [
      stat(es ? 'Puntuación global' : 'Overall score', num(s.overall, 1), {
        tone: tone(s.overall),
        note: es ? '40% técnico · 40% enlaces · 20% IA' : '40% technical · 40% links · 20% AI',
      }),
      stat(es ? 'Salud técnica' : 'Site health', s.site_health === null ? '—' : num(s.site_health, 1), {
        tone: tone(s.site_health), note: `${num(h.pages_crawled)} ${es ? 'páginas' : 'pages'}`,
      }),
      stat(es ? 'Autoridad de enlaces' : 'Link authority', num(s.link_authority, 1), {
        tone: tone(s.link_authority),
        note: `${num(h.referring_domains)} ${es ? 'dominios' : 'domains'}`,
      }),
      stat(es ? 'Visibilidad IA' : 'AI visibility', num(s.ai_visibility, 1), {
        tone: tone(s.ai_visibility), note: pct(h.ai_mention_rate),
      }),
      stat(es ? 'Problemas' : 'Issues', num(h.issues_found), {
        tone: h.critical_issues ? 'bad' : h.issues_found ? 'warn' : 'good',
        note: h.critical_issues ? `${h.critical_issues} ${es ? 'críticos' : 'critical'}` : '',
      }),
      stat(es ? 'Backlinks disponibles' : 'Backlinks available', num(h.backlinks_available_now), {
        tone: 'good', note: es ? 'que puedes hacer hoy' : 'you can do today',
      }),
    ]),
  ]);
}

function dataQualityBanner(ctx, report) {
  const es = ctx.lang === 'es';
  const q = report.scores.data_quality;
  if (!q) return el('span');

  const tone = q.level >= 3 ? 'good' : q.level === 2 ? 'info' : 'warn';
  const labels = {
    1: es ? 'Datos estimados' : 'Estimated data',
    2: es ? 'Posiciones reales, volumen estimado' : 'Real positions, estimated volume',
    3: es ? 'Datos reales de tu sitio' : 'Real data for your site',
    4: es ? 'Datos completos' : 'Complete data',
  };

  return card(null, frag([
    el('div', { style: 'display:flex;align-items:center;gap:12px;flex-wrap:wrap' }, [
      el('strong', { text: `${es ? 'Calidad de los datos' : 'Data quality'}: ${q.level}/${q.max_level}` }),
      pill(labels[q.level] || q.label, tone),
      el('div', { style: 'flex:1;min-width:140px' }, [meter((q.level / q.max_level) * 100, 100, tone)]),
    ]),
    q.missing?.length
      ? frag([
          el('p', { class: 'field-hint', style: 'margin-top:10px', text: es
            ? 'Para que estos números dejen de ser estimaciones y pasen a ser mediciones reales, conecta:'
            : 'To turn these numbers from estimates into real measurements, connect:' }),
          el('ul', { class: 'rec-list' }, q.missing.map((m) => el('li', { text: m }))),
          actionButton(es ? 'Cómo conectarlo' : 'How to connect it',
            () => ctx.navigate('datasources'), { small: true }),
        ])
      : el('p', { class: 'field-hint', style: 'margin-top:8px', text: es
          ? 'Estás usando datos medidos, no estimaciones.' : 'You are on measured data, not estimates.' }),
  ]));
}

// --- tabs ----------------------------------------------------------------

function fixesTab(ctx, report) {
  const es = ctx.lang === 'es';
  if (!report.fixes.length) {
    return card(null, empty(es ? 'Nada que arreglar' : 'Nothing to fix',
      es ? 'El escaneo no ha encontrado problemas.' : 'The scan found no issues.'));
  }
  const toneBySeverity = { critical: 'bad', error: 'bad', warning: 'warn', notice: 'info' };

  return frag([
    el('p', { class: 'field-hint', text: es
      ? 'En orden de impacto. Pulsa una fila para ver las URLs afectadas y pedir a la IA el arreglo exacto.'
      : 'In order of impact. Click a row for the affected URLs and to ask the AI for the exact fix.' }),
    table([
      { key: 'priority', label: '#', num: true, width: '48px' },
      { key: 'severity', label: t('label.severity'), width: '96px',
        render: (r) => pill(r.severity, toneBySeverity[r.severity] || '') },
      { key: 'title', label: es ? 'Problema' : 'Issue', render: (r) => el('div', {}, [
        el('span', { class: 'cell-strong', text: r.title }),
        el('div', { class: 'faint small cell-wrap', text: truncate(r.detail, 120) }),
      ]) },
      { key: 'affected', label: es ? 'Afecta a' : 'Affects', num: true,
        render: (r) => r.affected || '—' },
      { key: 'category', label: t('label.category'), render: (r) => pill(r.category) },
      { key: 'id', label: '', width: '110px', render: (r) => el('button', {
        class: 'btn btn-sm', text: es ? 'Arreglar' : 'Fix',
        onClick: (e) => { e.stopPropagation(); askAssistant(ctx, r); },
      }) },
    ], report.fixes, { onRowClick: (r) => openFix(ctx, r) }),
  ]);
}

function linksTab(ctx, report) {
  const es = ctx.lang === 'es';
  const b = report.backlinks;
  const s = b.summary;

  const groupTable = (rows, title, note) => card(title, rows.length
    ? table([
        { key: 'name', label: es ? 'Dónde' : 'Where', render: (r) => el('div', {}, [
          el('span', { class: 'cell-strong', text: r.name }),
          el('div', { class: 'faint small', text: r.domain }),
        ]) },
        { key: 'authority', label: es ? 'Autoridad' : 'Authority', num: true,
          render: (r) => scoreChip(r.authority) },
        { key: 'link_type', label: t('label.type'), render: (r) =>
          pill(r.link_type, r.link_type === 'dofollow' ? 'good' : r.link_type === 'unknown' ? '' : 'warn') },
        { key: 'effort', label: es ? 'Esfuerzo' : 'Effort', num: true, render: (r) =>
          pill('•'.repeat(r.effort), r.effort <= 2 ? 'good' : '') },
        { key: 'ai_weight', label: es ? 'Peso IA' : 'AI weight', num: true, render: (r) =>
          r.ai_weight ? scoreChip(r.ai_weight * 100) : '—' },
        { key: 'anchor', label: t('label.anchor'), render: (r) =>
          el('span', { class: 'small', text: truncate(r.anchor, 22) }) },
        { key: 'url', label: '', width: '88px', render: (r) =>
          el('a', { class: 'btn btn-sm', href: r.url, target: '_blank', rel: 'noopener',
                    text: es ? 'Abrir' : 'Open' }) },
      ], rows)
    : empty(es ? 'Nada en este grupo' : 'Nothing in this group'), { sub: note });

  return frag([
    el('div', { class: 'stats' }, [
      stat(es ? 'Disponibles ahora' : 'Available now', num(s.available_now), { tone: 'good' }),
      stat('Dofollow', num(s.dofollow_now)),
      stat(es ? 'Autoridad media' : 'Average authority', num(s.avg_authority_now, 1)),
      stat(es ? 'Autoridad máxima' : 'Highest authority', num(s.highest_authority_now, 0)),
      stat(es ? 'Horas estimadas' : 'Estimated hours', num(s.estimated_hours, 1), {
        note: es ? 'para hacerlos todos' : 'to do all of them',
      }),
    ]),
    callout(b.explanation, 'info'),
    groupTable(b.now, es ? `Puedes hacerlos hoy (${b.now.length})` : `You can do these today (${b.now.length})`,
      es ? 'Un formulario y ya. Empieza por arriba.' : 'One form each. Start at the top.'),
    groupTable(b.soon, es ? `Necesitan cuenta o revisión (${b.soon.length})` : `Need an account or review (${b.soon.length})`),
    groupTable(b.campaign, es ? `Necesitan contenido o relación (${b.campaign.length})` : `Need content or a relationship (${b.campaign.length})`),
    actionButton(es ? 'Preparar envíos de los de hoy' : 'Prepare submissions for today’s',
      () => ctx.navigate('submissions'), { primary: true }),
  ]);
}

function aiTab(ctx, report) {
  const es = ctx.lang === 'es';
  const ai = report.ai_visibility;
  return frag([
    el('div', { class: 'stats' }, [
      stat(es ? 'Tasa de mención' : 'Mention rate', pct(ai.mention_rate)),
      stat(es ? 'Tasa de cita' : 'Citation rate', pct(ai.citation_rate)),
      stat(es ? 'Preguntas' : 'Prompts', num(ai.prompts_tracked)),
      stat(es ? 'Respuestas medidas' : 'Answers measured', num(ai.runs)),
    ]),
    ai.runs === 0
      ? callout(es
          ? 'Todavía no se ha medido: hace falta al menos una clave de API de IA. Las preguntas ya están creadas y esperando.'
          : 'Not measured yet: this needs at least one AI API key. The prompts are already created and waiting.',
          'warn')
      : null,
    ai.recommendations?.length
      ? card(es ? 'Qué mover' : 'What to move',
          el('ul', { class: 'rec-list' }, ai.recommendations.map((r) => el('li', { text: r }))))
      : null,
    ai.top_cited_domains?.length
      ? card(es ? 'Dominios que citan los motores' : 'Domains the engines cite',
          table([
            { key: 'domain', label: t('label.domain'), render: (r) => externalLink(`https://${r.domain}`, r.domain) },
            { key: 'citations', label: es ? 'Citas' : 'Citations', num: true },
          ], ai.top_cited_domains),
          { sub: es
            ? 'Tu lista de objetivos de enlaces para IA: consigue estar aquí y aparecerás en las respuestas.'
            : 'Your AI link-target list: get onto these and you show up in the answers.' })
      : null,
    actionButton(es ? 'Ir a Visibilidad en IA' : 'Go to AI visibility',
      () => ctx.navigate('aivisibility')),
  ]);
}

async function shareTab(ctx) {
  const es = ctx.lang === 'es';
  const links = await api.get(`/projects/${ctx.project.id}/shares`);
  const origin = window.location.origin;

  return frag([
    callout(es
      ? 'Un enlace compartido deja ver este informe sin cuenta y sin permisos de escritura. Incluye un informe listo para pegar en Claude o en cualquier otro asistente, para que quien lo reciba pueda trabajarlo con su propia IA.'
      : 'A share link lets someone read this report with no account and no write access. It includes a paste-ready brief for Claude or any other assistant, so the recipient can work it with their own AI.',
      'info'),
    card(es ? 'Enlaces compartidos' : 'Share links', links.length
      ? table([
          { key: 'label', label: es ? 'Etiqueta' : 'Label' },
          { key: 'scope', label: es ? 'Alcance' : 'Scope', render: (r) => pill(r.scope) },
          { key: 'path', label: t('label.url'), render: (r) => el('div', { style: 'display:flex;gap:6px;align-items:center' }, [
            el('code', { class: 'small', text: truncate(r.path, 34) }),
            el('button', { class: 'btn btn-ghost btn-sm', text: t('action.copy'),
              onClick: (e) => { e.stopPropagation(); copyToClipboard(`${origin}${r.path}`); } }),
          ]) },
          { key: 'view_count', label: es ? 'Vistas' : 'Views', num: true },
          { key: 'valid', label: t('label.status'), render: (r) =>
            pill(r.valid ? (es ? 'activo' : 'active') : (es ? 'caducado' : 'expired'), r.valid ? 'good' : '') },
          { key: 'id', label: '', width: '90px', render: (r) => el('button', {
            class: 'btn btn-sm btn-danger', text: es ? 'Revocar' : 'Revoke',
            onClick: async (e) => {
              e.stopPropagation();
              await api.del(`/projects/${ctx.project.id}/shares/${r.id}`);
              toast(t('msg.deleted'), 'good'); ctx.reload();
            },
          }) },
        ], links)
      : empty(es ? 'Todavía no has compartido este informe' : 'You have not shared this report yet'),
      { actions: [actionButton(es ? 'Crear enlace' : 'Create link', () => createShare(ctx), { small: true, primary: true })] }),
    card(es ? 'Dar acceso completo a alguien' : 'Give someone full access', frag([
      el('p', { class: 'card-sub', text: es
        ? 'Si quieres que además pueda trabajar (lanzar escaneos, mover el pipeline), invítale como usuario. Cada persona puede poner su propia clave de IA.'
        : 'If they should also be able to work (run scans, move the pipeline), invite them as a user. Each person can set their own AI key.' }),
      actionButton(es ? 'Ir a Equipo' : 'Go to Team', () => ctx.navigate('team'), { primary: true }),
    ])),
  ]);
}

function createShare(ctx) {
  const es = ctx.lang === 'es';
  const label = el('input', { class: 'input', placeholder: es ? 'Informe para…' : 'Report for…' });
  const scope = el('select', { class: 'select' }, [
    ['report', es ? 'Informe completo (sin pipeline)' : 'Full report (no pipeline)'],
    ['backlinks', es ? 'Solo backlinks' : 'Backlinks only'],
    ['full', es ? 'Todo' : 'Everything'],
  ].map(([v, l]) => el('option', { value: v, text: l })));
  const days = el('select', { class: 'select' },
    [[7, '7 días'], [30, '30 días'], [90, '90 días'], [0, es ? 'Sin caducidad' : 'No expiry']]
      .map(([v, l]) => el('option', { value: v, text: l, selected: v === 30 })));
  const brief = el('input', { type: 'checkbox', checked: true });

  openModal({
    title: es ? 'Compartir informe' : 'Share report',
    body: frag([
      el('label', { class: 'field' }, [el('span', { text: es ? 'Etiqueta' : 'Label' }), label]),
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: es ? 'Alcance' : 'Scope' }), scope]),
        el('label', { class: 'field' }, [el('span', { text: es ? 'Caduca en' : 'Expires in' }), days]),
      ]),
      el('label', { class: 'checkbox' }, [brief, es
        ? 'Incluir el informe listo para pegar en una IA'
        : 'Include the paste-ready AI brief']),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.create'), async () => {
        const r = await api.post(`/projects/${ctx.project.id}/shares`, {
          label: label.value, scope: scope.value,
          valid_days: Number(days.value) || null, allow_ai_brief: brief.checked,
        });
        closeModal();
        copyToClipboard(`${window.location.origin}${r.path}`);
        toast(es ? 'Enlace creado y copiado' : 'Link created and copied', 'good');
        ctx.reload();
      }, { primary: true }),
    ],
  });
}

// --- fix detail + assistant ---------------------------------------------

function openFix(ctx, fix) {
  const es = ctx.lang === 'es';
  openModal({
    title: fix.title,
    wide: true,
    body: frag([
      el('div', { style: 'display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap' }, [
        pill(fix.severity, { critical: 'bad', error: 'bad', warning: 'warn' }[fix.severity] || 'info'),
        pill(fix.category),
        fix.affected ? pill(`${fix.affected} ${es ? 'afectadas' : 'affected'}`, 'accent') : null,
      ]),
      el('p', { text: fix.detail }),
      el('div', { class: 'callout callout-good' }, [
        el('div', {}, [el('strong', { text: es ? 'Cómo arreglarlo' : 'How to fix it' }), fix.how]),
      ]),
      fix.examples?.length
        ? frag([
            el('h3', { style: 'margin:14px 0 8px', text: es ? 'Ejemplos' : 'Examples' }),
            el('ul', { style: 'margin:0;padding-left:18px' },
              fix.examples.map((u) => el('li', {}, [externalLink(u)]))),
          ])
        : null,
    ]),
    footer: [
      fix.can_ask_ai
        ? actionButton(es ? 'Pedir el arreglo a la IA' : 'Ask the AI for the fix',
            () => { closeModal(); askAssistant(ctx, fix); }, { primary: true })
        : null,
      el('button', { class: 'btn', text: t('action.close'), onClick: closeModal }),
    ].filter(Boolean),
  });
}

async function askAssistant(ctx, fix) {
  const es = ctx.lang === 'es';
  const body = el('div', {}, [el('div', { class: 'skeleton', style: 'width:80%' }),
                              el('div', { class: 'skeleton', style: 'width:60%' })]);
  openModal({ title: `${es ? 'Arreglar' : 'Fix'}: ${fix.title}`, wide: true, body });

  let result;
  try {
    result = await api.post(`/projects/${ctx.project.id}/assist`, {
      finding_id: fix.id, language: ctx.lang, question: '', engine: '',
    });
  } catch (error) {
    body.replaceChildren(el('p', { class: 'muted', text: error.message }));
    return;
  }

  body.replaceChildren();
  if (result.answered) {
    body.append(
      el('div', { style: 'display:flex;gap:6px;margin-bottom:12px' }, [
        pill(result.engine, 'accent'), result.model ? pill(result.model) : null,
      ]),
      el('pre', { class: 'code wrap', text: result.answer }),
    );
  } else {
    body.append(
      callout(result.reason, 'info'),
      el('h3', { style: 'margin:14px 0 8px', text: es
        ? 'Informe listo para pegar en tu asistente' : 'Paste-ready brief for your assistant' }),
      el('pre', { class: 'code wrap', style: 'max-height:340px', text: result.brief }),
      el('div', { style: 'display:flex;gap:8px;margin-top:10px;flex-wrap:wrap' }, [
        actionButton(es ? 'Copiar informe' : 'Copy brief', () => copyToClipboard(result.brief), { primary: true }),
        el('a', {
          class: 'btn', target: '_blank', rel: 'noopener',
          href: 'https://claude.ai/new', text: es ? 'Abrir Claude' : 'Open Claude',
        }),
      ]),
    );
  }
}

export function actions(ctx) {
  const es = ctx.lang === 'es';
  if (!ctx.project) return [];
  return [
    actionButton(es ? 'Plan de 2 semanas con IA' : '2-week AI plan', async () => {
      const body = el('div', {}, [el('div', { class: 'skeleton' }), el('div', { class: 'skeleton', style: 'width:70%' })]);
      openModal({ title: es ? 'Plan de dos semanas' : 'Two-week plan', wide: true, body });
      const r = await api.post(`/projects/${ctx.project.id}/assist/plan`, null, { language: ctx.lang });
      body.replaceChildren();
      if (r.answered) body.append(el('pre', { class: 'code wrap', text: r.answer }));
      else body.append(
        callout(r.reason || '', 'info'),
        el('pre', { class: 'code wrap', style: 'max-height:380px', text: r.brief }),
        actionButton(es ? 'Copiar' : 'Copy', () => copyToClipboard(r.brief), { primary: true }),
      );
    }),
    actionButton(t('action.refresh'), () => { state.report = null; ctx.reload(); }),
  ];
}
