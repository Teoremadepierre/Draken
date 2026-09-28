// Application bootstrap: config, auth, project switching, hash routing and the
// per-view lifecycle. No build step - the browser loads these modules directly.

import { api, ApiError, hasToken, pollJob, setToken } from './api.js';
import { applyStaticLabels, getLang, setLang, t } from './i18n.js';
import {
  actionButton, card, clear, closeModal, el, empty, frag, ICONS, icon,
  initOverlays, loading, openModal, pill, toast,
} from './ui.js';

import * as dashboard from './views/dashboard.js';
import * as keywords from './views/keywords.js';
import * as clusters from './views/clusters.js';
import * as rankings from './views/rankings.js';
import * as gap from './views/gap.js';
import * as audit from './views/audit.js';
import * as onpage from './views/onpage.js';
import * as backlinks from './views/backlinks.js';
import * as opportunities from './views/opportunities.js';
import * as sources from './views/sources.js';
import * as submissions from './views/submissions.js';
import * as outreach from './views/outreach.js';
import * as campaigns from './views/campaigns.js';
import * as aivisibility from './views/aivisibility.js';
import * as geoassets from './views/geoassets.js';
import * as profile from './views/profile.js';
import * as jobs from './views/jobs.js';
import * as settings from './views/settings.js';

const VIEWS = [
  dashboard, keywords, clusters, rankings, gap, audit, onpage, backlinks,
  opportunities, sources, submissions, outreach, campaigns, aivisibility,
  geoassets, profile, jobs, settings,
];

const GROUPS = ['overview', 'research', 'site', 'links', 'ai', 'system'];

const app = {
  config: null,
  projects: [],
  project: null,
  viewId: 'dashboard',
  watchedJobs: new Set(),
};

// --- context handed to each view -----------------------------------------

function makeContext() {
  return {
    config: app.config,
    projects: app.projects,
    project: app.project,
    lang: getLang(),
    navigate,
    reload: () => renderView(app.viewId),
    refreshProjects: loadProjects,
    watchJob,
    noProject: () => card(null, empty(
      t('empty.noProject'), t('empty.noProjectBody'),
      actionButton(t('action.create'), openNewProject, { primary: true }),
    )),
  };
}

// --- routing -------------------------------------------------------------

function navigate(viewId) {
  if (window.location.hash.slice(1) === viewId) renderView(viewId);
  else window.location.hash = viewId;
}

function currentViewId() {
  const id = window.location.hash.slice(1);
  return VIEWS.some((v) => v.meta.id === id) ? id : 'dashboard';
}

async function renderView(viewId) {
  app.viewId = viewId;
  const view = VIEWS.find((v) => v.meta.id === viewId) || dashboard;
  const host = document.getElementById('view');

  document.getElementById('view-title').textContent = t(`view.${view.meta.id}`);
  document.getElementById('view-sub').textContent = t(`sub.${view.meta.id}`);
  renderNav();

  const ctx = makeContext();
  const actionsHost = clear(document.getElementById('view-actions'));
  if (view.actions) {
    try { actionsHost.append(frag(view.actions(ctx))); } catch { /* actions are best-effort */ }
  }

  clear(host).append(loading());
  try {
    const content = await view.render(ctx);
    clear(host).append(content instanceof Node ? content : document.createTextNode(String(content ?? '')));
  } catch (error) {
    clear(host).append(renderError(error, ctx));
  }
}

function renderError(error, ctx) {
  const es = ctx.lang === 'es';
  console.error(error);
  return card(t('msg.error'), frag([
    el('p', { text: error instanceof ApiError ? error.message : String(error?.message || error) }),
    error instanceof ApiError && error.status
      ? el('p', { class: 'field-hint', text: `HTTP ${error.status}` })
      : null,
    el('p', { class: 'field-hint', text: es
      ? 'Si acaba de pasar tras cambiar la configuración, reinicia el servicio. El detalle completo está en los logs del servidor.'
      : 'If this started after a configuration change, restart the service. Full detail is in the server logs.' }),
    actionButton(t('action.retry'), () => renderView(app.viewId), { primary: true }),
  ]));
}

