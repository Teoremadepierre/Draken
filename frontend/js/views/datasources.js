import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, copyToClipboard, el, empty, frag, meter, num,
  pill, stat, table, toast,
} from '../ui.js';

export const meta = { id: 'datasources', icon: 'datasources', group: 'system' };

let connectivity = null;

export async function render(ctx) {
  const es = ctx.lang === 'es';
  const sources = await api.get('/system/data-sources', { project_id: ctx.project?.id });
  const q = sources.quality;

  const out = frag([
    card(null, frag([
      el('div', { style: 'display:flex;align-items:center;gap:12px;flex-wrap:wrap' }, [
        el('h2', { text: `${es ? 'Calidad de datos' : 'Data quality'}: ${q.level}/${q.max_level}` }),
        pill(q.label, q.level >= 3 ? 'good' : q.level === 2 ? 'info' : 'warn'),
      ]),
      el('div', { style: 'margin:10px 0' }, [
        meter((q.level / q.max_level) * 100, 100, q.level >= 3 ? 'good' : q.level === 2 ? '' : 'warn'),
      ]),
      el('p', { class: 'card-sub', text: es
        ? 'Draken funciona sin ninguna clave, pero entonces varios números son estimaciones explicables en vez de mediciones. Cada fuente que conectas sustituye estimación por dato real, y la interfaz siempre te dice cuál está usando.'
        : 'Draken works with no keys at all, but then several numbers are explainable estimates rather than measurements. Each source you connect replaces an estimate with real data, and the interface always tells you which it is using.' }),
      el('div', { class: 'grid grid-3' }, [
        stat(es ? 'Keywords medidas' : 'Measured keywords', num(sources.measured_keywords), {
          note: es ? 'con datos reales, no estimados' : 'real data, not estimated',
        }),
        stat(es ? 'Enlaces verificados' : 'Verified links', num(sources.measured_links)),
        stat(es ? 'Motor SERP activo' : 'Active SERP engine', sources.serp_active, {
          small: true, note: sources.serp_exact ? (es ? 'exacto' : 'exact') : (es ? 'aproximado' : 'approximate'),
        }),
      ]),
    ])),
  ]);

  out.append(card(es ? 'Datos reales de tu propio sitio' : 'Real data for your own site', frag([
    el('p', { class: 'card-sub', text: es
      ? 'Estas dos fuentes son gratuitas y devuelven mediciones, no estimaciones. Para tu propio sitio son mejores que cualquier herramienta de pago, porque es lo que esas herramientas intentan modelar.'
      : 'These two are free and return measurements, not estimates. For your own site they beat any paid tool, because those tools are modelling exactly this.' }),
    sourceRow(ctx, {
      key: 'search_console',
      name: 'Google Search Console',
      connected: sources.first_party.search_console,
      gives: es
        ? 'Impresiones, clics, CTR y posición media reales, por consulta y por página. Detecta canibalización entre tus propias páginas.'
        : 'Real impressions, clicks, CTR and average position, per query and per page. Detects cannibalisation between your own pages.',
      setup: [
        es ? 'En Google Cloud, crea un proyecto y activa la Search Console API.' : 'In Google Cloud, create a project and enable the Search Console API.',
        es ? 'Crea una cuenta de servicio y descarga su clave JSON.' : 'Create a service account and download its JSON key.',
        es ? 'En Search Console → Configuración → Usuarios, añade el email de la cuenta de servicio como usuario.' : 'In Search Console → Settings → Users, add the service-account email as a user.',
        'DRAKEN_GSC_SERVICE_ACCOUNT_FILE=/ruta/a/la/clave.json',
        'DRAKEN_GSC_SITE_URL=sc-domain:tudominio.com',
      ],
      onImport: ctx.project ? async () => {
        const r = await api.post(`/projects/${ctx.project.id}/data/search-console`, null,
          { days: 28, track_top: 25 });
        if (r.error) { toast(r.error, 'bad'); return; }
        toast(`${r.imported} keywords · ${num(r.total_clicks)} ${es ? 'clics' : 'clicks'} · ${num(r.total_impressions)} ${es ? 'impresiones' : 'impressions'}`, 'good');
        ctx.reload();
      } : null,
    }),
    sourceRow(ctx, {
      key: 'bing_webmaster',
      name: 'Bing Webmaster Tools',
      connected: sources.first_party.bing_webmaster,
      gives: es
        ? 'Tus backlinks reales, gratis. Es el dato que las suites de pago cobran más caro, y Bing lo da completo para sitios verificados.'
        : 'Your real backlinks, free. It is the data paid suites charge most for, and Bing gives it in full for verified sites.',
      setup: [
        es ? 'Verifica tu sitio en Bing Webmaster Tools (puedes importarlo de Search Console).' : 'Verify your site in Bing Webmaster Tools (you can import it from Search Console).',
        es ? 'Ajustes → Acceso a la API → copia la clave.' : 'Settings → API access → copy the key.',
        'DRAKEN_BING_WEBMASTER_API_KEY=...',
      ],
      onImport: ctx.project ? async () => {
        const r = await api.post(`/projects/${ctx.project.id}/data/bing-links`);
        if (r.error) { toast(r.error, 'bad'); return; }
        toast(`${r.imported} ${es ? 'enlaces reales' : 'real links'} · ${r.referring_domains} ${es ? 'dominios' : 'domains'}`, 'good');
        ctx.reload();
      } : null,
    }),
  ])));

  out.append(card(es ? 'Motores de resultados (SERP)' : 'Search result engines (SERP)', frag([
    el('p', { class: 'card-sub', text: es
      ? `Draken prueba los motores en orden y usa el primero que responda: ${sources.serp_chain.join(' → ')}. Si uno está bloqueado o sin cuota, cae al siguiente en vez de devolver vacío.`
      : `Draken tries engines in order and uses the first that answers: ${sources.serp_chain.join(' → ')}. If one is blocked or out of quota it falls through instead of returning nothing.` }),
    table([
      { key: 'name', label: es ? 'Motor' : 'Engine' },
      { key: 'available', label: t('label.status'), render: (r) =>
        pill(r.available ? (es ? 'disponible' : 'available') : (es ? 'sin configurar' : 'not configured'),
             r.available ? 'good' : '') },
      { key: 'exact', label: es ? 'Exactitud' : 'Accuracy', render: (r) =>
        pill(r.exact ? (es ? 'exacto' : 'exact') : (es ? 'aproximado' : 'approximate'),
             r.exact ? 'good' : 'warn') },
      { key: 'env', label: es ? 'Variable' : 'Variable', render: (r) =>
        r.env ? el('code', { class: 'small', text: r.env }) : el('span', { class: 'faint small', text: es ? 'sin clave' : 'no key' }) },
      { key: 'note', label: es ? 'Nota' : 'Note', render: (r) => el('span', { class: 'small faint cell-wrap', text: r.note }) },
    ], serpRows(sources, es)),
  ])));

  out.append(card(es ? 'Diagnóstico de conectividad' : 'Connectivity diagnostics', frag([
    el('p', { class: 'card-sub', text: es
      ? 'Comprueba qué hosts puede alcanzar este servidor. Si varios fallan a la vez, casi siempre es una política de red y no las fuentes.'
      : 'Checks which hosts this server can reach. If several fail at once it is almost always a network policy, not the sources.' }),
    actionButton(es ? 'Comprobar ahora' : 'Check now', async () => {
      connectivity = await api.get('/system/connectivity', {
        target_url: ctx.project?.base_url || '',
      });
      ctx.reload();
    }, { primary: true }),
    connectivity ? connectivityResults(ctx, connectivity) : null,
  ])));

  return out;
}

