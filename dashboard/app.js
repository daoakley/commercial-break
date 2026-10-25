if(location.protocol==='file:')location.replace('http://127.0.0.1:8792/');
const $ = id => document.getElementById(id);
const markerNames = {start:'Window started',ad:'Ad starts',program:'Program resumes',uncertain:'Unsure / missed it',channel_changed:'Channel changed',undo:'Marker undone',end:'Window ended',extend:'Added five minutes'};
let snapshot=null, serverReceivedAt=0, busy=false, connected=false;
function render(data){
  snapshot=data; serverReceivedAt=performance.now(); connected=true;
  if(data.active&&data.channel_context){for(const k of ['source','channel','show'])if(!$(k).value&&data.channel_context[k])$(k).value=data.channel_context[k];}
  document.body.classList.remove('offline'); $('connection').textContent='Connected · local only';
  $('setup').hidden=!!data.active;
  const states={ad:'Commercial break',program:'Program / game',uncertain:'Uncertain — confirm when ready',idle:'No window running'};
  $('current').textContent=states[data.state];
  $('phase').textContent=data.active?'Observation window':(data.events.length?'Window complete':'Ready when you are');
  for(const id of ['ad','program','uncertain','channel_changed','undo','end','extend']) $(id).disabled=!data.active||busy;
  $('start').disabled=busy;
  const log=$('events'); log.replaceChildren();
  for(const e of [...data.events].reverse()){
    const li=document.createElement('li'),text=document.createElement('span'),t=document.createElement('time');
    text.textContent=markerNames[e.kind]||e.kind;
    if(e.kind==='end'&&['five_minutes','window_elapsed'].includes(e.reason)) text.textContent='Observation window complete';
    if(e.kind==='start'&&e.context) text.textContent+=' · '+e.context;
    if(data.undone.includes(e.id)) li.className='undone';
    const at=e.client_unix_ms||e.effective_unix_ms||e.received_unix_ms;
    t.textContent=new Date(at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
    li.append(text,t);log.append(li);
  }
  if(!data.events.length){const li=document.createElement('li');li.textContent='No observations yet.';log.append(li);}
  if(data.live){
    const live=data.live, name=live.show?.name;
    $('live-title').textContent=name?`${live.show.source==='vision_inference'?'Likely: ':''}${name}`:'Identifying the current show';
    $('live-source').textContent=[live.source,live.channel?.name,live.category?.value!=='unknown'?live.category?.value:null].filter(Boolean).join(' · ');
    $('live-state').textContent=live.covered?'Commercial Break active':'Cover off';
    $('live-observed').textContent=live.first_observed?`First observed ${new Date(live.first_observed*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'})}`:'Waiting for a program observation';
    $('live-native').textContent=`Native starts received: ${live.native_metrics?.accepted_starts||0} · Used: ${live.native_metrics?.used_starts||0}`;
    if(name&&!$('show').value)$('show').placeholder=name;
  }else if('live' in data){
    $('live-title').textContent='Live context unavailable';$('live-state').textContent='Waiting for current TV data';
    $('live-source').textContent='Saved study history remains available below.';
    $('live-observed').textContent='';$('live-native').textContent='';
  }
  renderDashboard(data);drawTimeline(data);tick();
}
function tick(){
  const left=snapshot?.active?Math.max(0,snapshot.remaining_seconds-(performance.now()-serverReceivedAt)/1000):(snapshot?.events.length?0:Number($('duration').value));
  const n=Math.ceil(left);$('timer').textContent=`${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`;
  if(snapshot?.active&&left<=0){for(const id of ['ad','program','uncertain','channel_changed','undo','end','extend']) $(id).disabled=true;}
}
function offline(){connected=false;document.body.classList.add('offline');$('connection').textContent='Disconnected — clicks are not saved';
  for(const id of ['start','ad','program','uncertain','channel_changed','undo','end','extend']) $(id).disabled=true;
}
async function refresh(){if(busy)return;try{const r=await fetch('/state',{cache:'no-store',signal:AbortSignal.timeout(2000)});if(!r.ok)throw Error();render(await r.json());}catch{offline();}}
async function mark(kind){
  if(busy||!connected)return;
  const payload={kind,request_id:crypto.randomUUID(),client_unix_ms:Date.now(),client_monotonic_ms:performance.now(),context:$('context').value,initial_state:$('initial').value,duration_seconds:Number($('duration').value),source:$('source').value,channel:$('channel').value,show:$('show').value,new_show:$('new_show').checked};
  if($('show_start').value)payload.show_start_ms=new Date($('show_start').value).getTime();
  busy=true;
  try{
    const r=await fetch('/mark',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:AbortSignal.timeout(3000)});
    const data=await r.json();if(!r.ok)throw Error(data.error||'Marker was not saved.');
    busy=false;render(data);if(kind==='start')$('new_show').checked=false;$('feedback').textContent=kind==='start'?'Window started. Watch the TV and mark each transition.':`${markerNames[kind]} — saved.`;
  }catch(e){busy=false;$('feedback').textContent=`Not confirmed: ${e.message} Check the event list before repeating.`;await refresh();}
}
for(const id of ['start','ad','program','uncertain','channel_changed','undo','end','extend']) $(id).addEventListener('click',()=>mark(id));
document.addEventListener('keydown',e=>{if(e.repeat||e.ctrlKey||e.metaKey||e.altKey||['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)||!snapshot?.active)return;
  const key=e.key.toLowerCase();if(key==='a'||key==='p'){e.preventDefault();mark(key==='a'?'ad':'program');}});
setInterval(tick,100);setInterval(refresh,1000);refresh();

function drawTimeline(data){
  const svg=$('timeline');svg.replaceChildren();
  const create=(tag,attrs,text)=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;svg.append(e);return e;};
  const rows=(data.chart_events||data.events).filter(e=>!(data.chart_undone||data.undone).includes(e.id));
  const start=rows.find(e=>e.kind==='start');
  $('show-name').textContent=data.channel_context?.show||start?.context||'Your viewing timeline';
  $('show-context').textContent=data.channel_context?.channel?`${data.channel_context.source} · ${data.channel_context.channel} · viewer-confirmed identity`:(start?'Unassigned window — add channel and show for the next one':'Start a window to build a baseline.');
  $('show-start').textContent=data.channel_context?.show_start_ms?new Date(data.channel_context.show_start_ms).toLocaleTimeString([],{hour:'numeric',minute:'2-digit'}):'Not confirmed';
  const begin=start?.received_unix_ms||data.server_unix_ms;
  const starts=rows.filter(e=>e.kind==='start');const lastStart=starts.at(-1);
  const ended=rows.find(e=>e.kind==='end'&&e.session_id===lastStart?.session_id);
  const windowLimit=s=>(s?.received_unix_ms||begin)+((s?.duration_seconds||300)+rows.filter(e=>e.session_id===s?.session_id&&e.kind==='extend').reduce((n,e)=>n+(e.added_seconds||0),0))*1000;
  const stop=Math.min(windowLimit(lastStart),ended?(ended.effective_unix_ms||ended.received_unix_ms):data.server_unix_ms);
  const span=Math.max(300000,stop-begin);
  const x=t=>Math.max(83,Math.min(570,83+(t-begin)/span*487));
  for(let i=0;i<=5;i++){const px=83+i/5*487;create('line',{x1:px,y1:21,x2:px,y2:114,class:'grid'});create('text',{x:px,y:139,'text-anchor':i===0?'start':i===5?'end':'middle'},start?new Date(begin+i/5*span).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):`${i}:00`);}
  create('text',{x:0,y:47},'Content');create('text',{x:0,y:93},'TV cover');
  create('rect',{x:83,y:28,width:487,height:28,rx:5,class:'track'});create('rect',{x:83,y:77,width:487,height:20,rx:4,class:'track'});
  const segments=[];let adTotal=0;const gaps=[];
  const timeOf=e=>Math.abs((e.client_unix_ms||e.received_unix_ms)-e.received_unix_ms)<=2000?(e.client_unix_ms||e.received_unix_ms):e.received_unix_ms;
  for(const windowStart of starts){
   let state=windowStart.initial_state,at=windowStart.received_unix_ms,breakStart=state==='ad'?at:null;const breaks=[];
   const windowRows=rows.filter(e=>e.session_id===windowStart.session_id),windowEnd=windowRows.find(e=>e.kind==='end');
   const until=Math.min(windowLimit(windowStart),windowEnd?(windowEnd.effective_unix_ms||windowEnd.received_unix_ms):data.server_unix_ms);
   for(const e of windowRows){if(!['ad','program','uncertain','channel_changed'].includes(e.kind))continue;const t=Math.max(at,Math.min(until,timeOf(e)));segments.push({a:at,b:t,state});
    if(e.kind==='ad'&&state!=='ad')breakStart=t;
    if(e.kind==='program'&&state==='ad'&&breakStart!==null){breaks.push([breakStart,t]);breakStart=null;}
    if(e.kind==='uncertain'||e.kind==='channel_changed'){gaps.push(...breaks.slice(1).map((b,i)=>(b[0]-breaks[i][1])/60000));breaks.length=0;breakStart=null;if(e.kind==='uncertain'&&segments.length)segments[segments.length-1].state='uncertain';}
    state=e.kind==='channel_changed'?'uncertain':e.kind;at=t;}
   segments.push({a:at,b:Math.max(at,until),state});
   gaps.push(...breaks.slice(1).map((b,i)=>(b[0]-breaks[i][1])/60000));
  }
  for(const s of segments){if(s.b<=s.a)continue;if(s.state==='ad')adTotal+=s.b-s.a;const r=create('rect',{x:x(s.a),y:28,width:Math.max(.5,x(s.b)-x(s.a)),height:28,rx:2,class:s.state});const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=`${s.state}: ${new Date(s.a).toLocaleTimeString()}–${new Date(s.b).toLocaleTimeString()} · viewer labels`;r.append(title);}
  const covers=data.cover_samples||[];let known=0;
  for(let i=0;i<covers.length;i++){const a=covers[i],next=covers[i+1];if(a.received_unix_ms<begin||a.received_unix_ms>stop)continue;known++;
    if(a.cover_active!==true)continue;const b=Math.min(stop,next?.received_unix_ms||a.received_unix_ms+2000,a.received_unix_ms+2500);if(b<=a.received_unix_ms)continue;
    const r=create('rect',{x:x(a.received_unix_ms),y:77,width:Math.max(.5,x(b)-x(a.received_unix_ms)),height:20,rx:1,class:'cover'});const title=document.createElementNS(svg.namespaceURI,'title');title.textContent='TV cover process active with a valid lease and no pause flag; sampled state, not direct display verification.';r.append(title);}
  if(!known)create('text',{x:326,y:91,'text-anchor':'middle'},'Awaiting TV status');
  if(start&&data.active)create('line',{x1:x(stop),x2:x(stop),y1:17,y2:115,class:'now'});
  $('break-gap').textContent=gaps.length>=3?`${(gaps.reduce((a,b)=>a+b,0)/gaps.length).toFixed(1)} min`:(gaps.length?`Learning · ${gaps.length} gap${gaps.length===1?'':'s'}`:'Learning');
  $('chart-source').textContent=starts.length?`${starts.length} window${starts.length===1?'':'s'} · viewer labels`:'Your observations';
  $('ad-time').textContent=start?`${Math.round(adTotal/1000)} sec`:'—';
  $('timeline-note').textContent=known?'Content = your observations. Cover = sampled TV state; short flashes may fall between samples.':'Content = your observations. The cover strip stays empty until TV status is available; it does not infer coverage from an ad label.';
}

