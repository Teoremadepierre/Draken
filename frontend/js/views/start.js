import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, el, frag, meter, num, pill, toast,
} from '../ui.js';

export const meta = { id: 'start', icon: 'start', group: 'overview' };

/**
 * The beginner path. Every step states what it is, why it matters, how long it
 * takes, and takes you straight there. Steps tick themselves off from real data,
 * so the checklist is never a lie.
 */
export async function render(ctx) {
  const es = ctx.lang === 'es';

  if (!ctx.project) {
    return frag([
      hero(ctx),
      card(null, frag([
        el('h2', { text: es ? 'Paso 1: escanea tu web' : 'Step 1: scan your site' }),
        el('p', { class: 'card-sub', text: es
          ? 'Todo empieza aquí. Pega tu URL en el Escáner y en un par de minutos tendrás el diagnóstico completo y la lista de backlinks que puedes conseguir.'
          : 'Everything starts here. Paste your URL in the Scanner and in a couple of minutes you have the full diagnosis and the list of backlinks you can get.' }),
        actionButton(es ? 'Ir al escáner' : 'Go to the scanner', () => ctx.navigate('scan'), { primary: true }),
      ])),
      glossary(ctx),
    ]);
  }

  const [overview, sources, profileCompleteness] = await Promise.all([
    api.get(`/projects/${ctx.project.id}/overview`),
    api.get('/system/data-sources', { project_id: ctx.project.id }),
    api.get(`/projects/${ctx.project.id}/profile/completeness`),
  ]);

  const steps = buildSteps(ctx, overview, sources, profileCompleteness);
  const done = steps.filter((s) => s.done).length;

  return frag([
    hero(ctx),
    card(null, frag([
      el('div', { style: 'display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px' }, [
        el('strong', { text: `${done} / ${steps.length} ${es ? 'completados' : 'done'}` }),
        el('div', { style: 'flex:1;min-width:160px' }, [
          meter((done / steps.length) * 100, 100, done === steps.length ? 'good' : ''),
        ]),
      ]),
      el('p', { class: 'field-hint', text: es
        ? 'Los pasos se marcan solos cuando Draken detecta que ya están hechos. En orden: cada uno depende del anterior.'
        : 'Steps tick themselves off when Draken detects they are done. In order: each depends on the one before.' }),
    ])),
    ...steps.map((step, i) => stepCard(ctx, step, i + 1)),
    glossary(ctx),
  ]);
}

function hero(ctx) {
  const es = ctx.lang === 'es';
  return el('div', { class: 'card', style: 'background:linear-gradient(135deg,var(--accent-soft),var(--teal-soft));border-color:transparent' }, [
    el('h2', { style: 'margin-bottom:6px', text: es ? 'Empieza aquí' : 'Start here' }),
    el('p', { style: 'margin:0;max-width:640px', class: 'muted', text: es
      ? 'Si es tu primera vez con SEO, sigue estos pasos en orden. No hace falta que entiendas la teoría: cada paso dice qué hace, por qué importa y cuánto tarda.'
      : 'If this is your first time with SEO, follow these steps in order. You do not need the theory: each step says what it does, why it matters and how long it takes.' }),
  ]);
}

