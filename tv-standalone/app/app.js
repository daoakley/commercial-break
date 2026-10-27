(function () {
  'use strict';
  var busy = false, debugOn = false, buttons = ['enable', 'disable', 'debug-toggle', 'appearance-open', 'close'];
  function el(id) { return document.getElementById(id); }
  function call(path, body, done) {
    var x = new XMLHttpRequest();
    x.open(body ? 'POST' : 'GET', 'http://127.0.0.1:18764/' + path, true);
    x.timeout = 2500;
    x.setRequestHeader('Authorization', 'Bearer ' + window.COMMERCIAL_BLOCK_TOKEN);
    if (body) x.setRequestHeader('Content-Type', 'application/json');
    x.onload = function () { try { if (x.status < 200 || x.status >= 300) throw new Error('Request failed'); done(null, JSON.parse(x.responseText)); } catch (e) { done(e); } };
    x.onerror = x.ontimeout = function () { done(new Error('Engine unavailable')); };
    x.send(body ? JSON.stringify(body) : null);
  }
  function render(error, s) {
    if (error) {
      el('status').textContent = 'TV engine unavailable';
      el('detail').textContent = 'The app is installed. Its privileged engine needs restarting after a TV reboot.';
      el('enable').disabled = el('disable').disabled = el('debug-toggle').disabled = true;
      el('debug-detail').textContent = 'Debug status unavailable. A saved 48-hour deadline is checked when the engine restarts.';
      return;
    }
    el('status').textContent = s.enabled ? (s.covered ? 'Commercial blocked' : 'Commercial Break is on') : 'Commercial Break is off';
    el('detail').textContent = s.otherActive ? 'The computer-assisted blocker is active. Stop it before enabling this version.' : s.message;
    el('indicator').style.background = s.enabled ? '#a8d8bc' : '#7d8c83';
    el('matches').textContent = s.matches;
    el('queries').textContent = s.queries;
    el('enable').disabled = s.enabled || s.otherActive;
    el('disable').disabled = !s.enabled;
    el('debug-toggle').disabled = !s.debug;
    debugOn = !!(s.debug && s.debug.enabled);
    el('debug-toggle').textContent = debugOn ? 'Stop debug & clear' : 'Start debug recording';
    el('debug-toggle').setAttribute('aria-checked', debugOn ? 'true' : 'false');
    if (s.debug) {
      var d = s.debug, seconds = d.remainingSeconds || 0;
      var remaining = Math.floor(seconds / 3600) + 'h ' + Math.floor(seconds % 3600 / 60) + 'm remaining';
      el('debug-detail').textContent = debugOn
        ? 'Debug on · ' + remaining + ' · ' + d.records + ' records · ' + Math.round(d.bytes / 1048576) + ' MB. ' + (!s.enabled ? 'Recording pauses while blocking is off. ' : '') + 'Auto-off deletes everything.'
        : 'Debug off. Start a 48-hour review session. Stopping deletes all session pictures and metadata.';
      if (d.error) el('debug-detail').textContent += ' ' + d.error;
    }
  }
  function refresh() { if (!busy) call('status', null, render); }
  function change(path, on) { if (busy) return; busy = true; call(path, { enabled: on }, function (e, s) { busy = false; render(e, s); }); }
  el('enable').onclick = function () { change('control', true); };
  el('disable').onclick = function () { change('control', false); };
  el('debug-toggle').onclick = function () { change('debug', !debugOn); };
  el('close').onclick = function () { try { tizen.application.getCurrentApplication().exit(); } catch (e) {} };
  document.addEventListener('keydown', function (e) {
    if (document.getElementById('appearance-panel') && !document.getElementById('appearance-panel').hidden) return;
    if (e.keyCode === 10009 || e.keyCode === 27) { el('close').click(); return; }
    if ([37, 38, 39, 40].indexOf(e.keyCode) < 0) return;
    e.preventDefault();
    var available = buttons.filter(function (id) { return !el(id).disabled; });
    var i = available.indexOf(document.activeElement.id), d = (e.keyCode === 37 || e.keyCode === 38) ? -1 : 1;
    el(available[(i + d + available.length) % available.length]).focus();
  });
  el('close').focus(); refresh(); setInterval(refresh, 2000);
})();
