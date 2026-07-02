/* Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. */
const state = { token: sessionStorage.getItem("token"), courseId: null };
const results = document.querySelector("#results");
const nonce = () => crypto.getRandomValues(new Uint32Array(4)).join("-") + crypto.randomUUID();
const authHeaders = () => ({Authorization:`Bearer ${state.token}`});

document.querySelector("#login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const email=document.querySelector("#login-email").value;
  const password=document.querySelector("#login-password").value;
  const totp=document.querySelector("#login-totp").value.trim();
  const response=await fetch("/api/v1/auth/token",{method:"POST",headers:{Authorization:`Basic ${btoa(`${email}:${password}`)}`,...(totp?{"X-TOTP-Code":totp}:{})}});
  const data=await response.json().catch(()=>({}));
  if(!response.ok){document.querySelector("#login-status").textContent=data.detail||"Login failed";return;}
  state.token=data.access_token;
  sessionStorage.setItem("token",state.token);
  document.querySelector("#login-status").textContent=`Signed in as ${data.display_name||email}`;
  loadConversations();
});

document.querySelector("#search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.token) {
    results.innerHTML = '<div class="result warning">Sign in through the API first. The production screen will provide the institution login.</div>';
    return;
  }
  const q = document.querySelector("#query").value;
  const response = await fetch(`/api/v1/search?q=${encodeURIComponent(q)}`, {headers:authHeaders()});
  if (!response.ok) { results.textContent = `Search failed (${response.status})`; return; }
  const data = await response.json();
  results.innerHTML = data.results.map(item => `<article class="result"><small>${item.kind.toUpperCase()}</small><h2>${escapeHtml(item.title)}</h2><p>${item.excerpt}</p>${item.url ? `<a href="${item.url}" target="_blank" rel="noopener">Continue on YouTube</a>` : ""}</article>`).join("") || `<div class="result warning">${escapeHtml(data.coverage_warning)}</div>`;
});

function escapeHtml(value) { const node=document.createElement("span"); node.textContent=value || ""; return node.innerHTML; }
async function loadConversations(){
  if(!state.token)return;
  const response=await fetch("/api/v1/conversations",{headers:authHeaders()});
  if(!response.ok)return;
  const items=await response.json();
  document.querySelector("#conversation-select").innerHTML='<option value="">Select a chat room</option>'+items.map(item=>`<option value="${item.id}">${escapeHtml(item.title)}${item.topic?` · ${escapeHtml(item.topic)}`:""}</option>`).join("");
}

async function loadMessages(){
  const id=document.querySelector("#conversation-select").value;
  if(!id||!state.token)return;
  const response=await fetch(`/api/v1/conversations/${id}/messages`,{headers:authHeaders()});
  if(!response.ok)return;
  const messages=await response.json();
  document.querySelector("#messages").innerHTML=messages.map(item=>`<article class="bubble ${item.sender_name==="Chatbot"?"bot":"user"}"><small>${escapeHtml(item.sender_name)}</small><p>${escapeHtml(item.body)}</p>${item.shared_type?`<em>Shared ${escapeHtml(item.shared_type)}: ${escapeHtml(item.shared_id)}</em>`:""}</article>`).join("")||'<div class="empty">No messages yet.</div>';
}

document.querySelector("#conversation-select").addEventListener("change",loadMessages);

