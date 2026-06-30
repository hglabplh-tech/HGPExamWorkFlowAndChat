/* Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. */
const token = sessionStorage.getItem("token");
const headers = () => ({Authorization:`Bearer ${token}`});
const nonce = () => crypto.getRandomValues(new Uint32Array(4)).join("-") + crypto.randomUUID();

async function refresh() {
  const target = document.querySelector("#trust-lists");
  if (!token) { target.innerHTML='<div class="result warning">Administrator sign-in is required.</div>'; return; }
  const response = await fetch("/api/v1/trust-lists", {headers:headers()});
  if (!response.ok) { target.textContent=`Unable to load trusted lists (${response.status})`; return; }
  const items = await response.json();
  target.innerHTML = items.map(item => `<article class="result"><small>${item.framework} · TLv${item.tsl_version}</small><h2>${escapeHtml(item.name)}</h2><p>Signature: ${item.signature_status} · ${item.enabled ? "enabled" : "disabled"}</p><code>${item.sha256}</code><p><button class="trust-decision" data-id="${item.id}" data-enable="${!item.enabled}">${item.enabled?"Disable":"Enable"}</button></p></article>`).join("") || '<div class="empty">No customer trusted lists have been added.</div>';
}

async function refreshPki() {
  const target=document.querySelector("#pki-lists");
  if (!token) return;
  const response=await fetch("/api/v1/private-pki",{headers:headers()});
  if (!response.ok) { target.textContent=`Unable to load private PKIs (${response.status})`; return; }
  const items=await response.json();
  target.innerHTML=items.map(item=>`<article class="result"><small>PRIVATE PKI</small><h2>${escapeHtml(item.name)}</h2><p>${item.status} · ${item.enabled?"enabled":"disabled"}</p><code>${item.fingerprint}</code><p><button class="pki-decision" data-id="${item.id}" data-enable="${!item.enabled}">${item.enabled?"Disable":"Enable"}</button></p></article>`).join("") || '<div class="empty">No private PKI configured.</div>';
}

async function refreshScoring() {
  const target=document.querySelector("#scoring-list");
  if(!token)return;
  const response=await fetch("/api/v1/scoring-profiles",{headers:headers()});
  if(!response.ok){target.textContent=`Unable to load scoring profiles (${response.status})`;return;}
  const items=await response.json();
  target.innerHTML=items.map(item=>`<article class="result"><small>${item.discipline} · VERSION ${item.version}</small><h2>${item.active?"Active profile":"Historical profile"}</h2><p>Grading: ${escapeHtml(JSON.stringify(item.grading_weights))}</p><p>Search: ${escapeHtml(JSON.stringify(item.search_weights))}</p></article>`).join("")||'<div class="empty">No discipline profiles configured.</div>';
}

document.addEventListener("click",async event=>{
  const button=event.target.closest(".trust-decision,.pki-decision");
  if(!button)return;
  const privatePki=button.classList.contains("pki-decision");
  const response=await fetch(`/api/v1/${privatePki?"private-pki":"trust-lists"}/${button.dataset.id}/decision`,{method:"POST",headers:{...headers(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify({enable:button.dataset.enable==="true",reason:"Administrator trust configuration decision"})});
  if(!response.ok){const data=await response.json();alert(data.detail||"Decision failed");return;}
  privatePki?refreshPki():refresh();
});

document.querySelector("#trust-form").addEventListener("submit", async event => {
  event.preventDefault();
  const file = document.querySelector("#trust-file").files[0];
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary=""; bytes.forEach(value => binary += String.fromCharCode(value));
  const response = await fetch("/api/v1/trust-lists", {
    method:"POST",
    headers:{...headers(), "Content-Type":"application/json", "X-Request-Nonce":nonce()},
    body:JSON.stringify({name:document.querySelector("#trust-name").value, framework:document.querySelector("#trust-framework").value, xml_base64:btoa(binary), is_official:false})
  });
  const data = await response.json();
  document.querySelector("#trust-status").textContent = response.ok ? `Added; signature status: ${data.signature_status}` : (data.detail || "Upload failed");
  if (response.ok) refresh();
});

document.querySelector("#pki-form").addEventListener("submit", async event => {
  event.preventDefault();
  const root=await document.querySelector("#pki-root").files[0].text();
  const intermediateFile=document.querySelector("#pki-intermediate").files[0];
  const intermediates=intermediateFile?await intermediateFile.text():"";
  const response=await fetch("/api/v1/private-pki",{
    method:"POST",
    headers:{...headers(),"Content-Type":"application/json","X-Request-Nonce":nonce()},
    body:JSON.stringify({name:document.querySelector("#pki-name").value,root_certificate_pem:root,intermediate_bundle_pem:intermediates,ocsp_responder_url:document.querySelector("#pki-ocsp").value||null})
  });
  const data=await response.json();
  document.querySelector("#pki-status").textContent=response.ok?`Private root validated: ${data.root_fingerprint}`:(data.detail||"Upload failed");
  if(response.ok)refreshPki();
});

document.querySelector("#scoring-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const number=id=>Number(document.querySelector(id).value);
  const payload={discipline:document.querySelector("#score-discipline").value,semantic_profile:document.querySelector("#score-profile").value,grading_weights:{jaccard:number("#w-jaccard"),keywords:number("#w-keywords"),semantic:number("#w-semantic"),trained_scoring:number("#w-trained"),fact_entailment:number("#w-facts"),contradiction:number("#w-contradiction"),length:number("#w-length")},search_weights:{full_text:number("#w-fulltext"),semantic:number("#w-search-semantic")}};
  const response=await fetch("/api/v1/scoring-profiles",{method:"POST",headers:{...headers(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify(payload)});
  const data=await response.json();
  document.querySelector("#scoring-status").textContent=response.ok?`Created ${data.discipline} profile version ${data.version}`:(data.detail||"Configuration failed");
  if(response.ok)refreshScoring();
});

function escapeHtml(value) { const node=document.createElement("span"); node.textContent=value || ""; return node.innerHTML; }
refresh();
refreshPki();
refreshScoring();