// --- navigation ----------------------------------------------------------

function renderNav() {
  const nav = clear(document.getElementById('nav'));
  for (const group of GROUPS) {
    const items = VIEWS.filter((v) => v.meta.group === group);
    if (!items.length) continue;
    nav.append(el('div', { class: 'nav-group' }, [
      el('div', { class: 'nav-group-label', text: t(`group.${group}`) }),
      ...items.map((v) => {
        const button = el('button', {
          class: `nav-item${v.meta.id === app.viewId ? ' is-active' : ''}`,
        }, [
          icon(ICONS[v.meta.icon] || ICONS.dashboard, 16),
          el('span', { text: t(`view.${v.meta.id}`) }),
        ]);
        button.addEventListener('click', () => navigate(v.meta.id));
        return button;
      }),
    ]));
  }
}

function renderEnvBadges() {
  const host = clear(document.getElementById('env-badges'));
  const c = app.config;
  if (!c) return;
  if (c.serp_approximate) host.append(pill('SERP ~', 'warn'));
  if (c.submissions_dry_run) host.append(pill('dry-run', 'warn'));
  if (!Object.values(c.ai_engines_configured || {}).some(Boolean)) host.append(pill('no AI', 'warn'));
  if (c.outreach_send_enabled) host.append(pill('mail on', 'good'));
  host.append(pill(`v${c.version}`));
}

// --- projects ------------------------------------------------------------

async function loadProjects() {
  app.projects = await api.get('/projects');
  const select = clear(document.getElementById('project-select'));

  if (!app.projects.length) {
    app.project = null;
    select.append(el('option', { value: '', text: t('empty.noProject') }));
    return;
  }

  const stored = Number(localStorage.getItem('draken_project'));
  app.project = app.projects.find((p) => p.id === stored) || app.projects[0];
  localStorage.setItem('draken_project', app.project.id);

  for (const p of app.projects) {
    select.append(el('option', {
      value: p.id, text: p.name, selected: p.id === app.project.id,
    }));
  }
}

function openNewProject() {
  const es = getLang() === 'es';
  const name = el('input', { class: 'input', placeholder: 'Acme' });
  const domain = el('input', { class: 'input', placeholder: 'acme.com' });
  const country = el('input', { class: 'input', value: es ? 'ES' : 'US' });
  const language = el('input', { class: 'input', value: es ? 'es' : 'en' });
  const industry = el('input', { class: 'input',
    placeholder: es ? 'software, restaurante, legal…' : 'software, restaurant, legal…' });
  const competitors = el('input', { class: 'input', placeholder: 'competitor-one.com, competitor-two.com' });

  openModal({
    title: es ? 'Nuevo proyecto' : 'New project',
    body: frag([
      el('p', { class: 'field-hint', text: es
        ? 'Al crearlo, Draken puntúa las 355 fuentes del catálogo para este dominio y te deja una cola de oportunidades lista.'
        : 'On creation, Draken scores all 355 catalog sources for this domain and leaves you a ready work queue.' }),
      el('div', { class: 'field-row' }, [
        el('label', { class: 'field' }, [el('span', { text: t('label.name') }), name]),
        el('label', { class: 'field' }, [el('span', { text: t('label.domain') }), domain]),
        el('label', { class: 'field' }, [el('span', { text: t('label.country') }), country]),
        el('label', { class: 'field' }, [el('span', { text: t('label.language') }), language]),
      ]),
      el('label', { class: 'field' }, [
        el('span', { text: t('label.industry') }), industry,
        el('div', { class: 'field-hint', text: es
          ? 'Decide qué directorios verticales puntúan alto. Ponlo aunque sea aproximado.'
          : 'Decides which vertical directories score high. Set it even if approximate.' }),
      ]),
      el('label', { class: 'field' }, [
        el('span', { text: t('label.competitors') }), competitors,
      ]),
    ]),
    footer: [
      el('button', { class: 'btn', text: t('action.cancel'), onClick: closeModal }),
      actionButton(t('action.create'), async () => {
        if (!name.value.trim() || !domain.value.trim()) {
          toast(es ? 'Nombre y dominio son obligatorios' : 'Name and domain are required', 'bad');
          return;
        }
        try {
          const project = await api.post('/projects', {
            name: name.value.trim(), domain: domain.value.trim(),
            country: country.value.trim() || 'US', language: language.value.trim() || 'en',
            industry: industry.value.trim(),
            competitors: competitors.value.split(',').map((s) => s.trim()).filter(Boolean),
            brand_terms: [name.value.trim()],
          });
          closeModal();
          localStorage.setItem('draken_project', project.id);
          await loadProjects();
          toast(es ? 'Proyecto creado con su cola de oportunidades' : 'Project created with its opportunity queue', 'good');
          navigate('dashboard');
          renderView('dashboard');
        } catch (error) {
          toast(error.message, 'bad', t('msg.error'));
        }
      }, { primary: true }),
    ],
  });
}

