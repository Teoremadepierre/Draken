import { api } from '../api.js';
import { t } from '../i18n.js';
import {
  actionButton, callout, card, closeModal, confirmDialog, copyToClipboard,
  dateTime, el, empty, frag, openModal, pill, table, toast,
} from '../ui.js';

export const meta = { id: 'team', icon: 'profile', group: 'system' };

export async function render(ctx) {
  const es = ctx.lang === 'es';
  const [users, me] = await Promise.all([api.get('/users'), api.get('/users/me')]);

  const out = frag([
    callout(es
      ? 'Tres roles: propietario (todo, incluido gestionar usuarios), editor (lanza escaneos y trabaja el pipeline) y lector (solo ve informes). Cada persona puede poner su propia clave de IA, así que trabaja con su asistente y no con el tuyo.'
      : 'Three roles: owner (everything, including managing users), editor (runs scans and works the pipeline) and viewer (reads reports only). Each person can set their own AI key, so they work with their assistant rather than yours.',
      'info'),
  ]);

  if (!me.auth_enabled) {
    out.append(callout(es
      ? 'La autenticación está desactivada (DRAKEN_AUTH_ENABLED=false), así que cualquiera que llegue al servidor entra. Actívala antes de exponerlo fuera de tu red.'
      : 'Authentication is off (DRAKEN_AUTH_ENABLED=false), so anyone who reaches the server gets in. Turn it on before exposing it outside your network.',
      'warn', es ? 'Atención' : 'Heads up'));
  }

  out.append(card(es ? 'Personas' : 'People', users.length
    ? table([
        { key: 'username', label: es ? 'Usuario' : 'User', render: (r) => el('div', {}, [
          el('span', { class: 'cell-strong', text: r.display_name || r.username }),
          el('div', { class: 'faint small', text: r.email || r.username }),
        ]) },
        { key: 'role', label: es ? 'Rol' : 'Role', render: (r) =>
          pill(roleLabel(r.role, es), r.role === 'owner' ? 'accent' : r.role === 'editor' ? 'teal' : '') },
        { key: 'is_active', label: t('label.status'), render: (r) =>
          r.pending_invite
            ? pill(es ? 'invitación pendiente' : 'invite pending', 'warn')
            : pill(r.is_active ? (es ? 'activo' : 'active') : (es ? 'desactivado' : 'disabled'),
                   r.is_active ? 'good' : '') },
        { key: 'has_own_ai_key', label: es ? 'IA propia' : 'Own AI', render: (r) =>
          r.has_own_ai_key ? pill(r.ai_engine || 'sí', 'good') : pill('—') },
        { key: 'last_login_at', label: es ? 'Último acceso' : 'Last login',
          render: (r) => dateTime(r.last_login_at) },
        { key: 'id', label: '', width: '120px', render: (r) => el('div', { class: 'row-actions' }, [
          el('button', { class: 'btn btn-ghost btn-sm', text: t('action.details'),
            onClick: (e) => { e.stopPropagation(); openUser(ctx, r); } }),
          el('button', { class: 'btn btn-ghost btn-sm', text: '×', title: t('action.delete'),
            onClick: (e) => {
              e.stopPropagation();
              confirmDialog(
                es ? `¿Eliminar a ${r.username}?` : `Delete ${r.username}?`,
                async () => {
                  try {
                    await api.del(`/users/${r.id}`);
                    toast(t('msg.deleted'), 'good'); ctx.reload();
                  } catch (error) { toast(error.message, 'bad'); }
                },
              );
            } }),
        ]) },
      ], users)
    : empty(es ? 'Solo estás tú' : 'Just you'),
    { actions: [actionButton(es ? 'Invitar' : 'Invite', () => openInvite(ctx), { small: true, primary: true })] }));

  out.append(card(es ? 'Compartir sin cuenta' : 'Share without an account', frag([
    el('p', { class: 'card-sub', text: es
      ? 'Si alguien solo tiene que leer un informe, no hace falta darle cuenta: crea un enlace compartido desde el Escáner. Es de solo lectura, caduca cuando tú decidas, y lleva incluido un informe listo para pegar en su propio Claude.'
      : 'If someone only needs to read a report, they do not need an account: create a share link from the Scanner. Read-only, expires when you decide, and it carries a paste-ready brief for their own Claude.' }),
    actionButton(es ? 'Ir al escáner' : 'Go to the scanner', () => ctx.navigate('scan'), { primary: true }),
  ])));

  return out;
}

function roleLabel(role, es) {
  if (!es) return role;
  return { owner: 'propietario', editor: 'editor', viewer: 'lector' }[role] || role;
}