function serpRows(sources, es) {
  const meta = {
    serpapi: { name: 'SerpApi', exact: true, env: 'DRAKEN_SERPAPI_KEY',
      note: es ? 'Posiciones exactas de Google. De pago.' : 'Exact Google positions. Paid.' },
    dataforseo: { name: 'DataForSEO', exact: true, env: 'DRAKEN_DATAFORSEO_LOGIN',
      note: es ? 'Posiciones exactas de Google. De pago.' : 'Exact Google positions. Paid.' },
    brave: { name: 'Brave Search API', exact: false, env: 'DRAKEN_BRAVE_API_KEY',
      note: es ? 'Índice independiente. Tiene plan gratuito de 2.000 consultas al mes.' : 'Independent index. Free tier of 2,000 queries a month.' },
    searxng: { name: 'SearXNG (tuyo)', exact: false, env: 'DRAKEN_SEARXNG_URL',
      note: es ? 'Tu propia instancia. Agrega varios motores y no depende de nadie.' : 'Your own instance. Aggregates several engines and depends on nobody.' },
    duckduckgo_html: { name: 'DuckDuckGo', exact: false, env: '',
      note: es ? 'Sin clave. Aproximado pero real.' : 'No key. Approximate but real.' },
    mojeek: { name: 'Mojeek', exact: false, env: '',
      note: es ? 'Sin clave. Índice propio, usado como reserva.' : 'No key. Own index, used as a fallback.' },
  };
  return Object.entries(sources.serp_providers).map(([key, available]) => ({
    key, available, ...meta[key],
  }));
}

