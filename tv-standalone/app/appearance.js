(function () {
  'use strict';
  var themes = window.CommercialBreakThemes, selected = 'default', saved = 'default', group = 'Original', busy = false;
  var previewOnly = window.CB_THEME_PREVIEW === true, opener = null;
  var panel = document.createElement('section');
  panel.id = 'appearance-panel'; panel.hidden = true; panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-modal', 'true'); panel.setAttribute('aria-labelledby', 'appearance-title');
  panel.innerHTML = '<div class="appearance-shell"><header class="appearance-header"><div><p class="appearance-eyebrow">COMMERCIAL BREAK / APPEARANCE</p><h1 id="appearance-title">Make the break yours.</h1><p class="appearance-subtitle">A little stillness, in your own style.</p></div><button id="appearance-close" class="appearance-secondary">Close <span aria-hidden="true">×</span></button></header><div class="appearance-layout"><div class="appearance-feature"><div class="appearance-canvas-wrap"><canvas id="appearance-preview" width="1920" height="1080" role="img" aria-label="Break screen preview"></canvas><span class="appearance-preview-tag">PREVIEW</span></div><div class="appearance-caption"><div><p id="appearance-category"></p><h2 id="appearance-name"></h2><p id="appearance-description"></p></div><span class="appearance-still">Still scene · On your TV</span></div><p id="appearance-note" aria-live="polite"></p></div><div class="appearance-library"><div id="appearance-groups" role="tablist" aria-label="Theme collections"></div><div id="appearance-options" role="group" aria-label="Themes"></div></div></div><footer class="appearance-footer"><div><span class="appearance-dot"></span><span id="appearance-saved">Original is your current theme</span><p>The show keeps playing. Your choice appears on the next break.</p></div><div class="appearance-actions"><button id="appearance-original" class="appearance-secondary">Keep Original</button><button id="appearance-save">Use this theme <span aria-hidden="true">↗</span></button></div></footer></div>';
  document.body.appendChild(panel);
  function el(id) { return document.getElementById(id); }
  function byId(id) { for (var i=0;i<themes.length;i++) if (themes[i].id===id) return themes[i]; return themes[0]; }
  function color(value) { return 'rgba('+parseInt(value.slice(1,3),16)+','+parseInt(value.slice(3,5),16)+','+parseInt(value.slice(5,7),16)+','+(value.length===9?parseInt(value.slice(7,9),16)/255:1)+')'; }
  function draw(canvas, scene) {
    var c=canvas.getContext('2d'); c.clearRect(0,0,canvas.width,canvas.height); c.save(); c.scale(canvas.width/1920,canvas.height/1080);
    scene.objects.forEach(function(o) {
      c.fillStyle=c.strokeStyle=color(o.color||'#FFFFFFFF'); c.beginPath();
      if(o.type==='rectangle') c.fillRect(o.x,o.y,o.width,o.height);
      else if(o.type==='ellipse') { c.save(); c.translate(o.x+o.width/2,o.y+o.height/2);c.scale(o.width/2,o.height/2);c.arc(0,0,1,0,Math.PI*2);c.fill();c.restore(); }
      else if(o.type==='polygon') { o.points.forEach(function(p,i){if(i)c.lineTo(p.x,p.y);else c.moveTo(p.x,p.y);});c.closePath();c.fill(); }
      else if(o.type==='line') { c.moveTo(o.x1,o.y1);c.lineTo(o.x2,o.y2);c.lineWidth=1.5;c.stroke(); }
      else if(o.type==='textblock') { c.font='400 '+o.size+'px SamsungOne, Arial, sans-serif';c.textAlign='center';c.textBaseline='middle';c.fillText(o.text,o.x+o.width/2,o.y+o.height/2,o.width); }
    });
    if(scene.infoMode==='clock') {
      var now=new Date(),hour=now.getHours();
      c.fillStyle='#D8DEDA';c.font='400 36px SamsungOne, Arial, sans-serif';c.textAlign='right';c.textBaseline='top';
      c.fillText((hour%12||12)+':'+('0'+now.getMinutes()).slice(-2)+' '+(hour<12?'AM':'PM'),1800,76);
    }
    c.restore();
  }
  function notify(message) { el('appearance-note').textContent=message; }
  function request(path, body, done) {
    if(previewOnly) { done(null,{appearance:{theme:body?body.theme:saved}}); return; }
    var x=new XMLHttpRequest();x.open(body?'POST':'GET','http://127.0.0.1:18764/'+path,true);x.timeout=2500;
    x.setRequestHeader('Authorization','Bearer '+window.COMMERCIAL_BLOCK_TOKEN);
    if(body)x.setRequestHeader('Content-Type','application/json');
    x.onload=function(){try{if(x.status<200||x.status>=300)throw new Error();done(null,JSON.parse(x.responseText));}catch(e){done(new Error('Could not confirm the setting. Reopen Break screen to check the saved theme.'));}};
    x.onerror=x.ontimeout=function(){done(new Error('TV engine unavailable. Reopen Break screen to check the saved theme.'));};
    x.send(body?JSON.stringify(body):null);
  }
  function render() {
    var t=byId(selected);draw(el('appearance-preview'),t.scene);
    el('appearance-name').textContent=t.name;el('appearance-category').textContent=t.category.toUpperCase();el('appearance-description').textContent=t.description;
    el('appearance-preview').setAttribute('aria-label',t.name+' — '+t.description);
    el('appearance-saved').textContent=byId(saved).name+' is your current theme';
    el('appearance-save').disabled=busy;
    var options=el('appearance-options');options.innerHTML='';
    themes.filter(function(x){return x.category===group;}).forEach(function(x){
      var b=document.createElement('button');b.className='appearance-choice';b.setAttribute('aria-pressed',String(x.id===selected));b.setAttribute('aria-label',x.name);b.dataset.theme=x.id;
      var canvas=document.createElement('canvas');canvas.width=320;canvas.height=180;canvas.setAttribute('aria-hidden','true');b.appendChild(canvas);draw(canvas,x.scene);
      var label=document.createElement('span');label.textContent=x.name;b.appendChild(label);
      var check=document.createElement('i');check.textContent=x.id===selected?'✓':'';check.setAttribute('aria-hidden','true');b.appendChild(check);
      b.onclick=function(){selected=x.id;notify(previewOnly?'Design preview only. The TV is unchanged.':'Previewing '+x.name+'. Select “Use this theme” to save.');render();panel.querySelector('[data-theme="'+x.id+'"]').focus();};options.appendChild(b);
    });
    Array.prototype.forEach.call(el('appearance-groups').children,function(b){b.setAttribute('aria-selected',String(b.textContent===group));});
  }
  ['Original','Seasons','US holidays','Zen','City skylines'].forEach(function(name){var b=document.createElement('button');b.textContent=name;b.setAttribute('role','tab');b.onclick=function(){group=name;render();};el('appearance-groups').appendChild(b);});
  function close() { if(busy)return;panel.hidden=true;var main=document.querySelector('main');if(main)main.removeAttribute('aria-hidden');if(opener)opener.focus(); }
  function open() {
    opener=document.activeElement;selected=saved;group=byId(selected).category;panel.hidden=false;var main=document.querySelector('main');if(main)main.setAttribute('aria-hidden','true');
    notify(previewOnly?'Design preview only. Nothing here changes your TV.':'Loading your saved appearance…');render();el('appearance-close').focus();
    request('status',null,function(error,s){if(panel.hidden)return;if(error){notify(error.message);return;}saved=byId(s.appearance&&s.appearance.theme||'default').id;selected=saved;group=byId(saved).category;render();notify(previewOnly?'Design preview only. Nothing here changes your TV.':'Your current graphic stays in place until you save a new choice.');});
  }
  el('appearance-close').onclick=close;
  el('appearance-original').onclick=function(){selected='default';group='Original';render();notify('Original preview. Select “Use this theme” to restore it.');};
  el('appearance-save').onclick=function(){if(busy)return;busy=true;el('appearance-save').disabled=true;var choice=selected;
    request('appearance',{theme:choice},function(error,s){busy=false;if(error){notify(error.message);el('appearance-save').disabled=false;return;}saved=byId(s.appearance&&s.appearance.theme||choice).id;render();notify(previewOnly?'Preview selection saved. The TV has not been changed.':'Saved. '+byId(saved).name+' will appear on the next commercial break.');el('appearance-save').focus();});
  };
  document.addEventListener('keydown',function(e){
    if(panel.hidden)return;
    if(e.keyCode===27||e.keyCode===10009){e.preventDefault();e.stopImmediatePropagation();close();return;}
    if([37,38,39,40,9].indexOf(e.keyCode)<0)return;
    e.preventDefault();e.stopImmediatePropagation();
    var all=Array.prototype.slice.call(panel.querySelectorAll('button')).filter(function(b){return !b.disabled&&b.getClientRects().length;});
    var current=document.activeElement,i=all.indexOf(current);
    if(e.keyCode===9){all[(i+(e.shiftKey?-1:1)+all.length)%all.length].focus();return;}
    if(i<0){all[0].focus();return;}
    var r=current.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2,best=null,distance=Infinity;
    all.forEach(function(b){if(b===current)return;var q=b.getBoundingClientRect(),dx=q.left+q.width/2-x,dy=q.top+q.height/2-y;
      var horizontal=e.keyCode===37||e.keyCode===39,forward=horizontal?dx:dy,side=horizontal?dy:dx;
      if((e.keyCode===37||e.keyCode===38)?forward>=-2:forward<=2)return;
      var d=Math.abs(forward)+Math.abs(side)*2;if(d<distance){best=b;distance=d;}
    });if(best){best.focus();best.scrollIntoView({block:'nearest'});}
  },true);
  setInterval(function(){if(!panel.hidden)draw(el('appearance-preview'),byId(selected).scene);},30000);
  window.CBAppearance={open:open,draw:draw};
  if(el('appearance-open'))el('appearance-open').onclick=open;
  if(previewOnly){open();el('appearance-close').textContent='Back to preview';}
})();