function buildSteps(ctx, overview, sources, completeness) {
  const es = ctx.lang === 'es';
  const c = overview.counts;
  const health = overview.site_health;

  return [
    {
      id: 'scan',
      done: Boolean(health.audit_id),
      title: es ? 'Escanea tu web' : 'Scan your site',
      why: es
        ? 'Sin saber qué está roto, cualquier otra cosa que hagas es a ciegas. El escaneo encuentra los problemas técnicos, tus enlaces actuales y qué backlinks puedes conseguir.'
        : 'Without knowing what is broken, everything else is guesswork. The scan finds technical problems, your current links, and which backlinks you can get.',
      time: es ? '2 minutos' : '2 minutes',
      view: 'scan',
      cta: es ? 'Escanear' : 'Scan',
      result: health.audit_id
        ? (es ? `Hecho: ${num(health.pages_crawled)} páginas, salud ${num(health.score, 0)}/100`
              : `Done: ${num(health.pages_crawled)} pages, health ${num(health.score, 0)}/100`)
        : '',
    },
    {
      id: 'fix',
      done: Boolean(health.audit_id) && (health.issue_counts?.critical || 0) === 0
            && (health.issue_counts?.error || 0) === 0,
      title: es ? 'Arregla lo crítico' : 'Fix the critical issues',
      why: es
        ? 'Conseguir enlaces hacia un sitio roto es tirar el trabajo. Arregla primero lo que impide que te indexen: páginas caídas, títulos duplicados, falta de H1.'
        : 'Earning links to a broken site wastes the work. Fix what blocks indexing first: dead pages, duplicate titles, missing H1s.',
      time: es ? '1-3 horas' : '1-3 hours',
      view: 'scan',
      cta: es ? 'Ver qué arreglar' : 'See what to fix',
      result: health.audit_id
        ? (es ? `${(health.issue_counts?.critical || 0)} críticos, ${(health.issue_counts?.error || 0)} errores`
              : `${(health.issue_counts?.critical || 0)} critical, ${(health.issue_counts?.error || 0)} errors`)
        : '',
      hint: es
        ? 'Cada problema tiene un botón "Arreglar" que le pide a la IA el cambio exacto para tu caso.'
        : 'Every issue has a "Fix" button that asks the AI for the exact change for your case.',
    },
    {
      id: 'profile',
      done: completeness.completeness >= 1.0,
      title: es ? 'Rellena la ficha de empresa' : 'Fill in the business profile',
      why: es
        ? 'Estos datos se copian a 40 sitios distintos. Escribirlos una vez y bien es lo que evita tener que corregir 40 fichas después. Es el paso que más gente se salta y el que más caro sale.'
        : 'This data gets copied to 40 different sites. Writing it once, correctly, is what stops you fixing 40 listings later. It is the most-skipped step and the most expensive one to skip.',
      time: es ? '20 minutos' : '20 minutes',
      view: 'profile',
      cta: es ? 'Rellenar ficha' : 'Fill the profile',
      result: `${Math.round(completeness.completeness * 100)}% ${es ? 'completa' : 'complete'}`,
      blocking: es
        ? 'Draken no deja preparar envíos por debajo del 50%: una ficha incompleta con tu marca es peor que ninguna.'
        : 'Draken blocks submissions below 50%: an incomplete listing under your brand is worse than none.',
    },
    {
      id: 'links',
      done: c.referring_domains >= 10,
      title: es ? 'Consigue tus primeros enlaces' : 'Get your first links',
      why: es
        ? 'Con cero backlinks tienes un techo de posicionamiento muy bajo por muy bueno que sea el contenido. Empieza por las fichas y perfiles: son gratis, no se pierden y no hay que convencer a nadie.'
        : 'With zero backlinks there is a hard ceiling on rankings no matter how good the content is. Start with listings and profiles: free, durable, and nobody has to say yes.',
      time: es ? '4-6 horas repartidas' : '4-6 hours spread out',
      view: 'opportunities',
      cta: es ? 'Ver oportunidades' : 'See opportunities',
      result: `${num(c.referring_domains)} ${es ? 'dominios de referencia' : 'referring domains'}`,
      hint: es
        ? 'Filtra por esfuerzo 1-2 y trabaja de arriba abajo. La meta del primer mes son 30 dominios.'
        : 'Filter to effort 1-2 and work top to bottom. The first-month target is 30 domains.',
    },
    {
      id: 'keywords',
      done: c.keywords >= 20,
      title: es ? 'Investiga tus palabras clave' : 'Research your keywords',
      why: es
        ? 'Saber qué busca la gente es lo que decide sobre qué escribir y a qué página apuntar los enlaces. Dos a cinco términos semilla bastan para empezar.'
        : 'Knowing what people search for is what decides what to write and where to point links. Two to five seed terms is enough to start.',
      time: es ? '30 minutos' : '30 minutes',
      view: 'keywords',
      cta: es ? 'Investigar' : 'Research',
      result: `${num(c.keywords)} keywords`,
    },
    {
      id: 'realdata',
      done: sources.first_party.search_console || sources.first_party.bing_webmaster,
      title: es ? 'Conecta datos reales' : 'Connect real data',
      why: es
        ? 'Hasta aquí muchos números son estimaciones. Search Console te da las impresiones, clics y posiciones que Google midió de verdad, y Bing te da tus backlinks reales gratis. Es lo que convierte esta herramienta en datos y no en aproximaciones.'
        : 'Up to here many numbers are estimates. Search Console gives you the impressions, clicks and positions Google actually measured, and Bing gives you your real backlinks for free. This is what turns the tool from approximations into data.',
      time: es ? '15 minutos, una sola vez' : '15 minutes, once',
      view: 'datasources',
      cta: es ? 'Conectar' : 'Connect',
      result: `${es ? 'Calidad de datos' : 'Data quality'} ${sources.quality.level}/4`,
    },
    {
      id: 'ai',
      done: (overview.ai_visibility?.by_engine || []).length > 0,
      title: es ? 'Mide cómo te ven las IA' : 'Measure how AI sees you',
      why: es
        ? 'Cada vez más gente pregunta a un asistente en vez de buscar. Si el asistente no te nombra, no existes en ese canal. Aquí hay mucha menos competencia que en Google, sobre todo en español.'
        : 'More people ask an assistant instead of searching. If the assistant does not name you, you do not exist in that channel. There is far less competition here than in Google, especially in Spanish.',
      time: es ? '10 minutos' : '10 minutes',
      view: 'aivisibility',
      cta: es ? 'Medir' : 'Measure',
      result: (overview.ai_visibility?.by_engine || []).length
        ? `${Math.round((overview.ai_visibility.mention_rate || 0) * 100)}% ${es ? 'de menciones' : 'mention rate'}`
        : (es ? 'Sin medir' : 'Not measured'),
    },
    {
      id: 'routine',
      done: false,
      title: es ? 'Conviértelo en rutina' : 'Make it a routine',
      why: es
        ? 'El SEO no se termina, se mantiene. Una vez al mes: re-escanea, recupera los enlaces perdidos, publica algo que merezca enlaces y revisa la visibilidad en IA.'
        : 'SEO is not finished, it is maintained. Once a month: re-scan, recover lost links, publish something worth linking to, and re-check AI visibility.',
      time: es ? '2 horas al mes' : '2 hours a month',
      view: 'jobs',
      cta: es ? 'Ver tareas automáticas' : 'See automated jobs',
      result: '',
      hint: es
        ? 'El "Barrido completo" hace todo esto de una vez, y se puede programar con cron.'
        : 'The "Full sweep" job does all of it at once, and can be scheduled with cron.',
    },
  ];
}