let captureState=null, shownImage=null, displayMode='latest', latestFrame=null, latestError='';
const formatTime=value=>value?new Date(value*1000).toLocaleTimeString([],{hour:'numeric',minute:'2-digit',second:'2-digit'}):'Not available';
function detailRows(target, rows){
  const root=$(target);root.replaceChildren();
  for(const [name,value] of rows){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=name;dd.textContent=value??'Not available';root.append(dt,dd);}
}
function renderDashboard(data){
  if('native' in data)renderNative(data.native);
  if('capture' in data)renderCapture(data.capture);
  if(!('live' in data))return;
  const live=data.live;
  if(!live){$('data-freshness').textContent='Detector unavailable — no live status received.';detailRows('live-details',[]);return;}
  $('data-freshness').textContent=live.fresh?`Connected · last frame ${Math.round(live.frame_age_seconds)} seconds ago · status refreshes every 2 seconds`:
    live.connected?'Detector connected, but TV frames are stale. Values below are last known.':'Detector disconnected. Values below are last known.';
  if(!live.fresh)$('live-state').textContent='Last known context · data stale';
  else $('live-state').textContent=live.covered?'Blocker reports cover requested':'Blocker reports cover off';
  if(!('native' in data))$('live-native').textContent='Waiting for YouTube metadata';
  const forecast=p=>p?.unix_range?`${formatTime(p.unix_range[0])}–${formatTime(p.unix_range[1])} (estimate)`:'Still learning';
  detailRows('live-details',[
    ['TV application',live.source],['Channel',live.channel?.name||'Not identified'],
    ['Show identity',live.show?.name?`${live.show.source==='vision_inference'?'Inferred':'Supplied metadata'}${live.show.confidence?` · ${Math.round(live.show.confidence*100)}% confidence`:''}`:'Not identified'],
    ['Category',live.category?.value||'Unknown'],['Broadcast start',formatTime(live.broadcast_start)],
    ['First observed',formatTime(live.first_observed)],['Last ad seen',formatTime(live.last_ad)],
    ['Last break ended',formatTime(live.last_break_end)],['Next break',forecast(live.predicted_next_break)],
    ['Expected break end',forecast(live.predicted_break_end)],['Frame number',live.frame_sequence],
    ['Playback generation',live.epoch]
  ]);
}
function renderCapture(state){
  captureState=state;
  const pending=state.phase==='capturing';$('capture').disabled=pending;
  $('capture').textContent=pending?'Capturing…':'Capture displayed screen';
  if(state.tv){const tv=state.tv;
    $('tv-read-time').textContent=`Read at ${formatTime(tv.observed_unix)} · snapshot, not a live feed`;
    detailRows('tv-details',[
      ['Foreground app',tv.app||'Unknown'],['Helper heartbeat',tv.heartbeat_age_seconds>=0?`${tv.heartbeat_age_seconds}s old at capture`:'Not available'],
      ['Cover process + lease',tv.cover_active?'Active':'Inactive'],['Capture pause flag',tv.capture_pause_active?'Active':'Inactive'],
      ['TV mute',tv.muted===true?'Muted':tv.muted===false?'Not muted':'Unknown']
    ]);
  }
  if(displayMode!=='screen'){if(latestFrame)renderLatestAge();return;}
  if(state.image_id&&state.image_id!==shownImage){
    shownImage=state.image_id;const url='/screen.png?v='+encodeURIComponent(state.image_id);
    $('screen-image').src=url;$('screen-image').hidden=false;$('screen-placeholder').hidden=true;
    $('screen-open').href=url;$('screen-open').hidden=false;
  }
  const previous=state.image_id?`Image received ${formatTime(state.captured_unix)} · ${state.width} × ${state.height} · ${state.duration_seconds}s request`:'';
  $('capture-status').textContent=pending?`Requesting fresh screen… ${Math.max(0,Math.floor(Date.now()/1000-state.started_unix))}s / 30s${previous?' · Showing previous image':''}`:
    state.phase==='error'?`${state.error}${previous?' Previous '+previous.toLowerCase():''}`:previous||'On demand · no automatic screenshots';

}
$('capture').addEventListener('click',async()=>{
  displayMode='screen';shownImage=null;
  $('screen-open').removeAttribute('download');$('screen-open').textContent='Open full image ↗';
  $('capture').disabled=true;$('capture-status').textContent='Sending capture request…';
  try{
    const r=await fetch('/capture',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(3000)});
    if(!r.ok)throw Error();renderCapture(await r.json());
  }catch{$('capture').disabled=false;$('capture-status').textContent='Dashboard not reachable. Reconnect and try again; the TV has not been changed.';}
});
$('screen-image').addEventListener('error',()=>{$('capture-status').textContent='Screenshot could not be displayed. Try another capture.';});

