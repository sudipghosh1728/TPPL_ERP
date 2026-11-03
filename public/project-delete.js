/* Admin deletion requires a complete downloaded snapshot and explicit confirmation. */
function installProjectDeletion(){
 const previousJobs=manufacturingJobs;manufacturingJobs=function(){const body=previousJobs();if(selectedJob||!['Admin','Purchase'].includes(sessionUser.role))return body;const rows=state.deletion_mails||[];return body+panel('Project deletion emails','Complete project ZIPs are emailed automatically to ayush@tpplpune.com. Pending attachments remain private until sent. If email setup is missing, configure it before retrying.',table(['PROJECT','RECIPIENT','STATUS',''],rows.map(r=>[esc(r.project_title)+`<small>JOB-${String(r.job_id).padStart(4,'0')}</small>`,esc(r.recipient),badge(r.status),r.status==='Sent'?esc(r.sent_at||'Sent'):`<button class="secondary" data-retry-deletion-mail="${r.id}" data-mail-status="${esc(r.status)}">${r.status==='Queued'?'Retry email':'Check delivery & retry'}</button>`])));};
 const previousDetail=jobDetail;
 jobDetail=function(j){return previousDetail(j)+(['Admin','Purchase'].includes(sessionUser.role)?`<section class="panel project-delete-panel"><h3>Company hard-drive storage</h3><p>Keep this project searchable and move its documents, reports and archive files to your company file server. Project details, approvals and chat text stay in the ERP.</p><button class="secondary" data-drive-project="${j.id}">Manage file storage</button></section><section class="panel project-delete-panel"><h3>Delete project</h3><p>Download all project documents and reports before permanently removing this project.</p><button class="secondary" data-delete-project="${j.id}">Delete project…</button></section>`:'');};
 const priorJobs=manufacturingJobs;manufacturingJobs=function(){return priorJobs()+(!selectedJob&&['Admin','Purchase'].includes(sessionUser.role)?panel('Company hard-drive storage','Move existing documents to your company laptop and external drive while keeping projects, approvals and chat searchable. A configured file server is required.','<button class="secondary" data-drive-project="">Manage all stored files</button>'):'');};
}

