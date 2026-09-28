import { api } from '../api.js';
import { t } from '../i18n.js';
import { actionButton, barRow, callout, card, el, frag, num, pill, toast } from '../ui.js';

export const meta = { id: 'profile', icon: 'profile', group: 'system' };

export async function render(ctx) {
  if (!ctx.project) return ctx.noProject();
  const es = ctx.lang === 'es';
  const [profile, completeness] = await Promise.all([
    api.get(`/projects/${ctx.project.id}/profile`),
    api.get(`/projects/${ctx.project.id}/profile/completeness`),
  ]);

  const fields = {};
  const input = (key, label, { type = 'text', hint, wide } = {}) => {
    const node = el('input', { class: 'input', type, value: profile[key] ?? '' });
    fields[key] = () => node.value;
    return el('label', { class: 'field', style: wide ? 'grid-column:1/-1' : null }, [
      el('span', { text: label }), node,
      hint ? el('div', { class: 'field-hint', text: hint }) : null,
    ]);
  };
  const textarea = (key, label, hint) => {
    const node = el('textarea', { class: 'textarea', style: 'font-family:inherit;font-size:13px' });
    node.value = profile[key] ?? '';
    fields[key] = () => node.value;
    return el('label', { class: 'field' }, [
      el('span', { text: label }), node,
      hint ? el('div', { class: 'field-hint', text: hint }) : null,
    ]);
  };
  const listInput = (key, label, hint) => {
    const value = Array.isArray(profile[key]) ? profile[key].join(', ') : '';
    const node = el('input', { class: 'input', value });
    fields[key] = () => node.value.split(',').map((s) => s.trim()).filter(Boolean);
    return el('label', { class: 'field' }, [
      el('span', { text: label }), node,
      hint ? el('div', { class: 'field-hint', text: hint }) : null,
    ]);
  };

  const socialKeys = ['linkedin', 'x', 'facebook', 'instagram', 'youtube', 'github'];
  const socialNodes = {};
  const socials = el('div', { class: 'field-row' }, socialKeys.map((k) => {
    const node = el('input', { class: 'input', value: (profile.social_profiles || {})[k] || '' });
    socialNodes[k] = node;
    return el('label', { class: 'field' }, [el('span', { text: k }), node]);
  }));

  const out = frag([
    callout(es
      ? 'Estos datos se reutilizan en cada alta de directorio, cada citación y en el JSON-LD. Escríbelos una vez, correctamente: cada ficha creada con datos incompletos es una que habrá que corregir después.'
      : 'This data is reused by every directory listing, every citation and the JSON-LD. Write it once, correctly: every listing created with incomplete data is one you will have to go back and fix.',
      'info'),
    card(es ? 'Completitud' : 'Completeness', frag([
      barRow(es ? 'Campos rellenos' : 'Fields filled', completeness.completeness * 100, 100, {
        formatted: `${Math.round(completeness.completeness * 100)}%`,
        tone: completeness.completeness >= 1 ? 'good' : completeness.completeness >= 0.5 ? 'warn' : 'bad',
      }),
      completeness.missing_fields.length
        ? el('div', { style: 'margin-top:8px' }, [
            el('span', { class: 'field-hint', text: `${es ? 'Pendientes' : 'Missing'}: ` }),
            ...completeness.missing_fields.map((f) => pill(String(f).replace(/_/g, ' '), 'warn')),
          ])
        : el('p', { class: 'field-hint', text: es ? 'Todo listo para enviar altas.' : 'Ready to submit listings.' }),
      el('p', { class: 'field-hint', text: completeness.note }),
    ])),
  ]);

  out.append(card(es ? 'Identidad' : 'Identity', el('div', { class: 'field-row' }, [
    input('display_name', es ? 'Nombre comercial' : 'Display name', {
      hint: es ? 'Exactamente como quieres que aparezca en todas las fichas' : 'Exactly as it should appear on every listing',
    }),
    input('legal_name', es ? 'Razón social' : 'Legal name'),
    input('tagline', es ? 'Lema' : 'Tagline'),
    input('founded_year', es ? 'Año de fundación' : 'Founded year', { type: 'number' }),
    input('employee_count', es ? 'Tamaño' : 'Size', { hint: '1-10, 11-50, …' }),
    input('logo_url', es ? 'URL del logo' : 'Logo URL'),
  ])));

  out.append(card(es ? 'Descripciones' : 'Descriptions', frag([
    textarea('short_description', es ? 'Descripción corta' : 'Short description',
      es ? 'Máximo 160 caracteres: es el límite de casi todos los formularios.' : 'Keep it under 160 characters: that is almost every form’s limit.'),
    textarea('long_description', es ? 'Descripción larga' : 'Long description',
      es ? 'Dos o tres frases claras sobre qué haces y para quién. Los asistentes de IA reutilizan este texto.' : 'Two or three clear sentences on what you do and for whom. AI assistants reuse this text.'),
    listInput('categories', es ? 'Categorías' : 'Categories'),
    listInput('keywords', es ? 'Palabras clave' : 'Keywords'),
  ])));

  out.append(card(es ? 'Contacto y dirección (NAP)' : 'Contact and address (NAP)',
    el('div', { class: 'field-row' }, [
      input('email', 'Email', { type: 'email' }),
      input('phone', es ? 'Teléfono' : 'Phone', {
        hint: es ? 'Formato internacional, siempre el mismo' : 'International format, always identical',
      }),
      input('website', 'Website'),
      input('street', es ? 'Calle' : 'Street'),
      input('city', es ? 'Ciudad' : 'City'),
      input('region', es ? 'Provincia / región' : 'Region'),
      input('postal_code', es ? 'Código postal' : 'Postal code'),
      input('country', es ? 'País' : 'Country'),
      input('latitude', es ? 'Latitud' : 'Latitude', { type: 'number' }),
      input('longitude', es ? 'Longitud' : 'Longitude', { type: 'number' }),
    ])));

  out.append(card(es ? 'Perfiles sociales' : 'Social profiles', frag([
    el('p', { class: 'card-sub', text: es
      ? 'Se publican como sameAs en el JSON-LD, que es cómo se vinculan tus perfiles a una sola entidad.'
      : 'Published as sameAs in the JSON-LD, which is how your profiles get linked to a single entity.' }),
    socials,
  ])));

  out.append(card(es ? 'Servicio' : 'Service', el('div', { class: 'field-row' }, [
    listInput('service_areas', es ? 'Zonas de servicio' : 'Service areas'),
    listInput('payment_methods', es ? 'Formas de pago' : 'Payment methods'),
  ])));

  out.append(el('div', { style: 'display:flex;gap:8px' }, [
    actionButton(t('action.save'), async () => {
      const payload = {};
      for (const [key, getValue] of Object.entries(fields)) {
        const value = getValue();
        if (['founded_year'].includes(key)) payload[key] = value === '' ? null : Number(value);
        else if (['latitude', 'longitude'].includes(key)) payload[key] = value === '' ? null : Number(value);
        else payload[key] = value;
      }
      payload.social_profiles = Object.fromEntries(
        Object.entries(socialNodes).map(([k, node]) => [k, node.value]).filter(([, v]) => v));
      payload.opening_hours = profile.opening_hours || [];
      payload.extra_fields = profile.extra_fields || {};
      await api.put(`/projects/${ctx.project.id}/profile`, payload);
      toast(t('msg.saved'), 'good');
      ctx.reload();
    }, { primary: true }),
  ]));

  return out;
}

export function actions(ctx) {
  if (!ctx.project) return [];
  return [actionButton(t('view.geoassets'), () => ctx.navigate('geoassets'))];
}