function renderLatestAge(){
  if(!latestFrame||displayMode!=='latest'||latestError)return;
  const age=Math.max(0,Math.floor(Date.now()/1000-latestFrame.received_unix));
  $('capture-status').textContent=`Incoming frame ${latestFrame.sequence||''} · received ${formatTime(latestFrame.received_unix)} · ${age}s old${age>45?' · STALE':''} · ${latestFrame.load_ms}ms to load`;
}
$('latest-frame').addEventListener('click',async()=>{
  displayMode='latest';latestError='';$('latest-frame').disabled=true;$('capture-status').textContent='Loading the latest received frame…';
  const started=performance.now();
  try{
    const r=await fetch('/latest-frame',{cache:'no-store',signal:AbortSignal.timeout(3000)}),data=await r.json();
    if(!r.ok)throw Error(data.error||'Frame unavailable');
    latestFrame={...data,load_ms:Math.round(performance.now()-started)};
    const url='data:image/png;base64,'+data.image;
    $('screen-image').src=url;$('screen-image').hidden=false;$('screen-placeholder').hidden=true;
    $('screen-open').href=url;$('screen-open').download='commercial-break-frame.png';$('screen-open').textContent='Save frame';$('screen-open').hidden=false;
    renderLatestAge();
  }catch(e){latestError=e.message;$('capture-status').textContent=latestError+'. Any displayed image is from the previous request.';}
  finally{$('latest-frame').disabled=false;}
});
setInterval(renderLatestAge,1000);