// --- background jobs -----------------------------------------------------

function watchJob(jobId, onDone) {
  if (app.watchedJobs.has(jobId)) return;
  app.watchedJobs.add(jobId);
  pollJob(jobId, { intervalMs: 2000 })
    .then((job) => {
      app.watchedJobs.delete(jobId);
      if (job.state === 'failed') {
        toast(job.error ? String(job.error).split('\n')[0] : t('msg.error'), 'bad', `${job.kind} #${jobId}`);
      } else if (job.state === 'succeeded' && !onDone) {
        toast(t('msg.done'), 'good', `${job.kind} #${jobId}`);
      }
      onDone?.(job);
    })
    .catch((error) => {
      app.watchedJobs.delete(jobId);
      toast(error.message, 'bad', t('msg.error'));
    });
}

// --- auth ----------------------------------------------------------------

function showLogin(message) {
  document.getElementById('app').hidden = true;
  const screen = document.getElementById('login');
  screen.hidden = false;
  const error = document.getElementById('login-error');
  if (message) { error.textContent = message; error.hidden = false; }
}

function showApp() {
  document.getElementById('login').hidden = true;
  document.getElementById('app').hidden = false;
}

async function attemptStart() {
  try {
    app.config = await api.get('/config');
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) { showLogin(); return; }
    document.body.append(el('div', { class: 'callout callout-warn', style: 'margin:20px' }, [
      el('div', {}, [
        el('strong', { text: 'Draken' }),
        `Could not reach the API: ${error.message}`,
      ]),
    ]));
    return;
  }

  if (app.config.auth_enabled && !hasToken()) { showLogin(); return; }

  showApp();
  renderEnvBadges();
  await loadProjects();
  renderView(currentViewId());
}

// --- wiring --------------------------------------------------------------

function init() {
  applyStaticLabels();
  initOverlays();

  document.getElementById('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    try {
      const result = await api.post('/auth/login', {
        username: form.get('username'), password: form.get('password'),
      });
      setToken(result.token);
      document.getElementById('login-error').hidden = true;
      await attemptStart();
    } catch (error) {
      const message = error.status === 401 ? t('login.failed') : error.message;
      const node = document.getElementById('login-error');
      node.textContent = message;
      node.hidden = false;
    }
  });

  document.getElementById('project-select').addEventListener('change', async (event) => {
    localStorage.setItem('draken_project', event.target.value);
    await loadProjects();
    renderView(app.viewId);
  });

  document.getElementById('new-project').addEventListener('click', openNewProject);

  document.getElementById('nav-toggle').addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('is-open');
  });
  document.getElementById('nav').addEventListener('click', () => {
    document.getElementById('sidebar').classList.remove('is-open');
  });

  document.querySelectorAll('.lang-btn').forEach((button) => {
    button.addEventListener('click', () => {
      setLang(button.dataset.lang);
      document.querySelectorAll('.lang-btn').forEach((b) =>
        b.classList.toggle('is-active', b.dataset.lang === getLang()));
      renderView(app.viewId);
    });
  });
  document.querySelectorAll('.lang-btn').forEach((b) =>
    b.classList.toggle('is-active', b.dataset.lang === getLang()));

  window.addEventListener('hashchange', () => renderView(currentViewId()));
  window.addEventListener('draken:unauthorized', () => showLogin(t('login.failed')));

  attemptStart();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
