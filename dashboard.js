'use strict';
const $ = id => document.getElementById(id);
const base = '/meeting-ui/dashboard/';
let csrf = '', selected = null, original = '', offset = 0, pageTotal = 0, busy = false, searchTimer;
const limit = 50;
function notice(message, error = false) { $('notice').textContent = message; $('notice').classList.toggle('error', error); $('notice').hidden = !message; }
async function api(path, body) {
  const options = {credentials: 'same-origin', headers: {'Accept': 'application/json', 'X-Meeting-Origin': location.origin}};
  if (body) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.headers['X-Meeting-CSRF'] = csrf; options.body = JSON.stringify(body); }
  const response = await fetch(base + 'api/' + path, options);
  let data; try { data = await response.json(); } catch (_) { throw new Error('Dashboard response unavailable. Check the worker and proxy.'); }
  if (!response.ok) {
    if (response.status === 401) { $('login').hidden = false; }
    throw new Error(data.error || 'Request failed. Refresh before retrying.');
  }
  return data;
}
function element(tag, text, className) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; }
function badge(status) { const node = element('span', status, 'badge'); node.classList.toggle('approved', /Approved|knowledge base/.test(status)); node.classList.toggle('failed', /failed|attention/.test(status)); node.classList.toggle('processing', /Processing|progress/.test(status)); return node; }
function rev(number) { return number ? 'r' + number : '—'; }
function renderText(target, text) {
  // Source Markdown/HTML is data: no innerHTML, remote images or script-capable links.
  target.replaceChildren(); let paragraph = [];
  const flush = () => { if (paragraph.length) { target.append(element('p', paragraph.join('\n'))); paragraph = []; } };
  for (const line of text.split('\n')) {
    if (!line.trim()) { flush(); continue; }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) { flush(); target.append(element('h' + heading[1].length, heading[2])); }
    else if (line.startsWith('> ')) { flush(); target.append(element('blockquote', line.slice(2))); }
    else paragraph.push(line);
  }
  flush();
}
async function loadList() {
  const query = new URLSearchParams({offset, limit, q: $('search').value, status: $('filter').value});
  const data = await api('meetings?' + query);
  pageTotal = data.total;
  for (const key of ['total', 'processing', 'review', 'indexed']) $('count-' + key).textContent = data.counts[key];
  const previousStatus = $('filter').value;
  $('filter').replaceChildren(new Option('All statuses', ''));
  for (const status of data.statuses) $('filter').append(new Option(status, status));
  $('filter').value = previousStatus;
  $('rows').replaceChildren();
  for (const meeting of data.meetings) {
    const row = element('tr'), title = element('td');
    const open = element('button', meeting.title, 'meeting-link'); open.addEventListener('click', () => navigate(meeting.id));
    title.append(open, element('small', meeting.meeting_date || 'Date not provided'), element('small', meeting.id)); row.append(title);
    const state = element('td'); state.append(badge(meeting.status)); row.append(state);
    for (const number of [meeting.revision, meeting.approved_revision, meeting.indexed_revision]) row.append(element('td', rev(number)));
    const action = element('td'), button = element('button', meeting.state === 'completed' ? 'Open' : 'Status', 'secondary');
    button.addEventListener('click', () => navigate(meeting.id)); action.append(button); row.append(action); $('rows').append(row);
  }
  $('empty').hidden = data.meetings.length > 0; $('result-count').textContent = data.total + ' found';
  $('page').textContent = data.total ? `${offset + 1}–${offset + data.meetings.length} of ${data.total}` : '0 meetings';
  $('previous').disabled = offset === 0; $('next').disabled = offset + limit >= data.total;
}
function draft() {
  const mapping = {};
  for (const input of $('speakers').querySelectorAll('input')) if (input.value.trim()) mapping[input.dataset.label] = input.value.trim();
  return {content: $('recap').value, metadata: {meeting_title: $('title').value.trim(), meeting_date: $('date').value,
    participants: $('people').value.split(',').map(name => name.trim()).filter(Boolean)}, mapping};
}
function dirty() { return !!selected?.review && JSON.stringify(draft()) !== original; }
function updateButtons() {
  const changed = dirty(), pending = !!selected?.review?.pending;
  for (const control of [$('recap'), $('title'), $('date'), $('people'), ...$('speakers').querySelectorAll('input')]) control.disabled = busy || pending;
  $('save').disabled = busy || !changed || pending;
  $('approve').disabled = busy || changed || pending || selected?.meeting.approved_revision === selected?.review?.revision;
  $('save-state').textContent = pending ? 'Revision generation in progress' : changed ? 'Unsaved changes' : 'Saved on MINISFORUM';
  $('approval-hint').textContent = changed ? 'Save this draft before approving it.' : selected?.meeting.approved_revision === selected?.review?.revision ? 'This revision is approved. A later edit will need its own approval.' : 'Approval makes this exact saved revision eligible for ingestion.';
}
async function openMeeting(id) {
  const data = await api('meetings/' + id);
  if (location.hash.slice(1).toLowerCase() !== id) return;
  selected = data;
  $('listing').hidden = true; $('meeting').hidden = false;
  const item = data.meeting;
  $('meeting-title').textContent = item.title; $('meeting-date').textContent = item.meeting_date || 'MEETING STATUS'; $('meeting-job').textContent = 'Job ' + item.id;
  $('meeting-status').replaceWith(Object.assign(badge(item.status), {id: 'meeting-status'}));
  $('current-rev').textContent = 'Current draft: ' + rev(item.revision); $('approved-rev').textContent = 'Approved snapshot: ' + rev(item.approved_revision);
  $('indexed-rev').textContent = 'Last indexed: ' + rev(item.indexed_revision);
  $('meeting-progress').textContent = (item.detail || '') + (item.indexed_at ? ' · Index recorded ' + item.indexed_at : '') + (!item.indexing_known ? ' · Ingestion state is unavailable; indexing is not confirmed.' : '');
  const error = item.error || item.review_error || item.indexing_error;
  $('meeting-error').textContent = error || ''; $('meeting-error').hidden = !error;
  $('workspace').hidden = !data.review;
  if (!data.review) { original = ''; return; }
  const value = data.review;
  $('recap').value = value.report; renderText($('recap-preview'), value.report);
  $('recap-label').hidden = true; $('recap-preview').hidden = false; $('toggle-edit').textContent = 'Edit recap';
  $('title').value = value.metadata.meeting_title || ''; $('date').value = value.metadata.meeting_date || '';
  $('people').value = (value.metadata.participants || []).join(', '); $('transcript').textContent = value.transcript;
  $('changes').textContent = value.changes || 'This is the first revision.'; $('speakers').replaceChildren();
  for (const label of value.speakers) {
    const holder = element('label', label), input = document.createElement('input'); input.dataset.label = label;
    input.maxLength = 100; input.value = value.speaker_mapping[label] || ''; input.placeholder = 'Leave unnamed until confirmed'; input.addEventListener('input', updateButtons); holder.append(input); $('speakers').append(holder);
  }
  if (!value.speakers.length) $('speakers').append(element('p', 'No assigned speaker labels in this transcript.', 'hint'));
  $('history').replaceChildren();
  for (const history of data.history) {
    const row = element('div', undefined, 'history-row');
    row.append(element('strong', rev(history.revision)), element('span', new Date(history.created * 1000).toLocaleString() + ' · ' + history.kind));
    if (history.revision === item.approved_revision) row.append(badge('Approved'));
    if (history.revision === item.indexed_revision) row.append(badge('Indexed'));
    const preview = element('button', 'View', 'secondary'); preview.addEventListener('click', () => showHistory(item.id, history.revision)); row.append(preview); $('history').append(row);
  }
  original = JSON.stringify(draft());
  for (const control of [$('recap'), $('title'), $('date'), $('people'), ...$('speakers').querySelectorAll('input')]) control.disabled = !!value.pending;
  updateButtons(); selectTab('recap');
}
async function showHistory(id, revision) {
  try { const data = await api(`meetings/${id}/revisions/${revision}`); $('history-title').textContent = 'Revision ' + revision + ' · read only'; renderText($('history-preview'), data.report); $('history-dialog').showModal(); }
  catch (error) { notice(error.message, true); }
}
function selectTab(name) { for (const tab of ['recap', 'transcript', 'details', 'history']) { $('tab-' + tab).setAttribute('aria-selected', tab === name ? 'true' : 'false'); $('panel-' + tab).hidden = tab !== name; } }
function navigate(id = '') {
  if (dirty() && !confirm('Discard your unsaved edits? The last saved revision will remain unchanged.')) return;
  original = ''; selected = null;
  if (location.hash.slice(1) === id) route(); else location.hash = id;
}
async function route() {
  const id = location.hash.slice(1).toLowerCase();
  try {
    if (/^[a-f0-9]{32}$/.test(id)) await openMeeting(id);
    else { selected = null; $('meeting').hidden = true; $('listing').hidden = false; await loadList(); }
  } catch (error) { notice(error.message, true); }
}
async function start() {
  try { const session = await api('session'); csrf = session.csrf; $('account').textContent = session.user.name; $('login').hidden = true; await route(); }
  catch (error) { $('listing').hidden = true; notice(error.message, true); }
}
$('save').addEventListener('click', async () => {
  if (!selected?.review || busy || !dirty()) return;
  if (!$('title').reportValidity() || !$('date').reportValidity()) return;
  busy = true; updateButtons();
  const id = selected.meeting.id, revision = selected.review.revision;
  try {
    const data = await api('meetings/' + id, {action: 'dashboard-save', revision, ...draft()});
    original = ''; selected = null;
    notice(`Draft r${data.review.revision} saved on MINISFORUM. ` + (data.meeting.approved_revision ? `Approved r${data.meeting.approved_revision} remains unchanged until you approve the new draft.` : 'It is not approved.'));
    location.hash = ''; await route();
  } catch (error) { notice(error.message + ' Your edits remain here. If the connection was lost, open this meeting in another tab to check its revision before retrying.', true); }
  finally { busy = false; if (selected?.review) updateButtons(); }
});
$('approve').addEventListener('click', () => { if (!selected?.review || dirty() || busy) return; $('approval-text').textContent = `${selected.meeting.title} · revision ${selected.review.revision}.`; $('approval-error').hidden = true; $('approval-error').textContent = ''; $('approval-dialog').showModal(); });
$('cancel-approval').addEventListener('click', () => $('approval-dialog').close());
$('confirm-approval').addEventListener('click', async () => {
  if (!selected?.review || dirty() || busy) return;
  busy = true; $('confirm-approval').disabled = true; updateButtons();
  try { const id = selected.meeting.id; const data = await api('meetings/' + id, {action: 'approve', revision: selected.review.revision}); $('approval-dialog').close(); original = ''; await openMeeting(id); notice(data.message); }
  catch (error) { if (!$('approval-dialog').open) $('approval-dialog').showModal(); $('approval-error').textContent = error.message + ' The approval was not confirmed. Keep this window open or close it and refresh the meeting before retrying.'; $('approval-error').hidden = false; }
  finally { busy = false; $('confirm-approval').disabled = false; updateButtons(); }
});
$('toggle-edit').addEventListener('click', () => { const edit = $('recap-label').hidden; if (!edit) renderText($('recap-preview'), $('recap').value); $('recap-label').hidden = !edit; $('recap-preview').hidden = edit; $('toggle-edit').textContent = edit ? 'Preview text' : 'Edit recap'; if (edit) $('recap').focus(); });
for (const name of ['recap', 'transcript', 'details', 'history']) $('tab-' + name).addEventListener('click', () => selectTab(name));
for (const id of ['recap', 'title', 'date', 'people']) $(id).addEventListener('input', updateButtons);
$('back').addEventListener('click', () => navigate());
$('refresh').addEventListener('click', () => loadList().catch(error => notice(error.message, true)));
$('search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { offset = 0; loadList().catch(error => notice(error.message, true)); }, 300); });
$('filter').addEventListener('change', () => { offset = 0; loadList().catch(error => notice(error.message, true)); });
$('previous').addEventListener('click', () => { offset = Math.max(0, offset - limit); loadList().catch(error => notice(error.message, true)); });
$('next').addEventListener('click', () => { if (offset + limit < pageTotal) offset += limit; loadList().catch(error => notice(error.message, true)); });
$('close-history').addEventListener('click', () => $('history-dialog').close()); $('try-again').addEventListener('click', start);
window.addEventListener('hashchange', () => { if (dirty()) { if (!confirm('Discard unsaved edits?')) { history.replaceState(null, '', '#' + selected.meeting.id); return; } } original = ''; route(); });
window.addEventListener('beforeunload', event => { if (dirty()) { event.preventDefault(); event.returnValue = ''; } });
setInterval(() => { if (!selected && $('login').hidden && !document.hidden) loadList().catch(error => notice(error.message, true)); }, 20000);
start();
