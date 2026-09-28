import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, el, empty, frag, num, pill, stat, table, toast,
} from '../ui.js';

export const meta = { id: 'onpage', icon: 'onpage', group: 'site' };

const state = { url: '', keyword: '', secondary: '', report: null };

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';

  const url = el('input', {
    class: 'input', value: state.url || ctx.project.base_url || `https://${ctx.project.domain}`,
    placeholder: 'https://…',
  });
  const keyword = el('input', { class: 'input', value: state.keyword, placeholder: es ? 'keyword objetivo' : 'target keyword' });
  const secondary = el('input', { class: 'input', value: state.secondary, placeholder: es ? 'secundarias, separadas por comas' : 'secondary, comma separated' });

  const form = card(es ? 'Analizar una URL' : 'Analyse a URL', frag([
    el('div', { class: 'field-row' }, [
      el('label', { class: 'field' }, [el('span', { text: t('label.url') }), url]),
      el('label', { class: 'field' }, [el('span', { text: es ? 'Keyword objetivo' : 'Target keyword' }), keyword]),
      el('label', { class: 'field' }, [el('span', { text: es ? 'Keywords secundarias' : 'Secondary keywords' }), secondary]),
    ]),
    actionButton(es ? 'Analizar' : 'Analyse', async () => {
      state.url = url.value.trim();
      state.keyword = keyword.value.trim();
      state.secondary = secondary.value.trim();
      if (!state.url) { toast(es ? 'Indica una URL' : 'Enter a URL', 'bad'); return; }
      state.report = await api.post(`/projects/${ctx.project.id}/onpage`, {
        url: state.url,
        target_keyword: state.keyword,
        secondary_keywords: state.secondary ? state.secondary.split(',').map((s) => s.trim()).filter(Boolean) : [],
      });
      ctx.reload();
    }, { primary: true }),
  ]));

  const out = frag([form]);
  const report = state.report;
  if (!report) return out;

  if (report.error) {
    out.append(callout(report.error, 'warn', es ? 'No se pudo analizar' : 'Could not analyse'));
    return out;
  }

  const m = report.metrics || {};
  const kp = report.keyword_placement || {};
  out.append(el('div', { class: 'stats' }, [
    stat(t('label.score'), num(report.score, 1), {
      tone: report.score >= 80 ? 'good' : report.score >= 55 ? 'warn' : 'bad',
    }),
    stat(es ? 'Palabras' : 'Words', num(m.word_count)),
    stat('H2', num(m.h2_count)),
    stat(es ? 'Enlaces internos' : 'Internal links', num(m.internal_links)),
    stat(es ? 'Respuesta' : 'Response', `${num(m.response_ms)} ms`),
    stat(es ? 'Preparación IA' : 'AI readiness', num(report.ai_readiness?.score, 1)),
  ]));

  if (state.keyword) {
    out.append(card(es ? `Colocación de "${state.keyword}"` : `Placement of "${state.keyword}"`, frag([
      el('div', { style: 'display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px' }, [
        ['in_title', es ? 'Título' : 'Title'],
        ['in_h1', 'H1'],
        ['in_h2', 'H2'],
        ['in_meta_description', es ? 'Meta descripción' : 'Meta description'],
        ['in_url', 'URL'],
        ['in_first_100_words', es ? 'Primeras 100 palabras' : 'First 100 words'],
      ].map(([key, label]) => pill(label, kp[key] ? 'good' : 'bad'))),
      el('dl', { class: 'kv' }, [
        el('dt', { text: es ? 'Apariciones' : 'Occurrences' }), el('dd', { text: num(kp.occurrences) }),
        el('dt', { text: es ? 'Densidad' : 'Density' }), el('dd', { text: `${num(kp.density_percent, 2)}%` }),
      ]),
    ])));
  }

  out.append(card(es ? 'Qué cambiar' : 'What to change',
    (report.recommendations || []).length
      ? table([
          { key: 'priority', label: es ? 'Prioridad' : 'Priority', width: '90px', render: (r) =>
            pill(r.priority, r.priority === 'high' ? 'bad' : r.priority === 'medium' ? 'warn' : '') },
          { key: 'area', label: es ? 'Área' : 'Area', render: (r) => pill(r.area) },
          { key: 'issue', label: t('label.issue'), render: (r) => el('div', {}, [
            el('span', { class: 'cell-strong', text: r.issue }),
            el('div', { class: 'faint small cell-wrap', text: r.action }),
          ]) },
        ], report.recommendations)
      : el('p', { class: 'muted', text: es ? 'Nada que cambiar.' : 'Nothing to change.' })));

  out.append(el('div', { class: 'grid grid-2' }, [
    card(es ? 'Legibilidad' : 'Readability', el('dl', { class: 'kv' }, [
      el('dt', { text: es ? 'Frases' : 'Sentences' }), el('dd', { text: num(report.readability?.sentences) }),
      el('dt', { text: es ? 'Longitud media' : 'Average length' }),
      el('dd', { text: `${num(report.readability?.avg_sentence_length, 1)} ${es ? 'palabras' : 'words'}` }),
      el('dt', { text: es ? 'Frases largas' : 'Long sentences' }),
      el('dd', { text: `${num((report.readability?.long_sentence_share || 0) * 100, 0)}%` }),
      el('dt', { text: es ? 'Veredicto' : 'Verdict' }), el('dd', { text: report.readability?.verdict || '—' }),
    ])),
    card(es ? 'Preparación para IA' : 'AI readiness', frag([
      el('div', { style: 'display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px' }, [
        pill('JSON-LD', report.ai_readiness?.has_schema ? 'good' : 'bad'),
        pill('FAQPage', report.ai_readiness?.has_faq_schema ? 'good' : ''),
        pill('Organization', report.ai_readiness?.has_organization_schema ? 'good' : ''),
        pill(`${report.ai_readiness?.quotable_sections ?? 0} ${es ? 'secciones citables' : 'quotable sections'}`, 'accent'),
      ]),
      el('ul', { class: 'rec-list' }, (report.ai_readiness?.notes || []).map((n) => el('li', { text: n }))),
    ])),
  ]));

  if ((report.entities || []).length) {
    out.append(card(es ? 'Términos dominantes en la página' : 'Terms the page is about',
      el('div', { style: 'display:flex;flex-wrap:wrap;gap:5px' },
        report.entities.slice(0, 24).map((e) => pill(`${e.term} ·${e.count}`))),
      { sub: es
        ? 'Lo que la página dice realmente. Si tu keyword objetivo no está aquí, la página trata de otra cosa.'
        : 'What the page actually talks about. If your target keyword is absent here, the page is about something else.' }));
  }

  return out;
}

export function actions(ctx) {
  if (!ctx.project) return [];
  return [actionButton(t('action.clear'), () => {
    state.report = null; state.url = ''; state.keyword = ''; state.secondary = '';
    ctx.reload();
  })];
}
