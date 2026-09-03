let activeBusinessId: string | null =
  typeof window !== 'undefined' ? window.localStorage.getItem('nr_business_id') : null;

export function getActiveBusinessId(): string | null {
  return activeBusinessId;
}

export function setActiveBusinessId(id: string | null) {
  activeBusinessId = id;
  if (typeof window === 'undefined') return;
  if (id) window.localStorage.setItem('nr_business_id', id);
  else window.localStorage.removeItem('nr_business_id');
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (activeBusinessId && !headers.has('X-Business-Id')) {
    headers.set('X-Business-Id', activeBusinessId);
  }
  return fetch(input, {
    ...init,
    credentials: 'include',
    headers,
  });
}
