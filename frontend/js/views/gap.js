import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, compact, el, empty, externalLink, frag, num, pill,
  scoreChip, stat, table, toast,
} from '../ui.js';

export const meta = { id: 'gap', icon: 'gap', group: 'research' };

let result = null;

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';

  const out = frag([
    callout(es
      ? 'El gap se calcula sobre los SERP que Draken ya ha guardado, así que ejecuta primero el seguimiento de posiciones sobre tus keywords.'
      : 'The gap is computed from the SERPs Draken has already cached, so run rank tracking on your keywords first.',
      'info'),
  ]);

  if (!(ctx.project.competitors || []).length) {
    out.append(card(null, empty(
      es ? 'No hay competidores definidos' : 'No competitors defined',
      es ? 'Añade dominios de competidores en la configuración del proyecto para comparar.'
         : 'Add competitor domains in the project settings to compare.',
      actionButton(t('view.settings'), () => ctx.navigate('settings'), { primary: true }),
    )));
    return out;
  }

  out.append(el('div', { class: 'filters' }, [
    el('span', { class: 'field-hint', text: `${es ? 'Comparando con' : 'Comparing against'}: ${(ctx.project.competitors || []).join(', ')}` }),
    actionButton(es ? 'Calcular gap' : 'Compute gap', async () => {
      result = await api.post(`/projects/${ctx.project.id}/keywords/gap`, {
        competitors: ctx.project.competitors, country: ctx.project.country, limit: 300,
      });
      ctx.reload();
    }, { primary: true, small: true }),
  ]));

  if (!result) return out;

  if (result.message) {
    out.append(callout(result.message, 'warn'));
    return out;
  }

  out.append(el('div', { class: 'stats' }, [
    stat(es ? 'Términos analizados' : 'Terms analysed', num(result.terms_analysed)),
    stat(es ? 'Huecos encontrados' : 'Gaps found', num((result.gaps || []).length)),
    stat(es ? 'No posicionas' : 'Not ranking', num(result.not_ranking), { tone: 'bad' }),
    stat(es ? 'Te superan' : 'Outranked', num(result.outranked), { tone: 'warn' }),
  ]));

  if (!(result.gaps || []).length) {
    out.append(card(null, empty(
      es ? 'Sin huecos' : 'No gaps',
      es ? 'En los SERP guardados no hay keywords donde la competencia te supere. Amplía tu lista de keywords seguidas.'
         : 'In the cached SERPs there are no keywords where competitors beat you. Widen your tracked keyword list.',
    )));
    return out;
  }

  out.append(card(es ? 'Huecos por prioridad' : 'Gaps by priority', table([
    { key: 'term', label: t('label.keyword'), render: (r) => el('span', { class: 'cell-strong', text: r.term }) },
    { key: 'volume', label: t('label.volume'), num: true, render: (r) => compact(r.volume) },
    { key: 'difficulty', label: 'KD', num: true, render: (r) => scoreChip(r.difficulty, { invert: true }) },
    { key: 'our_position', label: es ? 'Tú' : 'You', num: true, render: (r) =>
      r.our_position ? pill(`#${r.our_position}`, 'warn') : pill('—', 'bad') },
    { key: 'best_competitor', label: es ? 'Mejor competidor' : 'Best competitor', render: (r) => el('div', {}, [
      el('span', { class: 'small', text: r.best_competitor }),
      el('div', { class: 'faint small', text: `#${r.best_competitor_position}` }),
    ]) },
    { key: 'competitors_ranking', label: es ? 'Cuántos' : 'How many', num: true },
    { key: 'gap_type', label: t('label.type'), render: (r) =>
      pill(r.gap_type === 'not_ranking' ? (es ? 'sin posición' : 'not ranking') : (es ? 'superado' : 'outranked'),
        r.gap_type === 'not_ranking' ? 'bad' : 'warn') },
    { key: 'priority', label: es ? 'Prioridad' : 'Priority', num: true, render: (r) => scoreChip(r.priority) },
  ], result.gaps), {
    sub: es
      ? 'Cuantos más competidores posicionen para un término, más claro es que tú también puedes.'
      : 'The more competitors ranking for a term, the clearer it is that you can too.',
  }));

  return out;
}

export function actions(ctx) {
  if (!ctx.project) return [];
  return [actionButton(t('action.clear'), () => { result = null; ctx.reload(); })];
}
