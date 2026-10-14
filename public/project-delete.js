/* Admin deletion requires a complete downloaded snapshot and explicit confirmation. */
function installProjectDeletion(){
 const previousDetail=jobDetail;
 jobDetail=function(j){return previousDetail(j)+(sessionUser.role==='Admin'?`<section class="panel project-delete-panel"><h3>Delete project</h3><p>Download all project documents and reports before permanently removing this project.</p><button class="secondary" data-delete-project="${j.id}">Delete project…</button></section>`:'');};
}
function deleteProjectForm(id){
 const j=workJob(+id);if(!j||sessionUser.role!=='Admin')return;
 const ref=jobRef(j);let archive=null,downloadReady=false;
 modal('Download archive before deleting',`<form id="delete-project-form"><p><strong>${esc(ref)} · ${esc(j.title)}</strong></p><p>The ZIP contains all uploaded documents, approvals, inspection reports, chat, material issues and project history, including earlier dispatch archives.</p><p class="info-note">Deleting removes the project and its documents, requests, approvals, messages and notifications permanently. Shared customer, stock movement and accounting records remain; issued stock is not returned. A deletion receipt remains in company activity.</p><button type="button" class="secondary" id="download-delete-archive">1. Download complete project ZIP</button><p id="delete-download-status" role="status"></p><fieldset id="delete-confirmation" disabled><legend>2. Confirm permanent deletion</legend><label><input type="checkbox" name="download_confirmed" required> I have saved and checked the downloaded ZIP.</label>${field('Type '+ref+' to confirm','confirmation')}</fieldset><div class="form-error" role="alert"></div><div class="modal-actions"><button type="button" class="secondary" data-close>Keep project</button><button class="primary" type="submit" id="confirm-delete-project" disabled>Delete project permanently</button></div></form>`);
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
  await post('projects/delete',{job_id:j.id,export_token:archive.token,download_confirmed:form.elements.download_confirmed.checked,confirmation:form.elements.confirmation.value,request_id:requestId});selectedJob=null;$('#modal').close();page='jobs';render();toast('Project and related project records deleted');
 }catch(err){error.textContent=err.message;ready();}finally{download.disabled=false;}};
}
document.addEventListener('click',e=>{const button=e.target.closest('[data-delete-project]');if(button)deleteProjectForm(+button.dataset.deleteProject);});
