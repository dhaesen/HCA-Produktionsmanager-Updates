'use strict';

/* HCA v0.13.5: Authentifizierung vor allen fachlichen API-Aufrufen. */
(() => {
  const nativeFetch = window.fetch.bind(window);
  const storageKey = 'hca-user-session-v1';
  let releaseGate;
  let gateReleased = false;
  const gate = new Promise(resolve => { releaseGate = resolve; });

  function token() {
    try { return String(localStorage.getItem(storageKey) || ''); }
    catch (_) { return ''; }
  }

  window.hcaAuthSession = {
    key: storageKey,
    token,
    set(value) {
      try {
        if (value) localStorage.setItem(storageKey, String(value));
        else localStorage.removeItem(storageKey);
      } catch (_) {}
    },
    release() {
      if (!gateReleased) {
        gateReleased = true;
        releaseGate();
      }
    }
  };

  window.fetch = async function hcaAuthenticatedFetch(input, init = {}) {
    const url = typeof input === 'string' ? input : String(input?.url || '');
    const isHcaApi = url.includes('/api/hca-shared/');
    const isAuthRoute = url.includes('/api/hca-shared/auth/');
    if (isHcaApi && !isAuthRoute && !gateReleased) await gate;

    if (!isHcaApi) return nativeFetch(input, init);
    const headers = new Headers(init.headers || (typeof input !== 'string' ? input?.headers : undefined) || {});
    const session = token();
    if (session) headers.set('X-HCA-Session', session);
    return nativeFetch(input, {...init, headers});
  };
})();
