'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let key = location.hash.slice(1) || sessionStorage.getItem('doctorado_key') || '';
if (location.hash) { sessionStorage.setItem('doctorado_key', key); history.replaceState(null, '', location.pathname); }
let state, items = [], plan = null, historyRows = [], toastTimer, currentView = 'batch';
let lifecycleController;
const selectedHistory=new Set();
async function keepSessionOpen() {
  lifecycleController=new AbortController();
  const controller=lifecycleController;
  try {
    const response=await fetch('/api/lifecycle',{headers:{'X-App-Key':key},signal:controller.signal});
    if(!response.ok)throw new Error('Sesión cerrada');
    const reader=response.body.getReader();
    while(!(await reader.read()).done){}
  } catch(error) {
    if(controller.signal.aborted)return;
  }
  if(!controller.signal.aborted)toast('La sesión se ha cerrado. Abre la app desde su acceso para continuar.',true);
}
window.addEventListener('pagehide',()=>lifecycleController?.abort());
window.addEventListener('pageshow',event=>{if(event.persisted)keepSessionOpen();});
const kindLabels = {experiment:'Experimentos',sample:'Muestras',characterization:'Caracterizaciones',result:'Resultados',other:'Otros registros',technique:'Técnicas'};
const prefixes = {experiment:'EXP',sample:'MUE',characterization:'CAR',result:'RES',other:'ID'};
const metaFields = {category:'category',owner_kind:'owner-kind',owner_code:'owner-code',date:'file-date',content:'content',technique:'technique',samples:'samples',replicate:'replicate',version:'version',experiments:'experiments',characterizations:'characterizations',note:'note'};