function openInvite(ctx) {
  const es = ctx.lang === 'es';
  const username = el('input', { class: 'input', placeholder: 'pierre' });
  const displayName = el('input', { class: 'input', placeholder: 'Pierre Ramírez' });
  const email = el('input', { class: 'input', type: 'email', placeholder: 'pierre@empresa.com' });
  const role = el('select', { class: 'select' }, [
    ['editor', es ? 'Editor — lanza escaneos y trabaja el pipeline' : 'Editor — runs scans and works the pipeline'],
    ['viewer', es ? 'Lector — solo ve informes' : 'Viewer — reads reports only'],
    ['owner', es ? 'Propietario — todo, incluidos usuarios' : 'Owner — everything, including users'],
  ].map(([v, l]) => el('option', { value: v, text: l })));
  const days = el('input', { class: 'input', type: 'number', value: 14, min: 1, max: 90 });

  openModal({
    title: es ? 'Invitar a alguien' : 'Invite someone',
    body: frag([
      el('p', { class: 'field-hint', text: es
        ? 'No se envía ningún correo: Draken te da un enlace de un solo uso que le pasas como quieras. Así añadir a alguien nunca depende de tener SMTP configurado.'
        : 'No email is sent: Draken gives you a one-time link you pass along however you like. Adding someone never depends on SMTP being set up.' }),
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: es ? 'Usuario' : 'Username' }), username]),
        el('label', { class: 'field' }, [el('span', { text: es ? 'Nombre' : 'Name' }), displayName]),
      ]),
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: 'Email' }), email]),
        el('label', { class: 'field' }, [el('span', { text: es ? 'Caduca en (días)' : 'Expires in (days)' }), days]),
      ]),
      el('label', { class: 'field' }, [el('span', { text: es ? 'Rol' : 'Role' }), role]),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(es ? 'Crear invitación' : 'Create invite', async () => {
        if (!username.value.trim()) { toast(es ? 'Hace falta un usuario' : 'Username required', 'bad'); return; }
        try {
          const r = await api.post('/users/invite', {
            username: username.value.trim(), display_name: displayName.value,
            email: email.value, role: role.value, valid_days: Number(days.value), project_ids: [],
          });
          closeModal();
          showInviteLink(ctx, r);
          ctx.reload();
        } catch (error) { toast(error.message, 'bad'); }
      }, { primary: true }),
    ],
  });
}

function showInviteLink(ctx, invite) {
  const es = ctx.lang === 'es';
  const url = `${window.location.origin}${invite.invite_path}`;
  openModal({
    title: es ? 'Invitación creada' : 'Invite created',
    body: frag([
      el('p', { text: es
        ? `Pásale este enlace a ${invite.username}. Al abrirlo elige una contraseña y entra. Funciona una sola vez.`
        : `Send this link to ${invite.username}. Opening it lets them set a password and sign in. It works once.` }),
      el('pre', { class: 'code wrap', text: url }),
      el('p', { class: 'field-hint', text: `${es ? 'Caduca' : 'Expires'}: ${dateTime(invite.expires_at)}` }),
    ]),
    footer: [
      actionButton(t('action.copy'), () => copyToClipboard(url), { primary: true }),
      el('button', { class: 'btn', text: t('action.close'), onClick: closeModal }),
    ],
  });
}

function openUser(ctx, user) {
  const es = ctx.lang === 'es';
  const role = el('select', { class: 'select' },
    ['owner', 'editor', 'viewer'].map((v) =>
      el('option', { value: v, text: roleLabel(v, es), selected: user.role === v })));
  const active = el('input', { type: 'checkbox', checked: user.is_active });
  const engine = el('select', { class: 'select' },
    [['', es ? '— usar la clave global —' : '— use the global key —'],
     ['anthropic', 'Anthropic'], ['openai', 'OpenAI'],
     ['perplexity', 'Perplexity'], ['gemini', 'Gemini']]
      .map(([v, l]) => el('option', { value: v, text: l, selected: user.ai_engine === v })));
  const key = el('input', {
    class: 'input', type: 'password',
    placeholder: user.has_own_ai_key ? (es ? '— ya configurada —' : '— already set —') : 'sk-…',
  });

  openModal({
    title: user.display_name || user.username,
    body: frag([
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: es ? 'Rol' : 'Role' }), role]),
        el('label', { class: 'field' }, [
          el('span', { text: t('label.status') }),
          el('label', { class: 'checkbox' }, [active, es ? 'Activo' : 'Active']),
        ]),
      ]),
      el('h3', { style: 'margin:14px 0 6px', text: es ? 'Su propia IA' : 'Their own AI' }),
      el('p', { class: 'field-hint', text: es
        ? 'Si pones aquí su clave, sus consultas al asistente van a su cuenta y no a la tuya. Se guarda cifrada en tu base de datos y nunca se devuelve por la API.'
        : 'With their key here, their assistant queries go to their account instead of yours. It is stored in your database and never returned over the API.' }),
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: es ? 'Motor' : 'Engine' }), engine]),
        el('label', { class: 'field' }, [el('span', { text: es ? 'Clave' : 'Key' }), key]),
      ]),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.save'), async () => {
        const payload = { role: role.value, is_active: active.checked, ai_engine: engine.value };
        if (key.value.trim()) payload.ai_api_key = key.value.trim();
        await api.patch(`/users/${user.id}`, payload);
        closeModal(); toast(t('msg.saved'), 'good'); ctx.reload();
      }, { primary: true }),
    ],
  });
}

export function actions(ctx) {
  const es = ctx.lang === 'es';
  return [actionButton(es ? 'Invitar' : 'Invite', () => openInvite(ctx), { primary: true })];
}
