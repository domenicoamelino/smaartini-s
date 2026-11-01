'use strict';
(() => {
  const data = window.SMARTINI_ROADMAP;
  const $ = id => document.getElementById(id);
  const el = (tag, text, cls) => { const node = document.createElement(tag); if (text) node.textContent = text; if (cls) node.className = cls; return node; };
  const collapsedPhases = new Set();
  const tasks = new Map(data.tasks.map(t => [t.id, t]));
  for (const phase of data.phases) { const option = el('option', phase.title); option.value = phase.id; $('phase').append(option); }
  function show(task) {
    $('detail-phase').textContent = data.phases.find(p => p.id === task.phase).title;
    $('detail-title').textContent = task.title;
    $('detail-status').textContent = `${task.status.toUpperCase()} · ${task.step !== null ? data.steps[task.step] + ' · proposed sequence only' : task.status === 'delivered' ? 'Delivered baseline' : 'Future scope TBD'}`;
    $('detail-description').textContent = task.description;
    for (const [id, entries] of [['dependencies', task.dependsOn.map(key => tasks.get(key))], ['unlocks', data.tasks.filter(t => t.dependsOn.includes(task.id))]]) {
      $(id).replaceChildren();
      if (!entries.length) $(id).append(el('li', 'None specified.'));
      for (const entry of entries) { const li = el('li'); const button = el('button', entry.title); button.addEventListener('click', () => show(entry)); li.append(button); $(id).append(li); }
    }
    if (!$('detail').open) $('detail').showModal();
  }
  function render() {
    const query = $('search').value.trim().toLowerCase();
    const visible = data.tasks.filter(t => ($('phase').value === 'all' || t.phase === $('phase').value) && ($('status').value === 'all' || t.status === $('status').value) && `${t.title} ${t.description}`.toLowerCase().includes(query));
    $('count').textContent = `${visible.length} of ${data.tasks.length} workstreams match`;
    $('empty').hidden = visible.length !== 0;
    const chart = $('chart'); chart.replaceChildren(); chart.style.minWidth = $('scale').value === 'wide' ? '1600px' : '1000px';
    const axis = el('div', '', 'axis'); axis.append(el('strong', 'WORKSTREAM / STATUS')); const months = el('div', '', 'months');
    for (const label of data.steps) months.append(el('span', label)); axis.append(months); chart.append(axis);
    for (const phase of data.phases) {
      const subset = visible.filter(t => t.phase === phase.id); if (!subset.length) continue;
      const group = el('details', '', 'phase-group');
      group.open = !collapsedPhases.has(phase.id);
      const summary = el('summary', '', 'phase-row');
      summary.append(el('span', phase.title), el('span', `${subset.length} workstreams · expand / collapse`, 'phase-summary'));
      group.append(summary);
      group.addEventListener('toggle', () => {
        if (group.open) collapsedPhases.delete(phase.id);
        else collapsedPhases.add(phase.id);
      });
      chart.append(group);
      for (const task of subset) {
        const row = el('div', '', 'row'); const button = el('button', '', 'task'); button.append(el('span', `${task.milestone ? '◆ ' : ''}${task.title}`), el('small', `${task.status.toUpperCase()} · ${task.dependsOn.length} dependencies`)); button.addEventListener('click', () => show(task)); row.append(button);
        const track = el('div', '', 'track');
        if (task.step !== null) { const bar = el('button', `${task.milestone ? '◆ ' : ''}${task.title}`, `bar ${task.status}${task.milestone ? ' milestone' : ''}`); bar.style.setProperty('--left', `${task.step / data.steps.length * 100}%`); bar.style.setProperty('--width', `${100 / data.steps.length - 1}%`); bar.setAttribute('aria-label', `${task.title}, ${data.steps[task.step]}, proposed order only. Open details`); bar.addEventListener('click', () => show(task)); track.append(bar); }
        else track.append(el('span', task.status === 'delivered' ? '✓ Delivered foundation' : '○ Future horizon · scope TBD', `unscheduled ${task.status}`));
        row.append(track); group.append(row);
      }
    }
  }
  for (const id of ['phase', 'status', 'scale']) $(id).addEventListener('change', render);
  $('search').addEventListener('input', render);
  $('reset').addEventListener('click', () => { collapsedPhases.clear(); $('phase').value = $('status').value = 'all'; $('search').value = ''; $('scale').value = 'compact'; render(); });
  $('close').addEventListener('click', () => $('detail').close());
  render();
})();