function stepCard(ctx, step, index) {
  const es = ctx.lang === 'es';
  return el('div', {
    class: 'card',
    style: step.done ? 'border-color:var(--good);opacity:.78' : '',
  }, [
    el('div', { class: 'card-head' }, [
      el('div', { style: 'display:flex;align-items:center;gap:10px' }, [
        el('span', {
          style: `display:inline-grid;place-items:center;width:26px;height:26px;border-radius:50%;
                  font-size:12px;font-weight:700;
                  background:${step.done ? 'var(--good)' : 'var(--bg-elev-2)'};
                  color:${step.done ? '#06231a' : 'var(--text-dim)'}`,
          text: step.done ? '✓' : String(index),
        }),
        el('h2', { text: step.title }),
      ]),
      el('div', { class: 'row-actions' }, [
        step.time ? pill(step.time) : null,
        step.result ? pill(step.result, step.done ? 'good' : '') : null,
      ]),
    ]),
    el('p', { style: 'max-width:720px', text: step.why }),
    step.blocking ? el('div', { class: 'callout callout-warn' }, [el('div', { text: step.blocking })]) : null,
    step.hint ? el('p', { class: 'field-hint', text: step.hint }) : null,
    actionButton(step.cta, () => ctx.navigate(step.view), { primary: !step.done }),
  ]);
}

