// Thin fetch wrapper. Every call goes through here so auth, errors and query
// serialisation are handled once.

let token = localStorage.getItem('draken_token') || '';

export function setToken(value) {
  token = value || '';
  if (token) localStorage.setItem('draken_token', token);
  else localStorage.removeItem('draken_token');
}

export function hasToken() {
  return Boolean(token);
}

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function qs(params) {
  if (!params) return '';
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v));
    else search.append(key, value);
  }
  const out = search.toString();
  return out ? `?${out}` : '';
}

async function request(method, path, { params, body, raw } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const response = await fetch(`/api${path}${qs(params)}`, {
    method,
    headers,
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401) {
    setToken('');
    window.dispatchEvent(new CustomEvent('draken:unauthorized'));
    throw new ApiError('Not authenticated', 401, null);
  }
  if (response.status === 204) return null;

  if (raw) {
    if (!response.ok) throw new ApiError(await response.text(), response.status, null);
    return response.text();
  }

  const text = await response.text();
  let payload = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = text; }
  }

  if (!response.ok) {
    const detail = payload && typeof payload === 'object' ? payload.detail : payload;
    throw new ApiError(formatDetail(detail) || `HTTP ${response.status}`, response.status, payload);
  }
  return payload;
}

// FastAPI validation errors arrive as a list of objects; make them readable.
function formatDetail(detail) {
  if (!detail) return '';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const where = Array.isArray(d.loc) ? d.loc.filter((p) => p !== 'body').join('.') : '';
        return where ? `${where}: ${d.msg}` : d.msg;
      })
      .join('; ');
  }
  return JSON.stringify(detail);
}

export const api = {
  get: (path, params) => request('GET', path, { params }),
  getText: (path, params) => request('GET', path, { params, raw: true }),
  post: (path, body, params) => request('POST', path, { body, params }),
  put: (path, body) => request('PUT', path, { body }),
  patch: (path, body, params) => request('PATCH', path, { body, params }),
  del: (path) => request('DELETE', path),
};

// --- polling -------------------------------------------------------------

export async function pollJob(jobId, { onTick, intervalMs = 1500, timeoutMs = 600000 } = {}) {
  const started = Date.now();
  for (;;) {
    const job = await api.get(`/jobs/${jobId}`);
    if (onTick) onTick(job);
    if (['succeeded', 'failed', 'cancelled'].includes(job.state)) return job;
    if (Date.now() - started > timeoutMs) {
      throw new ApiError('Timed out waiting for the job to finish', 0, job);
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}
