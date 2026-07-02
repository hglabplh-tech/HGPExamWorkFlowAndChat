/* Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. */
let token = sessionStorage.getItem("token");
const headers = () => ({Authorization:`Bearer ${token}`});
const nonce = () => crypto.getRandomValues(new Uint32Array(4)).join("-") + crypto.randomUUID();
const apiBase = () => (window.HCP_CLIENT_CONFIG && window.HCP_CLIENT_CONFIG.apiBase) || "";
const apiUrl = path => `${apiBase()}${path}`;

document.querySelector("#login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const email=document.querySelector("#login-email").value;
  const password=document.querySelector("#login-password").value;
  const totp=document.querySelector("#login-totp").value.trim();
  const auth=btoa(`${email}:${password}`);
  if(totp){
    const check=await fetch(apiUrl("/api/v1/auth/check_totp"),{method:"POST",headers:{Authorization:`Basic ${auth}`,"X-TOTP-Code":totp}});
    const checkData=await check.json().catch(()=>({}));
    if(!check.ok||!checkData.valid){document.querySelector("#login-status").textContent=checkData.detail||"TOTP check failed";return;}
  }
  const response=await fetch(apiUrl("/api/v1/auth/token"),{method:"POST",headers:{Authorization:`Basic ${auth}`,...(totp?{"X-TOTP-Code":totp}:{})}});
  const data=await response.json().catch(()=>({}));
  if(!response.ok){document.querySelector("#login-status").textContent=data.detail||"Login failed";return;}
  token=data.access_token;
  sessionStorage.setItem("token",token);
  document.querySelector("#login-status").textContent=`Signed in as ${data.display_name||email}`;
  refresh(); refreshPki(); refreshScoring(); refreshThesauri(); loadAdminCourses(); loadAdminChatrooms();
});

document.querySelector("#send-login-totp").addEventListener("click",async()=>{
  const email=document.querySelector("#login-email").value;
  const password=document.querySelector("#login-password").value;
  if(!email||!password){document.querySelector("#login-status").textContent="Enter email and password first.";return;}
  const auth=btoa(`${email}:${password}`);
  const response=await fetch(apiUrl("/api/v1/auth/send_totp"),{method:"POST",headers:{Authorization:`Basic ${auth}`}});
  const data=await response.json().catch(()=>({}));
  document.querySelector("#login-status").textContent=response.ok?`TOTP sent via ${data.channel}; valid for ${data.expires_in_seconds} seconds.`:(data.detail||"Could not send TOTP");
});

document.querySelector("#admin-logout").addEventListener("click",async()=>{
  if(token){
    await fetch(apiUrl("/api/v1/auth/logout"),{method:"POST",headers:headers()}).catch(()=>null);
  }
  token=null;
  sessionStorage.removeItem("token");
  document.querySelector("#login-status").textContent="Logged out.";
});

async function loadAdminCourses(){
  const target=document.querySelector("#admin-course-list");
  if(!token)return;
  const response=await fetch("/api/v1/courses",{headers:headers()});
  const items=await response.json().catch(()=>[]);
  target.innerHTML=response.ok?items.map(item=>`<button class="course" data-id="${item.id}">${escapeHtml(item.title)} · ${escapeHtml(item.code)}</button>`).join(""):'<div class="result warning">Unable to load courses.</div>';
}

async function loadAdminChatrooms(){
  const target=document.querySelector("#admin-chatroom-list");
  if(!token)return;
  const response=await fetch("/api/v1/conversations",{headers:headers()});
  const items=await response.json().catch(()=>[]);
  target.innerHTML=response.ok?items.map(item=>`<article class="result"><small>${escapeHtml(item.kind)} · ${escapeHtml(item.purpose)}</small><h2>${escapeHtml(item.title)}</h2><p>${escapeHtml(item.topic||"")}</p></article>`).join(""):'<div class="result warning">Unable to load chatrooms.</div>';
}

