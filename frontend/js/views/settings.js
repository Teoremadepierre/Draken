import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, confirmDialog, el, frag, num, pill, toast,
} from '../ui.js';

export const meta = { id: 'settings', icon: 'settings', group: 'system' };

export async function render(ctx) {
  const es = ctx.lang === 'es';
  const health = await api.get('/health');
  const out = frag([]);

  if (ctx.project) {
    const name = el('input', { class: 'input', value: ctx.project.name });
    const baseUrl = el('input', { class: 'input', value: ctx.project.base_url });
    const country = el('input', { class: 'input', value: ctx.project.country });
    const language = el('input', { class: 'input', value: ctx.project.language });
    const industry = el('input', { class: 'input', value: ctx.project.industry,
      placeholder: es ? 'software, restaurante, legal, inmobiliaria…' : 'software, restaurant, legal, real-estate…' });
    const competitors = el('input', { class: 'input', value: (ctx.project.competitors || []).join(', ') });
    const brandTerms = el('input', { class: 'input', value: (ctx.project.brand_terms || []).join(', ') });
    const description = el('textarea', { class: 'textarea', style: 'font-family:inherit;font-size:13px;min-height:70px' });
    description.value = ctx.project.description || '';

    out.append(card(es ? 'Proyecto' : 'Project', frag([
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: t('label.name') }), name]),
        el('label', { class: 'field' }, [el('span', { text: t('label.domain') }),
          el('input', { class: 'input', value: ctx.project.domain, disabled: true })]),
        el('label', { class: 'field' }, [el('span', { text: t('label.baseUrl') }), baseUrl]),
        el('label', { class: 'field' }, [el('span', { text: t('label.country') }), country]),
        el('label', { class: 'field' }, [el('span', { text: t('label.language') }), language]),
        el('label', { class: 'field' }, [el('span', { text: t('label.industry') }), industry]),
      ]),
      el('label', { class: 'field' }, [
        el('span', { text: t('label.competitors') }), competitors,
        el('div', { class: 'field-hint', text: es
          ? 'Dominios separados por comas. Alimentan el link intersect, el gap de keywords y la cuota de voz en IA.'
          : 'Comma-separated domains. They feed link intersect, keyword gap and AI share of voice.' }),
      ]),
      el('label', { class: 'field' }, [
        el('span', { text: t('label.brandTerms') }), brandTerms,
        el('div', { class: 'field-hint', text: es
          ? 'Cómo te nombran: se usa para clasificar anchors de marca y detectar menciones en respuestas de IA.'
          : 'How you are named: used to classify branded anchors and to detect mentions in AI answers.' }),
      ]),
      el('label', { class: 'field' }, [el('span', { text: t('label.description') }), description]),
      el('div', { style: 'display:flex;gap:8px' }, [
        actionButton(t('action.save'), async () => {
          await api.patch(`/projects/${ctx.project.id}`, {
            name: name.value, base_url: baseUrl.value,
            country: country.value.toUpperCase(), language: language.value.toLowerCase(),
            industry: industry.value, description: description.value,
            competitors: competitors.value.split(',').map((s) => s.trim()).filter(Boolean),
            brand_terms: brandTerms.value.split(',').map((s) => s.trim()).filter(Boolean),
          });
          toast(t('msg.saved'), 'good');
          await ctx.refreshProjects();
          ctx.reload();
        }, { primary: true }),
        actionButton(t('action.delete'), () => confirmDialog(
          es ? `¿Eliminar "${ctx.project.name}" y todos sus datos?` : `Delete "${ctx.project.name}" and all its data?`,
          async () => {
            await api.del(`/projects/${ctx.project.id}`);
            toast(t('msg.deleted'), 'good');
            localStorage.removeItem('draken_project');
            await ctx.refreshProjects();
            ctx.navigate('dashboard');
          },
        )),
      ]),
    ])));
  }

  out.append(card(es ? 'Estado del despliegue' : 'Deployment state', frag([
    el('p', { class: 'card-sub', text: es
      ? 'Todo esto se configura con variables de entorno DRAKEN_* en tu .env. Reinicia el servicio después de cambiarlas.'
      : 'All of this is configured with DRAKEN_* environment variables in your .env. Restart the service after changing them.' }),
    el('dl', { class: 'kv' }, [
      el('dt', { text: es ? 'Versión' : 'Version' }), el('dd', { text: health.version }),
      el('dt', { text: 'Env' }), el('dd', {}, [pill(health.env, health.env === 'production' ? 'good' : '')]),
      el('dt', { text: es ? 'Autenticación' : 'Authentication' }),
      el('dd', {}, [pill(health.auth_enabled ? (es ? 'activa' : 'on') : (es ? 'desactivada' : 'off'),
        health.auth_enabled ? 'good' : 'warn')]),
      el('dt', { text: es ? 'Proveedor SERP' : 'SERP provider' }),
      el('dd', {}, [
        pill(health.serp_provider, health.serp_approximate ? 'warn' : 'good'),
        health.serp_approximate
          ? el('div', { class: 'field-hint', text: es
              ? 'Configura DRAKEN_SERPAPI_KEY o las credenciales de DataForSEO para posiciones exactas de Google.'
              : 'Set DRAKEN_SERPAPI_KEY or DataForSEO credentials for exact Google positions.' })
          : null,
      ]),
      el('dt', { text: es ? 'Motores de IA' : 'AI engines' }),
      el('dd', {}, (health.ai_engines || []).length
        ? health.ai_engines.map((e) => pill(e, 'good'))
        : [pill(es ? 'ninguno configurado' : 'none configured', 'warn')]),
      el('dt', { text: es ? 'Envíos: simulación' : 'Submissions: dry run' }),
      el('dd', {}, [pill(health.submissions.dry_run ? (es ? 'activa' : 'on') : (es ? 'desactivada' : 'off'),
        health.submissions.dry_run ? 'warn' : 'good')]),
      el('dt', { text: es ? 'Envíos: requiere aprobación' : 'Submissions: require approval' }),
      el('dd', {}, [pill(health.submissions.require_approval ? (es ? 'sí' : 'yes') : (es ? 'no' : 'no'),
        health.submissions.require_approval ? 'good' : 'warn')]),
      el('dt', { text: es ? 'Envío de emails' : 'Email sending' }),
      el('dd', {}, [pill(health.outreach_send_enabled ? (es ? 'activo' : 'on') : (es ? 'desactivado' : 'off'),
        health.outreach_send_enabled ? 'good' : '')]),
      el('dt', { text: es ? 'Tareas registradas' : 'Registered jobs' }),
      el('dd', { text: num((health.job_kinds || []).length) }),
    ]),
  ])));

  out.append(card(es ? 'Cómo suben los datos de nivel' : 'How the data gets better', frag([
    el('p', { class: 'card-sub', text: es
      ? 'Draken funciona sin ninguna clave. Cada clave que añadas sustituye una estimación por un dato real, y la interfaz siempre te dice cuál está usando.'
      : 'Draken works with no keys at all. Each key you add replaces an estimate with real data, and the interface always tells you which one it is using.' }),
    el('ul', { class: 'rec-list' }, [
      el('li', { text: es
        ? 'DRAKEN_SERPAPI_KEY o DataForSEO: posiciones reales de Google en vez del motor gratuito aproximado, y dificultad calculada sobre el SERP real.'
        : 'DRAKEN_SERPAPI_KEY or DataForSEO: real Google positions instead of the approximate free engine, and difficulty computed from the real SERP.' }),
      el('li', { text: es
        ? 'DRAKEN_OPENPAGERANK_KEY: autoridad de dominio medida (gratis con límites) en lugar de la estimación estructural.'
        : 'DRAKEN_OPENPAGERANK_KEY: measured domain authority (free with limits) instead of the structural estimate.' }),
      el('li', { text: es
        ? 'Una API de IA (Anthropic, OpenAI, Perplexity o Gemini): sin ella no se puede medir la visibilidad en asistentes. Perplexity es la más informativa porque devuelve sus fuentes.'
        : 'An AI API (Anthropic, OpenAI, Perplexity or Gemini): without one, assistant visibility cannot be measured. Perplexity is the most informative because it returns its sources.' }),
      el('li', { text: es
        ? 'Import de Search Console: el índice de backlinks más completo que vas a conseguir gratis. El descubrimiento por búsquedas solo ve una muestra.'
        : 'A Search Console export: the most complete backlink index you will get for free. Search-based discovery only sees a sample.' }),
    ]),
  ])));

  return out;
}

export function actions(ctx) {
  return [actionButton(t('action.refresh'), () => ctx.reload())];
}