function toast(message, error=false) { clearTimeout(toastTimer); $('toast').textContent=message; $('toast').className=error?'error':''; $('toast').hidden=false; toastTimer=setTimeout(()=>$('toast').hidden=true,error?9500:4500); }
function busy(message) { $('busy-text').textContent=message; $('busy').hidden=false; }
function unbusy() { $('busy').hidden=true; }
async function api(path, body) {
  const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'X-App-Key':key,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json(); if(!response.ok)throw new Error(data.error||'No se pudo completar la operación.'); return data;
}
async function attempt(fn) { try{return await fn();}catch(error){unbusy();toast(error.message,true);return null;} }
function bytes(value) { if(value==null)return 'Carpeta'; if(value<1024)return value+' B'; const units=['KB','MB','GB','TB']; let v=value/1024,i=0;while(v>=1024&&i<3){v/=1024;i++;}return v.toLocaleString('es-ES',{maximumFractionDigits:1})+' '+units[i]; }
function today() {const d=new Date();return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');}
function getMeta() {const m={};for(const [field,id]of Object.entries(metaFields))m[field]=$(id).value;m.replicate=Number(m.replicate||0);m.version=m.category.startsWith('raw_')?0:Number(m.version||0);m.independent_raw=$('raw-confirm').checked;return m;}
function fillMeta(m) {for(const [field,id]of Object.entries(metaFields)){if(m[field]!==undefined)$(id).value=Array.isArray(m[field])?m[field].join(', '):m[field];}$('raw-confirm').checked=Boolean(m.independent_raw);updateCategory(false);updateOwner(false);}
function invalidate() {plan=null;if($('review-content'))$('review-content').innerHTML='Vuelve al paso anterior y actualiza la revisión.';}
function itemMeta(item) {if(!item.override)item.override=MetadataModel.fresh(today());return item.override;}
async function runAudit() {
  busy('Revisando estructura y nombres, sin modificar archivos…');const r=await api('/api/audit',{});unbusy();
  $('audit-results').innerHTML=`<p>${esc(r.note)}</p><p>${r.scanned} archivo(s) revisado(s) · ${r.findings.length} observación(es)${r.truncated?' · Revisión parcial: límite alcanzado':''}</p>`+r.findings.map(f=>`<div class="preview-item"><strong>${esc(f.kind)}</strong><p>${esc(f.message)}</p><code>${esc(f.path)}</code></div>`).join('');
}
function mode() {return document.querySelector('input[name=mode]:checked').value;}
function updateMode() {$('output-controls').hidden=mode()==='rename';$('rename-note').hidden=mode()!=='rename';invalidate();}
function updateCategory(changeOwner=true) {
  const category=$('category').value, raw=category.startsWith('raw_');
  $('destination-hint').textContent=state.categories[category]?.hint||'';
  $('version').disabled=raw;if(raw)$('version').value=0;
  $('raw-note').hidden=!raw;
  $('raw-note').textContent=category==='raw_original'?'Se conservarán el nombre original y la estructura completa. Selecciona la adquisición con sus archivos auxiliares.':'Se exportará una copia renombrada. El original permanece intacto. Utiliza esta opción solo para un archivo independiente.';
  $('raw-confirm-wrap').hidden=category!=='raw_copy';
  if(changeOwner&&!$('owner-code').value)$('owner-kind').value=state.categories[category].owner;
  updateOwner(false);invalidate();
}
function updateOwner() {
  const kind=$('owner-kind').value, value=$('owner-code').value.trim().toUpperCase();
  $('owner-code').placeholder=(prefixes[kind]||'ID')+'-…';
  $('owner-status').className='field-hint';
  $('owner-status').textContent=value?'Registro: '+value:'Identificador del registro, por ejemplo CAR-27 o EXP-12.';
}

async function addPaths(paths) {
  if(!paths.length)return;
  busy('Leyendo los archivos de entrada…');
  const data=await api('/api/inspect',{paths});
  for(const item of data.items){if(!items.some(x=>x.path.toLowerCase()===item.path.toLowerCase()))items.push({...item,selected:true,override:MetadataModel.fresh(today()),bulkSelected:false,recordDescription:''});}
  unbusy();invalidate();renderFiles();toast(data.items.length+' entrada(s) preparada(s).');
}
function renderFiles() {
  $('empty-files').hidden=items.length>0;$('files-area').hidden=!items.length;
  $('file-count').textContent=items.length+' entrada(s)';$('select-all').checked=items.length>0&&items.every(i=>i.selected);
  const selected=items.filter(i=>i.selected);$('selection-summary').textContent=selected.length?`${selected.length} entrada${selected.length===1?'':'s'} · ${bytes(selected.reduce((n,i)=>n+i.bytes,0))}`:'Ningún archivo seleccionado';$('preview').disabled=!selected.length;$('next-step').disabled=!selected.length;
  $('file-list').innerHTML=items.map(item=>{
    const m=item.override||getMeta(),ext=item.kind==='folder'?'PACK':item.name.includes('.')?item.name.split('.').pop().slice(0,5).toUpperCase():'FILE';
    return `<div class="file-row"><input type="checkbox" data-select="${item.key}" aria-label="Seleccionar ${esc(item.name)}" ${item.selected?'checked':''}><div class="file-icon">${esc(ext)}</div><div><div class="file-name">${esc(item.name)}</div><div class="file-path" title="${esc(item.path)}">${esc(item.path)}</div><div class="file-meta">${bytes(item.bytes)}${item.kind==='folder'?' · '+item.files+' archivos':''}${m.owner_code?' · '+esc(m.owner_code):''}</div></div><button class="row-action" data-remove="${item.key}" aria-label="Quitar ${esc(item.name)}" title="Quitar del lote">×</button></div>`;
  }).join('');
  const selectedItems=items.filter(i=>i.selected);
  renderMetadataEditors();if(!quickMode)renderDestinations();
  document.querySelectorAll('[data-select]').forEach(el=>el.addEventListener('change',()=>{items.find(i=>i.key===el.dataset.select).selected=el.checked;invalidate();renderFiles();}));
  document.querySelectorAll('[data-remove]').forEach(el=>el.addEventListener('click',()=>{items=items.filter(i=>i.key!==el.dataset.remove);invalidate();renderFiles();}));
}
function openModal(html) {$('modal-content').innerHTML=html;$('modal').showModal();document.querySelectorAll('[data-close-modal]').forEach(el=>el.addEventListener('click',()=>$('modal').close()));}
function modalHeader(title,subtitle='') {return `<div class="modal-header"><div><h2>${esc(title)}</h2><p>${esc(subtitle)}</p></div><button class="modal-close" data-close-modal aria-label="Cerrar diálogo">×</button></div>`;}
async function pickFolder(initial) {
  let folder=initial||state.doctorado;
  let data;try{data=await api('/api/browse',{path:folder});}catch(error){if(folder===state.doctorado)throw error;data=await api('/api/browse',{path:state.doctorado});}
  return new Promise(resolve=>{
    let finished=false;
    const finish=paths=>{if(finished)return;finished=true;resolve(paths);};
    const draw=()=>{
      const html=modalHeader('Seleccionar carpeta','Abre una subcarpeta o introduce su ruta completa.')+`<div class="modal-body"><label for="browse-path">Ruta de carpeta</label><div class="path-input"><input id="browse-path" value="${esc(data.path)}"><button id="browse-go" class="button">Abrir ruta</button></div><p id="browse-error" class="preview-error" role="alert"></p><button id="browse-up" class="button small" ${data.parent===data.path?'disabled':''}>↑ Subir un nivel</button><div class="directory-list">${data.folders.length?data.folders.map((r,n)=>`<button class="directory-button" data-directory="${n}">▸ ${esc(r.name)}</button>`).join(''):'<p class="muted">Esta carpeta no tiene subcarpetas.</p>'}</div><p class="field-hint">Carpeta elegida: <code>${esc(data.path)}</code></p></div><div class="modal-footer"><p></p><div><button class="button" data-close-modal>Cancelar</button><button id="browse-select" class="button primary">Usar esta carpeta</button></div></div>`;
      if(!$('modal').open)openModal(html);else{$('modal-content').innerHTML=html;document.querySelectorAll('[data-close-modal]').forEach(el=>el.onclick=()=>$('modal').close());}
      const navigate=async path=>{try{data=await api('/api/browse',{path});draw();}catch(e){$('browse-error').textContent=e.message;}};
      $('browse-go').onclick=()=>navigate($('browse-path').value);
      $('browse-path').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();navigate(e.target.value);}};
      $('browse-up').onclick=()=>navigate(data.parent);
      document.querySelectorAll('[data-directory]').forEach(el=>el.onclick=()=>navigate(data.folders[Number(el.dataset.directory)].path));
      $('browse-select').onclick=()=>{finish([data.path]);$('modal').close();};
    };
    draw();$('modal').addEventListener('close',()=>finish([]),{once:true});
  });
}
async function pick(kind,initial=$('input-path').value) {if(kind==='folder')return pickFolder(initial);busy('Elige los archivos en el selector de Windows…');const data=await api('/api/pick',{kind,initial});unbusy();return data.paths;}
async function explore(path) {
  busy('Leyendo la carpeta de entrada…');const data=await api('/api/list',{path});unbusy();
  openModal(modalHeader('Contenido de la carpeta',path)+`<div class="modal-body">${data.items.length?data.items.map((i,n)=>`<label class="folder-entry"><input type="checkbox" data-child="${n}"><span class="folder-kind">${i.kind==='folder'?'CARPETA ENTERA':'ARCHIVO'}</span><span>${esc(i.name)}<small class="muted"> · ${bytes(i.bytes)}</small></span></label>`).join(''):'<p class="empty-state">Esta carpeta está vacía.</p>'}</div><div class="modal-footer"><p>Una carpeta seleccionada incluye todo su contenido. Para elegir archivos sueltos de otra ubicación, usa Elegir archivos.</p><div><button class="button" data-close-modal>Cancelar</button><button id="add-children" class="button primary">Añadir seleccionados</button></div></div>`);
  $('add-children').onclick=()=>attempt(async()=>{const paths=[...document.querySelectorAll('[data-child]:checked')].map(el=>data.items[Number(el.dataset.child)].path);$('modal').close();await addPaths(paths);});
}
function rowInput(item,field,label,type='text',extra='') {
  const meta=itemMeta(item), value=meta[field]??'';
  return `<label>${esc(label)}<input data-meta="${field}" data-row="${item.key}" aria-label="${esc(label+' de '+item.name)}" type="${type}" value="${esc(Array.isArray(value)?value.join(', '):value)}" ${extra}></label>`;
}
function rowSelect(item,field,label,options) {
  return `<label>${esc(label)}<select data-meta="${field}" data-row="${item.key}" aria-label="${esc(label+' de '+item.name)}"><option value="">Elegir…</option>${options.map(([value,title])=>`<option value="${value}" ${itemMeta(item)[field]===value?'selected':''}>${esc(title)}</option>`).join('')}</select></label>`;
}
function clearSuggestedRoute(item) {if(item.routeMeta){item.output='';item.routeMeta=null;item.folderState=null;}}
function renderMetadataEditors() {
  if(quickMode){renderQuickEditors();return;}
  const expanded=new Set([...document.querySelectorAll('[data-options][open]')].map(el=>el.dataset.options));
  $('metadata-files').innerHTML=items.filter(i=>i.selected).map(item=>{
    const m=itemMeta(item), raw=m.category.startsWith('raw_');
    return `<article class="file-editor" data-editor="${item.key}"><div class="file-editor-heading"><div><h3>${esc(item.name)}</h3><small>${bytes(item.bytes)}</small></div><label class="bulk-target"><input type="checkbox" data-bulk-target="${item.key}" ${item.bulkSelected?'checked':''}> Edición conjunta</label></div><div class="file-editor-grid">${rowSelect(item,'category','Tipo de archivo',Object.entries(state.categories).map(([k,v])=>[k,v.label]))}${rowSelect(item,'owner_kind','Registro',[['characterization','Caracterización · CAR'],['experiment','Experimento · EXP'],['sample','Muestra · MUE'],['result','Resultado · RES'],['other','Otro tipo']])}${rowInput(item,'owner_code','ID','text','placeholder="CAR-27, EXP-12, MUE-8…"')}${rowInput(item,'date','Fecha','date')}${rowInput(item,'content','Contenido','text','placeholder="Vacío: conservar descripción del nombre original"')}</div><p data-row-error="${item.key}" class="preview-error" role="alert">${esc(item.metaError||'')}</p>${raw?`<p class="row-raw-note">${m.category==='raw_original'?'Se conservan los nombres del equipo y todos los archivos interiores.':'Solo para un RAW independiente; el original se conserva.'}</p>`:''}${m.category==='raw_copy'?`<label class="check-row"><input type="checkbox" data-meta="independent_raw" data-row="${item.key}" ${m.independent_raw?'checked':''}> Confirmo que este RAW no depende de archivos auxiliares.</label>`:''}<details data-options="${item.key}" ${expanded.has(item.key)?'open':''}><summary>Técnica, muestras, réplica y otros datos</summary><div class="file-editor-grid">${rowInput(item,'technique','Técnica')}${rowInput(item,'samples','Muestras')}${rowInput(item,'replicate','Réplica','number','min="0" max="999"')}${rowInput(item,'version','Versión','number',`min="0" max="999" ${raw?'disabled':''}`)}${rowInput(item,'experiments','Experimentos relacionados')}${rowInput(item,'characterizations','Caracterizaciones relacionadas')}${rowInput(item,'note','Observación')}</div></details>${m.quick_name?`<label>Nombre manual activo (vacía para usar los campos del formulario)<input data-meta="quick_name" data-row="${item.key}" value="${esc(m.quick_name)}"></label>`:''}</article>`;
  }).join('');
  document.querySelectorAll('[data-bulk-target]').forEach(el=>el.onchange=()=>{items.find(i=>i.key===el.dataset.bulkTarget).bulkSelected=el.checked;});
  document.querySelectorAll('[data-meta]').forEach(el=>{
    const update=()=>{
      const item=items.find(i=>i.key===el.dataset.row), field=el.dataset.meta;
      item.override=MetadataModel.change(itemMeta(item),field,el.type==='checkbox'?el.checked:el.value,state.categories[el.value]?.owner||'');
      item.metaError='';clearSuggestedRoute(item);invalidate();
      if(field==='owner_code'){
        el.value=item.override.owner_code;
        document.querySelector(`[data-row="${item.key}"][data-meta="owner_kind"]`).value=item.override.owner_kind;
      }
      const error=document.querySelector(`[data-row-error="${item.key}"]`);if(error)error.textContent='';
      if(field==='category'){renderMetadataEditors();document.querySelector(`[data-row="${item.key}"][data-meta="category"]`)?.focus();}
      renderDestinations();
    };
    if(el.tagName==='SELECT'||el.type==='checkbox')el.onchange=update;else el.oninput=update;
  });
}
function folderBase(item) {return item.folderParent||state.folder_roots[itemMeta(item).owner_code.split('-')[0]]||state.doctorado;}
function selectedFolder(item) {return item.folderOptions?.folders.find(f=>f.path.toLowerCase()===String(item.output||'').toLowerCase());}
function folderMessage(item) {
  const selected=selectedFolder(item);
  if(selected?.created_in_session)return selected.can_delete?'Creada en esta sesión; puedes eliminarla mientras esté vacía.':'Creada en esta sesión; contiene archivos y no se puede eliminar.';
  return item.output?'Carpeta seleccionada. Las carpetas anteriores no se pueden eliminar desde aquí.':'Elige una carpeta existente o pulsa + Añadir carpeta.';
}
function renderDestinations() {
  for(const item of items.filter(i=>i.selected)){
    const scope=itemMeta(item).owner_code.split('-')[0];
    if(item.folderScope&&item.folderScope!==scope){item.folderParent=null;item.folderOptions=null;item.output='';item.recordDescription='';item.folderOpen=false;}
    item.folderScope=scope;
  }
  $('destinations-list').innerHTML=items.filter(i=>i.selected).map(item=>`<article class="file-destination"><h3>${esc(item.name)} <span>${esc(itemMeta(item).owner_code||'Falta ID')}</span></h3><div class="folder-base"><span>Buscar en:</span><code>${esc(folderBase(item))}</code><button class="text-button" data-base-picker="${item.key}">Cambiar carpeta base</button></div><label>Carpeta de destino</label><div class="path-input"><input data-folder-query="${item.key}" aria-label="Carpeta de destino de ${esc(item.name)}" role="combobox" aria-autocomplete="list" aria-expanded="${item.folderOpen?'true':'false'}" aria-controls="folders-${item.key}" value="${esc(item.folderQuery??item.recordDescription??'')}" placeholder="Haz clic para elegir una carpeta"><button class="button primary-soft" data-add-folder="${item.key}">+ Añadir carpeta</button></div><div class="folder-menu" id="folders-${item.key}" ${item.folderOpen?'':'hidden'}></div><div data-new-folder-panel="${item.key}" class="new-folder-panel" ${item.creatingFolder?'':'hidden'}><label>Nombre de la nueva carpeta<input data-new-folder-name="${item.key}" aria-label="Nueva carpeta para ${esc(item.name)}" value="${esc(item.newFolderName||'')}" placeholder="Por ejemplo DRX"></label><div class="source-actions"><button class="button primary" data-confirm-folder="${item.key}">Crear carpeta</button><button class="button" data-cancel-folder="${item.key}">Cancelar</button></div><p class="field-hint">Se crea ahora en la carpeta base. Solo podrás eliminarla durante esta sesión y si está vacía.</p></div><p data-folder-status="${item.key}" class="field-hint" role="status">${esc(folderMessage(item))}</p><code class="chosen-folder">${esc(item.output||'Sin carpeta seleccionada')}</code><details class="related-details"><summary>Usar una ruta manual</summary><label>Ruta completa<div class="path-input"><input data-output="${item.key}" aria-label="Destino manual de ${esc(item.name)}" value="${esc(item.output||'')}" placeholder="Ruta completa de salida"><button class="button" data-output-picker="${item.key}">Elegir</button></div></label></details></article>`).join('');
  document.querySelectorAll('[data-folder-query]').forEach(el=>{
    const item=items.find(i=>i.key===el.dataset.folderQuery);
    el.onfocus=()=>{item.folderFilter='';attempt(()=>loadFolderChoices(item));};
    el.onclick=()=>{if(!item.folderOpen){item.folderFilter='';attempt(()=>loadFolderChoices(item));}};
    el.oninput=()=>{item.folderQuery=el.value;item.folderFilter=el.value;item.recordDescription='';item.output='';item.routeMeta=null;invalidate();drawFolderChoices(item);};
    el.onkeydown=e=>{if(e.key==='Escape'){item.folderOpen=false;drawFolderChoices(item);}if(e.key==='ArrowDown'){e.preventDefault();document.querySelector(`#folders-${item.key} [data-choose-folder]`)?.focus();}};
    if(item.folderOpen)drawFolderChoices(item);
  });
  document.querySelectorAll('[data-add-folder]').forEach(el=>el.onclick=()=>{
    const item=items.find(i=>i.key===el.dataset.addFolder);item.creatingFolder=true;item.newFolderName=item.output?'':item.folderQuery||'';renderDestinations();document.querySelector(`[data-new-folder-name="${item.key}"]`)?.focus();
  });
  document.querySelectorAll('[data-new-folder-name]').forEach(el=>{el.oninput=()=>{items.find(i=>i.key===el.dataset.newFolderName).newFolderName=el.value;};el.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();attempt(()=>createFolder(items.find(i=>i.key===el.dataset.newFolderName)));}};});
  document.querySelectorAll('[data-confirm-folder]').forEach(el=>el.onclick=()=>attempt(()=>createFolder(items.find(i=>i.key===el.dataset.confirmFolder))));
  document.querySelectorAll('[data-cancel-folder]').forEach(el=>el.onclick=()=>{items.find(i=>i.key===el.dataset.cancelFolder).creatingFolder=false;renderDestinations();});
  document.querySelectorAll('[data-base-picker]').forEach(el=>el.onclick=()=>attempt(async()=>{
    const item=items.find(i=>i.key===el.dataset.basePicker), paths=await pickFolder(folderBase(item));
    if(paths.length){const data=await api('/api/folders',{meta:itemMeta(item),parent:paths[0]});item.folderParent=data.parent;item.folderOptions=data;item.output='';item.folderQuery='';item.recordDescription='';item.folderOpen=true;invalidate();renderDestinations();}
  }));
  document.querySelectorAll('[data-output]').forEach(el=>el.oninput=()=>{const item=items.find(i=>i.key===el.dataset.output);item.output=el.value;item.routeMeta=null;item.folderQuery='';item.recordDescription='';invalidate();});
  document.querySelectorAll('[data-output-picker]').forEach(el=>el.onclick=()=>attempt(async()=>{const item=items.find(i=>i.key===el.dataset.outputPicker);const paths=await pickFolder(item.output||state.doctorado);if(paths.length){item.output=paths[0];item.routeMeta=null;item.folderQuery='';item.recordDescription='';invalidate();renderDestinations();}}));
}
async function loadFolderChoices(item) {
  if(item.folderLoading)return;item.folderLoading=true;
  for(const row of items){if(row!==item&&row.folderOpen){row.folderOpen=false;drawFolderChoices(row);}}
  const scope=item.folderScope, base=folderBase(item), request=(item.folderRequest||0)+1;item.folderRequest=request;
  try{
    const data=await api('/api/folders',{meta:itemMeta(item),parent:item.folderParent||undefined});
    if(item.folderScope!==scope||item.folderRequest!==request||folderBase(item)!==base)return;
    item.folderOptions=data;item.folderParent=data.parent;item.folderOpen=true;drawFolderChoices(item);
  } finally {item.folderLoading=false;}
}
function drawFolderChoices(item) {
  const panel=$('folders-'+item.key);if(!panel)return;
  panel.hidden=!item.folderOpen;
  const status=document.querySelector(`[data-folder-status="${item.key}"]`);if(status)status.textContent=folderMessage(item);
  const input=document.querySelector(`[data-folder-query="${item.key}"]`);input?.setAttribute('aria-expanded',item.folderOpen?'true':'false');
  if(!item.folderOpen)return;
  const search=String(item.folderFilter||'').toLocaleLowerCase();
  const folders=(item.folderOptions?.folders||[]).filter(f=>f.name.toLocaleLowerCase().includes(search));
  panel.innerHTML=folders.length?folders.map((f,n)=>`<div class="folder-choice"><button class="folder-choice-name" data-choose-folder="${n}">▸ ${esc(f.name)}</button>${f.created_in_session?`<span class="session-folder-tag">Nueva en esta sesión</span><button class="text-button folder-delete" data-remove-folder="${n}" ${f.can_delete?'':'disabled'} title="${f.can_delete?'Eliminar esta carpeta vacía':'Contiene archivos o subcarpetas; no se puede eliminar'}">Eliminar</button>`:''}</div>`).join(''):'<p class="field-hint">No hay carpetas coincidentes. Usa + Añadir carpeta para crear una.</p>';
  panel.querySelectorAll('[data-choose-folder]').forEach(el=>el.onclick=()=>{
    const selected=folders[Number(el.dataset.chooseFolder)];item.output=selected.path;item.recordDescription=selected.name;item.folderQuery=selected.name;item.folderFilter='';item.routeMeta=null;item.folderOpen=false;invalidate();renderDestinations();
  });
  panel.querySelectorAll('[data-remove-folder]').forEach(el=>el.onclick=()=>confirmFolderRemoval(item,folders[Number(el.dataset.removeFolder)]));
}
async function createFolder(item) {
  if(item.folderCreating)return;item.folderCreating=true;
  const button=document.querySelector(`[data-confirm-folder="${item.key}"]`);if(button)button.disabled=true;
  try{
    const data=await api('/api/folders/create',{meta:itemMeta(item),parent:item.folderParent||undefined,name:item.newFolderName});
    item.folderOptions=data;item.folderParent=data.parent;item.output=data.path;item.recordDescription=data.name;item.folderQuery=data.name;item.routeMeta=null;item.creatingFolder=false;item.folderOpen=true;invalidate();renderDestinations();toast(data.created?'Carpeta creada y seleccionada.':'La carpeta ya existía; se ha seleccionado.');
  } finally {item.folderCreating=false;if(button)button.disabled=false;}
}
function confirmFolderRemoval(item,folder) {
  openModal(modalHeader('Eliminar carpeta vacía','Solo se elimina esta carpeta creada desde la sesión actual.')+`<div class="modal-body"><code>${esc(folder.path)}</code><p>Si contiene archivos o ha cambiado, la app impedirá el borrado.</p><p id="folder-delete-error" class="preview-error" role="alert"></p></div><div class="modal-footer"><button class="button" data-close-modal>Cancelar</button><button id="confirm-folder-delete" class="button danger">Eliminar carpeta</button></div>`);
  $('confirm-folder-delete').onclick=async()=>{
    $('confirm-folder-delete').disabled=true;
    try{const result=await api('/api/folders/delete',{token:folder.token});
      const deleted=result.deleted.split(String.fromCharCode(92)).join('/').toLowerCase();
      for(const row of items){row.folderOptions=null;if(row.output){const path=row.output.split(String.fromCharCode(92)).join('/').toLowerCase();if(path===deleted||path.startsWith(deleted+'/')){row.output='';row.folderQuery='';row.recordDescription='';row.routeMeta=null;}}}
      $('modal').close();invalidate();renderDestinations();await loadFolderChoices(item);toast('Carpeta vacía eliminada.');
    }catch(e){$('folder-delete-error').textContent=e.message;$('confirm-folder-delete').disabled=false;}
  };
}
function applyBulk() {
  const targets=items.filter(i=>i.selected&&i.bulkSelected);
  const fields=[...document.querySelectorAll('[data-bulk-field]:checked')].map(el=>el.dataset.bulkField);
  if(!targets.length)throw new Error('Marca Edición conjunta en los archivos que quieras cambiar.');
  if(!fields.length)throw new Error('Marca los campos que quieres aplicar.');
  const values=getMeta();
  for(const item of targets){item.override=MetadataModel.apply(itemMeta(item),values,fields);item.metaError='';clearSuggestedRoute(item);}
  invalidate();renderFiles();$('bulk-status').textContent=`Se aplicaron ${fields.length} campo(s) a ${targets.length} archivo(s).`;
}
let wizardStep=1;
let quickMode=true, library={revision:0,favorites:[],templates:[]};
function setStep(step) {
  wizardStep=step;
  const titles=['Nuevo lote','Indica a qué corresponden','Elige los destinos','Revisa y confirma'];
  const number=quickMode&&step===4?3:step;
  $('wizard-title').textContent=(quickMode&&step===2?'Datos y destino':titles[step-1]);
  $('wizard-help').textContent=({1:'Selecciona los archivos que quieres organizar.',2:'Asigna un destino y completa los datos de cada archivo.',3:'Selecciona la carpeta de salida de cada archivo.',4:'Comprueba los nombres y destinos antes de exportar.'})[step];
  document.querySelector('.metadata-card .card-heading h2').textContent=quickMode?'Archivos del lote':'Datos del archivo';
  document.querySelector('.metadata-card .card-heading p').textContent=quickMode?'Usa una plantilla para rellenar los datos habituales o selecciona un destino favorito.':'Completa el registro, la fecha y la descripción de cada archivo.';
  document.querySelector('.bulk-panel').hidden=quickMode;
  document.querySelector('.name-example').hidden=quickMode;
  $('step-label').textContent='Paso '+number+' de '+(quickMode?3:4);
  document.querySelector('[data-progress="3"]').hidden=quickMode;
  document.querySelector('[data-progress="3"]').previousElementSibling.hidden=quickMode;
  document.querySelector('[data-progress="4"] b').textContent=quickMode?'3':'4';
  document.querySelectorAll('[data-step]').forEach(el=>el.hidden=Number(el.dataset.step)!==step);
  document.querySelectorAll('[data-progress]').forEach(el=>{const active=Number(el.dataset.progress)===step;el.classList.toggle('current',active);if(active)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');});
  $('previous-step').hidden=step===1;$('next-step').hidden=step===4;$('preview').hidden=step!==4;
  $('next-step').textContent=(step===3||(quickMode&&step===2))?'Siguiente: revisar →':'Siguiente →';
  renderFiles();window.scrollTo({top:0,behavior:'instant'});$('wizard-title').setAttribute('tabindex','-1');$('wizard-title').focus();
}
async function nextStep() {
  const selected=items.filter(i=>i.selected);if(!selected.length)throw new Error('Selecciona al menos un archivo.');
  if(wizardStep===2){
    if(quickMode){await preview();return;}
    const result=await api('/api/validate',{items:selected.map(i=>({key:i.key,path:i.path,meta:itemMeta(i)}))});
    for(const row of result.items)items.find(i=>i.key===row.key).metaError=row.error;
    if(!result.valid){renderMetadataEditors();document.querySelector('[data-row-error]:not(:empty)')?.scrollIntoView({block:'center',behavior:'smooth'});return;}
  }
  if(wizardStep===3){await preview();return;}
  setStep(wizardStep+1);
}
async function preview() {
  // Seleccionar una carpeta nunca crea otra de forma implícita.
  for(const item of items.filter(i=>i.selected)){
    if(!item.output&&String(item.folderQuery||'').trim()){
      const data=await api('/api/folders',{meta:itemMeta(item),parent:item.folderParent||undefined});
      const existing=data.folders.find(f=>f.name.toLowerCase()===item.folderQuery.trim().toLowerCase());
      if(!existing)throw new Error('Elige una carpeta existente o créala con + Añadir carpeta para '+item.name+'.');
      item.output=existing.path;item.recordDescription=existing.name;item.folderOptions=data;
    }
  }
  for(const item of items.filter(i=>i.selected)){if(item.routeMeta&&item.routeMeta!==JSON.stringify(itemMeta(item)))throw new Error('Han cambiado los datos. Vuelve a proponer destinos o edita la ruta del archivo.');}
  busy('Preparando los nombres y comprobando las rutas…');
  const defaults=getMeta();plan=await api('/api/preview',{mode:mode(),output:$('output-path').value,defaults,items:items.filter(i=>i.selected).map(i=>({key:i.key,path:i.path,output:i.output||'',meta:itemMeta(i)}))});unbusy();
  setStep(4);
  $('review-content').innerHTML=`<p>${plan.valid?'Revisión preparada. Comprueba cada salida antes de confirmar.':'Hay errores que debes corregir antes de continuar.'}</p>`+plan.items.map(i=>`<div class="preview-item ${i.error?'bad':''}"><div class="preview-names"><span>${esc(i.original_name||i.source)}</span><span class="arrow">→</span><strong>${esc(i.name||'Pendiente')}</strong><span class="status-tag ${i.error?'error':''}">${i.error?'Corregir':'Listo'}</span></div><p><strong>Destino:</strong><code>${esc(i.destination||'Falta elegir destino')}</code></p>${i.error?`<p class="preview-error">${esc(i.error)}</p>`:''}${(i.warnings||[]).filter(w=>!w.startsWith('Copia local:')).map(w=>`<p class="preview-warning">${esc(w)}</p>`).join('')}</div>`).join('')+`<div class="review-action"><p>${plan.mode==='copy'?'Se conservan los originales. Si utilizas Drive, comprueba que la sincronización haya terminado.':'Esta operación cambia los nombres originales en su carpeta.'}</p><button id="execute" class="button ${plan.mode==='copy'?'primary':'danger'}" ${plan.valid?'':'disabled'}>${plan.mode==='copy'?'Exportar lote':'Confirmar renombrado en origen'}</button></div>`;
  $('execute').onclick=()=>attempt(execute);
}
async function execute() {
  const activePlan=plan;if(!activePlan?.valid)return;$('execute').disabled=true;busy('Copiando archivos y registrando las operaciones…');
  const start=await api('/api/execute',{plan_id:activePlan.id});let job;
  do{await new Promise(resolve=>setTimeout(resolve,650));job=await api('/api/job/'+start.job);}while(job.state==='running');
  unbusy();if(job.state==='error')throw new Error(job.error);
  const result=job.result,errors=result.results.filter(r=>r.status==='error').length;plan=null;
  openModal(modalHeader(errors?'Lote terminado con incidencias':'Lote registrado',errors?'Revisa las entradas que no se han podido completar.':'Los archivos y sus nombres han quedado registrados.')+`<div class="modal-body"><div class="result-hero"><h3>${result.results.length-errors} de ${result.results.length} entrada(s) correctas</h3><p>${result.manifest?'El registro CSV está en tu carpeta de salida.':'Consulta los detalles de la operación en el historial.'}</p>${result.manifest?`<code>${esc(result.manifest)}</code>`:''}</div>${result.manifest_error?`<p class="preview-warning">${esc(result.manifest_error)}</p>`:''}${result.results.map(r=>`<div class="result-row"><div><strong>${esc(r.name)}</strong><code>${esc(r.destination)}</code>${r.error?`<p>${esc(r.error)}</p>`:''}</div><span class="status-tag ${r.status==='error'?'error':''}">${statusLabel(r.status)}</span></div>`).join('')}</div><div class="modal-footer"><p>Los archivos originales se han conservado.</p><div><button id="result-history" class="button">Ver historial</button><button id="result-back" class="button primary">${errors?"Corregir lote":"Preparar otro lote"}</button></div></div>`);
  $('result-back').onclick=()=>{$('modal').close();if(!errors)items=[];invalidate();setStep(errors?2:1);};
  $('result-history').onclick=()=>{$('modal').close();switchView('history');};
}
function statusLabel(value){return {completado:'Completado',ya_exportado:'Ya exportado',sin_cambio:'Sin cambios',error:'Error',revisar:'Revisar',en_curso:'En curso'}[value]||value;}
async function download(path,name) {
  const response=await fetch(path,{headers:{'X-App-Key':key}});if(!response.ok)throw new Error('No se pudo exportar el registro.');
  const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),15000);
}
async function renderHistory() {
  const data=await api('/api/history');historyRows=data.rows;selectedHistory.clear();filterHistory();$('history-location').textContent='Se muestran las últimas 5.000 operaciones.';
}
function filterHistory() {
  const term=$('history-search').value.toLocaleLowerCase();const rows=historyRows.filter(r=>JSON.stringify(r).toLocaleLowerCase().includes(term));
  $('history-table').innerHTML=rows.length?`<div class="table-wrap"><table><thead><tr><th><input id="history-select-visible" type="checkbox" aria-label="Seleccionar entradas visibles"></th><th>Fecha / operación</th><th>Original → salida</th><th>Registro / tipo</th><th>Estado</th></tr></thead><tbody>${rows.map(r=>`<tr><td><input type="checkbox" data-history-id="${r.id}" aria-label="Seleccionar operación de ${esc(r.original_name)}" ${selectedHistory.has(r.id)?'checked':''} ${r.status==='en_curso'?'disabled':''}></td><td>${esc(new Date(r.time).toLocaleString('es-ES'))}<br><small class="muted">${r.mode==='copy'?'Exportar copia':'Renombrar'} · ${bytes(r.bytes)}</small></td><td><div class="history-pair"><div>${esc(r.original_name)}</div><div class="arrow">↓</div><div><strong>${esc(r.name)}</strong></div><details><summary>Rutas de la operación</summary><code>Entrada: ${esc(r.source)}<br>Salida: ${esc(r.destination)}</code></details>${r.error?`<p class="preview-error">${esc(r.error)}</p>`:''}</div></td><td><strong>${esc(r.meta.owner_code)}</strong><br><small class="muted">${esc(state.categories[r.meta.category]?.label||r.meta.category)}</small></td><td><span class="status-tag ${esc(r.status)}">${esc(statusLabel(r.status))}</span></td></tr>`).join('')}</tbody></table></div>`:'<div class="empty-state">Todavía no hay operaciones que mostrar.</div>';

  const eligible=rows.filter(r=>r.status!=='en_curso');
  const all=$('history-select-visible');
  if(all){all.checked=eligible.length>0&&eligible.every(r=>selectedHistory.has(r.id));all.indeterminate=!all.checked&&eligible.some(r=>selectedHistory.has(r.id));all.disabled=!eligible.length;all.onchange=()=>{for(const r of eligible){if(all.checked)selectedHistory.add(r.id);else selectedHistory.delete(r.id);}filterHistory();};}
  document.querySelectorAll('[data-history-id]').forEach(el=>el.onchange=()=>{if(el.checked)selectedHistory.add(el.dataset.historyId);else selectedHistory.delete(el.dataset.historyId);filterHistory();});
  $('history-selected').textContent=selectedHistory.size?selectedHistory.size+' entrada(s) seleccionada(s)':'Ninguna entrada seleccionada';
  $('delete-history').disabled=!selectedHistory.size;
}
function confirmHistoryDeletion(){
  const ids=[...selectedHistory];if(!ids.length)return;
  openModal(modalHeader('Borrar entradas del historial',ids.length+' entrada(s) seleccionada(s)')+`<div class="modal-body"><p>Se eliminará el registro de estas operaciones de forma permanente. Los archivos originales y exportados se conservarán.</p><p id="history-delete-error" class="preview-error" role="alert"></p></div><div class="modal-footer"><button class="button" data-close-modal>Cancelar</button><button id="confirm-history-delete" class="button danger">Borrar ${ids.length} entrada(s)</button></div>`);
  $('confirm-history-delete').onclick=async()=>{const button=$('confirm-history-delete');button.disabled=true;try{const result=await api('/api/history/delete',{ids,confirmed:true});$('modal').close();await renderHistory();toast(result.deleted+' entrada(s) eliminada(s) del historial.');}catch(error){$('history-delete-error').textContent=error.message;button.disabled=false;}};
}
async function switchView(view) {
  currentView=view;$('section-name').textContent=({batch:'Nuevo lote',library:'Plantillas y favoritos',history:'Historial',audit:'Auditoría',guide:'Ayuda'})[view]||view;document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!=='view-'+view);document.querySelectorAll('[data-view]').forEach(el=>el.classList.toggle('active',el.dataset.view===view));
  if(view==='library')await attempt(loadLibrary);if(view==='history')await attempt(renderHistory);if(view==='guide')await attempt(async()=>{$('original-convention').textContent=(await api('/api/convention')).text;});window.scrollTo({top:0,behavior:'smooth'});
}
function bind() {
  $('delete-history').onclick=confirmHistoryDeletion;
  $('header-help').onclick=e=>{e.preventDefault();switchView('guide');};
  document.querySelectorAll('[data-view]').forEach(el=>el.onclick=()=>switchView(el.dataset.view));
  $('previous-step').onclick=()=>setStep(quickMode&&wizardStep===4?2:Math.max(1,wizardStep-1));$('next-step').onclick=()=>attempt(nextStep);
  $('metadata-form').onsubmit=e=>e.preventDefault();
  $('metadata-form').addEventListener('input',e=>{if(e.target.id==='owner-code')updateOwner(false);});
  $('apply-bulk').onclick=()=>attempt(applyBulk);
  const bulkLabels={category:'Tipo de archivo',owner_kind:'Registro',owner_code:'ID',date:'Fecha',content:'Contenido',technique:'Técnica',samples:'Muestras',replicate:'Réplica',version:'Versión',experiments:'Experimentos',characterizations:'Caracterizaciones',note:'Observación'};
  $('bulk-fields').innerHTML=Object.entries(bulkLabels).map(([field,label])=>`<label><input type="checkbox" data-bulk-field="${field}"> ${label}</label>`).join('');
  $('category').onchange=()=>updateCategory();$('owner-kind').onchange=()=>updateOwner();$('owner-code').onchange=()=>{const v=$('owner-code').value.trim().toUpperCase();$('owner-code').value=v;const k=Object.keys(prefixes).find(k=>v.startsWith(prefixes[k]+'-'));if(k)$('owner-kind').value=k;updateOwner();};
  document.querySelectorAll('input[name=mode]').forEach(el=>el.onchange=updateMode);$('output-path').oninput=()=>{invalidate();renderDestinations();};
  $('pick-files').onclick=()=>attempt(async()=>addPaths(await pick('files')));
  $('pick-input').onclick=()=>attempt(async()=>{const paths=await pick('folder');if(paths.length){$('input-path').value=paths[0];await explore(paths[0]);}});
  $('pick-package').onclick=()=>attempt(async()=>addPaths(await pick('folder')));
  $('pick-output').onclick=()=>attempt(async()=>{const paths=await pick('folder',$('output-path').value);if(paths.length){$('output-path').value=paths[0];invalidate();renderDestinations();}});
  $('add-path').onclick=()=>attempt(()=>addPaths($('input-path').value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean)));
  $('input-path').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();$('add-path').click();}});
  $('list-input').onclick=()=>attempt(()=>explore($('input-path').value));
  $('select-all').onchange=()=>{items.forEach(i=>i.selected=$('select-all').checked);invalidate();renderFiles();};$('clear-files').onclick=()=>{items=[];invalidate();renderFiles();};
  $('preview').onclick=()=>attempt(preview);$('refresh-history').onclick=()=>attempt(renderHistory);$('history-search').oninput=filterHistory;
  $('run-audit').onclick=()=>attempt(runAudit);
  $('open-inbox').onclick=()=>attempt(()=>explore($('inbox').value));
  $('shutdown').onclick=()=>{openModal(modalHeader('Cerrar aplicación','El historial y los archivos exportados se conservarán.')+'<div class="modal-body"><p>Se detendrá esta sesión. Para volver a abrirla, utiliza el acceso de la aplicación.</p></div><div class="modal-footer"><button class="button" data-close-modal>Seguir trabajando</button><button id="confirm-shutdown" class="button primary">Cerrar aplicación</button></div>');$('confirm-shutdown').onclick=()=>attempt(async()=>{await api('/api/shutdown',{});$('modal').close();toast('Aplicación cerrada. Ya puedes cerrar esta pestaña.');document.querySelectorAll('button').forEach(el=>el.disabled=true);});};
}
async function init() {
  try {
    state=await api('/api/state');keepSessionOpen();$('category').innerHTML=Object.entries(state.categories).map(([id,v])=>`<option value="${id}">${esc(v.label)}</option>`).join('');
    $('category').value='export';$('file-date').value=today();$('output-path').value='';
    await loadLibrary();updateOwner();updateCategory(false);updateMode();bind();bindQuick();setStep(1);
    try{const structure=await api('/api/structure');$('inbox').innerHTML=structure.inboxes.map(p=>`<option value="${esc(p)}">${esc(p)}</option>`).join('');$('open-inbox').disabled=!structure.inboxes.length;if(!$('input-path').value.trim())$('input-path').value=structure.inboxes[0]||'';$('drive-note').textContent='Si utilizas Drive, espera a que termine la sincronización antes de abrir el archivo en otro equipo.';}catch(e){$('open-inbox').disabled=true;toast(e.message,true);}
  }catch(error){toast(error.message,true);$('empty-files').innerHTML='<h3>No se pudo iniciar PhDex</h3><p>Abre la app desde <strong>Abrir PhDex.cmd</strong> y utiliza la nueva pestaña que se abra.</p>';}
}

