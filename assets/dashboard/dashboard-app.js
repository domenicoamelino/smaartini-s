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
function markdownPlain(text) {
  return String(text || '').replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|#39);/gi, (raw, entity) => {
    const names={amp:'&',lt:'<',gt:'>',quot:'"',apos:"'"};
    if (names[entity.toLowerCase()]) return names[entity.toLowerCase()];
    const code=entity.toLowerCase().startsWith('#x')?parseInt(entity.slice(2),16):parseInt(entity.slice(1),10);
    return Number.isInteger(code)&&code>0&&code<=0x10ffff&&!(code>=0xd800&&code<=0xdfff)?String.fromCodePoint(code):raw;
  });
}
function recapDisplaySource(text) {
  // Some old drafts contain literal escaped newlines before Markdown blocks.
  // Normalize the preview only, preserving fenced and inline code verbatim.
  let fence=false;
  return String(text).replace(/\r\n?/g,'\n').split('\n').map(line=>{
    if (/^\s*(```|~~~)/.test(line)) {fence=!fence;return line;}
    if(fence)return line;
    return line.split(/(`+[^`]*`+)/g).map((part,index)=> index%2?part:part.replace(/\\n\\n/g,'\n\n').replace(/\\n(?=[ \t]*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|$))/g,'\n')).join('');
  }).join('\n');
}
function renderMarkdownTokens(target,tokens,depth=0) {
  if(depth>30){target.append(document.createTextNode('[Formatting nesting limit reached]'));return;}
  for(const token of tokens || []) {
    let node;
    switch(token.type) {
      case 'space':continue;
      case 'heading':node=element('h'+Math.min(6,Math.max(1,token.depth)));break;
      case 'paragraph':node=element('p');break;
      case 'strong':node=element('strong');break;
      case 'em':node=element('em');break;
      case 'del':node=element('del');break;
      case 'blockquote':node=element('blockquote');break;
      case 'br':target.append(document.createElement('br'));continue;
      case 'hr':target.append(document.createElement('hr'));continue;
      case 'code':node=element('pre');node.append(element('code',token.text));target.append(node);continue;
      case 'codespan':target.append(element('code',markdownPlain(token.text)));continue;
      case 'list': {
        node=element(token.ordered?'ol':'ul');
        if(token.ordered&&Number.isSafeInteger(token.start)&&token.start>0)node.start=token.start;
        for(const item of token.items){const li=element('li');if(item.task)li.append(document.createTextNode(item.checked?'☑ ':'☐ '));renderMarkdownTokens(li,item.tokens,depth+1);node.append(li);}
        target.append(node);continue;
      }
      case 'table': {
        const wrap=element('div',undefined,'recap-table'),table=element('table'),head=element('thead'),row=element('tr');
        for(const cell of token.header){const th=element('th');renderMarkdownTokens(th,cell.tokens,depth+1);row.append(th);}head.append(row);table.append(head);
        const body=element('tbody');for(const cells of token.rows){const tr=element('tr');for(const cell of cells){const td=element('td');renderMarkdownTokens(td,cell.tokens,depth+1);tr.append(td);}body.append(tr);}table.append(body);wrap.append(table);target.append(wrap);continue;
      }
      case 'link': {
        let safe=false;try{const url=new URL(markdownPlain(token.href),location.href);safe=['https:','http:','mailto:'].includes(url.protocol);}catch(_){}
        node=element(safe?'a':'span');if(safe){node.href=markdownPlain(token.href);node.rel='noopener noreferrer';}
        renderMarkdownTokens(node,token.tokens,depth+1);target.append(node);continue;
      }
      case 'image':target.append(document.createTextNode(markdownPlain(token.text || '[image omitted]')));continue;
      case 'html':target.append(document.createTextNode(token.raw || token.text || ''));continue;
      default:
        if(token.tokens)renderMarkdownTokens(target,token.tokens,depth+1);
        else target.append(document.createTextNode(markdownPlain(token.text || token.raw || '')));
        continue;
    }
    renderMarkdownTokens(node,token.tokens,depth+1);target.append(node);
  }
}
function renderText(target,text) {
  // Marked is used only as a lexer. All output is built with DOM nodes and
  // textContent: no HTML insertion, remote images or executable URL schemes.
  target.replaceChildren();
  try { renderMarkdownTokens(target,marked.lexer(recapDisplaySource(text),{gfm:true,breaks:false})); }
  catch(_) { target.append(element('p',String(text))); }
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
function recapDirty() { return !!selected?.review && JSON.stringify(draft()) !== original; }
function dirty() { return recapDirty() || transcriptDirty(); }
function updateButtons() {
  const changed = dirty(), pending = !!selected?.review?.pending;
  for (const control of [$('recap'), $('title'), $('date'), $('people'), ...$('speakers').querySelectorAll('input')]) control.disabled = busy || pending;
  $('save').disabled = busy || !recapDirty() || pending || transcriptDirty() || selected?.review?.transcript_reviewed === false;
  $('approve').disabled = busy || changed || pending || selected?.review?.recap_ready === false || selected?.meeting.approved_revision === selected?.review?.revision;
  transcriptButtons();
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
  $('people').value = (value.metadata.participants || []).join(', '); setupTranscript(value);
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
  updateButtons(); selectTab(value.transcript_reviewed === false || value.recap_ready === false ? 'transcript' : 'recap');
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
setInterval(() => { if ($('login').hidden && !document.hidden && !busy) { if (!selected) loadList().catch(error => notice(error.message, true)); else if (selected.review?.pending && !dirty()) openMeeting(selected.meeting.id).catch(error => notice(error.message, true)); } }, 20000);



let editedTurns = new Map(), transcriptOriginal = '', allTurns = [];
function timeLabel(seconds) { return Math.floor(seconds / 60) + ':' + String(Math.floor(seconds % 60)).padStart(2, '0'); }
function transcriptDirty() { return !!selected?.review && (editedTurns.size > 0 || $('meeting-end').value !== transcriptOriginal); }
function setupTranscript(value) {
  editedTurns = new Map(); allTurns = value.document_blocks || [];
  $('meeting-end').value = value.meeting_end_seconds == null ? '' : timeLabel(value.meeting_end_seconds);
  transcriptOriginal = $('meeting-end').value; $('confirm-transcript').checked = false;
  if ($('recording').getAttribute('src') !== value.audio_url) $('recording').src = value.audio_url;
  const prefix = base+'api/meetings/'+selected.meeting.id+'/';
  $('download-transcript').href=prefix+'transcript.txt';$('download-transcript-json').href=prefix+'transcript.json';
  $('turn-search').value = ''; renderTurns(); setupRecovery(value,prefix);
}
function transcriptButtons() {
  const locked = busy || !!selected?.review?.pending;
  $('save-transcript').disabled = locked || !transcriptDirty() || recapDirty();
  $('generate-recap').disabled = locked || !$('confirm-transcript').checked || recapDirty();
  $('retry-recap').hidden = !selected?.meeting?.review_error;
  $('retry-recap').disabled = locked || dirty();
  for (const input of $('turns').querySelectorAll('input,textarea,button')) input.disabled = locked;
  $('meeting-end').disabled = locked; $('confirm-transcript').disabled = locked;
  $('import-recap').disabled=locked || !selected?.review?.transcript_reviewed;
  $('recover-draft').disabled=locked || !selected?.review?.transcript_reviewed;
}
function renderTurns() {
  const query = $('turn-search').value.toLocaleLowerCase();
  const rows = allTurns.filter(t => (!query || (editedTurns.get(t.id)?.text || t.text).toLocaleLowerCase().includes(query)) && (!$('warnings-only').checked || t.warnings.length));
  const fragment=document.createDocumentFragment();
  for (const t of rows) {
    const current = {...t, ...editedTurns.get(t.id)}, box = element('article', undefined, 'document-paragraph');
    box.classList.toggle('flagged', !!t.warnings.length);box.classList.toggle('excluded',!!(current.excluded || t.outside_meeting));
    const header=element('div',undefined,'paragraph-heading');
    const listen = element('button', timeLabel(t.start)+'–'+timeLabel(t.end), 'timestamp');
    listen.addEventListener('click', () => { $('recording').currentTime = Math.max(0, t.start - 1); $('recording').play().catch(() => notice('Press play on the recording.')); }); header.append(listen);
    if (current.confirmed_speaker) header.append(element('span',current.confirmed_speaker,'hint'));
    if(current.reviewed) header.append(element('span','Checked','hint'));
    if(current.excluded || t.outside_meeting) header.append(element('span','Excluded from recap','hint'));
    const editButton=element('button','Edit paragraph','text-button');header.append(editButton);box.append(header);
    const wording=element('p',current.text,'transcript-wording');box.append(wording);
    const editor=element('div',undefined,'paragraph-editor');editor.hidden=true;box.append(editor);
    if(t.warnings.length){const flag=element('details');flag.append(element('summary',t.warnings.length+' listening suggestion'+(t.warnings.length===1?'':'s')));for(const reason of t.warnings)flag.append(element('p',reason,'hint'));box.append(flag);}
    editButton.addEventListener('click',()=>{
      if(!editor.hidden){editor.hidden=true;wording.hidden=false;editButton.textContent='Edit paragraph';return;}
      editor.replaceChildren();const value={...t,...editedTurns.get(t.id)};
      const text=document.createElement('textarea');text.rows=5;text.maxLength=8000;text.value=value.text;text.setAttribute('aria-label','Transcript paragraph '+t.id);editor.append(text);
      const note=document.createElement('input');note.maxLength=1000;note.value=value.note;note.placeholder='Unresolved name, amount or context — optional note';note.setAttribute('aria-label','Review note '+t.id);editor.append(note);
      const speaker=document.createElement('input');speaker.maxLength=100;speaker.value=value.confirmed_speaker||'';speaker.placeholder='Speaker — only if personally confirmed for this whole paragraph';speaker.setAttribute('aria-label','Confirmed speaker '+t.id);editor.append(speaker);
      const controls={};for(const [key,label] of [['reviewed','Checked by me (optional)'],['excluded','Exclude from recap']]){const holder=element('label',label),input=document.createElement('input');input.type='checkbox';input.checked=value[key];controls[key]=input;holder.prepend(input);editor.append(holder);}
      const changed=()=>{const edit={text:text.value,note:note.value,confirmed_speaker:speaker.value,reviewed:controls.reviewed.checked,excluded:controls.excluded.checked};
        if(Object.keys(edit).every(k=>edit[k]===t[k]))editedTurns.delete(t.id);else editedTurns.set(t.id,edit);
        wording.textContent=text.value;box.classList.toggle('excluded',edit.excluded||t.outside_meeting);updateButtons();};
      for(const input of [text,note,speaker,...Object.values(controls)])input.addEventListener('input',changed);
      editor.hidden=false;wording.hidden=true;editButton.textContent='Done editing';transcriptButtons();text.focus();
    });
    fragment.append(box);
  }
  $('turns').replaceChildren(fragment);$('document-count').textContent=rows.length+' paragraphs · one scrollable document · no per-word review required';transcriptButtons();
}
function setupRecovery(value,prefix){
  const attempts=value.generation_attempts||[];$('recovery-panel').hidden=!attempts.length&&!value.error;
  const recent=attempts.find(a=>a.status==='failed');
  $('failure-reason').textContent=recent?.failure?.message || (value.pending?'Generation is running. Completed stages are saved as they finish.':'Saved generation attempts and response metrics.');
  const lines=[];for(const a of attempts){lines.push(`Attempt ${a.task.slice(0,8)} · source r${a.base_revision} · ${a.status}`);if(a.failure)lines.push(a.failure.type+': '+a.failure.message);
    for(const r of a.responses||[])lines.push(`${r.file}: ${r.done_reason}; output tokens ${r.output_tokens??'unavailable'}; prompt tokens ${r.prompt_tokens??'unavailable'}; ${r.characters} characters`);
    for(const e of a.events||[])lines.push(Object.entries(e).map(([k,v])=>k+': '+String(v)).join(' · '));lines.push('');}
  $('generation-log').textContent=lines.join('\n');$('generation-details').open=!!value.error;
  $('recover-draft').hidden=!value.recovered_draft;$('download-recovered').hidden=!value.recovered_draft;
  $('download-recovered').href=prefix+'recovered.md';$('download-generation-log').href=prefix+'generation-log.json';
}
function loadManualRecap(text){
  if(!selected?.review || !selected.review.transcript_reviewed || selected.review.pending)return;
  if(recapDirty()&&!confirm('Replace your unsaved recap edits with this text?'))return;
  $('recap').value=text;$('recap-label').hidden=false;$('recap-preview').hidden=true;$('toggle-edit').textContent='Preview text';selectTab('recap');updateButtons();
  notice('Text loaded for editing. Review it, save the draft and approve the saved revision separately.');
}
$('recover-draft').addEventListener('click',()=>loadManualRecap(selected?.review?.recovered_draft||''));
$('import-recap').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>240000)throw new Error('Choose a plain text or Markdown recap of at most 60,000 characters.');const text=await file.text();if(!text.trim()||text.length>60000||text.includes('\u0000'))throw new Error('Invalid or oversized recap text.');loadManualRecap(text);}catch(error){notice(error.message,true);}event.target.value='';});
async function saveTranscript(action) {
  if (!selected?.review || busy || recapDirty()) return;
  let end = null; const value = $('meeting-end').value.trim();
  if (value) { const match = /^(\d+):([0-5]\d)$/.exec(value); if (!match) { notice('Enter the meeting end as minutes:seconds, for example 18:30.',true); return; } end = Number(match[1])*60+Number(match[2]); }
  if (editedTurns.size > 500) { notice('Save up to 500 edited paragraphs at once.',true); return; }
  busy = true; updateButtons();
  try { const id = selected.meeting.id; const data = await api('meetings/'+id, {action,revision:selected.review.revision,blocks:Object.fromEntries(editedTurns),meeting_end_seconds:end,confirm_review:$('confirm-transcript').checked});
    original=''; await openMeeting(id); notice(data.message);
  } catch(error) { notice(error.message + ' Your unsaved edits remain here.',true); }
  finally { busy=false;updateButtons(); }
}
$('save-transcript').addEventListener('click',()=>saveTranscript('transcript-save'));
$('generate-recap').addEventListener('click',()=>saveTranscript('transcript-confirm'));
$('retry-recap').addEventListener('click',()=>saveTranscript('retry'));
for (const id of ['meeting-end','confirm-transcript']) $(id).addEventListener('input',updateButtons);
for (const id of ['turn-search','warnings-only']) $(id).addEventListener('input',renderTurns);
start();
