/* Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. */
const state = { token: sessionStorage.getItem("token"), courseId: null, historyId: null };
const results = document.querySelector("#results");
const nonce = () => crypto.getRandomValues(new Uint32Array(4)).join("-") + crypto.randomUUID();
const authHeaders = () => ({Authorization:`Bearer ${state.token}`});
const apiBase = () => (window.HCP_CLIENT_CONFIG && window.HCP_CLIENT_CONFIG.apiBase) || "";
const apiUrl = path => `${apiBase()}${path}`;
let recorder = null;
let recordedChunks = [];

document.querySelector("#login-form").addEventListener("submit", async event => {
  event.preventDefault();
  const email=document.querySelector("#login-email").value;
  const password=document.querySelector("#login-password").value;
  const totp=document.querySelector("#login-totp").value.trim();
  if(totp){
    const check=await fetch(apiUrl("/api/v1/auth/check_totp"),{method:"POST",headers:{Authorization:`Basic ${btoa(`${email}:${password}`)}`,"X-TOTP-Code":totp}});
    const checkData=await check.json().catch(()=>({}));
    if(!check.ok||!checkData.valid){document.querySelector("#login-status").textContent=checkData.detail||"TOTP check failed";return;}
  }
  const response=await fetch(apiUrl("/api/v1/auth/token"),{method:"POST",headers:{Authorization:`Basic ${btoa(`${email}:${password}`)}`,...(totp?{"X-TOTP-Code":totp}:{})}});
  const data=await response.json().catch(()=>({}));
  if(!response.ok){document.querySelector("#login-status").textContent=data.detail||"Login failed";return;}
  state.token=data.access_token;
  sessionStorage.setItem("token",state.token);
  document.querySelector("#login-status").textContent=`Signed in as ${data.display_name||email}`;
  loadCourses(); loadConversations(); loadHistories();
});

document.querySelector("#send-login-totp").addEventListener("click",async()=>{
  const email=document.querySelector("#login-email").value;
  const password=document.querySelector("#login-password").value;
  if(!email||!password){document.querySelector("#login-status").textContent="Enter user id and password first.";return;}
  const response=await fetch(apiUrl("/api/v1/auth/send_totp"),{method:"POST",headers:{Authorization:`Basic ${btoa(`${email}:${password}`)}`}});
  const data=await response.json().catch(()=>({}));
  document.querySelector("#login-status").textContent=response.ok?`TOTP sent via ${data.channel}; valid for ${data.expires_in_seconds} seconds.`:(data.detail||"Could not send TOTP");
});