function durationText(value){
  if(value===undefined||value===null)return 'Not supplied';
  const n=Math.round(value),h=Math.floor(n/3600),m=Math.floor(n%3600/60),s=n%60;
  return h?`${h}h ${m}m ${s}s`:`${m}m ${s}s`;
}
function renderNative(native){
  const states={paused_after_failures:'Paused after a connection or app stability issue',disabled_for_stability:'Disabled while investigating app exits',connecting:'Connecting…',connected:'Connected',reconnecting:'Reconnecting…',disconnected:'Disconnected',waiting_for_youtube_tv:'Waiting for YouTube TV',another_observer_active:'Another observer is active'};
  $('native-state').textContent=(states[native.connection]||'Unavailable')+(native.event_age_seconds!=null?` · ${Math.round(native.event_age_seconds)}s since event`:'');
  if(native.connection==='connected'&&!native.fresh)$('native-state').textContent+=' · stale';
  const rows=[];
  if(native.playback_reference)rows.push(['Playback reference',native.playback_reference]);
  if(native.player_state!==undefined){
    const stateNames={'1':'Playback active','2':'Paused','3':'Buffering','0':'Ended','1081':'Inserted-ad playback signal'};
    rows.push(['YouTube state',stateNames[native.player_state]||`State ${native.player_state}`]);
  }
  if(native.position_seconds!=null)rows.push(['Playback position',durationText(native.position_seconds)],['Position measured',formatTime(native.position_observed_unix)]);
  if(native.duration_seconds!=null)rows.push(['Reported duration',durationText(native.duration_seconds)]);
  if(native.seekable_start_seconds!=null&&native.seekable_end_seconds!=null)rows.push(['Seekable range',`${durationText(native.seekable_start_seconds)} – ${durationText(native.seekable_end_seconds)}`]);
  if(native.playback_reference)rows.push(['This content first seen',formatTime(native.content_first_seen_unix)],['Content changes observed',native.content_changes]);
  if(native.ad_events!==undefined)rows.push(['Inserted-ad events',native.ad_events]);
  if(native.connections!==undefined)rows.push(['Connection attempts',native.connections],['Poll timeouts recovered',native.poll_timeouts??0]);
  if(native.last_inserted_ad_unix)rows.push(['Last inserted-ad event',formatTime(native.last_inserted_ad_unix)],['Ad reference',native.ad_reference],['Reported ad/pod time',durationText(native.ad_duration_reported)]);
  detailRows('native-details',rows);
  $('live-native').textContent=native.fresh?'YouTube metadata connected · observation only':'YouTube metadata: '+(states[native.connection]||'Unavailable').toLowerCase();
}