function connectivityResults(ctx, data) {
  const es = ctx.lang === 'es';
  return frag([
    el('div', { style: 'margin-top:14px' }, [
      callout(data.verdict, data.severity === 'good' ? 'good' : data.severity === 'bad' ? 'warn' : 'info'),
    ]),
    data.diagnosis ? callout(data.diagnosis, 'warn', es ? 'Diagnóstico' : 'Diagnosis') : null,
    table([
      { key: 'reachable', label: '', width: '54px', render: (r) =>
        pill(r.reachable ? 'OK' : 'X', r.reachable ? 'good' : 'bad') },
      { key: 'name', label: es ? 'Servicio' : 'Service', render: (r) => el('div', {}, [
        el('span', { class: 'cell-strong', text: r.name }),
        el('div', { class: 'faint small mono', text: r.host }),
      ]) },
      { key: 'enables', label: es ? 'Para qué sirve' : 'What it enables', render: (r) =>
        el('span', { class: 'small cell-wrap', text: r.enables }) },
      { key: 'latency_ms', label: 'ms', num: true, render: (r) => (r.reachable ? num(r.latency_ms) : '—') },
      { key: 'error', label: es ? 'Problema' : 'Problem', render: (r) =>
        r.error ? el('span', { class: 'small', style: 'color:var(--bad)', text: r.error }) : '—' },
    ], data.probes),
    data.disabled_features?.length
      ? frag([
          el('h3', { style: 'margin:16px 0 8px', text: es ? 'Qué queda deshabilitado' : 'What is disabled' }),
          el('ul', { class: 'rec-list' }, data.disabled_features.map((d) =>
            el('li', { text: `${d.feature} — ${es ? 'por' : 'because of'} ${d.because.join(', ')}` }))),
        ])
      : null,
    data.blocked?.length
      ? frag([
          el('h3', { style: 'margin:16px 0 8px', text: es ? 'Cómo arreglarlo' : 'How to fix it' }),
          el('ul', { class: 'rec-list' }, data.blocked.map((b) =>
            el('li', { text: `${b.name}: ${b.remediation}` }))),
          el('p', { class: 'field-hint', text: data.general_remediation }),
        ])
      : null,
  ]);
}

function sourceRow(ctx, source) {
  const es = ctx.lang === 'es';
  return el('div', {
    class: 'card',
    style: `margin-bottom:12px;border-color:${source.connected ? 'var(--good)' : 'var(--border-soft)'}`,
  }, [
    el('div', { class: 'card-head' }, [
      el('h3', { text: source.name }),
      pill(source.connected ? (es ? 'conectado' : 'connected') : (es ? 'sin conectar' : 'not connected'),
           source.connected ? 'good' : 'warn'),
    ]),
    el('p', { style: 'max-width:700px', text: source.gives }),
    source.connected
      ? (source.onImport
          ? actionButton(es ? 'Importar ahora' : 'Import now', source.onImport, { primary: true })
          : el('p', { class: 'field-hint', text: es ? 'Elige un proyecto para importar.' : 'Pick a project to import.' }))
      : frag([
          el('h4', { style: 'margin:12px 0 6px;font-size:13px', text: es ? 'Cómo conectarlo' : 'How to connect it' }),
          el('ol', { style: 'margin:0;padding-left:20px;font-size:13px;color:var(--text-dim)' },
            source.setup.map((step) => el('li', { style: 'margin-bottom:4px' }, [
              step.startsWith('DRAKEN_')
                ? el('code', { class: 'small', text: step })
                : step,
            ]))),
          el('p', { class: 'field-hint', text: es
            ? 'Añádelo a tu .env y reinicia el servicio.'
            : 'Add it to your .env and restart the service.' }),
        ]),
  ]);
}

export function actions(ctx) {
  const es = ctx.lang === 'es';
  return [
    actionButton(es ? 'Comprobar conexión' : 'Check connectivity', async () => {
      connectivity = await api.get('/system/connectivity', { target_url: ctx.project?.base_url || '' });
      toast(connectivity.verdict, connectivity.severity === 'good' ? 'good' : 'warn');
      ctx.reload();
    }, { primary: true }),
    actionButton(t('action.refresh'), () => ctx.reload()),
  ];
}
