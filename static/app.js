const $=s=>document.querySelector(s), money=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR'}).format(n), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let data={orders:[],trades:[],edits:[]}, editing=null, custom=JSON.parse(localStorage.getItem('vcclRecorderCustomTrades')||'[]');
$('#date').value=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
async function api(path,method='GET',body){const r=await fetch('/recorder'+path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});if(r.status===401){location.href='/login';throw Error('Sign in again');}const j=await r.json();if(!r.ok)throw Error(typeof j.detail==='string'?j.detail:'Request failed');return j;}
const purposeLabel=p=>({stop:'Stop loss',target:'Target',discretionary:'Discretionary',unknown:'Unknown',inherit:'Use order default'}[p]||'Unknown');
const legacyPurpose=e=>e?.purpose??(['stop','target'].includes(e?.role)?e.role:'unknown');
const purposeOptions=selected=>['inherit','stop','target','discretionary','unknown'].map(p=>`<option value="${p}" ${selected===p?'selected':''}>${purposeLabel(p)}</option>`).join('');
const editFor=id=>data.edits.find(e=>e.order===id);
function executionTime(value){
    if(!value) return '—';
    // Dhan's timezone-free exchange timestamps are already in IST.
    const text=String(value).replace(' ','T');
    if(!/(Z|[+-]\d{2}:?\d{2})$/i.test(text)) return text.slice(11,19)||'—';
    const date=new Date(text);
    return Number.isNaN(date.getTime())?'—':date.toLocaleTimeString('en-GB',{timeZone:'Asia/Kolkata',hour12:false});
}
function tradeTimes(t){
    const legs=t.legs||[];
    if(!legs.length) return '';
    const first=legs[0].time, last=legs[legs.length-1].time;
    return `<div class="trade-times"><span>Entry <strong>${esc(executionTime(first))}</strong></span><span>${t.status==='CLOSED'?'Exit':'Last fill'} <strong>${esc(executionTime(last))}</strong></span><small>IST${t.status==='OPEN'?' · position open':''}</small></div>`;
}
function orderCard(o, showTimes=false){let e=editFor(o.id);return `<button class="order" draggable="true" data-order="${esc(o.id)}"><span class="side ${o.side==='SELL'?'sell':''}">${esc(o.side)}</span><span>${esc(o.symbol)}<small>${esc(o.id)} · ${esc(o.status)} · ${esc(o.effect||'Unfilled')}${e&&o.effect!=='Entry'?' · '+esc(purposeLabel(legacyPurpose(e)))+(e.breakeven?' · SL at breakeven':''):''}</small>${showTimes?`<small class="order-times">Placed ${esc(executionTime(o.created))} · Updated ${esc(executionTime(o.time))} IST</small>`:''}</span><b>${esc(o.filled||0)} / ${esc(o.qty)}<small>${money(o.average||o.price||0)}</small></b></button>`;}
function protectionCard(t){
    if(!t.status) return '';
    const p=t.protection||{planned:{},orders:[],plan_history:[]};
    const label=r=>r==='stop'?'SL':'Target';
    const planned=['stop','target'].map(r=>`<span>Planned ${label(r)} <strong>${p.planned[r]!=null?money(p.planned[r]):'—'}</strong></span>`).join('');
    const broker=p.orders.map(o=>{const h=o.history, last=h[h.length-1];return `<div class="broker-level"><b>${label(o.role)} order · ${esc(o.confidence)}</b><small>${esc(o.order)} · ${esc(last?.status||'Unknown')}</small>${last?`<span>${money(o.role==='stop'?(last.trigger||last.price):last.price)} · ${h.length} captured states</span>`:''}<details><summary>Order price history</summary>${h.map((x,i)=>`<p>${esc(executionTime(x.time))} IST · ${i===0?'First observed':'Update'} · Limit ${money(x.price)} / Trigger ${money(x.trigger)} · ${esc(x.status)}<small>${esc(x.source)}</small></p>`).join('')}</details></div>`}).join('');
    return `<section class="protection"><div class="planned-levels">${planned}</div><button class="secondary plan-button" data-plan="${esc(t.id)}">Edit planned SL / target</button>${broker||'<p class="muted">No linked SL / target orders. Select an order to confirm its exit purpose.</p>'}${p.plan_history.length?`<details><summary>Planned level history (${p.plan_history.length})</summary>${p.plan_history.map(x=>`<p class="muted">${esc(executionTime(x.time))} IST · ${label(x.role)} ${x.price==null?'cleared':money(x.price)}${x.notes?' · '+esc(x.notes):''}</p>`).join('')}</details>`:''}</section>`;
}
function render(){const s=data.state;$('#connection').textContent='● '+(s.connected?s.stream:'Offline · connect to import');$('#error').textContent=s.error||'';$('#connectButton').textContent=s.connected?'Disconnect':'Connect Dhan ↗';$('#pnl').textContent=money(data.trades.reduce((n,t)=>n+t.pnl,0));$('#pnl').className=data.trades.reduce((n,t)=>n+t.pnl,0)<0?'negative':'positive';$('#tradeCount').textContent=data.trades.length;$('#openCount').textContent=data.trades.filter(t=>t.status==='OPEN').length+' open positions';$('#orderCount').textContent=data.orders.length;$('#eventCount').textContent=data.events+' captured events · all dates';$('#sync').textContent=s.last_sync?new Date(s.last_sync).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata'}):'—';
let trades=[...data.trades,...custom.filter(t=>t.day===data.day)];
$('#tradeGrid').innerHTML=trades.map(t=>{const autoOrders=new Set((t.legs||[]).map(l=>l.order));let assigned=data.orders.filter(o=>editFor(o.id)?.trade===t.id||(!editFor(o.id)&&autoOrders.has(o.id)));return `<article class="trade" data-trade="${esc(t.id)}"><header>${esc(t.symbol||t.name)}<span class="badge">${esc(t.status||'CUSTOM')}</span></header>${t.status?`<div class="gain ${t.pnl<0?'negative':'positive'}">${money(t.pnl)}</div><div class="muted">Gross realized · ${Math.abs(t.net)} quantity open · ${t.direction===1?'Long':'Short'}</div>`:'<p>Manual journal collection</p>'}${tradeTimes(t)}<h4>ASSIGNED ORDERS</h4>${assigned.map(o=>orderCard(o)).join('')||'<p class="muted">Drop orders here to assign</p>'}${t.legs?.length?`<details><summary class="muted">${t.legs.length} execution allocations · FIFO</summary>${t.legs.map(l=>`<p class="muted">${esc(executionTime(l.time))} IST · ${l.partial_exit?'partial exit':esc(l.role)}${l.role==='exit'?' · '+esc(purposeLabel(l.purpose))+(l.breakeven?' · SL at breakeven':'')+' ('+esc(l.purpose_source)+')':''} · ${esc(l.order)} · ${l.qty} @ ${money(l.price)} · ${l.remaining_qty??0} units remain</p>`).join('')}</details>`:''}${protectionCard(t)}</article>`}).join('')||'<div class="empty"><strong>Your next trade starts here.</strong>Connect Dhan to import today’s orders and executions.<br>Trades appear automatically as fills arrive.</div>';
$('#tray').innerHTML=data.orders.map(o=>orderCard(o,true)).join('')||'<div class="empty">No matching intraday NIFTY or SENSEX option orders for this day.</div>';
let q=$('#search').value.toLowerCase();$('#orderRows').innerHTML=data.orders.filter(o=>JSON.stringify(o).toLowerCase().includes(q)).map(o=>`<tr data-order="${esc(o.id)}"><td>${esc((o.time||o.created||'').slice(11,19))}</td><td>${esc(o.symbol)}<small>${esc(o.id)}</small></td><td class="${o.side==='BUY'?'positive':'negative'}">${esc(o.side)}</td><td>${esc(o.status)}</td><td>${esc(o.filled||0)} / ${esc(o.qty)}</td><td>${money(o.price||0)} / ${money(o.trigger||0)}</td><td>${money(o.average||0)}</td></tr>`).join('');}
async function refresh(){try{data=await api('/api/journal?day='+$('#date').value);render();}catch(e){$('#error').textContent=e.message;}}
document.addEventListener('click',async e=>{const close=e.target.closest('[data-close]');if(close)$('#'+close.dataset.close).close();const order=e.target.closest('[data-order]');if(order)openEditor(order.dataset.order);});
document.addEventListener('dragstart',e=>{let o=e.target.closest('[data-order]');if(o)e.dataTransfer.setData('text/plain',o.dataset.order);});
document.addEventListener('dragover',e=>{let t=e.target.closest('[data-trade]');if(t){e.preventDefault();t.classList.add('dragover');}});
document.addEventListener('dragleave',e=>e.target.closest('[data-trade]')?.classList.remove('dragover'));
document.addEventListener('drop',async e=>{let t=e.target.closest('[data-trade]');if(t){e.preventDefault();t.classList.remove('dragover');let id=e.dataTransfer.getData('text/plain');if(data.orders.some(o=>o.id===id))await openEditor(id,t.dataset.trade);}});
let exitAllocations=[];
async function openEditor(id,trade){
    editing=id;const o=data.orders.find(o=>o.id===id),edit=editFor(id);
    $('#editTitle').textContent=o.symbol+' · '+o.id;
    $('#editTrade').innerHTML='<option value="">Unassigned</option>'+[...data.trades,...custom.filter(t=>t.day===data.day)].map(t=>`<option value="${esc(t.id)}">${esc(t.symbol||t.name)} · ${esc(t.id)}</option>`).join('');
    $('#editTrade').value=trade??edit?.trade??data.trades.find(t=>t.legs.some(l=>l.order===id))?.id??'';
    const suggestion=data.trades.flatMap(t=>t.protection?.orders||[]).find(x=>x.order===id);
    const purpose=edit?legacyPurpose(edit):suggestion?.role||(['SL','SLM','STOP_LOSS','STOP_LOSS_MARKET'].includes(o.type)?'stop':String(o.leg)==='3'||o.leg==='TARGET_LEG'?'target':'unknown');
    $('#editPurpose').value=purpose;$('#editBreakeven').checked=!!edit?.breakeven;$('#editBreakeven').disabled=purpose!=='stop';
    $('#positionEffect').textContent=`Calculated effect: ${o.effect||'Unfilled'} · Entry ${o.entry_qty||0} · Exit ${o.exit_qty||0} units${Number(o.filled||0)<Number(o.qty||0)?' · '+(Number(o.qty||0)-Number(o.filled||0))+' units unfilled':''}`;
    exitAllocations=data.trades.flatMap(t=>t.legs.filter(l=>l.order===id&&l.role==='exit').map(l=>({trade:t.id,fill:l.id,leg:l,symbol:t.symbol})));
    $('#allocationEditor').innerHTML=exitAllocations.length?'<h3>Exit execution allocations</h3><p>Override the purpose for an individual closing fill. Entry allocations remain unchanged.</p>'+exitAllocations.map((a,i)=>{const v=(data.allocation_edits||[]).find(x=>x.trade===a.trade&&x.fill===a.fill);return `<fieldset class="allocation"><legend>${esc(a.symbol)} · ${a.leg.qty} units</legend><p>${esc(executionTime(a.leg.time))} IST @ ${money(a.leg.price)} · Current: ${esc(purposeLabel(a.leg.purpose))}${a.leg.breakeven?' · SL at breakeven':''}</p><label>Exit purpose<select data-allocation-purpose="${i}">${purposeOptions(v?.purpose||'inherit')}</select></label><label class="checkbox-label"><input type="checkbox" data-allocation-be="${i}" ${v?.breakeven?'checked':''} ${v?.purpose==='stop'?'':'disabled'}> Stop adjusted to breakeven</label></fieldset>`}).join(''):'<p>No closing executions yet. This default can classify future exits or an unfilled protection order.</p>';
    $('#notes').value=edit?.notes||'';$('#history').textContent='Loading…';$('#editor').showModal();
    try{const events=await api('/api/events/'+encodeURIComponent(id));if(editing!==id)return;$('#history').innerHTML=events.map(e=>`<details><summary>${esc(e.received.slice(11,19))} · ${esc(e.source)}</summary><pre>${esc(JSON.stringify(e.payload,null,2))}</pre></details>`).join('')||'No captured history.';}catch(e){$('#history').textContent=e.message;}
}
$('#editPurpose').onchange=()=>{const stop=$('#editPurpose').value==='stop';$('#editBreakeven').disabled=!stop;if(!stop)$('#editBreakeven').checked=false;};
$('#allocationEditor').onchange=e=>{const i=e.target.dataset.allocationPurpose;if(i===undefined)return;const box=$(`[data-allocation-be="${i}"]`);box.disabled=e.target.value!=='stop';if(box.disabled)box.checked=false;};
$('#editForm').onsubmit=async e=>{e.preventDefault();const button=$('#editForm button[type=submit]');button.disabled=true;try{
    const allocations=exitAllocations.map((a,i)=>({trade:a.trade,fill:a.fill,purpose:$(`[data-allocation-purpose="${i}"]`).value,breakeven:$(`[data-allocation-be="${i}"]`).checked}));
    await api('/api/assign/'+encodeURIComponent(editing),'PUT',{trade:$('#editTrade').value,purpose:$('#editPurpose').value,breakeven:$('#editBreakeven').checked,notes:$('#notes').value,allocations});
    $('#editor').close();$('#saveStatus').textContent='Exit classification saved on server';await refresh();
}catch(e){$('#history').textContent=e.message;}finally{button.disabled=false;}};
$('#connectButton').onclick=async()=>{if(data.state?.connected){await api('/api/disconnect','POST');refresh();}else $('#credentials').showModal();};
$('#credentialForm').onsubmit=async e=>{e.preventDefault();$('#submitConnect').disabled=true;$('#submitConnect').textContent='Importing…';try{await api('/api/connect','POST',{client:$('#client').value.trim(),token:$('#token').value.trim()});$('#token').value='';$('#credentials').close();await refresh();}catch(e){alert(e.message);}finally{$('#submitConnect').disabled=false;$('#submitConnect').textContent='Connect & import today';}};
$('#newTrade').onclick=()=>{let name=prompt('Name this trade collection (e.g. Opening breakout)');if(name?.trim()){custom.push({id:'manual:'+crypto.randomUUID(),name:name.trim(),day:data.day});localStorage.setItem('vcclRecorderCustomTrades',JSON.stringify(custom));render();}};
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-view]').forEach(x=>x.classList.toggle('selected',x===b));$('#board').hidden=b.dataset.view!=='board';$('#orders').hidden=b.dataset.view!=='orders';});$('#date').onchange=refresh;$('#search').oninput=render;refresh();setInterval(refresh,2000);

let planning=null;
document.addEventListener('click',e=>{const b=e.target.closest('[data-plan]');if(!b)return;planning=b.dataset.plan;const t=data.trades.find(t=>t.id===planning);$('#planTitle').textContent=t.symbol;$('#plannedStop').value=t.protection?.planned.stop??'';$('#plannedTarget').value=t.protection?.planned.target??'';$('#planNotes').value='';$('#planError').textContent='';$('#planEditor').showModal();});
$('#planForm').onsubmit=async e=>{e.preventDefault();const t=data.trades.find(t=>t.id===planning), old=t.protection?.planned||{};const button=$('#savePlan');button.disabled=true;try{for(const [role,selector] of [['stop','#plannedStop'],['target','#plannedTarget']]){const value=$(selector).value;const price=value===''?null:Number(value);if(price!==(old[role]??null))await api('/api/plans','POST',{trade:planning,role,price,notes:$('#planNotes').value});}$('#planEditor').close();await refresh();}catch(e){$('#planError').textContent=e.message;}finally{button.disabled=false;}};