function glossary(ctx) {
  const es = ctx.lang === 'es';
  const terms = es ? [
    ['Backlink', 'Un enlace desde otra web hacia la tuya. Cuenta como un voto de confianza.'],
    ['Dominio de referencia', 'Una web distinta que te enlaza. Importa mucho más que el número total de enlaces: 10 enlaces de 10 webs valen más que 100 de una sola.'],
    ['Dofollow / nofollow', 'Un atributo del enlace. Dofollow transmite autoridad; nofollow no, aunque sigue sirviendo como señal de marca y lo leen las IA.'],
    ['Anchor (texto ancla)', 'Las palabras sobre las que se pincha. Si todos tus enlaces usan tu keyword exacta, parece manipulado. Lo natural es que usen tu nombre.'],
    ['Autoridad de dominio', 'Una estimación de 0 a 100 de la fuerza de una web. Es de terceros, no de Google: úsala para comparar, no como objetivo.'],
    ['Dificultad (KD)', 'Cuánto cuesta posicionar para una keyword, de 0 a 100. Se calcula mirando la fuerza de quien ya está arriba.'],
    ['Intención de búsqueda', 'Qué quiere quien busca: informarse, comparar o comprar. Decide qué tipo de página necesitas.'],
    ['SERP', 'La página de resultados del buscador.'],
    ['Citación local', 'Una ficha de tu negocio en un directorio, con nombre, dirección y teléfono. La clave es que sean idénticos en todas.'],
    ['NAP', 'Name, Address, Phone. Los tres datos que tienen que coincidir exactamente en todas tus fichas.'],
    ['Datos estructurados (JSON-LD)', 'Un bloque de código que describe tu negocio en un formato que máquinas y IA entienden sin adivinar.'],
    ['llms.txt', 'Un fichero de texto en la raíz de tu web que explica quién eres a los rastreadores de IA. Como robots.txt, pero para asistentes.'],
    ['GEO', 'Optimizar para que los asistentes de IA te nombren y te citen, no para posicionar en Google.'],
  ] : [
    ['Backlink', 'A link from another site to yours. It counts as a vote of confidence.'],
    ['Referring domain', 'A distinct site that links to you. Matters far more than total links: 10 links from 10 sites beat 100 from one.'],
    ['Dofollow / nofollow', 'A link attribute. Dofollow passes authority; nofollow does not, though it still works as a brand signal and AI models read it.'],
    ['Anchor text', 'The words you click on. If every link uses your exact keyword it looks manipulated. Natural profiles mostly use your name.'],
    ['Domain authority', 'A third-party 0-100 estimate of a site’s strength. Not a Google signal: compare with it, do not target it.'],
    ['Difficulty (KD)', 'How hard a keyword is to rank for, 0-100, computed from the strength of who is already there.'],
    ['Search intent', 'What the searcher wants: to learn, to compare, or to buy. It decides what kind of page you need.'],
    ['SERP', 'The search engine results page.'],
    ['Local citation', 'A listing of your business in a directory with name, address and phone. The point is that they are identical everywhere.'],
    ['NAP', 'Name, Address, Phone. The three fields that must match exactly across every listing.'],
    ['Structured data (JSON-LD)', 'A code block describing your business in a format machines and AI parse without guessing.'],
    ['llms.txt', 'A text file at your site root explaining who you are to AI crawlers. Like robots.txt, but for assistants.'],
    ['GEO', 'Optimising so AI assistants name and cite you, rather than for Google rankings.'],
  ];

  return card(es ? 'Glosario: las palabras que vas a ver' : 'Glossary: the words you will see',
    el('dl', { class: 'kv' }, terms.flatMap(([term, meaning]) => [
      el('dt', { text: term }),
      el('dd', { text: meaning }),
    ])),
    { sub: es
      ? 'No hace falta memorizarlo. Vuelve aquí cuando algo no te suene.'
      : 'No need to memorise it. Come back when something does not ring a bell.' });
}

export function actions(ctx) {
  const es = ctx.lang === 'es';
  return [
    actionButton(es ? 'Escanear una web' : 'Scan a site', () => ctx.navigate('scan'), { primary: true }),
  ];
}
