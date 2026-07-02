/* Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. */
window.HCP_CLIENT_CONFIG = window.HCP_CLIENT_CONFIG || {
  apiBase: ""
};

(() => {
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const base = window.HCP_CLIENT_CONFIG.apiBase || "";
    if (base && typeof input === "string" && input.startsWith("/api/")) {
      return originalFetch(`${base}${input}`, init);
    }
    if (base && input instanceof Request && new URL(input.url).pathname.startsWith("/api/")) {
      return originalFetch(new Request(`${base}${new URL(input.url).pathname}${new URL(input.url).search}`, input), init);
    }
    return originalFetch(input, init);
  };
})();