async function companyDriveForm(jobId){
 if(!['Admin','Purchase'].includes(sessionUser.role))return;
 modal('Company hard-drive storage','<p id="drive-status" role="status">Checking your file server…</p><div id="drive-content"></div>');
 $('#modal').classList.add('wide');
 const status=$('#drive-status'),content=$('#drive-content');
 try{
  const r=await fetch('/api/file-storage/status'),data=await r.json();if(!r.ok)throw Error(data.error);
  if(!status.isConnected)return;status.textContent=data.message;
  content.innerHTML='<div id="drive-counts">'+table(['FILES','IN MONGODB','ON DRIVE'],data.collections.map(r=>[esc(({job_documents:'POs, drawings & certificates',report_workbooks:'Uploaded reports',dispatch_archives:'Dispatch & deletion ZIP parts',project_delete_parts:'Temporary download ZIP parts'})[r.collection]),r.in_mongo,r.on_drive]))+'</div>'+`<p class="form-intro">These totals cover the whole company. ${jobId?'This transfer covers only the selected project.':'This transfer covers all stored project and report files.'} Each file is read back and verified before replacing its database copy with a reference. Existing projects are kept.</p><p>Your file server must be online to open documents. Keep a separate backup of the drive and MongoDB metadata together.</p><button class="primary" id="drive-move" ${data.connected?'':'disabled'}>Move ${jobId?'project':'all existing'} files to drive</button><p id="drive-progress" role="status"></p><p>You can close this window to pause after the current file; reopening safely resumes.</p>`;
  content.querySelector('#drive-move').onclick=async function(){
   this.disabled=true;const progress=content.querySelector('#drive-progress');let moved=0,bytes=0;
   try{
    while(content.isConnected&&$('#modal').open){
     const response=await fetch('/api/file-storage/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(jobId?{job_id:jobId}:{})}),out=await response.json();if(!response.ok)throw Error(out.error);
     moved+=out.moved;bytes+=out.bytes;progress.textContent=`${moved} files verified · ${(bytes/1048576).toFixed(2)} MB moved · ${out.remaining} remaining`;
     if(!out.remaining){const refreshed=await fetch('/api/file-storage/status');if(refreshed.ok){const latest=await refreshed.json();content.querySelectorAll('#drive-counts tbody tr').forEach((row,i)=>{row.cells[1].textContent=latest.collections[i].in_mongo;row.cells[2].textContent=latest.collections[i].on_drive;});}status.textContent='Transfer complete. Projects remain available in the ERP.';break;}
    }
   }catch(e){progress.textContent=e.message+' Verified earlier transfers are retained. Retry to continue.';}finally{this.disabled=false;}
  };
 }catch(e){status.textContent=e.message;}
}
document.addEventListener('click',e=>{const button=e.target.closest('[data-drive-project]');if(button)companyDriveForm(button.dataset.driveProject?Number(button.dataset.driveProject):null);});
function deleteProjectForm(id){
 const j=workJob(+id);if(!j||!['Admin','Purchase'].includes(sessionUser.role))return;
 const ref=jobRef(j);let archive=null,downloadReady=false;
 modal('Download archive before deleting',`<form id="delete-project-form"><p><strong>${esc(ref)} · ${esc(j.title)}</strong></p><p>The ZIP contains all uploaded documents, approvals, inspection reports, chat, material issues and project history, including earlier dispatch archives.</p><p class="info-note">Deleting removes the project and its documents, requests, approvals, messages and notifications permanently. Shared customer, stock movement and accounting records remain; issued stock is not returned. A deletion receipt remains in company activity. The complete ZIP is automatically emailed to ayush@tpplpune.com after deletion. A private delivery copy is retained until the mail service accepts it; failed or unconfigured delivery stays visible in Project deletion emails.</p><button type="button" class="secondary" id="download-delete-archive">1. Download complete project ZIP</button><p id="delete-download-status" role="status"></p><fieldset id="delete-confirmation" disabled><legend>2. Confirm permanent deletion</legend><label><input type="checkbox" name="download_confirmed" required> I have saved and checked the downloaded ZIP.</label>${field('Type '+ref+' to confirm','confirmation')}</fieldset><div class="form-error" role="alert"></div><div class="modal-actions"><button type="button" class="secondary" data-close>Keep project</button><button class="primary" type="submit" id="confirm-delete-project" disabled>Delete project permanently</button></div></form>`);
 const form=$('#delete-project-form'),download=form.querySelector('#download-delete-archive'),status=form.querySelector('#delete-download-status'),confirm=form.querySelector('#delete-confirmation'),submit=form.querySelector('[type=submit]'),error=form.querySelector('.form-error');
 const ready=()=>submit.disabled=!downloadReady||!form.elements.download_confirmed.checked||form.elements.confirmation.value!==ref;
 form.addEventListener('input',ready);
 download.onclick=async()=>{
  download.disabled=true;downloadReady=false;archive=null;confirm.disabled=true;submit.disabled=true;error.textContent='';status.textContent='Preparing documents and reports…';
  try{
   const r=await fetch('/api/projects/delete-export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:j.id})}),result=await r.json();if(!r.ok)throw Error(result.error);archive=result;
   const buffers=[];let size=0;
   for(let part=0;part<archive.parts;part++){
    if(!form.isConnected||!$('#modal').open)return;
    status.textContent=`Downloading archive · ${part+1} of ${archive.parts}`;
    const response=await fetch(`/api/projects/delete-export/${encodeURIComponent(archive.token)}/${part}`);
    if(!response.ok)throw Error((await response.json()).error);
    const chunk=await response.arrayBuffer();buffers.push(chunk);size+=chunk.byteLength;
   }
   const blob=new Blob(buffers,{type:'application/zip'}),digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer()))].map(b=>b.toString(16).padStart(2,'0')).join('');
   if(size!==archive.bytes||digest!==archive.sha256)throw Error('Download verification failed. Download the ZIP again before deleting.');
   if(!form.isConnected||!$('#modal').open)return;
   const link=document.createElement('a'),url=URL.createObjectURL(blob);link.href=url;link.download=archive.filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
   downloadReady=true;confirm.disabled=false;form.elements.download_confirmed.checked=false;form.elements.confirmation.value='';status.textContent='ZIP download started and integrity verified. Confirm that you saved the file before deleting. This download is valid for one hour.';ready();
  }catch(e){error.textContent=e.message;status.textContent='Archive download did not finish. The project has not been deleted.';}finally{download.disabled=false;}
 };
 const requestId=crypto.randomUUID();
 form.onsubmit=async e=>{e.preventDefault();if(!downloadReady||submit.disabled)return;submit.disabled=true;download.disabled=true;error.textContent='';try{
  const result=await post('projects/delete',{job_id:j.id,export_token:archive.token,download_confirmed:form.elements.download_confirmed.checked,confirmation:form.elements.confirmation.value,request_id:requestId});selectedJob=null;$('#modal').close();page='jobs';render();toast(result.deletion_mail_status==='Sent'?'Project deleted. Archive email sent to ayush@tpplpune.com.':'Project deleted. Archive email is '+(result.deletion_mail_status||'queued')+' — check Project deletion emails.');
 }catch(err){error.textContent=err.message;ready();}finally{download.disabled=false;}};
}
document.addEventListener('click',e=>{const button=e.target.closest('[data-delete-project]');if(button)deleteProjectForm(+button.dataset.deleteProject);});

document.addEventListener('click',async e=>{const b=e.target.closest('[data-retry-deletion-mail]');if(!b)return;const checked=b.dataset.mailStatus!=='Queued';if(checked&&!confirm('Confirm you checked the mail provider and this archive email was NOT accepted. Retrying an accepted email can create a duplicate.'))return;b.disabled=true;try{const r=await post('projects/retry-deletion-mail',{id:Number(b.dataset.retryDeletionMail),delivery_checked:checked});toast(r.deletion_mail_status==='Sent'?'Archive email sent to ayush@tpplpune.com.':'Email '+(r.deletion_mail_status||'queued')+'. Check your mail service configuration and delivery status.');}catch(error){toast(error.message);}finally{b.disabled=false;}});
