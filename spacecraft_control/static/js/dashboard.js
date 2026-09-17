/* AURORA ground console. Server is authoritative; no telemetry polling. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const all = (query) => [...document.querySelectorAll(query)];
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const fmt = (value, digits = 1) => typeof value === 'number' ? value.toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits}) : String(value ?? '—');
  const elapsed = (seconds) => { const n = Math.floor(seconds || 0); return [Math.floor(n / 3600), Math.floor(n / 60) % 60, n % 60].map(v => String(v).padStart(2,'0')).join(':'); };
  const utc = (date) => date ? new Date(date).toISOString().slice(11,19) : '--:--:--';
  const severityClass = (s) => ({WARNING:'amber-text', CRITICAL:'red-text', AUTO_ACTION:'blue-text', RECOVERY:'green-text', INFO:'muted', COMMAND:'blue-text'}[s] || 'muted');
  const severityDot = (s) => ({WARNING:'amber', CRITICAL:'red', AUTO_ACTION:'blue', RECOVERY:'green'}[s] || 'gray');
  const state = {connected:false, frame:null, status:null, history:[], events:[], commands:[], incidents:[], alarms:[], group:'power', log:'events', selectedIncident:null, incidentEvents:[], lastReceived:0, runId:null, charts:[]};
  const CHARTS = {
    power: [
      {title:'Battery charge', unit:'%', keys:['battery_charge_percent'], labels:['State of charge'], colors:['#7bbaa9'], min:0, max:100},
      {title:'Bus voltage', unit:'V', keys:['battery_voltage'], labels:['Battery voltage'], colors:['#9cb7dd']},
      {title:'Power balance', unit:'W', keys:['power_generation','power_consumption'], labels:['Generation','Consumption'], colors:['#7bbaa9','#d3b477'], min:0},
    ],
    thermal: [
      {title:'OBC temperature', unit:'°C', keys:['obc_temperature'], labels:['OBC · critical ≥ 80°C'], colors:['#93b4d2']},
      {title:'Payload temperature', unit:'°C', keys:['payload_temperature'], labels:['Payload · critical ≥ 85°C'], colors:['#d3b477']},
      {title:'Thermal environment', unit:'°C', keys:['battery_temperature','external_temperature'], labels:['Battery','External'], colors:['#7bbaa9','#889bd0']},
    ],
    attitude: [
      {title:'Reaction wheel', unit:'rpm', keys:['reaction_wheel_rpm'], labels:['Wheel · critical ≥ 7,200 rpm'], colors:['#93b4d2'], min:0},
      {title:'Signal strength', unit:'dBm', keys:['signal_strength'], labels:['Received signal strength'], colors:['#7bbaa9']},
      {title:'Packet loss', unit:'%', keys:['packet_loss'], labels:['Packet loss · critical ≥ 20%'], colors:['#d3b477'], min:0},
    ],
    computer: [
      {title:'CPU load', unit:'%', keys:['cpu_load'], labels:['Processor utilization'], colors:['#93b4d2'], min:0, max:100},
      {title:'Memory & storage', unit:'%', keys:['memory_usage','storage_usage'], labels:['Memory','Storage'], colors:['#7bbaa9','#889bd0'], min:0, max:100},
      {title:'Science data buffer', unit:'%', keys:['data_buffer_usage'], labels:['Buffer utilization'], colors:['#d3b477'], min:0, max:100},
    ],
  };

  function createCharts() {
    state.charts.forEach(chart => chart.destroy());
    Chart.defaults.color = '#667b90';
    Chart.defaults.font.family = "'SFMono-Regular', Consolas, monospace";
    Chart.defaults.font.size = 8;
    state.charts = CHARTS[state.group].map((spec, index) => {
      $(`chart-title-${index}`).textContent = spec.title;
      $(`chart-${index}`).setAttribute('aria-label', `${spec.title}, ${spec.unit}, last 120 telemetry frames`);
      $(`chart-legend-${index}`).innerHTML = spec.labels.map((label, i) => `<span style="--legend-color:${spec.colors[i]}">${label}</span>`).join('');
      return new Chart($(`chart-${index}`), {
        type:'line',
        data: {labels:[], datasets:spec.keys.map((key, i) => ({label:spec.labels[i], data:[], borderColor:spec.colors[i], backgroundColor:spec.colors[i]+'0c', borderWidth:1.5, pointRadius:0, pointHitRadius:10, tension:0.25, fill:i === 0}))},
        options: {responsive:true, maintainAspectRatio:false, animation:false, normalized:true,
          interaction:{mode:'index', intersect:false},
          plugins:{legend:{display:false}, tooltip:{backgroundColor:'#1c2a38', titleColor:'#a8bacb', bodyColor:'#d4e0eb', borderColor:'#3a5066', borderWidth:1, padding:10, displayColors:true, callbacks:{label:ctx => ` ${spec.labels[ctx.datasetIndex].split(' · ')[0]}: ${fmt(ctx.parsed.y, spec.unit === 'rpm' ? 0 : 1)} ${spec.unit}`}}},
          scales:{x:{grid:{display:false}, border:{display:false}, ticks:{maxTicksLimit:5, maxRotation:0, autoSkip:true, padding:6}}, y:{min:spec.min, max:spec.max, grace:'10%', border:{display:false}, grid:{color:'#25313d80', drawTicks:false}, ticks:{maxTicksLimit:4, padding:7}}},
        },
      });
    });
    updateCharts();
  }

  function updateCharts() {
    state.charts.forEach((chart, index) => {
      const spec = CHARTS[state.group][index];
      chart.data.labels = state.history.map(frame => elapsed(frame.mission_elapsed_time));
      chart.data.datasets.forEach((dataset, i) => { dataset.data = state.history.map(frame => frame[spec.keys[i]]); });
      chart.update('none');
      if (state.frame) $(`chart-value-${index}`).textContent = spec.keys.map(key => fmt(state.frame[key], spec.unit === 'rpm' ? 0 : 1)).join(' / ') + ' ' + spec.unit;
    });
  }

  function renderTelemetry(frame, addHistory = true) {
    state.frame = frame;
    state.lastReceived = Date.now();
    if (frame.run_id !== state.runId) { state.runId = frame.run_id; state.history = []; }
    if (addHistory) {
      const last = state.history[state.history.length - 1];
      if (last?.telemetry_sequence_number === frame.telemetry_sequence_number) state.history[state.history.length-1] = frame;
      else state.history.push(frame);
      state.history = state.history.slice(-120);
    }
    all('[data-value]').forEach(node => {
      const key = node.dataset.value;
      const digits = ['reaction_wheel_rpm','downlink_rate'].includes(key) ? 0 : key === 'angular_velocity' ? 2 : 1;
      node.textContent = fmt(frame[key], digits);
    });
    $('flight-mode').textContent = frame.spacecraft_mode.replaceAll('_',' ');
    $('flight-mode').className = frame.spacecraft_mode === 'SAFE_MODE' ? 'red-text' : frame.spacecraft_mode === 'POWER_SAVE' ? 'amber-text' : '';
    $('link-status').innerHTML = icon('radio') + ' ' + esc(frame.link_status);
    $('link-status').className = frame.link_status === 'CONNECTED' ? 'green-text' : frame.link_status === 'LOST' ? 'red-text' : 'amber-text';
    $('orbit-phase').innerHTML = (frame.orbit_phase === 'SUNLIGHT' ? icon('sun') : '◐') + ' ' + frame.orbit_phase;
    $('orbit-phase').className = frame.orbit_phase === 'SUNLIGHT' ? 'amber-text' : 'blue-text';
    $('mission-time').textContent = elapsed(frame.mission_elapsed_time);
    $('last-telemetry').innerHTML = utc(frame.timestamp) + ' <small>UTC</small>';
    $('orbit-number').textContent = '#' + String(frame.orbit_number).padStart(4,'0');
    $('orbit-marker').style.left = `${frame.orbit_progress * 100}%`;
    $('orbit-progress-label').textContent = Math.round(frame.orbit_progress * 100) + '%';
    const angle = frame.orbit_progress * Math.PI * 2 - 0.6;
    const x = 132 * Math.cos(angle), y = 45 * Math.sin(angle), tilt = -18 * Math.PI / 180;
    $('orbit-satellite').setAttribute('transform', `translate(${170+x*Math.cos(tilt)-y*Math.sin(tilt)} ${75+x*Math.sin(tilt)+y*Math.cos(tilt)})`);
    const levels = {EPS:frame.battery_charge_percent, THERMAL:frame.obc_temperature, ADCS:frame.reaction_wheel_rpm/100, COMMS:(frame.signal_strength+130)/70*100, PAYLOAD:frame.payload_temperature, OBC:frame.cpu_load};
    all('[data-subsystem]').forEach(node => {
      const subsystem = node.dataset.subsystem, value = frame.subsystem_status[subsystem];
      node.textContent = value === 'NORMAL' ? 'NOMINAL' : value;
      node.className = 'badge ' + value.toLowerCase();
      $('card-'+subsystem).className = 'subsystem-card ' + value.toLowerCase();
    });
    all('[data-meter]').forEach(node => { node.style.width = Math.max(0,Math.min(100,levels[node.dataset.meter]))+'%'; });
    const anomalies = Object.values(frame.subsystem_status).filter(s => ['WARNING','CRITICAL'].includes(s)).length;
    const offline = Object.values(frame.subsystem_status).filter(s => s === 'OFFLINE').length;
    $('subsystem-summary').innerHTML = `<i class="dot ${anomalies ? 'amber' : 'green'}"></i> ${anomalies ? `${anomalies} subsystems require attention` : offline ? 'Systems nominal · payload off' : 'All systems nominal'}`;
    updateCharts();
  }

  function renderStatus(status) {
    state.status = status;
    state.statusReceived = Date.now();
    $('simulation-status').textContent = status.simulation;
    $('simulation-status').className = (status.simulation === 'RUNNING' ? 'green-text' : 'amber-text') + ' small-mono';
    $('simulation-time').textContent = elapsed(status.simulation_time);
    $('frame-count').textContent = fmt(status.frames,0);
    $('session-uptime').textContent = elapsed(status.uptime);
    $('pause-toggle').innerHTML = icon(status.simulation === 'PAUSED' ? 'play' : 'pause') + `<span>${status.simulation === 'PAUSED' ? 'Resume' : 'Pause'}</span>`;
    $('demo-toggle').innerHTML = icon(status.auto_demo ? 'pause' : 'play') + `<span>${status.auto_demo ? 'Auto demo running' : 'Start auto demo'}</span>`;
    $('demo-toggle').classList.toggle('running',status.auto_demo);
    $('demo-toggle').setAttribute('aria-pressed', String(status.auto_demo));
    all('[data-speed]').forEach(button => { const active = Number(button.dataset.speed) === status.speed; button.classList.toggle('active',active); button.setAttribute('aria-pressed',String(active)); });
    all('[data-fault]').forEach(button => {
      const active = status.faults.includes(button.dataset.fault);
      button.classList.toggle('injected',active);
      button.querySelector('.fault-plus').textContent = active ? '●' : '+';
      button.disabled = !state.connected || active;
    });
    $('connection-banner').hidden = state.connected && !status.error;
    if (status.error) $('connection-banner').textContent = status.error + '. Reset or resume the simulation after checking the server log.';
  }

  function renderAlarms(alarms) {
    const previousIds = new Set(state.alarms.map(alarm => alarm.id));
    state.alarms = alarms;
    $('alarm-count').textContent = alarms.length;
    $('nav-alarm-count').textContent = alarms.length;
    $('nav-alarm-count').classList.toggle('red-text',alarms.some(a => a.severity === 'CRITICAL'));
    if (!alarms.length) {
      $('alarms-list').innerHTML = `<div class="empty-alarms"><div class="all-clear-icon">${icon('check')}</div><strong>All clear</strong><p>No active alarms. All monitored<br>parameters are within limits.</p></div>`;
      return;
    }
    $('alarms-list').innerHTML = [...alarms].sort((a,b) => (a.severity === 'CRITICAL' ? -1 : 1) - (b.severity === 'CRITICAL' ? -1 : 1)).map(alarm => `<div class="alarm-item${previousIds.has(alarm.id) ? '' : ' new-alarm'}"><div class="alarm-item-header"><span class="${severityClass(alarm.severity)}">● ${esc(alarm.severity)}</span><span>${esc(alarm.subsystem)}</span></div><p>${esc(alarm.label)}<strong class="mono ${severityClass(alarm.severity)}">${fmt(alarm.measured_value,alarm.unit === 'rpm' ? 0 : 1)} ${esc(alarm.unit)}</strong></p><small>LIMIT: ${alarm.direction === 'low' ? '≤' : '≥'} ${alarm.threshold} ${esc(alarm.unit)} · AUTO PROTECTION</small></div>`).join('');
  }

  function addRecord(collection, row) {
    if (!state[collection].some(item => item.id === row.id)) state[collection].unshift(row);
    state[collection] = state[collection].sort((a,b) => b.id-a.id).slice(0,200);
  }

  function renderJournal() {
    $('event-count').textContent = state.events.length;
    const log = state.log, filter = $('event-filter').value;
    $('event-filter').hidden = log !== 'events';
    $('journal-description').textContent = {events:'Live mission events', commands:'Command history · AUTO + OPERATOR', incidents:'Select an incident to inspect its timeline'}[log];
    const headers = log === 'events' ? ['TIME (UTC)','SEVERITY','EVENT'] : log === 'commands' ? ['TIME (UTC)','SOURCE','COMMAND / RESULT'] : ['INCIDENT','STATUS','DESCRIPTION'];
    $('journal-table').querySelector('thead').innerHTML = `<tr>${headers.map(h => `<th scope="col">${h}</th>`).join('')}</tr>`;
    const rows = state[log].filter(row => log !== 'events' || filter === 'ALL' || row.severity === filter);
    $('journal-table').querySelector('tbody').innerHTML = rows.length ? rows.map(row => {
      if (log === 'events') return `<tr><td>${utc(row.timestamp)}</td><td><span class="event-severity ${severityClass(row.severity)}">${esc(row.severity === 'AUTO_ACTION' ? 'AUTO' : row.severity)}</span></td><td><span class="event-subsystem">${esc(row.subsystem)}</span>${esc(row.message)}</td></tr>`;
      if (log === 'commands') return `<tr><td>${utc(row.timestamp)}</td><td><span class="event-severity ${row.source === 'AUTO' ? 'blue-text' : 'muted'}">${esc(row.source)}</span></td><td><span class="mono">${esc(row.command)}</span><br><small class="${row.result === 'REJECTED' ? 'red-text' : 'green-text'}">${esc(row.result)}</small> <small>${esc(row.reason)}</small></td></tr>`;
      return `<tr class="row-clickable" data-incident-id="${row.id}" tabindex="0" aria-label="View incident ${row.id}"><td>#${String(row.id).padStart(4,'0')}</td><td><span class="event-severity ${row.status === 'OPEN' ? 'amber-text' : row.status === 'RESOLVED' ? 'green-text' : 'muted'}">${esc(row.status)}</span></td><td>${esc(row.title)}</td></tr>`;
    }).join('') : `<tr><td colspan="3" class="empty-row">${log === 'commands' ? 'No commands issued yet.' : log === 'incidents' ? 'No incidents recorded. All systems nominal.' : 'No events match this filter.'}</td></tr>`;
  }

  async function selectIncident(id) {
    state.selectedIncident = id;
    state.incidentEvents = [];
    renderIncident();
    try {
      const response = await fetch(`/api/incidents/${id}`);
      if (!response.ok) throw new Error('Unable to retrieve incident timeline');
      const events = await response.json();
      if (state.selectedIncident !== id) return;
      const merged = [...events, ...state.events.filter(e => e.incident_id === id)];
      state.incidentEvents = [...new Map(merged.map(e => [e.id,e])).values()].sort((a,b) => a.id-b.id);
      renderIncident();
    } catch(error) { toast(error.message,true); }
  }

  function renderIncident() {
    const incident = state.incidents.find(item => item.id === state.selectedIncident);
    if (!incident) {
      $('incident-state').textContent = 'STANDBY';
      $('incident-state').className = 'outline-label';
      $('incident-detail').innerHTML = `<div class="empty-timeline">${icon('shield')}<strong>Mission running smoothly</strong><p>Related alarms and protective actions will appear here as an incident develops.</p><span>DETECT → PROTECT → RECOVER</span></div>`;
      return;
    }
    $('incident-state').textContent = incident.status;
    $('incident-state').className = 'outline-label ' + (incident.status === 'OPEN' ? 'amber-text' : incident.status === 'RESOLVED' ? 'green-text' : 'muted');
    const merged = [...state.incidentEvents, ...state.events.filter(e => e.incident_id === incident.id)];
    const events = [...new Map(merged.map(e => [e.id,e])).values()].sort((a,b) => a.id-b.id);
    const scroll = $('incident-detail').scrollTop;
    $('incident-detail').innerHTML = `<h3 class="incident-title">${esc(incident.title)}</h3><div class="incident-id">INCIDENT #${String(incident.id).padStart(4,'0')} · ${esc(incident.subsystem)}</div>` + events.map(event => `<div class="timeline-entry"><i class="dot ${severityDot(event.severity)}"></i><div><time>${utc(event.timestamp)} UTC <span class="${severityClass(event.severity)}">· ${esc(event.severity.replace('_',' '))}</span></time><p>${esc(event.message)}</p></div></div>`).join('');
    $('incident-detail').scrollTop = scroll;
  }

  function renderIncidents(incidents) {
    state.incidents = incidents;
    const newest = incidents[0];
    if (newest && (state.selectedIncident === null || (newest.status === 'OPEN' && newest.id > state.selectedIncident))) selectIncident(newest.id);
    else renderIncident();
    if (state.log === 'incidents') renderJournal();
  }

  function applySnapshot(snapshot) {
    state.runId = snapshot.telemetry.run_id;
    state.history = snapshot.history.slice(-120);
    state.events = snapshot.events;
    state.commands = snapshot.commands;
    state.selectedIncident = null;
    state.incidentEvents = [];
    renderTelemetry(snapshot.telemetry,false);
    renderStatus(snapshot.status);
    renderAlarms(snapshot.alarms);
    renderIncidents(snapshot.incidents);
    renderJournal();
  }

  function toast(message, error=false) {
    const node = document.createElement('div');
    node.className = 'toast' + (error ? ' error' : '');
    node.textContent = message;
    $('toast-region').appendChild(node);
    setTimeout(() => node.remove(),6000);
  }

  async function post(path, data) {
    if (!state.connected) { toast('Reconnect to the telemetry server before issuing commands.',true); return null; }
    try {
      const response = await fetch('/api/'+path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || result.detail || 'Request failed');
      return result;
    } catch(error) { toast(error.message,true); return null; }
  }

  function confirmAction(title, description, action) {
    const dialog = $('confirm-dialog');
    $('confirm-title').textContent = title;
    $('confirm-description').textContent = description;
    dialog.returnValue = '';
    dialog.onclose = () => { if (dialog.returnValue === 'confirm') action(); };
    dialog.showModal();
  }

  function setLog(log) {
    state.log = log;
    all('[data-log]').forEach(button => { button.classList.toggle('active',button.dataset.log === log); button.setAttribute('aria-selected',String(button.dataset.log === log)); });
    renderJournal();
  }

  function setConnected(connected) {
    state.connected = connected;
    $('feed-status').innerHTML = `<i class="dot ${connected ? 'green' : 'amber'}"></i> ${connected ? 'LIVE STREAM' : 'RECONNECTING'}`;
    $('connection-banner').hidden = connected;
    if (!connected) $('connection-banner').textContent = 'Telemetry connection interrupted. Displaying last received state; controls are unavailable.';
    all('[data-fault], [data-speed], #execute-command, #clear-faults, #pause-toggle, #reset-simulation, #demo-toggle').forEach(button => { button.disabled = !connected; });
    if (state.status) renderStatus(state.status);
    $('spacecraft-status').innerHTML = `<i class="dot ${connected ? 'green' : 'gray'}"></i> ${connected ? 'ONLINE' : 'UNKNOWN'}`;
    $('spacecraft-status').className = connected ? 'green-text' : 'muted';
  }

  all('[data-chart-group]').forEach(button => button.addEventListener('click', () => {
    state.group = button.dataset.chartGroup;
    all('[data-chart-group]').forEach(tab => { tab.classList.toggle('active',tab === button); tab.setAttribute('aria-selected',String(tab === button)); });
    createCharts();
  }));
  all('[data-log]').forEach(button => button.addEventListener('click',() => setLog(button.dataset.log)));
  $('event-filter').addEventListener('change',renderJournal);
  $('journal-table').addEventListener('click',event => { const row = event.target.closest('[data-incident-id]'); if (row) selectIncident(Number(row.dataset.incidentId)); });
  $('journal-table').addEventListener('keydown',event => { if (event.key === 'Enter') event.target.click(); });
  all('[data-nav]').forEach(button => button.addEventListener('click', () => {
    all('[data-nav]').forEach(node => node.classList.toggle('active',node === button));
    const target = button.dataset.nav;
    if (['commands','incidents'].includes(target)) { setLog(target); $('journal').scrollIntoView({block:'center'}); }
    else $(target).scrollIntoView({block:target === 'overview' ? 'start' : 'center'});
  }));
  all('[data-fault]').forEach(button => button.addEventListener('click', async () => {
    const result = await post('fault/inject',{fault:button.dataset.fault});
    if (result) { toast('Fault injected. Watch the telemetry and autonomous response.'); const group = {BATTERY_DRAIN:'power',PAYLOAD_OVERHEAT:'thermal',OBC_OVERHEAT:'thermal',COMMUNICATION_LOSS:'attitude',ADCS_INSTABILITY:'attitude'}[button.dataset.fault]; document.querySelector(`[data-chart-group="${group}"]`).click(); }
  }));
  $('clear-faults').addEventListener('click',async () => { if (await post('fault/reset',{})) toast('Fault sources cleared. Telemetry will recover gradually.'); });
  $('execute-command').addEventListener('click',() => {
    const command = $('command-select').value;
    confirmAction(command.replaceAll('_',' '), 'Apply this command to the simulated spacecraft? The safety engine will validate the request and record the result in command history.',async () => { const result = await post('command',{command}); if (result) toast(`${result.command}: ${result.result}`); });
  });
  $('reset-simulation').addEventListener('click',() => confirmAction('Reset simulation?', 'Start a new run with nominal initial conditions. Current incidents will close as RESET; all recorded events and commands will remain in the journal.',async () => { if (await post('simulation',{action:'reset'})) toast('Simulation reset. New mission run initialized.'); }));
  $('pause-toggle').addEventListener('click',() => post('simulation',{action:state.status?.simulation === 'PAUSED' ? 'resume' : 'pause'}));
  all('[data-speed]').forEach(button => button.addEventListener('click',() => post('simulation',{action:'speed',value:Number(button.dataset.speed)})));
  $('demo-toggle').addEventListener('click',async () => { const enabled = !state.status?.auto_demo; if (await post('simulation',{action:'demo',value:enabled})) toast(enabled ? 'Auto demo enabled. First scenario starts in 15 simulated seconds.' : 'Auto demo stopped. Existing faults continue until recovery or reset.'); });
  $('export-log').addEventListener('click',() => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(state[state.log],null,2)],{type:'application/json'}));
    const a = document.createElement('a'); a.href = url; a.download = `aurora-${state.log}-${new Date().toISOString().slice(0,10)}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
    toast(`Exported ${state[state.log].length} loaded ${state.log}.`);
  });

  createCharts();
  renderJournal();
  setConnected(false);
  const socket = io({reconnectionDelay:1000, reconnectionDelayMax:5000});
  socket.on('connect',() => setConnected(true));
  socket.on('disconnect',() => setConnected(false));
  socket.on('connect_error',() => setConnected(false));
  socket.on('initial_state',applySnapshot);
  socket.on('simulation_reset',applySnapshot);
  socket.on('telemetry_update',renderTelemetry);
  socket.on('spacecraft_status_update',renderStatus);
  socket.on('alarm_update',renderAlarms);
  socket.on('incident_update',renderIncidents);
  socket.on('event_update',row => { addRecord('events',row); if (state.log === 'events') renderJournal(); renderIncident(); });
  socket.on('command_update',row => { addRecord('commands',row); if (state.log === 'commands') renderJournal(); });
  setInterval(() => {
    $('utc-clock').textContent = utc(new Date())+' UTC';
    const fresh = state.connected && (state.status?.simulation === 'PAUSED' || Date.now()-state.lastReceived < 4000);
    $('freshness-dot').className = 'dot ' + (fresh ? 'green' : 'amber');
    $('freshness-dot').title = fresh ? 'Telemetry current' : 'Telemetry stale';
    if (state.connected && state.status) $('session-uptime').textContent = elapsed(state.status.uptime + (Date.now()-state.statusReceived)/1000);
  },1000);
})();