document.querySelector("#register-start-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const payload={user_id:document.querySelector("#register-user-id").value,password:document.querySelector("#register-password").value,contact_email:document.querySelector("#register-contact-email").value,mobile_number:document.querySelector("#register-mobile").value||null};
  const response=await fetch(apiUrl("/api/v1/auth/register/start"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json().catch(()=>({}));
  document.querySelector("#register-status").textContent=response.ok?`Codes sent. SMS required: ${data.sms_required?"yes":"no"}.`:(data.detail||"Registration start failed");
});

document.querySelector("#register-verify-form").addEventListener("submit",async event=>{
  event.preventDefault();
  const payload={user_id:document.querySelector("#register-user-id").value,password:document.querySelector("#register-password").value,email_code:document.querySelector("#register-email-code").value,mobile_code:document.querySelector("#register-mobile-code").value||null,totp_delivery_channel:document.querySelector("#register-totp-channel").value};
  const response=await fetch(apiUrl("/api/v1/auth/register/verify"),{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json().catch(()=>({}));
  document.querySelector("#register-status").textContent=response.ok?"Activation email sent. Open the link within 30 minutes to activate your account.":(data.detail||"Registration verification failed");
});

document.querySelector("#logout-button").addEventListener("click",async()=>{
  if(state.token){
    await fetch(apiUrl("/api/v1/auth/logout"),{method:"POST",headers:authHeaders()}).catch(()=>null);
  }
  state.token=null;
  sessionStorage.removeItem("token");
  document.querySelector("#login-status").textContent="Logged out.";
  document.querySelector("#course-list").innerHTML='<div class="empty">Sign in to load courses.</div>';
  document.querySelector("#history-list").innerHTML='<div class="empty">Sign in to load histories.</div>';
  document.querySelector("#history-entries").innerHTML="";
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
  loadHistories();
});

async function loadHistories(){
  const target=document.querySelector("#history-list");
  if(!state.token){target.innerHTML='<div class="empty">Sign in to load histories.</div>';return;}
  const response=await fetch(apiUrl("/api/v1/research/histories"),{headers:authHeaders()});
  const items=await response.json().catch(()=>[]);
  if(!response.ok){target.innerHTML='<div class="result warning">Could not load research histories.</div>';return;}
  const active=items.find(item=>item.active)||items[0];
  if(active&&!state.historyId)state.historyId=active.id;
  target.innerHTML=items.map(item=>`<button class="history-item ${item.id===state.historyId?"active":""}" data-id="${item.id}" data-label="${escapeHtml(item.label)}" data-stored="${item.stored}">
    <strong>${escapeHtml(item.label)}</strong>
    <small>${item.stored?"stored":"active / working"} · ${item.entries} entries · ${new Date(item.updated_at).toLocaleString()}</small>
  </button>`).join("")||'<div class="empty">No history yet. Press New chat to create one.</div>';
  if(state.historyId)loadHistoryEntries(state.historyId);
}

async function loadHistoryEntries(id){
  const response=await fetch(apiUrl(`/api/v1/research/histories/${id}/entries`),{headers:authHeaders()});
  const entries=await response.json().catch(()=>[]);
  const target=document.querySelector("#history-entries");
  if(!response.ok){target.innerHTML='<div class="result warning">Could not load history entries.</div>';return;}
  target.innerHTML=entries.map(item=>`<article class="history-entry"><small>${escapeHtml(item.kind)} · ${new Date(item.created_at).toLocaleString()}</small><h2>${escapeHtml(item.label||item.input_text.slice(0,80))}</h2><p>${escapeHtml(item.input_text)}</p>${item.refined_text&&item.refined_text!==item.input_text?`<p><em>Refined:</em> ${escapeHtml(item.refined_text)}</p>`:""}<p>${escapeHtml(item.output_summary)}</p></article>`).join("")||'<div class="empty">No entries in this history yet.</div>';
}

document.querySelector("#history-list").addEventListener("click",async event=>{
  const item=event.target.closest(".history-item");
  if(!item)return;
  state.historyId=item.dataset.id;
  document.querySelector("#history-label").value=item.dataset.label;
  document.querySelector("#history-stored").checked=item.dataset.stored==="true";
  await fetch(apiUrl(`/api/v1/research/histories/${state.historyId}/activate`),{method:"POST",headers:{...authHeaders(),"X-Request-Nonce":nonce()}}).catch(()=>null);
  loadHistories();
});

document.querySelector("#history-new").addEventListener("click",async()=>{
  if(!state.token){document.querySelector("#history-list").innerHTML='<div class="result warning">Sign in first.</div>';return;}
  const response=await fetch(apiUrl("/api/v1/research/histories"),{method:"POST",headers:{...authHeaders(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify({label:"New chat"})});
  const data=await response.json().catch(()=>({}));
  if(response.ok){state.historyId=data.id;document.querySelector("#history-label").value=data.label;}
  loadHistories();
});

document.querySelector("#history-refresh").addEventListener("click",loadHistories);

document.querySelector("#history-edit-form").addEventListener("submit",async event=>{
  event.preventDefault();
  if(!state.historyId)return;
  await fetch(apiUrl(`/api/v1/research/histories/${state.historyId}`),{method:"PATCH",headers:{...authHeaders(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify({label:document.querySelector("#history-label").value||"New chat",stored:document.querySelector("#history-stored").checked})});
  loadHistories();
});

document.querySelector("#history-delete").addEventListener("click",async()=>{
  if(!state.historyId||!confirm("Delete this research history?"))return;
  await fetch(apiUrl(`/api/v1/research/histories/${state.historyId}`),{method:"DELETE",headers:{...authHeaders(),"X-Request-Nonce":nonce()}});
  state.historyId=null;
  document.querySelector("#history-label").value="";
  document.querySelector("#history-stored").checked=false;
  loadHistories();
});

function escapeHtml(value) { const node=document.createElement("span"); node.textContent=value || ""; return node.innerHTML; }
async function loadCourses(){
  if(!state.token)return;
  const response=await fetch("/api/v1/courses",{headers:authHeaders()});
  const courses=await response.json().catch(()=>[]);
  const target=document.querySelector("#course-list");
  if(!response.ok){target.innerHTML='<div class="result warning">Could not load courses.</div>';return;}
  target.innerHTML=courses.map(course=>`<button class="course" data-id="${course.id}">${escapeHtml(course.title)} · ${escapeHtml(course.code)}</button>`).join("")||'<div class="empty">No courses available.</div>';
}

document.querySelector("#course-list").addEventListener("click",event=>{
  const button=event.target.closest(".course");
  if(!button)return;
  document.querySelectorAll(".course").forEach(item=>item.classList.remove("active"));
  button.classList.add("active");
  state.courseId=button.dataset.id;
  document.querySelector(".hero .eyebrow").textContent=`${button.textContent} · EXAM PREPARATION`;
});

async function loadConversations(){
  if(!state.token)return;
  const response=await fetch("/api/v1/conversations",{headers:authHeaders()});
  if(!response.ok)return;
  const items=await response.json();
  document.querySelector("#conversation-select").innerHTML='<option value="">Select a chat room</option>'+items.map(item=>`<option value="${item.id}">${escapeHtml(item.title)}${item.topic?` · ${escapeHtml(item.topic)}`:""}</option>`).join("");
  document.querySelector("#chatroom-list").innerHTML=items.map(item=>`<button class="chatroom" data-id="${item.id}">${escapeHtml(item.title)}</button>`).join("")||'<div class="empty">No private or group chats.</div>';
}

async function loadMessages(){
  const id=document.querySelector("#conversation-select").value;
  if(!id||!state.token)return;
  const response=await fetch(`/api/v1/conversations/${id}/messages`,{headers:authHeaders()});
  if(!response.ok)return;
  const messages=await response.json();
  document.querySelector("#messages").innerHTML=messages.map(item=>`<article class="bubble ${item.sender_name==="Chatbot"?"bot":"user"}"><small>${escapeHtml(item.sender_name)}</small><p>${escapeHtml(item.body)}</p>${renderAttachments(item.attachments||[])}${item.shared_type?`<em>Shared ${escapeHtml(item.shared_type)}: ${escapeHtml(item.shared_id)}</em>`:""}</article>`).join("")||'<div class="empty">No messages yet.</div>';
}

function renderAttachments(items){
  return items.length?`<ul class="attachments">${items.map(item=>`<li>${escapeHtml(item.kind||"file")}: ${escapeHtml(item.filename)}${item.transcript?`<br><em>${escapeHtml(item.transcript)}</em>`:""}</li>`).join("")}</ul>`:"";
}

document.querySelector("#conversation-select").addEventListener("change",loadMessages);
document.querySelector("#chatroom-list").addEventListener("click",event=>{
  const button=event.target.closest(".chatroom");
  if(!button)return;
  document.querySelector("#conversation-select").value=button.dataset.id;
  loadMessages();
});

document.querySelector("#chat-form").addEventListener("submit", async event => {
  event.preventDefault();
  const conversationId=document.querySelector("#conversation-select").value;
  if (!state.token || !conversationId) {
    document.querySelector("#messages").insertAdjacentHTML("beforeend", '<p><b>Chat</b><br>Select a chat room and sign in first.</p>');
    return;
  }
  const files=[...document.querySelector("#chat-files").files];
  let response;
  if(files.length){
    const form=new FormData();
    form.append("body",document.querySelector("#chat-message").value);
    if(document.querySelector("#share-type").value)form.append("shared_type",document.querySelector("#share-type").value);
    if(document.querySelector("#share-id").value)form.append("shared_id",document.querySelector("#share-id").value);
    files.forEach(file=>form.append("files",file));
    response=await fetch(`/api/v1/conversations/${conversationId}/messages/upload`,{method:"POST",headers:{...authHeaders(),"X-Request-Nonce":nonce()},body:form});
  }else{
    const payload={body:document.querySelector("#chat-message").value,shared_type:document.querySelector("#share-type").value||null,shared_id:document.querySelector("#share-id").value||null};
    response=await fetch(`/api/v1/conversations/${conversationId}/messages`,{method:"POST",headers:{...authHeaders(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify(payload)});
  }
  if(!response.ok){const data=await response.json().catch(()=>({}));alert(data.detail||"Message failed");return;}
  document.querySelector("#chat-message").value="";
  document.querySelector("#chat-files").value="";
  loadMessages();
});

async function loadExams(){
  if(!state.token){document.querySelector("#exam-status").textContent="Sign in first.";return;}
  const courseId=state.courseId;
  if(!courseId){document.querySelector("#exam-status").textContent="Select a course first.";return;}
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
    <button type="button" class="score-question">Submit question</button>
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
document.querySelector("#exam-question-fields").addEventListener("click",async event=>{
  const button=event.target.closest(".score-question");
  if(!button)return;
  updateAnswersJson();
  const exam=JSON.parse(document.querySelector("#exam-answers").value||"{}");
  const card=button.closest(".question-card");
  const questionId=card.dataset.questionId;
  const examinationId=document.querySelector("#exam-id").value;
  const response=await fetch(`/api/v1/examinations/${examinationId}/questions/${questionId}/score-draft`,{method:"POST",headers:{...authHeaders(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify({answer:exam[questionId]})});
  const data=await response.json().catch(()=>({}));
  const target=document.querySelector("#score-results");
  target.insertAdjacentHTML("afterbegin",response.ok?`<article class="result"><small>${questionId}</small><h2>${data.score} / ${data.max_score}</h2><p>${escapeHtml(data.feedback||JSON.stringify(data.signals||{}))}</p></article>`:`<article class="result warning">${escapeHtml(data.detail||"Scoring failed")}</article>`);
  if(response.ok)loadHistories();
});

document.querySelector("#chat-plus").addEventListener("click",()=>document.querySelector("#chat-files").click());
document.querySelector("#chat-files").addEventListener("change",event=>{
  const files=[...event.target.files].map(file=>file.name).join(", ");
  if(files)document.querySelector("#chat-message").value+=` [attached: ${files}]`;
});
document.querySelector("#chat-mic").addEventListener("click",async()=>{
  const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SpeechRecognition){
    const blob=await recordOnePhrase();
    if(!blob)return;
    const form=new FormData();
    form.append("file",new File([blob],"dictation.webm",{type:blob.type||"audio/webm"}));
    const response=await fetch("/api/v1/audio/transcribe",{method:"POST",headers:authHeaders(),body:form});
    const data=await response.json().catch(()=>({}));
    document.querySelector("#chat-message").value+=` ${response.ok?data.transcript:(data.detail||"")}`;
    return;
  }
  const recognition=new SpeechRecognition();
  recognition.lang=navigator.language||"en-US";
  recognition.onresult=event=>{document.querySelector("#chat-message").value+=` ${event.results[0][0].transcript}`;};
  recognition.start();
});

document.querySelector("#chat-audio-send").addEventListener("click",async()=>{
  const conversationId=document.querySelector("#conversation-select").value;
  if(!state.token||!conversationId){alert("Select a chat room and sign in first.");return;}
  const blob=await recordOnePhrase();
  if(!blob)return;
  const form=new FormData();
  form.append("body",document.querySelector("#chat-message").value||"Audio message");
  form.append("files",new File([blob],"spoken-message.webm",{type:blob.type||"audio/webm"}));
  const response=await fetch(`/api/v1/conversations/${conversationId}/messages/upload`,{method:"POST",headers:{...authHeaders(),"X-Request-Nonce":nonce()},body:form});
  if(!response.ok){const data=await response.json().catch(()=>({}));alert(data.detail||"Audio send failed");return;}
  loadMessages();
});

async function recordOnePhrase(){
  if(!navigator.mediaDevices||!window.MediaRecorder){alert("Audio recording is not available in this browser.");return null;}
  if(recorder&&recorder.state==="recording"){recorder.stop();return null;}
  const stream=await navigator.mediaDevices.getUserMedia({audio:true});
  recordedChunks=[];
  recorder=new MediaRecorder(stream);
  const done=new Promise(resolve=>{
    recorder.ondataavailable=event=>{if(event.data.size)recordedChunks.push(event.data);};
    recorder.onstop=()=>{stream.getTracks().forEach(track=>track.stop());resolve(new Blob(recordedChunks,{type:"audio/webm"}));};
  });
  recorder.start();
  alert("Recording started. Press OK, then speak. Recording stops automatically after 5 seconds.");
  setTimeout(()=>{if(recorder.state==="recording")recorder.stop();},5000);
  return done;
}

document.querySelector("#chat-emoji").addEventListener("click",()=>{document.querySelector("#emoji-picker").hidden=!document.querySelector("#emoji-picker").hidden;});
document.querySelector("#emoji-picker").addEventListener("click",event=>{
  const button=event.target.closest("button");
  if(!button)return;
  document.querySelector("#chat-message").value+=button.textContent;
  document.querySelector("#emoji-picker").hidden=true;
});

document.querySelector("#totp-setup").addEventListener("click",async()=>{
  if(!state.token){document.querySelector("#totp-status").textContent="Sign in first.";return;}
  const response=await fetch(apiUrl("/api/v1/users/me/totp/setup"),{method:"POST",headers:{...authHeaders(),"X-Request-Nonce":nonce()}});
  const data=await response.json().catch(()=>({}));
  document.querySelector("#totp-secret").textContent=response.ok?`Secret: ${data.secret}\nURI: ${data.otpauth_uri}`:"";
  document.querySelector("#totp-status").textContent=response.ok?"Add the secret to your authenticator app, then enter the next code.":(data.detail||"TOTP setup failed");
});

document.querySelector("#totp-verify-form").addEventListener("submit",async event=>{
  event.preventDefault();
  if(!state.token){document.querySelector("#totp-status").textContent="Sign in first.";return;}
  const response=await fetch(apiUrl("/api/v1/users/me/totp/verify"),{method:"POST",headers:{...authHeaders(),"Content-Type":"application/json","X-Request-Nonce":nonce()},body:JSON.stringify({code:document.querySelector("#totp-code").value})});
  const data=await response.json().catch(()=>({}));
  document.querySelector("#totp-status").textContent=response.ok?"TOTP is enabled for this account. Use a fresh TOTP code at the next login.":(data.detail||"TOTP verification failed");
});

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

loadCourses(); loadConversations(); loadHistories();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/static/sw.js");
