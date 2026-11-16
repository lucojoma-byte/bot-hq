/* JOE HQ local UI, adapted from Bot HQ sidebar/chat/composer/computer concepts.
 * No external requests, raw model HTML, client-side credentials or demo replies. */
'use strict';
(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icons = {
    shield:'<path d="M12 3 4.5 6v5.5c0 4.7 7.5 9.5 7.5 9.5s7.5-4.8 7.5-9.5V6Z"/><path d="m8.5 12 2.3 2.3 4.7-5"/>',
    flower:'<path d="M12 9c-8-13-13 3-3 3-13 8 3 13 3 3 8 13 13-3 3-3 13-8-3-13-3-3Z"/><circle cx="12" cy="12" r="2"/>',
    holding:'<path d="M4 20h16M6 20V10h4v10M14 20V5h4v15M4 7l6-4 5 1 5-2"/>',
    bot:'<rect x="5" y="6" width="14" height="13" rx="4"/><path d="M12 3v3M3 12h2m14 0h2M9 11v1m6-1v1m-6 4h6"/>',
    plus:'<path d="M12 5v14M5 12h14"/>', arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
    send:'<path d="M12 19V5m-6 6 6-6 6 6"/>',
    computer:'<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
    folder:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    file:'<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 13h8m-8 4h5"/>',
    lock:'<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    logout:'<path d="M9 4H5v16h4m5-12 4 4-4 4m-5-4h12"/>',
    mic:'<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>',
    volume:'<path d="m11 4-6 5H2v6h3l6 5Zm4 4a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
    check:'<path d="m5 12 4 4L19 6"/>', close:'<path d="m6 6 12 12M6 18 18 6"/>',
    menu:'<path d="M4 6h16M4 12h16M4 18h16"/>',
    dots:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    refresh:'<path d="M20 9a8 8 0 1 0 0 6m0-12v6h-6"/>',
    message:'<path d="M21 11a8 8 0 0 1-8 8H5l-3 3V11a9 9 0 0 1 19 0Z"/><path d="M7 9h9m-9 5h6"/>',
    download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    arrowleft:'<path d="M19 12H5m5-5-5 5 5 5"/>',
    link:'<path d="m10 13 4-4m-6 7-2 2a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m2 1 2-2a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0"/>',
    leaf:'<path d="M20 3C7 2 2 9 6 16s15 5 14-13ZM4 21 16 8"/>',
    spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/>',
  };
  // Formato mínimo y seguro: primero se escapa TODO el texto; después solo **negritas** y `código`.
  const rich = v => esc(v).replace(/\*\*([^*\n]{1,200})\*\*/g,'<strong>$1</strong>').replace(/`([^`\n]{1,200})`/g,'<code>$1</code>');
  const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.bot}</svg>`;
  const scopes = {guardian:'Guardián',casa_kiraz:'Casa Kiraz',holding:'Holding'};
  const scopeStyle = scope => scope === 'casa_kiraz' ? 'bot-scope-kiraz' : scope === 'holding' ? 'bot-scope-holding' : 'bot-scope-guardian';
  const scopeIcon = scope => scope === 'casa_kiraz' ? 'flower' : scope === 'holding' ? 'holding' : 'shield';
  const avatar = (bot, more = '') => `<span class="bot-avatar ${more} ${scopeStyle(bot?.scope)}">${icon(scopeIcon(bot?.scope))}</span>`;
  const id = () => encodeURIComponent(S.selected || '');
  const S = {session:null,csrf:'',state:null,selected:null,detail:null,tab:'memory',polling:false,detailKey:'',messageKey:'',memoryDirty:false,recorder:null,recordingBot:null,chunks:[],toastTimer:null,busy:false,driveCache:{},transcribing:false,apps:null,appsLoading:false,computerKey:'',frameTimer:null,frameBusy:false};

  function toast(message, error = false) {
    const el = $('#toast'); el.textContent = message; el.classList.toggle('error',error); el.hidden = false;
    clearTimeout(S.toastTimer); S.toastTimer = setTimeout(() => {el.hidden=true;}, error ? 7500 : 4200);
  }
  function errorText(data, fallback) {
    if (typeof data?.error === 'string') return data.error;
    if (typeof data?.error?.message === 'string') return data.error.message;
    return typeof data?.message === 'string' ? data.message : fallback;
  }
  async function api(path, data, options = {}) {
    const headers = {'Accept':'application/json'};
    if (data !== undefined) {headers['Content-Type']='application/json';if(S.csrf) headers['X-CSRF-Token']=S.csrf;}
    if (S.build) headers['X-JOE-Build']=S.build;
    const response = await fetch(path,{method:data === undefined?'GET':'POST',headers,credentials:'same-origin',cache:'no-store',...(data === undefined?{}:{body:JSON.stringify(data)}),signal:AbortSignal.timeout(options.timeout || 35000)});
    let result; try {result=await response.json();} catch {result={};}
    if(!response.ok){
      if(response.status===401 && !['/api/login','/api/setup','/api/session'].includes(path)) {S.session=null;await session();}
      throw new Error(errorText(result,`No se pudo completar la operación (${response.status}).`));
    }
    if(result.ok===false) throw new Error(errorText(result,'La operación quedó pendiente.'));
    return result;
  }
  async function action(button, run) {
    if(button?.disabled) return;
    if(button) button.disabled=true;
    try {await run();} catch(error){toast(error.name==='TimeoutError'?'La operación tardó demasiado. Revisa su estado antes de repetirla.':error.message,true);}
    finally {if(button?.isConnected) button.disabled=false;}
  }
  function dots(thinking=false) {return `<div class="dots-orb ${thinking?'is-thinking':''}" aria-hidden="true">${'<i></i>'.repeat(49)}</div>`;}
  // Si el servidor se actualizó, esta pestaña trae una interfaz vieja: se recarga sola (una vez cada 20 s como máximo).
  function reloadForUpdate(){
    if(S.memoryDirty||(S.recorder&&S.recorder.state==='recording')){toast('Hay una versión nueva de JOE HQ. Guarda tus cambios y recarga la página.',true);return;}
    let last=0;try{last=Number(sessionStorage.getItem('joe-reload')||0);sessionStorage.setItem('joe-reload',String(Date.now()));}catch{}
    if(Date.now()-last<20000){toast('Hay una versión nueva de JOE HQ. Recarga la página (Cmd+R).',true);return;}
    location.reload();
  }
  async function session() {
    try {
      S.session=await api('/api/session');S.csrf=S.session.csrf||'';
      if(!S.build)S.build=S.session.build||'';else if(S.session.build&&S.session.build!==S.build){reloadForUpdate();return;}
      if(S.session.authenticated) {renderShell();await refresh();}
      else renderLogin(Boolean(S.session.setupRequired));
    } catch(error) {$('#app').innerHTML=`<div class="boot"><div class="brandmark">J<span>·</span></div><p>No se pudo abrir JOE HQ</p><p class="form-note">${esc(error.message)}</p><button class="btn" data-action="retry">Reintentar</button></div>`;}
  }
  function renderLogin(setup) {
    $('#app').innerHTML=`<main class="login"><section class="login-art"><div class="row"><div class="brandmark">J<span>·</span></div><div class="wordmark">JOE<span>HQ</span></div></div><div><div class="eyebrow">Tu sede de operaciones</div><h1>Menos ruido.<br>Más dirección.</h1><p>Un espacio para tu equipo de agentes.<br>Tres frentes. Una visión. Todo bajo tu control.</p></div><div class="foot">HECHO PARA JOE · EN TU MAC MINI</div></section><section class="login-form-wrap"><div class="login-form"><div class="brandmark large">J<span>·</span></div><h2>${setup?'Bienvenido a tu sede.':'Bienvenido de vuelta.'}</h2><p>${setup?'Crea una contraseña para abrir JOE HQ en esta Mac. Solo tú decides quién entra.':'Tu equipo está aquí. Ingresa tu contraseña local para continuar.'}</p><form id="auth-form" data-setup="${setup}"><label class="field">Contraseña local<input id="password" name="password" type="password" autocomplete="${setup?'new-password':'current-password'}" ${setup?'minlength="12"':''} maxlength="256" placeholder="${setup?'Al menos 12 caracteres':'Tu contraseña'}" required autofocus></label>${setup?'<label class="field">Confirma la contraseña<input name="confirmation" type="password" autocomplete="new-password" minlength="12" maxlength="256" placeholder="Vuelve a escribirla" required></label>':''}<div class="error-text" id="auth-error" role="alert" hidden></div><button class="btn full" type="submit">${setup?'Crear mi acceso':'Entrar a JOE HQ'}${icon('arrow')}</button></form><div class="local-note">${icon('lock')}Solo localhost · Contraseña guardada como hash</div></div></section></main>`;
    $('#password')?.focus();
  }
  function renderShell() {
    $('#app').innerHTML=`<div class="app"><aside class="sidebar"><div class="sidebar__brand"><div class="brandmark">J<span>·</span></div><div class="wordmark">JOE<span>HQ</span></div><span class="pill">LOCAL</span></div><div class="sidebar__section row spread"><span class="eyebrow">Tu equipo</span><span class="count" id="bot-count">— / 5</span></div><nav id="bot-list" class="bot-list" aria-label="Bots"></nav><button class="new-bot" data-action="new-bot">${icon('plus')}Crear bot</button><div class="sidebar-card"><div class="row">${icon('shield')}Cada negocio, en su espacio</div>Memoria, archivos y conexiones separados para trabajar con claridad.</div><footer class="sidebar__footer"><div class="row"><div class="user-avatar">JM</div><div class="grow"><div class="name">José María</div><div class="role">Director del Holding · D7</div></div><button class="icon-btn" data-action="logout" aria-label="Cerrar sesión" title="Cerrar sesión">${icon('logout')}</button></div><div class="sidebar__bottom"><span class="row"><i class="dot"></i>Esta Mac mini</span><span id="version-label">JOE HQ</span></div></footer></aside><main class="chat"><header class="chat__header"><button class="icon-btn mobile-menu" data-action="sidebar" aria-label="Abrir equipo">${icon('menu')}</button><span id="chat-avatar"></span><div class="grow"><h1 id="chat-title" class="chat__title">Tu equipo</h1><div id="chat-subtitle" class="chat__subtitle">Cargando espacio…</div></div><div class="chat__tools"><button class="icon-btn" data-action="new-session" aria-label="Nuevo hilo" title="Nuevo hilo">${icon('message')}</button><button class="icon-btn" data-action="details" aria-label="Abrir panel del bot" title="Panel del bot">${icon('computer')}</button></div></header><div id="status-banner" class="banner" hidden></div><div id="transcript" class="transcript" role="log" aria-label="Conversación" aria-live="polite"></div><div class="composer-area"><form id="message-form" class="composer"><textarea id="message-input" rows="2" maxlength="12000" placeholder="Escribe a tu equipo…" aria-label="Mensaje"></textarea><div class="composer__bottom"><div class="row"><button class="icon-btn" type="button" data-action="open-files" aria-label="Biblioteca de archivos" title="Biblioteca de archivos">${icon('plus')}</button><div class="profile-label">${icon('spark')}<span id="composer-model">Hermes · openai-codex</span></div></div><div class="row"><button class="icon-btn" type="button" id="mic-button" data-action="record" aria-label="Dictar mensaje" title="Dictar con voz local">${icon('mic')}</button><button type="submit" id="send-button" class="icon-btn send-btn" aria-label="Enviar mensaje">${icon('send')}</button></div></div></form><div class="composer-note">Hermes con tu suscripción · Las acciones externas requieren tu aprobación.</div></div></main><aside class="details"><header class="details__header"><h2>${icon('computer')}Computadora del agente</h2><span class="machine">HERMES · COMPUTER USE</span><button class="icon-btn mobile-panel-close" data-action="close-details" aria-label="Cerrar panel">${icon('close')}</button></header><div id="computer-area"></div><div id="tabs" class="tabs" role="tablist" aria-label="Herramientas del bot"></div><section id="panel" class="panel" role="tabpanel"></section></aside></div>`;
    if(!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) $('#mic-button').disabled=true;
  }
  function selectedBot(){return S.detail?.bot || S.state?.bots?.find(b=>b.id===S.selected);}
  function isThinking(bot){return ['thinking','running','queued','busy','pensando'].includes(bot?.status);}
  function statusLabel(bot){return isThinking(bot)?'Trabajando':bot?.status==='error'?'Requiere atención':'Espacio privado';}
  async function refresh(force=false) {
    if(!S.session?.authenticated||S.polling) return;
    S.polling=true;
    try {
      const state=await api('/api/state');S.state=state;
      if(state.build&&S.build&&state.build!==S.build){reloadForUpdate();return;}
      if(!state.bots?.some(b=>b.id===S.selected)) S.selected=state.selected || state.bots?.[0]?.id || null;
      renderSidebar();
      if(S.selected){
        const selected=S.selected;const detail=await api(`/api/bots/${encodeURIComponent(selected)}`);
        if(selected!==S.selected)return;
        detail.drive=S.driveCache[selected]||detail.drive;S.detail=detail;renderHeader();renderTranscript(force);renderComputer();renderTabs();renderPanel(force);
      } else {$('#transcript').innerHTML='<div class="empty">Crea tu primer bot para empezar.</div>';}
    } catch(error){if(S.session?.authenticated){const banner=$('#status-banner');if(banner){banner.textContent=error.message;banner.className='banner error';banner.hidden=false;}}}
    finally{S.polling=false;}
  }
  function renderSidebar(){
    const bots=S.state?.bots||[];
    $('#bot-count').textContent=`${bots.length} / 5`;
    $('#bot-list').innerHTML=bots.map(bot=>`<button class="bot-row ${bot.id===S.selected?'is-selected':''}" data-bot="${esc(bot.id)}" aria-current="${bot.id===S.selected?'page':'false'}">${avatar(bot)}<span class="grow"><span class="bot-row__name">${esc(bot.name)}</span><span class="bot-row__preview"><i class="dot"></i>${esc(statusLabel(bot))}</span></span></button>`).join('');
    const btn=$('[data-action="new-bot"]');if(btn)btn.disabled=bots.length>=5;
    $('#version-label').textContent=S.state?.version?`v${S.state.version}`:'JOE HQ';
  }
  function renderHeader(){
    const bot=selectedBot();if(!bot)return;
    $('#chat-avatar').innerHTML=avatar(bot);
    $('#chat-title').textContent=bot.name;
    $('#chat-subtitle').innerHTML=`<i class="dot"></i>${esc(scopes[bot.scope]||bot.scope)} · ${esc(statusLabel(bot))}`;
    $('#composer-model').textContent=`Hermes · ${bot.model||'openai-codex'}`;
    $('#message-input').placeholder=`Mensaje a ${bot.name}…`;
    const banner=$('#status-banner');
    const message=bot.error || S.detail?.error || (S.state?.staging?'ENSAYO · datos de prueba, separados de tu operación real.':null);
    banner.hidden=!message;if(message){banner.textContent=String(message);banner.className='banner error';}
  }
  function renderTranscript(force=false){
    const bot=selectedBot();const messages=S.detail?.messages||[];
    const key=JSON.stringify({id:S.selected,messages,status:bot?.status});if(!force&&key===S.messageKey)return;S.messageKey=key;
    const el=$('#transcript');const nearBottom=el.scrollHeight-el.scrollTop-el.clientHeight<100;
    if(!messages.length){
      const hints=bot.scope==='casa_kiraz'?['Organiza el seguimiento de mis clientas','Ayúdame a preparar la agenda de la semana']:bot.scope==='holding'?['Ordena las prioridades del Holding','Ayúdame a revisar mis decisiones pendientes']:['Organiza mis oportunidades de venta','Prepara un seguimiento para un prospecto'];
      el.innerHTML=`<div class="day-divider">UN NUEVO ESPACIO PARA AVANZAR</div><div class="welcome">${avatar(bot,'large')}<h2>¿Qué movemos<br>hoy, Joe?</h2><p>Este es el espacio de ${esc(bot.name)}. Dale una tarea concreta y sigue el trabajo aquí.</p>${hints.map(h=>`<button class="suggestion" data-suggestion="${esc(h)}">${esc(h)}${icon('arrow')}</button>`).join('')}<span class="micro muted"><span class="inline-lock">${icon('lock')}</span>Memoria y archivos de ${esc(scopes[bot.scope]||bot.scope)}</span></div>`;
    } else {
      el.innerHTML=`<div class="day-divider">ESPACIO DE ${esc((bot.name||'').toUpperCase())}</div>`+messages.filter(m=>(m.text??m.content)||m.status!=='pensando').map(m=>{
        const user=m.role==='user';const peer=m.role==='peer';const system=m.role==='system'||m.role==='notice';const failed=m.status==='error'||m.status==='failed';
        let time='';if(m.created_at||m.created){const stamp=m.created_at||m.created;let d=new Date(typeof stamp==='number'?stamp*1000:stamp);if(!Number.isNaN(d.valueOf()))time=d.toLocaleTimeString('es-MX',{hour:'2-digit',minute:'2-digit'});}
        const text=m.text??m.content??'';
        return `<article class="message ${user?'user':system?'system':peer?'peer':'assistant'} ${failed?'error':''}">${user||system?'':peer?`<span class="bot-avatar tiny peer-avatar">${icon('bot')}</span>`:avatar(bot,'tiny')}<div class="bubble-wrap"><div class="bubble">${rich(typeof text==='string'?text:JSON.stringify(text))}</div><div class="message-meta"><span>${esc(user?'Tú':system?'Sistema':peer?'Otro bot · Hermes':bot.name)}</span>${time?`<span>· ${esc(time)}</span>`:''}${m.status?`<span>· ${esc(({queued:'En cola',running:'Trabajando',pensando:'Pensando',error:'Error',failed:'Pendiente',done:'Listo',completed:'Listo',completo:'Listo',interrumpido:'Interrumpido'})[m.status]||m.status)}</span>`:''}${!user&&!system&&!peer&&!failed?`<button type="button" data-speak="${esc(m.id)}" aria-label="Escuchar respuesta" title="Escuchar con VibeVoice (local)">${icon('volume')}</button>`:''}</div></div></article>`;
      }).join('');
    }
    if(isThinking(bot))el.insertAdjacentHTML('beforeend','<div class="thinking" role="status"><span class="dots"><i></i><i></i><i></i></span>Hermes está trabajando…</div>');
    if(force||nearBottom)el.scrollTop=el.scrollHeight;
  }
  const actionWords={capture:'Mirando la pantalla',click:'Clic',double_click:'Doble clic',right_click:'Clic derecho',type:'Escribiendo',key:'Tecla',scroll:'Desplazando',drag:'Arrastrando',set_value:'Eligiendo valor',focus_app:'Cambiando de app',open_app:'Abriendo app',list_apps:'Revisando apps',list_windows:'Revisando ventanas',wait:'Esperando'};
  function renderComputer(){
    const bot=selectedBot();if(!bot)return;const c=S.state?.computer||{};
    const mine=c.owner==='agent'&&c.bot_id===bot.id;const other=c.owner==='agent'&&c.bot_id&&c.bot_id!==bot.id;
    const holder=other?(S.state?.bots||[]).find(b=>b.id===c.bot_id):null;const thinking=isThinking(bot);
    const events=c.events||[];const last=events[events.length-1];const pendingStep=mine?c.pending:null;
    const key=JSON.stringify({id:bot.id,mine,other,thinking,mode:c.mode,locked:c.locked,p:pendingStep?.id,digest:pendingStep?.digest,e:events.length,m:Math.ceil((c.seconds_left||0)/60)});
    if(key===S.computerKey)return;S.computerKey=key;
    const status=other?`La computadora está prestada a ${holder?.name||'otro bot'}`:mine?(thinking?(last?`${actionWords[last.action]||last.action}…`:'Pensando con Hermes…'):'Lista. Pídele una tarea en el chat.'):thinking?'Pensando con Hermes…':'El control está en tus manos';
    const screen=mine?`<img id="live-frame" src="/api/computer/frame?t=${Date.now()}" alt="Pantalla de esta Mac en vivo"><div class="live-overlay ${thinking?'is-on':''}">${dots(thinking)}<span>${esc(status)}</span></div><span class="live-tag"><i class="dot"></i>EN VIVO</span>`:`${dots(thinking)}<div class="computer__name">${esc(bot.name)}</div><div class="computer__status">${esc(status)}</div><div class="computer__dock" aria-hidden="true"><span>${icon('folder')}</span><span>${icon('message')}</span><span>${icon('file')}</span><span>${icon('leaf')}</span></div>`;
    const bar=mine||other?`<span class="row"><i class="dot live"></i>${mine?`${c.mode==='step'?'Paso a paso: tú apruebas cada acción':'Solo ver: no puede hacer clic ni escribir'} · ${Math.ceil((c.seconds_left||0)/60)} min`:'Otro bot tiene la pantalla'}</span><button class="btn danger" data-action="take-control">${icon('lock')}Tomar control</button>`:`<span class="row"><i class="dot"></i>Control humano</span><span class="row gap-6"><button class="btn secondary" data-action="grant" data-mode="view" title="15 minutos. Puede mirar y desplazarse. Nunca hace clic, teclea ni escribe.">Prestar · solo ver</button><button class="btn secondary" data-action="grant" data-mode="step" title="15 minutos. Cada clic, tecla o texto espera tu permiso.">Prestar · paso a paso</button></span>`;
    const exactPayload=pendingStep?.payload&&/^[a-f0-9]{64}$/.test(pendingStep?.digest||'');
    const step=pendingStep?`<div class="step-card" role="alert"><div class="step-title">${icon('lock')}El agente pide permiso</div><div class="step-what" id="step-what">${esc(pendingStep.summary)}</div>${pendingStep.where?`<div class="step-where">${esc(pendingStep.where)}</div>`:''}${pendingStep.warning?`<div class="step-warning">${icon('shield')}${esc(pendingStep.warning)}</div>`:''}${exactPayload?`<details class="step-exact" open><summary>Acción completa · sin recortes</summary><pre>${esc(JSON.stringify(pendingStep.payload,null,2))}</pre><div class="micro muted">Huella: ${esc(pendingStep.digest)}</div></details>`:'<p class="step-warning">El servidor no entrega la carga completa. Reinicia JOE HQ con el código actualizado antes de permitir acciones.</p>'}<div class="row gap-6"><button class="btn" data-step="${esc(pendingStep.id)}" data-digest="${esc(pendingStep.digest||'')}" data-decision="allow" ${exactPayload?'':'disabled'}>${icon('check')}Permitir este paso exacto</button><button class="btn secondary" data-step="${esc(pendingStep.id)}" data-decision="deny">Negar</button></div></div>`:'';
    const feed=mine&&events.length?`<ol class="event-feed">${events.slice(-5).reverse().map(e=>`<li class="${e.ok?'':'bad'}"><span>${e.blocked?'Bloqueado':esc(actionWords[e.action]||e.action)}</span><code>${esc(e.summary)}</code></li>`).join('')}</ol>`:'';
    const lockedNote=c.locked?`<div class="step-warning locked-note" role="alert">${icon('lock')}La Mac está con la pantalla bloqueada. El bot no puede ver ni actuar hasta que la desbloquees.</div>`:'';
    $('#computer-area').innerHTML=`${lockedNote}<div class="computer ${mine?'is-live':''}"><div class="computer__chrome"><div class="traffic-lights" aria-hidden="true"><span></span><span></span><span></span></div><span>${esc(bot.name)} / MAC MINI</span><span>⌘</span></div><div class="computer__screen">${screen}</div><div class="computer__bar">${bar}</div></div>${step}${feed}<div class="computer-caption">${mine?(c.mode==='step'?'Pantalla real de esta Mac. Ningún clic, tecla o texto ocurre sin tu Permitir para ese paso.':'Pantalla real de esta Mac. En «solo ver» el sistema bloquea todo clic, tecla y texto.'):'«Solo ver»: mira y se desplaza, nunca actúa. «Paso a paso»: cada acción espera tu permiso. Sin prestarla no ve ni toca nada.'}</div>`;
    clearInterval(S.frameTimer);S.frameTimer=null;
    if(mine)S.frameTimer=setInterval(()=>{const img=$('#live-frame');if(!img||document.hidden||S.frameBusy)return;S.frameBusy=true;const next=new Image();next.onload=()=>{if(img.isConnected)img.src=next.src;S.frameBusy=false;};next.onerror=()=>{S.frameBusy=false;};next.src=`/api/computer/frame?t=${Date.now()}`;},1500);
  }
  const tabNames={memory:'Memoria',tasks:'Tareas',files:'Archivos',connections:'Apps',approvals:'Aprobar'};
  function approvals(){return (S.detail?.approvals||S.state?.approvals||[]).filter(a=>!a.bot_id||a.bot_id===S.selected);}
  function pending(a){return ['pending','awaiting_approval','queued','pendiente',''].includes(a.status||'');}
  function renderTabs(){const count=approvals().filter(pending).length;$('#tabs').innerHTML=Object.entries(tabNames).map(([key,name])=>`<button class="tab ${S.tab===key?'active':''}" role="tab" id="tab-${key}" aria-selected="${S.tab===key}" aria-controls="panel" data-tab="${key}">${name}${key==='approvals'&&count?`<span class="badge">${count}</span>`:''}</button>`).join('');$('#panel').setAttribute('aria-labelledby',`tab-${S.tab}`);}
  const bytes = n => Number(n||0)<1024?`${n||0} B`:Number(n)<1048576?`${(Number(n)/1024).toFixed(1)} KB`:`${(Number(n)/1048576).toFixed(1)} MB`;
  function renderPanel(force=false){
    if(!S.detail)return;
    const detail=S.detail,bot=selectedBot();
    const key=JSON.stringify({id:S.selected,tab:S.tab,memory:detail.memory,tasks:detail.tasks,files:detail.files,approvals:approvals(),drive:detail.drive,profile:bot.profile,profiles:S.state?.profiles,cap:S.tab==='connections'?S.state?.capabilities:null,apps:S.tab==='connections'?S.apps:null});
    if(!force&&key===S.detailKey)return;
    if(S.memoryDirty||(!force&&$('#panel').contains(document.activeElement)))return;
    S.detailKey=key;const panel=$('#panel');
    if(S.tab==='memory'){
      panel.innerHTML=`<div class="panel-heading"><h3>Su forma de trabajar</h3><span class="tag">${esc(scopes[bot.scope]||bot.scope)}</span></div><form id="memory-form"><label class="field">SOUL.md · Identidad<textarea name="soul" class="mono" maxlength="40000" spellcheck="false">${esc(detail.memory?.soul||'')}</textarea></label><label class="field">MEMORY.md · Memoria de Hermes<textarea name="memory" class="mono" maxlength="40000" spellcheck="false">${esc(detail.memory?.memory||'')}</textarea></label><label class="field">USER.md · Contexto de Joe<textarea name="user" class="mono" maxlength="40000" spellcheck="false">${esc(detail.memory?.user||'')}</textarea></label><button type="submit" class="btn secondary full">${icon('check')}Guardar memoria</button><p class="panel-note">Se guarda únicamente en la memoria nativa de este bot.</p></form>${profileHTML(bot)}`;
    }else if(S.tab==='tasks'){
      panel.innerHTML=`<div class="panel-heading"><h3>Lo que sigue</h3><span class="tag">${(detail.tasks||[]).length} tareas</span></div><form id="task-form" class="mini-form"><input name="title" maxlength="300" placeholder="Agregar una tarea…" aria-label="Título de tarea" required><button type="submit" aria-label="Agregar tarea">${icon('plus')}</button></form>${(detail.tasks||[]).map(t=>{const done=t.status==='completa';return `<div class="task-row ${done?'done':''}">${icon(done?'check':'clock')}<div class="grow"><div class="task-title">${esc(t.title||t.text)}</div><div class="task-sub">${esc(done?'Completa':'Pendiente')}${t.origin?` · asignada por ${esc(t.origin)}`:''}</div></div>${done?'':`<button class="icon-btn" data-task-done="${esc(t.id)}" aria-label="Marcar completa" title="Marcar completa">${icon('check')}</button>`}</div>`;}).join('')||'<div class="empty">Una prioridad a la vez.<br>Agrega la siguiente tarea de este bot.</div>'}${relayHTML(bot)}`;
    }else if(S.tab==='files'){
      panel.innerHTML=`<div class="panel-heading"><h3>Biblioteca del bot</h3><button class="btn secondary small" data-action="new-file">${icon('plus')}Archivo</button></div>${(detail.files||[]).map(f=>`<div class="file-row">${icon('file')}<div class="grow"><div class="file-name">${esc(f.name)}</div><div class="file-size">${bytes(f.size)}</div></div><button class="icon-btn" data-download="${esc(f.name)}" aria-label="Descargar ${esc(f.name)}">${icon('download')}</button></div>`).join('')||'<div class="empty">Aquí viven sus entregables.<br>Crea un archivo o pídele a Hermes que lo prepare.</div>'}<p class="panel-note">Esta biblioteca pertenece solo a ${esc(scopes[bot.scope]||bot.scope)}.</p>`;
    }else if(S.tab==='connections'){
      if(!S.apps&&!S.appsLoading)void loadApps();
      panel.innerHTML=appsHTML(bot,detail);
    }else{
      const list=approvals();panel.innerHTML=`<div class="panel-heading"><h3>Tú das el visto bueno</h3><span class="tag">${list.filter(pending).length} pendientes</span></div><p>Nada se envía, publica, agenda ni borra sin este botón. Cada aprobación sirve una sola vez y caduca en 15 minutos.</p>${list.map(a=>`<article class="approval ${pending(a)?'':'done'}"><h4>${esc(a.title||a.tool||a.action||'Acción pendiente')}</h4><div class="micro muted">${esc(a.description||a.summary||'')}</div><dl class="payload">${Object.entries(a.payload||{}).filter(([k,v])=>!(v===''||v===null||(Array.isArray(v)&&!v.length)||k.endsWith('_id'))).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(Array.isArray(v)?(typeof v[0]==='object'?JSON.stringify(v):v.join(', ')):typeof v==='object'?JSON.stringify(v):v)}</dd>`).join('')}</dl>${pending(a)?`<div class="row"><button class="btn" data-approval="${esc(a.id)}" data-decision="approve">${icon('check')}Aprobar</button><button class="btn secondary" data-approval="${esc(a.id)}" data-decision="reject">Rechazar</button></div>`:`<div class="micro muted">Estado: ${esc(a.status)}</div>${a.result?`<pre>${esc(typeof a.result==='string'?a.result:JSON.stringify(a.result,null,2))}</pre>`:''}`}</article>`).join('')||'<div class="empty">No hay acciones esperando tu aprobación.</div>'}`;
    }
  }
  function profileHTML(bot){return `<div class="profile-block"><label class="field">Motor de este bot<select id="profile-select" aria-label="Perfil Hermes">${(S.state?.profiles||[]).map(p=>`<option value="${esc(p.id)}" ${p.id===bot.profile?'selected':''}>${esc(p.name||p.id)}${p.model?` · ${esc(p.model)}`:''}</option>`).join('')}</select></label><div class="form-note">Solo perfiles autorizados con tu suscripción. Sin llaves de API de pago.</div></div>`;}
  function relayHTML(bot){const targets=S.detail?.team||[];const kinds={same:'mismo negocio',parent:'Holding ↔ negocio',sibling:'bloqueado · negocios separados'};return `<div class="relay-box"><h4>Pedirle que le escriba a otro bot</h4>${targets.length?`<form id="relay-form" class="stack"><label class="field">Destino<select name="target_id">${targets.map(b=>`<option value="${esc(b.id)}" ${b.relation==='sibling'?'disabled':''}>${esc(b.name)} · ${esc(kinds[b.relation]||'')}</option>`).join('')}</select></label><label class="field">Mensaje<textarea name="text" maxlength="4000" placeholder="Una petición concreta…" required></textarea></label><button class="btn secondary" type="submit">${icon('message')}Enviar al bot</button></form>`:'<p>No hay otros bots.</p>'}<p class="panel-note">Usa message_agent de Hermes; la respuesta vuelve sola a este chat. Guardián y Casa Kiraz tienen bloqueados los mensajes y tareas directos, incluso con aprobación. Holding puede comunicarse con cada negocio, pero no reenviar de uno al otro.</p></div>`;}
  function driveHTML(drive){const files=Array.isArray(drive)?drive:drive?.files||[];const pages=drive?.next_pages||{};return `<div class="mt-14">${files.map(f=>`<div class="drive-file row spread"><span>${esc(f.name||f.title||f.id||String(f))}</span>${f.id?`<button class="icon-btn" data-drive-${f.mimeType==='application/vnd.google-apps.folder'?'folder':'read'}="${esc(f.id)}" aria-label="${f.mimeType==='application/vnd.google-apps.folder'?'Abrir carpeta':'Leer archivo'} ${esc(f.name)}">${icon(f.mimeType==='application/vnd.google-apps.folder'?'folder':'file')}</button>`:''}</div>`).join('')}${drive?.truncated?'<p class="panel-note">Listado parcial. Hay más archivos por cargar.</p>':''}${Object.entries(pages).map(([folder,token])=>`<button class="btn secondary full mt-14" data-drive-page="${esc(folder)}" data-page-token="${esc(token)}">Cargar más archivos</button>`).join('')}</div>`;}
  const scopeNames={guardian:'Guardián',casa_kiraz:'Casa Kiraz',holding:'Holding',ninguno:'Sin asignar'};
  const ago=t=>{if(!t)return 'sin probar en esta sesión';const s=Math.max(0,Math.round(Date.now()/1000-t));return s<90?'verificado hace instantes':s<3600?`verificado hace ${Math.round(s/60)} min`:`verificado hace ${Math.round(s/3600)} h`;};
  async function loadApps(force=false){S.appsLoading=true;try{S.apps=await api('/api/apps'+(force?'?refresh=1':''),undefined,{timeout:120000});}catch(error){S.apps={apps:[],error:error.message,auth:''};}finally{S.appsLoading=false;S.detailKey='';if(S.tab==='connections')renderPanel(true);}}
  function keyHTML(data){
    const has=Boolean(data?.has_key);
    return `<section class="key-box ${has?'is-set':''}" id="composio-key" aria-labelledby="key-title"><h4 id="key-title">${icon('lock')}Credencial de Composio</h4><p class="key-status"><span class="app-dot ${has?'on':'idle'}"></span>${has?'Llave propia guardada en .env':'Sin llave propia'} · En uso: ${esc(data?.auth||'consultando…')}</p><form id="key-form" class="stack"><label class="field">${has?'Reemplazar la llave guardada':'Llave de Composio (empieza con ck_)'}<input name="key" id="key-input" type="password" autocomplete="off" spellcheck="false" maxlength="200" placeholder="ck_…" required></label><button class="btn full" type="submit" id="key-save">${icon('lock')}${has?'Reemplazar llave':'Guardar solo en .env'}</button><p class="panel-note">${has?'La llave vive solo en el archivo .env de esta Mac. Nunca se muestra de vuelta.':'Se prueba contra Composio antes de guardarse. Sin llave, la app depende de que Hermes esté abierto para renovar su sesión cada hora.'}</p></form></section>`;
  }
  function appsHTML(bot,detail){
    const data=S.apps;const folders={guardian:['02_GUARDIAN_ACCESOS_CNC'],casa_kiraz:['03_CASA_KIRAZ'],holding:['01_PLAN_DE_VIDA_Y_RETIRO_CHAPALA','04_SISTEMAS_MARKETING_Y_VIRALIDAD']}[bot.scope]||[];
    const caps=S.state?.capabilities||{};const voice=caps.voice||{};
    const rows=!data?'<div class="empty">Consultando Composio…</div>':(data.apps||[]).map(a=>{
      const account=a.accounts?.[0];const label=account?.label||(account?'Cuenta conectada':'');
      const usable=a.exclusive?a.assigned_scope===bot.scope:a.active;
      const sub=!a.active?'No conectada en Composio':a.exclusive?`${esc(label)} · ${a.assigned_scope?`asignada a ${esc(scopeNames[a.assigned_scope]||a.assigned_scope)}`:'sin asignar: ningún bot la usa'}`:`${esc(label)} · cercada a ${folders.map(esc).join(', ')}`;
      const select=a.exclusive&&a.active&&account?`<label class="assign"><span>Negocio dueño</span><select data-assign="${esc(a.toolkit)}" data-account="${esc(account.id)}" aria-label="Negocio dueño de ${esc(a.name)}">${['ninguno','guardian','casa_kiraz','holding'].map(sc=>`<option value="${sc}" ${(a.assigned_scope||'ninguno')===sc?'selected':''}>${scopeNames[sc]}</option>`).join('')}</select></label>`:'';
      return `<div class="connection-row app-row"><span class="app-dot ${usable?'on':a.active?'idle':'off'}"></span><div class="grow"><div class="connection-name">${esc(a.name)}${a.name==='Drive'?' · Docs':''} <span class="tag">${usable?'Disponible para este bot':a.active?'No disponible para este bot':'Desconectada'}</span></div><div class="connection-sub">${sub}</div>${select}</div></div>`;}).join('');
    return `<div class="panel-heading"><h3>Apps de ${esc(scopes[bot.scope]||bot.scope)}</h3><button class="btn secondary small" data-action="apps-refresh">${icon('refresh')}Actualizar</button></div>${data?.error?`<div class="banner error inline">${esc(data.error)}</div>`:''}${keyHTML(data)}<div class="capability-box"><div class="row">${icon('lock')}Cada negocio, sus cuentas</div>Drive y Sheets se limitan a la carpeta del negocio. Gmail, Calendar, Instagram y GitHub pertenecen a un solo negocio: tú eliges cuál.</div>${rows}<button class="btn secondary full mt-17" data-action="drive">${icon('folder')}Explorar el Drive de este negocio</button><div id="drive-results">${driveHTML(detail.drive)}</div><div class="relay-box"><h4>Voz local</h4><label class="field">Voz de VibeVoice<select id="voice-select" aria-label="Voz">${(voice.voices||[]).map(v=>`<option value="${esc(v)}" ${v===voice.voice?'selected':''}>${esc(v)}</option>`).join('')}</select></label><p class="panel-note">Dictado: faster-whisper. Salida: VibeVoice-1.5B. Todo en esta Mac; la primera frase tarda cerca de un minuto en cargar.</p></div><div class="capability-box mt-18"><div class="row">${icon('computer')}Estado real</div>Hermes (openai-codex): ${esc(caps.hermes?.error?`error: ${caps.hermes.error}`:ago(caps.hermes?.verified_at))}<br>Composio: ${esc(caps.composio?.error||ago(caps.composio?.verified_at))}<br>Dictado: ${esc(ago(voice.stt_verified_at))}<br>Voz: ${esc(voice.tts_error||ago(voice.tts_verified_at))}${voice.loaded?' · motor cargado':''}</div><p class="panel-note">Enviar, publicar, crear eventos o borrar siempre requiere una aprobación individual.</p>`;
  }
  async function selectBot(botId){
    if(botId===S.selected){$('.app')?.classList.remove('show-sidebar');return;}
    if(S.memoryDirty){toast('Guarda los cambios de memoria antes de cambiar de bot.',true);return;}
    if(S.recorder&&S.recorder.state!=='inactive'){toast('Termina el dictado antes de cambiar de bot.',true);return;}
    S.selected=botId;S.detail=null;S.detailKey='';S.messageKey='';S.computerKey='';$('#message-input').value='';$('.app')?.classList.remove('show-sidebar');
    $('#transcript').innerHTML='<div class="empty">Abriendo el espacio…</div>';$('#panel').innerHTML='';
    while(S.polling) await new Promise(r=>setTimeout(r,40));await refresh(true);
  }
  function modal(html){const dialog=$('#modal');dialog.innerHTML=`<button class="icon-btn close-modal" data-action="close-modal" aria-label="Cerrar">${icon('close')}</button>${html}`;dialog.showModal();const first=dialog.querySelector('input,textarea,select');if(first)first.focus();}
  function createBot(){modal(`<h2 id="modal-title">Una nueva identidad.</h2><p>Hasta cinco bots persistentes. Usa hilos para cambiar de tema dentro del mismo bot.</p><form id="create-bot-form"><label class="field">Nombre del bot<input name="name" maxlength="60" placeholder="Ej. Guardián Operaciones" required></label><label class="field">Negocio<select name="scope"><option value="guardian">Guardián</option><option value="casa_kiraz">Casa Kiraz</option><option value="holding">Holding</option></select></label><p class="form-note">Su memoria, biblioteca y carpetas quedan vinculadas a este negocio.</p><div class="actions"><button class="btn secondary" type="button" data-action="close-modal">Cancelar</button><button class="btn" type="submit">Crear bot</button></div></form>`);}
  function createFile(){modal(`<h2 id="modal-title">Guardar un archivo.</h2><p>Se guardará en la biblioteca de ${esc(selectedBot()?.name)}.</p><form id="create-file-form"><label class="field">Nombre<input name="name" maxlength="100" pattern="[A-Za-z0-9_ .-]+" placeholder="seguimiento.md" required></label><label class="field">Contenido<textarea name="content" rows="8" maxlength="200000" placeholder="Escribe o pega el contenido…" required></textarea></label><div class="actions"><button type="button" class="btn secondary" data-action="close-modal">Cancelar</button><button class="btn" type="submit">Guardar archivo</button></div></form>`);}
  async function download(name){const response=await fetch(`/api/bots/${id()}/files?name=${encodeURIComponent(name)}`,{credentials:'same-origin',cache:'no-store'});if(!response.ok){let j={};try{j=await response.json();}catch{}throw new Error(errorText(j,'No se pudo descargar el archivo.'));}let blob;if(response.headers.get('Content-Type')?.includes('application/json')){const j=await response.json();blob=new Blob([j.content??''],{type:'text/plain;charset=utf-8'});}else blob=await response.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async function record(){
    if(S.recorder?.state==='recording'){S.recorder.stop();return;}if(S.transcribing)throw new Error('Espera a que termine la transcripción anterior.');
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw new Error('Este navegador no permite grabar audio. Usa un navegador actual en localhost.');
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    const preferred=['audio/webm;codecs=opus','audio/webm','audio/mp4'].find(t=>MediaRecorder.isTypeSupported(t));
    try{S.recorder=new MediaRecorder(stream,preferred?{mimeType:preferred}:{});}catch(error){stream.getTracks().forEach(t=>t.stop());throw error;}
    S.chunks=[];S.recordingBot=S.selected;const bot=S.selected;
    const btn=$('#mic-button');btn.classList.add('recording');btn.setAttribute('aria-label','Terminar dictado');btn.title='Terminar dictado';
    S.recorder.ondataavailable=e=>{if(e.data.size)S.chunks.push(e.data);};
    S.recorder.onerror=()=>{stream.getTracks().forEach(t=>t.stop());btn.classList.remove('recording');toast('No se pudo grabar el audio.',true);};
    S.recorder.onstop=async()=>{
      stream.getTracks().forEach(t=>t.stop());clearTimeout(S.recordTimer);btn.classList.remove('recording');btn.setAttribute('aria-label','Dictar mensaje');btn.title='Dictar con voz local';
      const blob=new Blob(S.chunks,{type:S.recorder.mimeType||'audio/webm'});S.recorder=null;
      if(blob.size>15*1024*1024){toast('El audio es demasiado grande. Graba un mensaje más corto.',true);return;}
      S.transcribing=true;toast('Transcribiendo en esta Mac…');
      try{const audio=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob);});const result=await api(`/api/bots/${encodeURIComponent(bot)}/transcribe`,{audio,mime:blob.type},{timeout:120000});if(bot===S.selected){const input=$('#message-input');input.value=[input.value,result.text||result.transcript||''].filter(Boolean).join(' ');input.focus();toast('Dictado listo. Revísalo antes de enviarlo.');}else toast('El dictado terminó; vuelve al bot donde lo grabaste.');}catch(error){toast(error.message,true);}finally{S.transcribing=false;}
    };
    S.recorder.start();S.recordTimer=setTimeout(()=>{if(S.recorder?.state==='recording')S.recorder.stop();},90000);toast('Escuchando… Pulsa el micrófono para terminar.');
  }
  async function speak(messageId){
    const m=(S.detail?.messages||[]).find(x=>String(x.id)===messageId);if(!m)return;
    toast('Generando voz con VibeVoice en esta Mac… la primera vez tarda cerca de un minuto.');const result=await api(`/api/bots/${id()}/speak`,{text:m.text||m.content||''},{timeout:420000});
    let audioURL=result.url;let objectURL=null;if(result.audio){const raw=atob(result.audio);const bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);objectURL=URL.createObjectURL(new Blob([bytes],{type:result.mime||'audio/wav'}));audioURL=objectURL;}
    if(!audioURL)throw new Error(result.message||'El motor de voz no devolvió audio.');
    if(result.url){const u=new URL(result.url,location.origin);if(u.origin!==location.origin)throw new Error('Se rechazó un audio externo.');audioURL=u.href;}
    const audio=new Audio(audioURL);if(objectURL){audio.onended=()=>URL.revokeObjectURL(objectURL);audio.onerror=()=>URL.revokeObjectURL(objectURL);}try{await audio.play();}catch(error){if(objectURL)URL.revokeObjectURL(objectURL);throw error;}
  }

  document.addEventListener('click',event=>{
    const btn=event.target.closest('button');if(!btn)return;
    if(btn.dataset.bot){void action(btn,()=>selectBot(btn.dataset.bot));return;}
    if(btn.dataset.suggestion){$('#message-input').value=btn.dataset.suggestion;$('#message-input').focus();return;}
    if(btn.dataset.tab){
      if(S.memoryDirty&&btn.dataset.tab!=='memory'){toast('Guarda primero tus cambios de memoria.',true);return;}
      S.tab=btn.dataset.tab;renderTabs();renderPanel(true);return;
    }
    if(btn.dataset.approval){void action(btn,async()=>{await api(`/api/approvals/${encodeURIComponent(btn.dataset.approval)}`,{decision:btn.dataset.decision});toast(btn.dataset.decision==='approve'?'Aprobado. Revisa el resultado.':'Rechazado: no se ejecutó.');await refresh(true);});return;}
    if(btn.dataset.driveFolder||btn.dataset.drivePage){void action(btn,async()=>{const result=await api(`/api/bots/${id()}/drive`,{folder_id:btn.dataset.driveFolder||btn.dataset.drivePage,...(btn.dataset.pageToken?{page_token:btn.dataset.pageToken}:{})},{timeout:120000});if(btn.dataset.drivePage)result.files=[...(S.detail.drive?.files||[]),...(result.files||[])];S.detail.drive=result;S.driveCache[S.selected]=result;const area=$('#drive-results');if(area)area.innerHTML=driveHTML(result);});return;}
    if(btn.dataset.driveRead){void action(btn,async()=>{const result=await api(`/api/bots/${id()}/drive-read`,{file_id:btn.dataset.driveRead},{timeout:120000});modal(`<h2 id="modal-title">${esc(result.name||'Archivo de Drive')}</h2><p>${result.truncated?'Contenido parcial. Archivo mayor al límite del visor.':'Lectura verificada dentro de la carpeta de este negocio.'}</p><pre class="document-preview">${esc(result.content||'')}</pre><div class="actions"><button class="btn secondary" data-action="close-modal">Cerrar</button></div>`);});return;}
    if(btn.dataset.download){void action(btn,()=>download(btn.dataset.download));return;}
    if(btn.dataset.speak){void action(btn,()=>speak(btn.dataset.speak));return;}
    if(btn.dataset.taskDone){void action(btn,async()=>{await api(`/api/bots/${id()}/task-done`,{task_id:btn.dataset.taskDone});await refresh(true);});return;}
    if(btn.dataset.step){void action(btn,async()=>{await api('/api/computer/decide',{id:btn.dataset.step,decision:btn.dataset.decision,digest:btn.dataset.digest||null});S.computerKey='';await refresh(true);});return;}
    switch(btn.dataset.action){
      case 'retry':void session();break;
      case 'sidebar':$('.app')?.classList.toggle('show-sidebar');break;
      case 'details':$('.app')?.classList.toggle('show-details');break;
      case 'close-details':$('.app')?.classList.remove('show-details');break;
      case 'close-modal':$('#modal').close();break;
      case 'new-bot':createBot();break;
      case 'new-file':createFile();break;
      case 'open-files':if(S.memoryDirty){toast('Guarda primero los cambios de memoria.',true);break;}S.tab='files';$('.app')?.classList.add('show-details');renderTabs();renderPanel(true);break;
      case 'new-session':void action(btn,async()=>{await api(`/api/bots/${id()}/session`,{});await refresh(true);toast('Nuevo hilo iniciado. La memoria del bot se conserva.');});break;
      case 'logout':void action(btn,async()=>{await api('/api/logout',{});S.detail=null;S.state=null;S.csrf='';S.memoryDirty=false;await session();});break;
      case 'grant':void action(btn,async()=>{await api(`/api/bots/${id()}/computer`,{owner:'agent',mode:btn.dataset.mode});S.computerKey='';await refresh(true);toast(btn.dataset.mode==='step'?'Pantalla prestada. Aprobarás cada paso aquí.':'Pantalla prestada para ver. El bot no puede hacer clic ni escribir.');});break;
      case 'take-control':void action(btn,async()=>{await api(`/api/bots/${id()}/computer`,{owner:'user'});S.computerKey='';await refresh(true);toast('Tomaste el control. El agente se detuvo.');});break;
      case 'apps-refresh':void action(btn,()=>loadApps(true));break;
      case 'drive':void action(btn,async()=>{const result=await api(`/api/bots/${id()}/drive`,{},{timeout:120000});S.detail.drive=result;S.driveCache[S.selected]=result;const area=$('#drive-results');if(area)area.innerHTML=driveHTML(S.detail.drive);toast(result.truncated?'Lectura parcial de Drive. Hay más archivos por cargar.':'Lectura de Drive completada.');});break;
      case 'record':void action(btn,record);break;
    }
  });
  document.addEventListener('submit',event=>{
    const form=event.target;if(!form.id)return;event.preventDefault();const button=form.querySelector('[type="submit"]');const data=Object.fromEntries(new FormData(form).entries());
    if(form.id==='auth-form'){
      const setup=form.dataset.setup==='true';const error=$('#auth-error');error.hidden=true;
      if(setup&&data.password!==data.confirmation){error.textContent='Las contraseñas no coinciden.';error.hidden=false;return;}
      void action(button,async()=>{try{const r=await api(setup?'/api/setup':'/api/login',{password:data.password});if(r.csrf)S.csrf=r.csrf;form.reset();await session();}catch(e){error.textContent=e.message;error.hidden=false;}});return;
    }
    if(form.id==='message-form'){
      const input=$('#message-input');const text=input.value.trim();if(!text||!S.selected)return;
      const bot=S.selected;void action(button,async()=>{await api(`/api/bots/${encodeURIComponent(bot)}/message`,{text});if(bot===S.selected&&input.value.trim()===text)input.value='';await refresh(true);});return;
    }
    if(form.id==='memory-form'){void action(button,async()=>{await api(`/api/bots/${id()}/memory`,data);S.memoryDirty=false;S.detailKey='';toast('Memoria guardada en su espacio.');await refresh(true);});return;}
    if(form.id==='task-form'){void action(button,async()=>{await api(`/api/bots/${id()}/tasks`,{title:data.title});form.reset();await refresh(true);});return;}
    if(form.id==='relay-form'){void action(button,async()=>{await api(`/api/bots/${id()}/relay`,{target_id:data.target_id,text:data.text});form.reset();await refresh(true);toast('Mensaje entregado por JOE HQ.');});return;}
    if(form.id==='key-form'){void action(button,async()=>{const r=await api('/api/apps/key',{key:data.key},{timeout:120000});form.reset();S.apps=r;S.detailKey='';renderPanel(true);toast(r.error?`Llave guardada, pero Composio respondió: ${r.error}`:'Llave guardada en .env y verificada con Composio.',Boolean(r.error));});return;}
    if(form.id==='create-bot-form'){void action(button,async()=>{const r=await api('/api/bots',data);$('#modal').close();S.selected=r.bot?.id||r.id||S.selected;S.detailKey='';S.messageKey='';await refresh(true);toast('Bot creado con su propio espacio.');});return;}
    if(form.id==='create-file-form'){void action(button,async()=>{await api(`/api/bots/${id()}/files`,data);$('#modal').close();await refresh(true);toast('Archivo guardado en la biblioteca.');});}
  });
  document.addEventListener('input',event=>{if(event.target.closest('#memory-form')){S.memoryDirty=true;const save=$('#memory-form button[type="submit"]');if(save)save.innerHTML=`${icon('check')}Guardar cambios`;}});
  document.addEventListener('change',event=>{
    const el=event.target;
    if(el.dataset.assign){const name=scopeNames[el.value];el.disabled=true;void api('/api/apps/assign',{toolkit:el.dataset.assign,account_id:el.dataset.account,scope:el.value},{timeout:120000}).then(r=>{S.apps=r;S.detailKey='';renderPanel(true);toast(el.value==='ninguno'?'Cuenta sin asignar: ningún bot la usa.':`Cuenta asignada solo a ${name}.`);}).catch(e=>{toast(e.message,true);void loadApps();});return;}
    if(el.id==='voice-select'){void api('/api/voice',{voice:el.value}).then(()=>toast('Voz actualizada.')).catch(e=>toast(e.message,true));return;}
    if(event.target.id==='profile-select'){const select=event.target;const previous=selectedBot()?.profile;if(S.memoryDirty){select.value=previous;toast('Guarda primero los cambios de memoria.',true);return;}select.disabled=true;void api(`/api/bots/${id()}/profile`,{profile:select.value}).then(async()=>{toast('Perfil de Hermes actualizado.');await refresh(true);}).catch(e=>{select.value=previous;toast(e.message,true);}).finally(()=>{if(select.isConnected)select.disabled=false;});}});
  document.addEventListener('keydown',event=>{if(event.target.id==='message-input'&&event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('#message-form').requestSubmit();}});
  $('#modal').addEventListener('click',event=>{if(event.target===$('#modal')){const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.target.close();}});
  window.addEventListener('beforeunload',event=>{if(S.memoryDirty){event.preventDefault();event.returnValue='';}});
  setInterval(()=>{if(!document.hidden)void refresh();},3000);
  setInterval(()=>{if(document.hidden)return;const c=S.state?.computer;if(c?.owner==='agent'||isThinking(selectedBot()))void refresh();},1000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)void refresh();});
  void session();
})();