async function loadLibrary(){library=await api('/api/library');renderLibrary();}
function renderLibrary(){
  for(const group of ['favorites','templates']){
    $(group+'-list').innerHTML=library[group].length?library[group].map(r=>`<div class="saved-item"><div><strong>${esc(r.label)}</strong><code>${esc(r.output)}</code>${r.meta?`<small>${esc(state.categories[r.meta.category]?.label||'')} · ${esc(r.meta.technique||'Sin técnica fija')}</small>`:''}</div><button class="button small" data-edit-saved="${r.id}" data-group="${group}">Editar</button><button class="text-button" data-delete-saved="${r.id}" data-group="${group}">Quitar</button></div>`).join(''):'<p class="muted">Todavía no hay elementos guardados.</p>';
  }
  document.querySelectorAll('[data-edit-saved]').forEach(b=>b.onclick=()=>editSaved(b.dataset.group,b.dataset.editSaved));
  document.querySelectorAll('[data-delete-saved]').forEach(b=>b.onclick=()=>{
    const group=b.dataset.group,row=library[group].find(r=>r.id===b.dataset.deleteSaved);
    openModal(modalHeader('Quitar '+row.label,'Solo se quita de tu biblioteca. La carpeta y sus archivos se conservan.')+`<div class="modal-footer"><button class="button" data-close-modal>Cancelar</button><button id="delete-saved-confirm" class="button danger">Quitar</button></div>`);
    $('delete-saved-confirm').onclick=()=>attempt(async()=>{library=await api('/api/library',{revision:library.revision,group,id:row.id,delete:true});$('modal').close();renderLibrary();renderMetadataEditors();});
  });
}
function savedOptions(group,selected){return library[group].map(r=>`<option value="${r.id}" ${r.id===selected?'selected':''}>${esc(r.label)}</option>`).join('');}
function renderQuickEditors(){
  const opened=new Set([...document.querySelectorAll('[data-quick-details][open]')].map(e=>e.dataset.quickDetails));
  $('metadata-files').innerHTML=items.filter(i=>i.selected).map(i=>{
    const m=itemMeta(i);if(!m.category){m.category='export';m.owner_kind=m.owner_kind||'characterization';}const raw=m.category.startsWith('raw_');
    return `<article class="file-editor"><h3>${esc(i.name)}</h3><div class="quick-selects"><label>Plantilla<select data-quick-template="${i.key}" aria-label="Plantilla de ${esc(i.name)}"><option value="">Elegir plantilla…</option>${savedOptions('templates',i.templateId)}</select></label><label>Destino favorito<select data-quick-favorite="${i.key}" aria-label="Favorito de ${esc(i.name)}"><option value="">Elegir favorito…</option>${savedOptions('favorites',i.favoriteId)}</select></label><button class="button" data-quick-folder="${i.key}">Otra carpeta</button></div><p class="field-hint">${esc(i.templateLabel?'Plantilla: '+i.templateLabel:'Tipo: Exportación del equipo. Puedes cambiarlo en Fecha y más opciones.')}</p><code class="chosen-folder">${esc(i.output||'Falta elegir destino')}</code><p class="field-hint">Fecha: ${esc(m.date)} · ${esc(state.categories[m.category]?.label||'')} ${m.quick_name?'· Nombre manual activo (sustituye los campos de arriba)':''}</p><div class="quick-fields">${rowInput(i,'owner_code','ID','text','placeholder="CAR-27, EXP-12, MUE-8…"')}${rowInput(i,'content','Descripción','text','placeholder="Ej. Difractograma"')}</div><p class="field-hint">ID: CAR-27, EXP-12 o MUE-8. Descripción vacía: se utiliza el nombre original.</p><details data-quick-details="${i.key}" ${opened.has(i.key)?'open':''}><summary>Fecha y más opciones</summary><div class="file-editor-grid">${rowInput(i,'date','Fecha','date')}${rowSelect(i,'category','Tipo de archivo',Object.entries(state.categories).map(([k,v])=>[k,v.label]))}${rowInput(i,'technique','Técnica')}${rowInput(i,'samples','Muestras')}${rowInput(i,'replicate','Réplica','number','min="0" max="999"')}${rowInput(i,'version','Versión','number',`min="0" max="999" ${raw?'disabled':''}`)}</div></details>${raw?`<p class="info-note">${m.category==='raw_original'?'Se conservarán todos los nombres originales.':'Solo para RAW independiente.'}</p>`:''}${m.category==='raw_copy'?`<label class="check-row"><input data-qmeta="independent_raw" data-row="${i.key}" type="checkbox" ${m.independent_raw?'checked':''}> Confirmo que es un RAW independiente.</label>`:''}${i.kind!=='folder'&&!raw?`<details><summary>Escribir directamente el nombre completo (opcional)</summary><label>Nombre sin extensión<input data-qmeta="quick_name" data-row="${i.key}" value="${esc(m.quick_name||'')}" placeholder="2026-10-21_CAR-27_Difractograma"></label><p class="field-hint">Sustituye ID, fecha y descripción al exportar. Debe seguir AAAA-MM-DD_ID_Descripción; se conserva la extensión original. Vacíalo para usar los campos de arriba.</p></details>`:''}</article>`;
  }).join('');
  document.querySelectorAll('#metadata-files [data-meta],#metadata-files [data-qmeta]').forEach(el=>{
    const update=()=>{const i=items.find(i=>i.key===el.dataset.row),field=el.dataset.meta||el.dataset.qmeta;
      i.override=MetadataModel.change(itemMeta(i),field,el.type==='checkbox'?el.checked:el.value,state.categories[el.value]?.owner||'');
      if(field==='category'){if(i.override.category.startsWith('raw_'))delete i.override.quick_name;renderQuickEditors();}
      invalidate();};
    if(el.tagName==='SELECT'||el.type==='checkbox')el.onchange=update;else el.oninput=update;
  });
  document.querySelectorAll('[data-quick-template]').forEach(el=>el.onchange=()=>{
    const t=library.templates.find(r=>r.id===el.value);if(!t)return;const i=items.find(i=>i.key===el.dataset.quickTemplate),m=itemMeta(i);
    // Una selección explícita aplica la plantilla completa, conservando solo ID y fecha del lote.
    i.override={...MetadataModel.fresh(m.date||today()),...t.meta,owner_code:m.owner_code,independent_raw:false};i.output=t.output;i.templateId=t.id;i.favoriteId=null;i.templateLabel=t.label;i.folderQuery='';i.routeMeta=null;invalidate();renderMetadataEditors();
  });
  document.querySelectorAll('[data-quick-favorite]').forEach(el=>el.onchange=()=>{const f=library.favorites.find(r=>r.id===el.value);if(!f)return;const i=items.find(i=>i.key===el.dataset.quickFavorite);i.output=f.output;i.favoriteId=f.id;i.routeMeta=null;i.folderQuery='';invalidate();renderMetadataEditors();});
  document.querySelectorAll('[data-quick-folder]').forEach(el=>el.onclick=()=>attempt(async()=>{const i=items.find(i=>i.key===el.dataset.quickFolder),paths=await pickFolder(i.output||state.doctorado);if(paths.length){i.output=paths[0];i.favoriteId=null;i.folderQuery='';i.routeMeta=null;invalidate();renderMetadataEditors();}}));
}
function bindQuick(){
  $('work-mode').onchange=()=>{quickMode=$('work-mode').value==='quick';if(quickMode){document.querySelector('input[name=mode][value=copy]').checked=true;updateMode();}invalidate();setStep(wizardStep===3&&quickMode?2:wizardStep);};
  $('new-favorite').onclick=()=>editSaved('favorites');$('new-template').onclick=()=>editSaved('templates');
}
function editSaved(group,id){
  const row=library[group].find(r=>r.id===id)||{},m=row.meta||{category:'export',owner_kind:'characterization'},template=group==='templates';
  const form=()=>({label:$('saved-label').value,output:$('saved-output').value,...(template?{meta:{category:$('saved-category').value,owner_kind:$('saved-kind').value,technique:$('saved-technique').value,content:$('saved-content').value,replicate:$('saved-replicate').value,version:$('saved-version').value}}:{})});
  const draft={...row};
  const draw=()=>{
    const v=draft.meta||m;
    openModal(modalHeader((id?'Editar ':'Crear ')+(template?'plantilla':'favorito'),template?'Define los datos que se repetirán al organizar estos archivos.':'Asigna un nombre a la carpeta para encontrarla al elegir un destino.')+`<form id="saved-form"><div class="modal-body"><label>Nombre<input id="saved-label" required maxlength="80" value="${esc(draft.label||'')}" placeholder="Ej. DRX — exportaciones"><small class="input-help">Nombre que aparecerá en el selector de plantillas o favoritos.</small></label><label>Carpeta de destino<div class="path-input"><input id="saved-output" required value="${esc(draft.output||'')}"><button type="button" id="saved-pick" class="button">Elegir</button></div></label>${template?`<div class="file-editor-grid"><label>Tipo de archivo<select id="saved-category">${Object.entries(state.categories).map(([k,c])=>`<option value="${k}" ${v.category===k?'selected':''}>${esc(c.label)}</option>`).join('')}</select></label><label>Registro<select id="saved-kind">${Object.entries(prefixes).map(([k,s])=>`<option value="${k}" ${v.owner_kind===k?'selected':''}>${({experiment:'Experimento · EXP',sample:'Muestra · MUE',characterization:'Caracterización · CAR',result:'Resultado · RES',other:'Otro registro'})[k]}</option>`).join('')}</select></label><label>Técnica<input id="saved-technique" value="${esc(v.technique||'')}" placeholder="Ej. DRX o FTIR"><small class="input-help">Se incluye en el nombre del archivo.</small></label><label>Descripción habitual (opcional)<input id="saved-content" value="${esc(v.content||'')}" placeholder="Ej. Difractograma"><small class="input-help">Déjala vacía para utilizar el nombre original.</small></label><label>Réplica<input id="saved-replicate" type="number" min="0" max="999" value="${v.replicate||0}"><small class="input-help">Otra adquisición. 0 omite el sufijo.</small></label><label>Versión<input id="saved-version" type="number" min="0" max="999" value="${v.version||0}"><small class="input-help">Otra edición del archivo. 0 omite el sufijo.</small></label></div><p class="field-hint">El ID y la fecha se completan en cada lote. Las opciones de esta plantilla se pueden ajustar para cada archivo.</p>`:''}<p id="saved-error" class="preview-error" role="alert"></p></div><div class="modal-footer"><button type="button" class="button" data-close-modal>Cancelar</button><button class="button primary">Guardar</button></div></form>`);
    $('saved-pick').onclick=()=>attempt(async()=>{Object.assign(draft,form());$('modal').close();const paths=await pickFolder(draft.output||state.doctorado);if(paths.length)draft.output=paths[0];draw();});
    $('saved-form').onsubmit=async e=>{e.preventDefault();const button=e.submitter;if(button)button.disabled=true;try{library=await api('/api/library',{revision:library.revision,group,id,value:form()});$('modal').close();renderLibrary();renderMetadataEditors();toast('Guardado para los próximos lotes.');}catch(error){$('saved-error').textContent=error.message;}finally{if(button)button.disabled=false;}};
  };draw();
}

init();