document.querySelector("#load-admin-courses").addEventListener("click",loadAdminCourses);
document.querySelector("#load-admin-chatrooms").addEventListener("click",loadAdminChatrooms);
document.querySelectorAll(".eye").forEach(button=>button.addEventListener("click",()=>{
  const input=document.querySelector(`#${button.dataset.target}`);
  input.type=input.type==="password"?"text":"password";
}));
document.querySelector("#cancel-user-create").addEventListener("click",()=>document.querySelector("#user-create-form").reset());
document.querySelector("#user-help").addEventListener("click",()=>document.querySelector("#user-help-dialog").showModal());
document.querySelector("#user-create-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const password=document.querySelector("#user-password").value;
  if(password!==document.querySelector("#user-password-confirm").value){document.querySelector("#user-create-status").textContent="Passwords do not match.";return;}
  const permissions=[...document.querySelectorAll(".rights-group input:checked")].map(item=>item.value);
  const payload={display_name:document.querySelector("#user-name").value,email:document.querySelector("#user-email").value,password,matriculation_number:document.querySelector("#user-matriculation").value||null,role:document.querySelector("#user-role").value,permissions};
  const response=await fetch("/api/v1/users",{method:"POST",headers:{...headers(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify(payload)});
  const data=await response.json().catch(()=>({}));
  document.querySelector("#user-create-status").textContent=response.ok?`Created user ${data.email}`:(data.detail||"User creation failed");
  if(response.ok)document.querySelector("#user-id").value=data.id;
});

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

async function refreshThesauri() {
  const target=document.querySelector("#thesaurus-list");
  if(!token)return;
  const response=await fetch("/api/v1/thesauri",{headers:headers()});
  if(!response.ok){target.textContent=`Unable to load thesauri (${response.status})`;return;}
  const items=await response.json();
  target.innerHTML=items.map(item=>`<article class="result"><small>${escapeHtml(item.language)} · ${escapeHtml(item.source_format)}</small><h2>${escapeHtml(item.name)}</h2><p>${item.active?"active":"inactive"} · ${item.entries.length} entries</p><code>${item.source_sha256}</code></article>`).join("")||'<div class="empty">No thesaurus uploaded.</div>';
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
  const payload={discipline:document.querySelector("#score-discipline").value,semantic_profile:document.querySelector("#score-profile").value,grading_weights:{jaccard:number("#w-jaccard"),keywords:number("#w-keywords"),semantic:number("#w-semantic"),trained_scoring:number("#w-trained"),fact_entailment:number("#w-facts"),contradiction:number("#w-contradiction"),length:number("#w-length")},search_weights:{full_text:number("#w-fulltext"),bm25:number("#w-bm25"),semantic:number("#w-search-semantic")}};
  const response=await fetch("/api/v1/scoring-profiles",{method:"POST",headers:{...headers(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify(payload)});
  const data=await response.json();
  document.querySelector("#scoring-status").textContent=response.ok?`Created ${data.discipline} profile version ${data.version}`:(data.detail||"Configuration failed");
  if(response.ok)refreshScoring();
});

document.querySelector("#totp-setup").addEventListener("click",async()=>{
  const response=await fetch("/api/v1/users/me/totp/setup",{method:"POST",headers:{...headers(),"X-Request-Nonce":nonce()}});
  const data=await response.json();
  document.querySelector("#totp-secret").textContent=response.ok?`Secret: ${data.secret}\nURI: ${data.otpauth_uri}`:(data.detail||"TOTP setup failed");
});

document.querySelector("#totp-verify-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const response=await fetch("/api/v1/users/me/totp/verify",{method:"POST",headers:{...headers(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify({code:document.querySelector("#totp-code").value})});
  const data=await response.json().catch(()=>({}));
  alert(response.ok?"TOTP is enabled":(data.detail||"TOTP verification failed"));
});

document.querySelector("#thesaurus-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const form=new FormData();
  form.append("file",document.querySelector("#thesaurus-file").files[0]);
  form.append("name",document.querySelector("#thesaurus-name").value);
  form.append("language",document.querySelector("#thesaurus-language").value);
  form.append("source_format",document.querySelector("#thesaurus-format").value);
  const response=await fetch("/api/v1/thesauri/upload",{method:"POST",headers:{...headers(),"X-Request-Nonce":nonce()},body:form});
  const data=await response.json().catch(()=>({}));
  document.querySelector("#thesaurus-status").textContent=response.ok?`Imported ${data.entries.length} entries`:(data.detail||"Import failed");
  if(response.ok)refreshThesauri();
});

