/* In-app reminders, recipient-specific urgency and attendance shortcuts. */
let reminderTimer=null,reminderUser=null,reminderQueue=[];
const reminderTone=role=>role==='Admin'?'red':role===sessionUser.role?'neutral':'yellow';
function reminderCard(r,flash=false){return `<article class="reminder-card tone-${r.tone}" role="status"><strong>${r.tone==='red'?'Admin reminder':r.tone==='yellow'?'Department reminder':'Reminder'} · ${esc(r.sender_name)}</strong><p>${esc(r.message)}</p><small>${esc(r.sender_role)} · ${esc(r.created_at.replace('T',' '))}</small>${!flash?`<div>${r.job_id?pbutton('Open project','open',`data-id="${r.job_id}"`):''}${!r.read_at?`<button class="secondary" data-reminder-read="${r.id}">Mark read</button>`:' · Read'}</div>`:''}</article>`;}
function receiveReminders(){
 if(!sessionUser)return;
 if(reminderUser!==sessionUser.id){clearTimeout(reminderTimer);reminderTimer=null;reminderQueue=[];document.querySelector('#reminder-highlight')?.remove();reminderUser=sessionUser.id;}
 const key='grey-reminder-shown-'+sessionUser.id;let seen=0;try{seen=Number(localStorage.getItem(key)||0)}catch{}
 const fresh=(state.reminders||[]).filter(r=>r.id>seen&&!r.read_at).sort((a,b)=>a.id-b.id);
 if(fresh.length){reminderQueue.push(...fresh);try{localStorage.setItem(key,String(Math.max(seen,...fresh.map(r=>r.id))))}catch{}}
 if(!reminderTimer)showNextReminder();
 const button=$('#project-alerts');if(button){const n=(state.reminders||[]).filter(r=>!r.read_at).length;button.textContent=button.textContent.replace(/ · \d+ reminders?$/,'')+(n?' · '+n+' reminder'+(n===1?'':'s'):'');}
}
function showNextReminder(){
 if(!reminderQueue.length||!sessionUser)return;
 const r=reminderQueue.shift(),uid=sessionUser.id,el=document.createElement('div');el.id='reminder-highlight';el.className='reminder-highlight tone-'+r.tone;el.innerHTML=reminderCard(r,true);document.body.append(el);
 reminderTimer=setTimeout(()=>{el.remove();reminderTimer=null;if(sessionUser?.id===uid)showNextReminder();else reminderQueue=[];},5000);
}
function urgentBanner(j){if(!j.urgent)return '';return `<div class="reminder-card urgent-project tone-${reminderTone(j.urgent_role)}"><strong>Urgent project · ${esc(j.title)}</strong><small>Marked urgent by ${esc(j.urgent_by)} · ${esc(j.urgent_role)}</small></div>`;}
function reminderForm(){
 workForm('Send reminder',select('Send to','destination',[...departments.map(d=>['department:'+d,d+' department']),...(state.reminder_directory||[]).filter(u=>u.id!==sessionUser.id).map(u=>['user:'+u.id,u.name+' · '+u.role])])+field('Reminder message','message')+select('Project (optional)','job_id',[['','No project'],...state.work_jobs.map(j=>[j.id,jobRef(j)+' · '+j.title])]),'reminders/send',async d=>{const [type,value]=d.destination.split(':');return {message:d.message,job_id:d.job_id||undefined,...(type==='user'?{recipient_id:Number(value)}:{department:value})}});
 $('#work-form [name=job_id]').required=false;
}
function installReminders(){
 const previousBind=bindSession;bindSession=function(){previousBind();$('.header-right').insertAdjacentHTML('beforeend','<a class="secondary small-button" id="attendance-shortcut" href="#attendance">Attendance</a><button class="secondary small-button" data-send-reminder>Send reminder</button>');receiveReminders();};
 const previousUpdates=updatesPage;updatesPage=function(){const incoming=(state.project_requests||[]).filter(r=>r.mode==='direct'&&(sessionUser.role==='Admin'||(sessionUser.role==='QC'&&r.status==='Pending')||r.target===sessionUser.role||r.created_by===sessionUser.id));return panel('Reminders','Red: Admin · Yellow: another department · Normal: your department.',`<div class="project-padding">${(state.reminders||[]).map(r=>reminderCard(r)).join('')||'<p>No reminders yet.</p>'}</div>`,`<button class="primary" data-send-reminder>Send reminder</button>`)+panel('Department work requests','Start open requests immediately. Submit completed work to QC from the project Requests tab.',table(['PROJECT','FROM / TO','WORK','STATUS',''],incoming.map(r=>[esc(workJob(r.job_id)?.title||jobRef({id:r.job_id})),esc(r.department+' → '+r.target),esc(r.notes),badge(r.status),pbutton('Open project','open',`data-id="${r.job_id}"`)])))+previousUpdates();};
 const previousSummary=projectSummary;projectSummary=function(j){return urgentBanner(j)+previousSummary(j)+(canRole('Design')&&j.stage!=='Completed'?`<button class="secondary" data-project-urgency="${j.id}">${j.urgent?'Remove urgent priority':'Mark project urgent'}</button>`:'');};
 const previousJobs=manufacturingJobs;manufacturingJobs=function(){return (!selectedJob?projectRows().filter(j=>j.urgent&&j.stage!=='Completed').map(urgentBanner).join(''):'')+previousJobs();};
}
document.addEventListener('click',async e=>{try{if(e.target.closest('[data-send-reminder]'))reminderForm();const read=e.target.closest('[data-reminder-read]');if(read)await post('reminders/read',{id:Number(read.dataset.reminderRead)});const priority=e.target.closest('[data-project-urgency]');if(priority){const j=workJob(Number(priority.dataset.projectUrgency));await post('projects/urgency',{...jobPayload(j,{}),urgent:!j.urgent});}}catch(err){toast(err.message)}});