document.querySelector("#chat-form").addEventListener("submit", async event => {
  event.preventDefault();
  const conversationId=document.querySelector("#conversation-select").value;
  if (!state.token || !conversationId) {
    document.querySelector("#messages").insertAdjacentHTML("beforeend", '<p><b>Chat</b><br>Select a chat room and sign in first.</p>');
    return;
  }
  const payload={body:document.querySelector("#chat-message").value,shared_type:document.querySelector("#share-type").value||null,shared_id:document.querySelector("#share-id").value||null};
  const response=await fetch(`/api/v1/conversations/${conversationId}/messages`,{method:"POST",headers:{...authHeaders(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify(payload)});
  if(!response.ok){const data=await response.json().catch(()=>({}));alert(data.detail||"Message failed");return;}
  document.querySelector("#chat-message").value="";
  loadMessages();
});

async function loadExams(){
  if(!state.token){document.querySelector("#exam-status").textContent="Sign in first.";return;}
  const courseId=document.querySelector("#student-course-id").value.trim();
  const response=await fetch(`/api/v1/courses/${courseId}/examinations`,{headers:authHeaders()});
  const items=await response.json().catch(()=>[]);
  if(!response.ok){document.querySelector("#exam-status").textContent=items.detail||"Could not load examinations";return;}
  document.querySelector("#exam-select").innerHTML='<option value="">Select an examination</option>'+items.map(item=>`<option value="${item.id}" data-kind="${item.kind.replace(/"/g,"")}">${escapeHtml(item.title)} · ${escapeHtml(item.kind)} · ${escapeHtml(item.state)}</option>`).join("");
  document.querySelector("#exam-select")._items=items;
}

function renderSelectedExam(){
  const select=document.querySelector("#exam-select");
  const item=(select._items||[]).find(exam=>exam.id===select.value);
  document.querySelector("#exam-id").value=item?.id||"";
  document.querySelector("#real-exam").checked=item?.kind==="real";
  const target=document.querySelector("#exam-question-fields");
  if(!item){target.innerHTML="";return;}
  target.innerHTML=item.questions.map((question,index)=>`<fieldset class="question-card" data-question-id="${question.id}" data-question-type="${question.question_type}">
    <legend>Question ${index+1} · ${question.max_score} points</legend>
    <p>${escapeHtml(question.prompt)}</p>
    ${question.choices?.length?question.choices.map(choice=>`<label><input name="q-${question.id}" value="${escapeHtml(choice)}" type="${question.question_type==="multiple_choice"?"checkbox":"radio"}"> ${escapeHtml(choice)}</label>`).join(""):`<textarea class="student-answer" rows="4" placeholder="Your answer"></textarea>`}
  </fieldset>`).join("");
  updateAnswersJson();
}

function updateAnswersJson(){
  const answers={};
  document.querySelectorAll("#exam-question-fields .question-card").forEach(card=>{
    const id=card.dataset.questionId;
    if(card.dataset.questionType==="free_text"){
      answers[id]=card.querySelector(".student-answer").value;
    }else{
      const checked=[...card.querySelectorAll("input:checked")].map(item=>item.value);
      answers[id]=card.dataset.questionType==="single_choice"?(checked[0]||""):checked;
    }
  });
  document.querySelector("#exam-answers").value=JSON.stringify(answers,null,2);
}

document.querySelector("#load-exams").addEventListener("click",loadExams);
document.querySelector("#exam-select").addEventListener("change",renderSelectedExam);
document.querySelector("#exam-question-fields").addEventListener("input",updateAnswersJson);
document.querySelector("#exam-question-fields").addEventListener("change",updateAnswersJson);

document.querySelector("#exam-form").addEventListener("submit", async event=>{
  event.preventDefault();
  if(!state.token){document.querySelector("#exam-status").textContent="Sign in first.";return;}
  const examinationId=document.querySelector("#exam-id").value.trim();
  const answers=JSON.parse(document.querySelector("#exam-answers").value||"{}");
  const files=[...document.querySelector("#exam-files").files];
  const uploadedFiles=[];
  for(const file of files){
    const bytes=new Uint8Array(await file.arrayBuffer());
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))).map(b=>b.toString(16).padStart(2,"0")).join("");
    uploadedFiles.push({name:file.name,type:file.type,size:file.size,sha256:hash});
  }
  const gathered={answers,uploaded_files:uploadedFiles,declared_real_exam:document.querySelector("#real-exam").checked};
  const content=JSON.stringify(gathered);
  const contentHash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(content)))).map(b=>b.toString(16).padStart(2,"0")).join("");
  let confirmationToken=null;
  if(document.querySelector("#real-exam").checked){
    if(!confirm("This is a real examination. Is this the right file and is the work ready?"))return;
    const prepare=await fetch("/api/v1/submissions/prepare",{method:"POST",headers:{...authHeaders(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify({examination_id:examinationId,content_sha256:contentHash})});
    const prepareData=await prepare.json();
    if(!prepare.ok){document.querySelector("#exam-status").textContent=prepareData.detail||"Preparation failed";return;}
    confirmationToken=prepareData.confirmation_token;
  }
  const submissionNonce=nonce();
  const response=await fetch("/api/v1/submissions",{method:"POST",headers:{...authHeaders(),"Content-Type":"application/json","X-Request-Nonce":submissionNonce},body:JSON.stringify({examination_id:examinationId,answers:gathered,content_base64:btoa(unescape(encodeURIComponent(content))),content_type:"application/json",signature_base64:document.querySelector("#exam-signature").value.trim(),signing_certificate_pem:document.querySelector("#exam-cert").value,signed_at:new Date().toISOString(),file_confirmed:document.querySelector("#real-exam").checked,ready_confirmed:document.querySelector("#real-exam").checked,confirmation_token:confirmationToken})});
  const data=await response.json().catch(()=>({}));
  document.querySelector("#exam-status").textContent=response.ok?`Submitted: ${data.id}`:(data.detail||"Submission failed");
});

loadConversations();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/static/sw.js");
