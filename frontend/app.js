/* Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. */
const state = { token: sessionStorage.getItem("token"), courseId: null };
const results = document.querySelector("#results");

document.querySelector("#search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.token) {
    results.innerHTML = '<div class="result warning">Sign in through the API first. The production screen will provide the institution login.</div>';
    return;
  }
  const q = document.querySelector("#query").value;
  const response = await fetch(`/api/v1/search?q=${encodeURIComponent(q)}`, {headers:{Authorization:`Bearer ${state.token}`}});
  if (!response.ok) { results.textContent = `Search failed (${response.status})`; return; }
  const data = await response.json();
  results.innerHTML = data.results.map(item => `<article class="result"><small>${item.kind.toUpperCase()}</small><h2>${escapeHtml(item.title)}</h2><p>${item.excerpt}</p>${item.url ? `<a href="${item.url}" target="_blank" rel="noopener">Continue on YouTube</a>` : ""}</article>`).join("") || `<div class="result warning">${escapeHtml(data.coverage_warning)}</div>`;
});

function escapeHtml(value) { const node=document.createElement("span"); node.textContent=value || ""; return node.innerHTML; }
document.querySelector("#chat-form").addEventListener("submit", event => {
  event.preventDefault();
  if (!state.token || !state.courseId) {
    document.querySelector("#messages").insertAdjacentHTML("beforeend", '<p><b>Chat</b><br>Select a course and sign in first.</p>');
  }
});
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/static/sw.js");