function addExamQuestion(values={}) {
  const list=document.querySelector("#exam-question-list");
  const index=list.children.length+1;
  const node=document.createElement("fieldset");
  node.className="question-card";
  node.innerHTML=`<legend>Question ${index}</legend>
    <label>Question text<textarea class="exam-prompt" rows="3" required>${escapeHtml(values.prompt||"")}</textarea></label>
    <label>Default / reference answer<textarea class="exam-reference" rows="3" required>${escapeHtml(values.reference_answer||"")}</textarea></label>
    <label>Points<input class="exam-points" type="number" min="0.1" max="1000" step="0.1" value="${values.max_score||10}"></label>
    <label>Required keywords, comma separated<input class="exam-keywords" value="${escapeHtml((values.required_keywords||[]).join(", "))}"></label>
    <label>Expected facts, one per line<textarea class="exam-facts" rows="2">${escapeHtml((values.expected_facts||[]).join("\n"))}</textarea></label>
    <label>Type<select class="exam-question-type"><option value="free_text">Free text</option><option value="single_choice">Single choice</option><option value="multiple_choice">Multiple choice</option></select></label>
    <label>Choices, one per line<textarea class="exam-choices" rows="2">${escapeHtml((values.choices||[]).join("\n"))}</textarea></label>
    <label>Correct choices, one per line<textarea class="exam-correct" rows="2">${escapeHtml((values.correct_options||[]).join("\n"))}</textarea></label>
    <label><input class="exam-partial" type="checkbox" ${values.partial_credit?"checked":""}> Penalized partial credit</label>
    <button type="button" class="remove-question">Remove</button>`;
  node.querySelector(".exam-question-type").value=values.question_type||"free_text";
  list.appendChild(node);
}

function examPayload() {
  const lines=value=>value.split(/\n+/).map(item=>item.trim()).filter(Boolean);
  const csv=value=>value.split(",").map(item=>item.trim()).filter(Boolean);
  return {
    format:"hgp-exam-work-flow-and-chat/exam-json-v1",
    title:document.querySelector("#exam-title").value,
    instructions:document.querySelector("#exam-instructions").value,
    kind:document.querySelector("#exam-kind").value,
    group_mode:document.querySelector("#exam-group-mode").checked,
    questions:[...document.querySelectorAll(".question-card")].map(card=>({
      prompt:card.querySelector(".exam-prompt").value,
      reference_answer:card.querySelector(".exam-reference").value,
      required_keywords:csv(card.querySelector(".exam-keywords").value),
      expected_facts:lines(card.querySelector(".exam-facts").value),
      max_score:Number(card.querySelector(".exam-points").value),
      question_type:card.querySelector(".exam-question-type").value,
      choices:lines(card.querySelector(".exam-choices").value),
      correct_options:lines(card.querySelector(".exam-correct").value),
      partial_credit:card.querySelector(".exam-partial").checked,
    })),
  };
}

document.querySelector("#add-exam-question").addEventListener("click",()=>addExamQuestion());
document.querySelector("#exam-question-list").addEventListener("click",event=>{
  const button=event.target.closest(".remove-question");
  if(button)button.closest(".question-card").remove();
});
document.querySelector("#download-exam-json").addEventListener("click",()=>{
  const blob=new Blob([JSON.stringify(examPayload(),null,2)],{type:"application/json"});
  const link=document.createElement("a");
  link.href=URL.createObjectURL(blob);
  link.download=`${document.querySelector("#exam-title").value||"examination"}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
});
document.querySelector("#exam-builder-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const payload=examPayload();
  const courseId=document.querySelector("#exam-course-id").value.trim();
  const response=await fetch(`/api/v1/courses/${courseId}/examinations/from-json`,{method:"POST",headers:{...headers(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify(payload)});
  const data=await response.json().catch(()=>({}));
  document.querySelector("#exam-builder-status").textContent=response.ok?`Draft exam created: ${data.id} with ${data.questions} questions`:(data.detail||"Exam creation failed");
});

function escapeHtml(value) { const node=document.createElement("span"); node.textContent=value || ""; return node.innerHTML; }
addExamQuestion();
refresh();
refreshPki();
refreshScoring();
refreshThesauri();
loadAdminCourses();
loadAdminChatrooms();
