'use strict';
const $=id=>document.getElementById(id);
const names={omlx:'oMLX',codex:'Codex',claude:'Claude'};
let selected=null,state=null,renderKey='',refreshBusy=false,connected=false;
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notice(text){$('notice').textContent=text;$('notice').hidden=!text;}
async function api(path,data){
 const response=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
 const body=await response.json();if(!response.ok)throw new Error(body.error||'The request failed');return body;
}
function clock(timestamp){return timestamp?new Date(timestamp*1000).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'';}
function retryLabel(provider){
 if(!provider.cooldown_seconds)return '';
 const minutes=Math.ceil(provider.cooldown_seconds/60);
 return `${provider.exact?'Resets':'Retry check'} ${clock(provider.retry_at)} · ${minutes} min`;
}
function renderProviders(){
 $('providers').innerHTML=['omlx','codex','claude'].map(name=>{
  const p=state.providers[name]||{state:'unknown'};
  const labels={ready:'Connected',limited:'Restricted',unknown:'Not checked',auth:'Sign-in needed',unavailable:'Unavailable',retry:'Recheck due'};
  const quota=(p.windows||[]).map(w=>`<div class="quota"><span>${w.minutes>=10080?'Weekly':w.minutes?Math.round(w.minutes/60)+'h':'Window'}</span><progress max="100" value="${Math.max(0,Math.min(100,w.remaining))}" aria-label="${esc(names[name])} allowance remaining"></progress><span>${Math.round(w.remaining)}% left</span></div>`).join('');
  return `<article class="provider"><div class="tag">${name==='omlx'?'LOCAL CONTROLLER':'SUBSCRIPTION'}</div><div class="provider-top"><h2>${names[name]}</h2><span class="pill ${esc(p.state)}">${esc(labels[p.state]||p.state)}</span></div>${quota}<p>${esc(retryLabel(p)||p.detail||'Checking connection…')}</p></article>`;
 }).join('');
 $('refresh').disabled=state.probing;$('refresh').textContent=state.probing?'Checking…':'↻ Check connections';
}
function renderTasks(){
 const nav=$('task-list');nav.replaceChildren();
 if(!state.runs.length){nav.innerHTML='<p class="muted">Your tasks will appear here.</p>';return;}
 state.runs.forEach(run=>{
  const button=document.createElement('button');button.className='task-item'+(run.id===selected?' selected':'');
  button.innerHTML=esc(run.title)+`<small>${esc(run.state)} · ${clock(run.created)}</small>`;
  button.onclick=()=>{selected=run.id;renderKey='';render();};nav.append(button);
 });
}
function render(){
 if(!state)return;
 renderProviders();renderTasks();
 const run=state.runs.find(r=>r.id===selected);
 const key=JSON.stringify(run||null);if(key===renderKey)return;renderKey=key;
 $('composer').hidden=!!run;$('empty-state').hidden=!!run;$('conversation').replaceChildren();$('review').replaceChildren();$('task-controls').replaceChildren();
 $('task-title').textContent=run?run.title:'What are we working on?';$('task-state').textContent=run?run.state:'Ready';$('task-state').className='pill '+(run?run.state:'');
 if(!run){$('events').innerHTML='<div class="waiting-event">Standing by for your first task.</div>';return;}
 run.messages.forEach(message=>{
  const item=document.createElement('article');item.className='message '+message.role;
  const label=document.createElement('div');label.className='message-label';label.textContent=message.role==='user'?'You':message.provider?names[message.provider]:message.role==='controller'?'oMLX · task plan':'Tool result';
  const content=document.createElement('pre');content.textContent=message.text;item.append(label,content);$('conversation').append(item);
 });
 const detail=document.createElement('p');detail.className='task-detail';detail.textContent=run.detail;$('task-controls').append(detail);
 if(run.state==='running'||run.state==='queued'){
  const pause=document.createElement('button');pause.className='quiet';pause.textContent='Pause after current step';pause.onclick=()=>action('/api/pause',{id:run.id});$('task-controls').append(pause);
 }
 if(run.state==='paused'&&!run.pending){
  const resume=document.createElement('button');resume.className='primary';resume.textContent='Resume task';resume.onclick=()=>action('/api/resume',{id:run.id});$('task-controls').append(resume);
 }
 if(run.pending){
  const pending=run.pending,card=document.createElement('section');card.className='review-card';
  card.innerHTML=`<h3>${pending.action==='write'?'Review file edit':'Review command'}</h3><p>${esc(pending.reason||'Proposed by '+names[pending.provider])}</p>${pending.action==='run'?'<p>Runs as your Mac user. The project folder is its starting directory, not a sandbox.</p>':''}`;
  const pre=document.createElement('pre');pre.textContent=pending.action==='write'?pending.diff:pending.command;card.append(pre);
  const buttons=document.createElement('div');buttons.className='actions';
  for(const [approved,text] of [[true,pending.action==='write'?'Apply this edit':'Run this command'],[false,'Reject']]){
   const button=document.createElement('button');button.textContent=text;button.className=approved?'primary':'quiet';
   button.onclick=async()=>{buttons.querySelectorAll('button').forEach(b=>b.disabled=true);await action('/api/review',{id:run.id,pending_id:pending.id,approved});};buttons.append(button);
  }
  card.append(buttons);$('review').append(card);
 }
 $('events').replaceChildren();
 run.events.slice(-14).reverse().forEach(event=>{
  const item=document.createElement('div');item.className='event '+event.kind;
  item.innerHTML=(event.provider?`<strong>${esc(names[event.provider])}</strong>`:'')+esc(event.text)+`<small>${clock(event.time)}</small>`;$('events').append(item);
 });
}
async function refresh(){
 if(refreshBusy)return;refreshBusy=true;
 try{state=await api('/api/state');connected=true;render();}
 catch(error){connected=false;notice(error.message);}finally{refreshBusy=false;}
}
async function action(path,data){try{await api(path,data);notice('');renderKey='';await refresh();}catch(error){notice(error.message);renderKey='';await refresh();}}
const detect_provider=text=>{
 const lower=text.toLowerCase();
 if(/\b(use|with|via|using)\s+(claude|anthropic)\b/.test(lower))return 'claude-only';
 if(/\b(use|with|via|using)\s+(codex|chatgpt|openai)\b/.test(lower))return 'codex-only';
 if(/\b(use|with|via|using)\s+(omlx|local|offline)\b/.test(lower))return 'omlx-only';
 return null;
};
const submit_task=async()=>{
 const text=$('prompt').value.trim();
 if(!text)return;
 $('prompt').disabled=true;
 try{
  const item=document.createElement('article');item.className='message user';
  const label=document.createElement('div');label.className='message-label';label.textContent='You';
  const content=document.createElement('pre');content.textContent=text;item.append(label,content);$('conversation').append(item);
  const detected_provider=detect_provider(text);
  const mode=detected_provider||$('route').value;
  const result=await api('/api/run',{prompt:text,workspace:'',mode:mode,tools:$('tools').checked});
  selected=result.id;$('prompt').value='';notice('');renderKey='';await refresh();
 }catch(error){notice(error.message);}finally{$('prompt').disabled=false;$('prompt').focus();}
};
$('new-task').onclick=()=>{selected=null;renderKey='';render();$('prompt').focus();};
$('refresh').onclick=()=>action('/api/probe',{});
$('composer').onsubmit=async event=>{event.preventDefault();};
$('prompt').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();submit_task();}};
(async()=>{
 const token=new URLSearchParams(location.hash.slice(1)).get('token');
 if(token){history.replaceState(null,'',location.pathname);try{await api('/api/unlock',{token});}catch(error){notice(error.message);return;}}
 await refresh();setInterval(refresh,2000);
})();
