/* Smriti: login, live sync, and the screens added for the three apps (family, elder, clinic). Loads after smriti.js. */
"use strict";

const ROLE_APP = { family: "family", elder: "elder", clinic: "clinic" };
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const SHARE = {
  okay_only: ["Only that I'm okay", "My family hears that I'm doing well. Nothing more."],
  health: ["Health worries too", "My family hears about my health worries, in my own words."],
  all: ["Everything we talk about", "My family hears how I am and what we talked about."],
};

/* ---------------------------------------------------------------- boot, login, logout */
async function boot() {
  const res = await fetch("/api/auth/me", { credentials: "same-origin" });
  const me = await res.json();
  state.me = me;
  if (!me.user) { showLogin(); return; }
  state.app = ROLE_APP[me.user.role] || me.app;
  const elderLang = ((me.parents || [])[0] || {}).language;
  setUiLang(store.get("ui") || (state.app === "elder" && UI_LANGS[elderLang] ? elderLang : "en"));
  document.body.classList.toggle("elder-app", state.app === "elder");
  document.title = `Smriti · ${APP_NAME[state.app]}`;
  const parents = me.parents || [];
  const saved = store.get(`parent.${me.user.id}`);
  state.parentId = (parents.find((p) => p.id === saved) || parents[0] || {}).id || null;
  state.parent = parents.find((p) => p.id === state.parentId) || null;
  await loadCallMode();
  startLiveSync();
  route();
}

function showLogin() {
  const me = state.me || { demo_users: [], app: "family" };
  document.body.classList.remove("elder-app");
  $("#nav").innerHTML = ""; $("#tabbar").innerHTML = ""; $("#sideFoot").innerHTML = "";
  if (!store.get("ui")) setUiLang("en"); else setUiLang(store.get("ui"));
  const who = { family: "Log in as the family", elder: "Log in as the elder", clinic: "Log in as the care team" }[me.app] || "Log in as the family";
  const ports = me.ports || {};
  $("#view").innerHTML = `<div class="login">
    <div class="card" style="max-width:560px;margin:8vh auto 0;padding:36px">
      <div class="row" style="gap:14px"><svg width="46" height="46" viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="18" fill="#0E5E63"/><path d="M9 24c5-9 17-9 22 0" stroke="#E3A72F" stroke-width="3" fill="none" stroke-linecap="round"/><circle cx="20" cy="15" r="3" fill="#fff"/></svg>
        <div><h1 style="font-size:30px">Smriti</h1><div class="muted">${tr("Every week, someone remembers")}</div></div></div>
      <div style="margin-top:20px">${uiLangSwitch()}</div>
      <h2 style="margin-top:22px">${tr(who)}</h2>
      <p class="muted" style="margin-top:6px">${tr("Demo login: pick a person. No password in the demo.")}</p>
      <div class="stack" style="margin-top:18px">${(me.demo_users || []).map((u) => `<button class="case" data-id="${u.id}" style="grid-template-columns:44px 1fr;align-items:center">
        <div class="avatar sm">${esc(u.name[0])}</div><div><b>${esc(u.name)}</b><div class="small muted">${esc(u.role_label)}${u.org ? " · " + esc(u.org) : ""}${u.age ? " · " + u.age + " years" : ""} · ${esc(u.smriti_id)}</div></div></button>`).join("") || `<p class="empty">No demo users yet.</p>`}</div>
      <p class="small muted" style="margin-top:18px">${tr("Other apps")}: <a href="${ports.family || "#"}">Family</a> · <a href="${ports.elder || "#"}">Elder</a> · <a href="${ports.clinic || "#"}">Care team</a></p>
    </div></div>`;
  $("#view").querySelectorAll(".case").forEach((b) => (b.onclick = async () => {
    await fetch("/api/auth/demo-login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: b.dataset.id }) });
    location.hash = "";
    boot();
  }));
}

async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
  if (state.sync) state.sync.close();
  state.me = null; state.parent = null; state.parentId = null;
  const me = await fetch("/api/auth/me", { credentials: "same-origin" }).then((r) => r.json());
  state.me = me;
  showLogin();
}

/* ---------------------------------------------------------------- parents: add, switch, reset; call language */
function languagePicker(p) {
  const pref = (p && p.language) || "en";
  const opts = Object.keys(NATIVE).map((k) => `<option value="${k}">${NATIVE[k]}${NATIVE[k] !== LANG[k] ? " · " + LANG[k] : ""}</option>`).join("");
  return `<label class="field"><span>Language for this call</span><select id="callLang">
    <option value="">${esc((p && p.call_name) || "Their")}'s preferred language (${esc(NATIVE[pref] || pref)})</option>
    <option value="ask">Let them choose: Smriti asks first</option>${opts}</select></label>`;
}

function parentSwitcher() {
  if (state.app !== "family") return "";
  const parents = (state.me && state.me.parents) || [];
  return `<div class="parent-switch"><label class="small muted" for="parentSel">Looking after</label>
    <select id="parentSel">${parents.map((x) => `<option value="${x.id}" ${x.id === state.parentId ? "selected" : ""}>${esc(x.call_name)} · ${esc(x.full_name)}</option>`).join("")}</select>
    <div class="row" style="margin-top:8px;gap:6px"><button type="button" class="btn sm" id="addParent">+ Add a parent</button><button type="button" class="btn quiet sm" id="resetDemo" title="Remove parents added in the app; keeps the sample family">Reset</button></div></div>`;
}

document.addEventListener("change", (e) => {
  if (e.target && e.target.id === "parentSel") {
    state.parentId = e.target.value;
    store.set(`parent.${state.me.user.id}`, state.parentId);
    state.parent = (state.me.parents || []).find((x) => x.id === state.parentId) || null;
    location.hash = "#/today";
    route();
  }
});

document.addEventListener("click", async (e) => {
  if (e.target.closest && e.target.closest("#addParent")) addParentDialog();
  if (e.target.closest && e.target.closest("#resetDemo")) {
    const el = modal(`<h2>Reset demo profiles?</h2><p class="muted">Removes every parent added in the app, with their calls and history. The sample family (Appa) stays.</p>
      <div class="actions"><button class="btn quiet" id="cancel">Cancel</button><button class="btn" id="go">Reset</button></div>`);
    $("#cancel", el).onclick = closeModal;
    $("#go", el).onclick = async () => {
      const r = await api("/api/people/reset-demo", { method: "POST" });
      closeModal();
      await refreshMe();
      state.parentId = ((state.me.parents || [])[0] || {}).id || null;
      state.parent = (state.me.parents || [])[0] || null;
      toast(`Removed ${r.removed} added profile${r.removed === 1 ? "" : "s"}.`);
      location.hash = "#/today"; route();
    };
  }
});

function addParentDialog() {
  const el = modal(`<h2>Add a parent</h2><p class="muted">Smriti will call them in the language you choose. They get their own simple page in the elder app.</p>
    <label class="field"><span>Full name</span><input id="fn" placeholder="e.g. Kamala Sharma"></label>
    <div class="grid g2" style="gap:12px"><label class="field"><span>What you call them</span><input id="cn" placeholder="Amma, Papa, Ajji…"></label>
      <label class="field"><span>Age</span><input id="age" type="number" min="40" max="120" placeholder="70"></label></div>
    <div class="grid g2" style="gap:12px"><label class="field"><span>City</span><input id="city" placeholder="Bengaluru"></label>
      <label class="field"><span>You are their</span><select id="rel"><option>son</option><option>daughter</option><option>grandchild</option><option>relative</option><option>friend</option></select></label></div>
    <label class="field"><span>Preferred language for calls</span><select id="lang">${Object.keys(NATIVE).map((k) => `<option value="${k}" ${k === "en" ? "selected" : ""}>${NATIVE[k]}${NATIVE[k] !== LANG[k] ? " · " + LANG[k] : ""}</option>`).join("")}</select></label>
    <label class="field"><span>What the family can see (they can change this later)</span><select id="share"><option value="health">Health worries too</option><option value="okay_only">Only that they're okay</option><option value="all">Everything they talk about</option></select></label>
    <label class="field"><span>Phone number (kept only in this browser)</span><input id="ph" inputmode="tel" placeholder="+91 98765 43210"></label>
    <div class="err" id="err" hidden></div>
    <div class="actions"><button class="btn quiet" id="cancel">Cancel</button><button class="btn" id="go">Add</button></div>`);
  $("#cancel", el).onclick = closeModal;
  $("#go", el).onclick = async () => {
    try {
      const age = parseInt($("#age", el).value, 10);
      const p = await api("/api/people/parents", { method: "POST", body: {
        full_name: $("#fn", el).value.trim(), call_name: $("#cn", el).value.trim(), age: Number.isFinite(age) ? age : null,
        city: $("#city", el).value.trim(), language: $("#lang", el).value, relation: $("#rel", el).value, share_level: $("#share", el).value } });
      const phone = $("#ph", el).value.replace(/[\s-]/g, "");
      if (phone) store.set("parentPhone." + p.id, phone);
      closeModal();
      await refreshMe();
      state.parentId = p.id; state.parent = p;
      store.set(`parent.${state.me.user.id}`, p.id);
      toast(`${p.call_name} added. Smriti will speak ${LANG[p.language] || p.language}.`);
      location.hash = "#/today"; route();
    } catch (err) { $("#err", el).textContent = err.message; $("#err", el).hidden = false; }
  };
}

/* ---------------------------------------------------------------- real calls or simulated (Bolna credits) */
async function loadCallMode() {
  try { state.callMode = await api("/api/auth/call-mode"); } catch { state.callMode = { live: false, available: false }; }
}

function currentRoute() {
  return (location.hash.replace(/^#\/?/, "") || HOME[state.app]).split("/")[0];
}

function usd(cents) { return cents === null || cents === undefined ? "" : `$${(Number(cents) / 100).toFixed(2)}`; }

function callModeSwitch() {
  const m = state.callMode || { live: false, available: false };
  return `<div class="credits ${m.live ? "on" : ""}" style="margin-top:12px">
    <div class="spread"><b>${m.live ? "Real calls" : "Simulated calls"}</b>
      <button type="button" class="switch ${m.live ? "on" : ""}" id="creditsToggle" role="switch" aria-checked="${m.live}" aria-label="Use Bolna credits" ${m.available ? "" : "disabled"}><i></i></button></div>
    <div class="small">${m.live ? `Using Bolna credits${m.wallet !== null && m.wallet !== undefined ? " · " + usd(m.wallet) + " left" : ""}` : m.available ? "No credits used. Switch on to place real calls." : "This server is offline-only (DEMO_MODE=1)."}</div></div>`;
}

function callModeNote() {
  const m = state.callMode || {};
  return m.live
    ? `<p class="mode-note live">Real call · uses Bolna credits (about $0.06 a minute).</p>`
    : `<p class="mode-note">Simulated call · no credits used. Turn on “Real calls” in the sidebar for a real phone call.</p>`;
}

document.addEventListener("click", async (e) => {
  const t = e.target.closest && e.target.closest("#creditsToggle");
  if (!t || t.disabled) return;
  const m = state.callMode || {};
  if (!m.live) {
    const el = modal(`<h2>Use Bolna credits?</h2><p class="muted">Calls from all three apps will become real phone calls and use your Bolna balance${m.wallet !== null && m.wallet !== undefined ? " (" + usd(m.wallet) + " left)" : ""}. About $0.06 a minute.</p>
      <div class="actions"><button class="btn quiet" id="cancel">Keep simulated</button><button class="btn" id="go">Turn on real calls</button></div>`);
    $("#cancel", el).onclick = closeModal;
    $("#go", el).onclick = async () => {
      try { state.callMode = { ...m, ...(await api("/api/auth/call-mode", { method: "PUT", body: { live: true } })) }; closeModal(); await loadCallMode(); renderNav(currentRoute()); }
      catch (err) { closeModal(); toast(err.message); }
    };
  } else {
    state.callMode = { ...m, ...(await api("/api/auth/call-mode", { method: "PUT", body: { live: false } })) };
    renderNav(currentRoute());
  }
});

/* ---------------------------------------------------------------- live sync across the three apps */
function startLiveSync() {
  if (state.sync) state.sync.close();
  let timer = null;
  try {
    state.sync = new EventSource("/api/auth/live");
    state.sync.onmessage = (e) => {
      let ev;
      try { ev = JSON.parse(e.data); } catch { return; }
      if (ev.type === "call_mode") { state.callMode = { ...(state.callMode || {}), live: ev.live }; renderNav(currentRoute()); toast(ev.live ? "Real calls are ON: calls use Bolna credits." : "Real calls are OFF: calls are simulated."); return; }
      if (ev.type === "activity") toast(ev.text);
      if ($(".scrim")) return; // don't redraw under an open dialog
      clearTimeout(timer);
      timer = setTimeout(() => { if (!$(".scrim")) refreshMe().then(route); }, 700);
    };
  } catch { /* the page still works without live updates */ }
}

async function refreshMe() {
  const me = await fetch("/api/auth/me", { credentials: "same-origin" }).then((r) => r.json());
  if (!me.user) return;
  state.me = me;
  state.parent = (me.parents || []).find((p) => p.id === state.parentId) || state.parent;
}

/* ---------------------------------------------------------------- shared pieces */
function historyList(items, empty = "Nothing yet.") {
  if (!items.length) return `<p class="empty">${empty}</p>`;
  return `<ul class="feed">${items.map((a) => `<li><span class="dot ${a.kind === "flag" ? "red" : a.kind === "review" ? "memory" : a.kind === "circle" ? "yellow" : "green"}"></span>
    <div><div>${esc(a.text)}</div><div class="small muted">${esc(a.actor)} · ${fmtDay(a.at)}, ${fmtTime(a.at)} · ${ago(a.at)}</div></div></li>`).join("")}</ul>`;
}

function memberRow(m, canDecide) {
  const status = m.status === "active" ? `<span class="chip green">${tr("In the circle")}</span>` : m.status === "pending" ? `<span class="chip yellow">${tr("Waiting for the elder")}</span>` : `<span class="chip">${esc(m.status)}</span>`;
  return `<div class="member"><div class="avatar sm">${esc(m.name[0])}</div><div style="flex:1"><b>${esc(m.name)}</b>
    <div class="small muted">${esc(m.role_label)}${m.org ? " · " + esc(m.org) : ""} · ${esc(m.smriti_id)}${m.invited_by ? " · added by " + esc(m.invited_by) : ""}</div></div>${status}
    ${canDecide && m.status === "pending" ? `<div class="row"><button class="btn sm" data-yes="${m.member_id}">${tr("Yes")}</button><button class="btn quiet sm" data-no="${m.member_id}">${tr("No")}</button></div>` : ""}</div>`;
}

function wireDecisions(root) {
  root.querySelectorAll("[data-yes],[data-no]").forEach((b) => (b.onclick = async () => {
    const id = b.dataset.yes || b.dataset.no;
    await api(`/api/people/members/${id}/decide`, { method: "POST", body: { accept: Boolean(b.dataset.yes) } });
    toast(tr(b.dataset.yes ? "Done. They're in your circle." : "Okay. They won't be added."));
    route();
  }));
}

function qr(el, text) {
  if (window.QRCode && el) { el.innerHTML = ""; new QRCode(el, { text, width: 132, height: 132, colorDark: "#1C2B2D", colorLight: "#FFFFFF" }); }
}

/* ---------------------------------------------------------------- family: schedules */
VIEWS.schedules = async (main) => {
  const r = await api("/api/family/schedules" + P());
  const p = state.parent || {};
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">Schedules</div><h1>When Smriti calls ${esc(p.call_name || "")}</h1>
    <p>Set a time and what to ask. Smriti asks it in ${esc(p.call_name || "their")}'s language, along with how they're feeling.</p></div>
    <button class="btn" id="newSched">${ic("spark")} New schedule</button></div>
    ${p.calls_paused ? `<div class="card flat" style="margin-bottom:16px;border-color:var(--amber)"><b>${esc(p.call_name)} has paused calls.</b> Only ${esc(p.call_name)} can turn them back on.</div>` : ""}
    <div class="grid g2">${r.items.map((s) => `<div class="card"><div class="spread"><h3 style="margin:0">${esc(s.label)}</h3><span class="chip ${s.active ? "green" : ""}">${s.active ? "On" : "Paused"}</span></div>
      <p class="muted" style="margin-top:6px">${s.days.length ? s.days.map((d) => WEEKDAYS[d]).join(", ") : "Every day"} at ${esc(s.time)} · ${s.kind === "memory" ? "memory check" : "check-in"}${s.created_by ? " · set by " + esc(s.created_by) : ""}</p>
      ${s.questions.length ? `<ul style="margin:12px 0 0;padding-left:20px">${s.questions.map((q) => `<li>${esc(q)}</li>`).join("")}</ul>` : `<p class="small muted" style="margin-top:12px">Just how they're feeling: sleep, appetite, mood, anything new.</p>`}
      <p class="small muted" style="margin-top:12px">${s.next_run_at ? "Next: " + fmtDay(s.next_run_at) + ", " + fmtTime(s.next_run_at) : ""}${s.last_run_at ? " · last ran " + ago(s.last_run_at) : ""}</p>
      <div class="row" style="margin-top:14px"><button class="btn sm" data-run="${s.id}">${ic("phone")} Run now</button><button class="btn quiet sm" data-toggle="${s.id}">${s.active ? "Pause" : "Turn on"}</button></div></div>`).join("")}</div>
    <p class="small muted" style="margin-top:16px">Calls only happen at these times when automatic calling is switched on for this account. In the demo, use Run now.</p>`;
  $("#newSched").onclick = () => scheduleDialog();
  main.querySelectorAll("[data-run]").forEach((b) => (b.onclick = () => runDialog(r.items.find((s) => s.id === b.dataset.run))));
  main.querySelectorAll("[data-toggle]").forEach((b) => (b.onclick = async () => {
    const s = r.items.find((x) => x.id === b.dataset.toggle);
    await api(`/api/family/schedules/${s.id}`, { method: "PATCH", body: { ...s, active: !s.active } });
    route();
  }));
};

function scheduleDialog() {
  const el = modal(`<h2>New schedule</h2><p class="muted">Smriti will call at this time and ask your questions kindly, in their language.</p>
    <label class="field"><span>Name</span><input id="sl" value="Evening check-in"></label>
    <label class="field"><span>Time</span><input id="st" type="time" value="20:00"></label>
    <div class="field"><span>Days (none = every day)</span><div class="row" id="sd">${WEEKDAYS.map((d, i) => `<button type="button" class="chip" data-d="${i}">${d}</button>`).join("")}</div></div>
    <label class="field"><span>What should Smriti ask? (one per line, up to 5)</span><textarea id="sq" rows="3" style="width:100%;border-radius:12px;border:1.5px solid var(--line);padding:10px 14px;font:inherit;background:var(--paper)">Did you take your BP tablet today?</textarea></label>
    <div class="err" id="err" hidden></div>
    <div class="actions"><button class="btn quiet" id="cancel">Cancel</button><button class="btn" id="go">Save</button></div>`);
  const days = new Set();
  el.querySelectorAll("[data-d]").forEach((b) => (b.onclick = () => { const d = +b.dataset.d; days.has(d) ? days.delete(d) : days.add(d); b.classList.toggle("peacock", days.has(d)); }));
  $("#cancel", el).onclick = closeModal;
  $("#go", el).onclick = async () => {
    try {
      await api("/api/family/schedules", { method: "POST", body: { label: $("#sl", el).value || "Check-in", time: $("#st", el).value || "20:00", days: [...days], questions: $("#sq", el).value.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 5), parent_id: state.parentId } });
      closeModal(); route();
    } catch (e) { $("#err", el).textContent = e.message; $("#err", el).hidden = false; }
  };
}

function runDialog(s) {
  const p = state.parent || {};
  const el = modal(`<h2>Run “${esc(s.label)}” now</h2>${callModeNote()}<p class="muted">Smriti will call ${esc(p.call_name)} now and ask: ${s.questions.length ? s.questions.map(esc).join(" · ") : "how they're feeling"}.</p>
    <label class="field"><span>Phone number</span><input id="ph" inputmode="tel" placeholder="+91 98765 43210" value="${esc(store.get("parentPhone." + state.parentId) || store.get("parentPhone"))}"></label>
    ${s.kind === "memory" ? "" : languagePicker(p)}
    <div class="err" id="err" hidden></div>
    <div class="actions"><button class="btn quiet" id="cancel">Cancel</button><button class="btn" id="go">${ic("phone")} Call now</button></div>`);
  $("#cancel", el).onclick = closeModal;
  $("#go", el).onclick = async () => {
    const phone = $("#ph", el).value.replace(/[\s-]/g, "");
    store.set("parentPhone." + state.parentId, phone);
    $("#go", el).disabled = true;
    try {
      const r = await api(`/api/family/schedules/${s.id}/run`, { method: "POST", body: { phone: phone || null, language: $("#callLang", el) ? $("#callLang", el).value || null : null } });
      closeModal();
      showLive(r.session_id, r.checkin_id, `${s.label}: calling ${p.call_name}`, s.kind === "memory" ? "memory" : "checkin");
    } catch (e) { $("#err", el).textContent = e.message; $("#err", el).hidden = false; $("#go", el).disabled = false; }
  };
}

/* ---------------------------------------------------------------- family: circle and contacts */
VIEWS.circle = async (main) => {
  const r = await api("/api/people/me");
  const me = r.me, c = r.circles.find((x) => x.parent_id === state.parentId) || r.circles[0];
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">Family circle</div><h1>${esc(c ? c.name : "Your circle")}</h1>
    <p>Everyone here sees the same timeline. ${esc((state.parent || {}).call_name || "The elder")} decides who joins and what is shared.</p></div></div>
    <div class="grid g2"><div class="card"><div class="spread"><h3 style="margin:0">Members</h3><button class="btn sm" id="invite">Add someone</button></div>
      <div style="margin-top:12px">${c ? c.members.map((m) => memberRow(m, false)).join("") : `<p class="empty">No circle yet.</p>`}</div>
      <p class="small muted" style="margin-top:12px">New members wait until ${esc((state.parent || {}).call_name || "the elder")} says yes, on their page or when Smriti asks on a call.</p></div>
    <div class="grid" style="align-content:start"><div class="card"><h3>Your Smriti ID</h3><div class="row" style="gap:20px;align-items:center"><div id="qr"></div>
      <div><div class="result-word" style="font-size:26px">${esc(me.smriti_id)}</div><p class="small muted" style="margin-top:6px">Share this ID or your phone number. When you both add each other, you're connected.</p></div></div></div>
      <div class="card"><div class="spread"><h3 style="margin:0">Contacts</h3><button class="btn quiet sm" id="addc">Add contact</button></div>
      <div style="margin-top:12px">${r.contacts.map((x) => `<div class="member"><div class="avatar sm">${esc(x.name[0])}</div><div style="flex:1"><b>${esc(x.name)}</b><div class="small muted">${esc(x.role_label)} · ${esc(x.smriti_id)}</div></div>
        ${x.mutual ? `<span class="chip green">Connected</span>` : x.added_you ? `<span class="chip yellow">Added you</span>` : `<span class="chip">Waiting for them</span>`}</div>`).join("") || `<p class="empty">No contacts yet.</p>`}</div></div></div></div>`;
  qr($("#qr"), me.smriti_id);
  $("#invite").onclick = () => inviteDialog();
  $("#addc").onclick = () => contactDialog();
};

function inviteDialog() {
  const el = modal(`<h2>Add someone to the circle</h2><p class="muted">Use their phone number or Smriti ID. They join when ${esc((state.parent || {}).call_name || "the elder")} agrees.</p>
    <label class="field"><span>Phone or Smriti ID</span><input id="q" placeholder="SM-PRIYA7 or +91…"></label>
    <label class="field"><span>Who are they?</span><select id="role"><option value="family">Family</option><option value="clinic">Doctor or care team</option></select></label>
    <div class="err" id="err" hidden></div><div class="actions"><button class="btn quiet" id="cancel">Cancel</button><button class="btn" id="go">Send request</button></div>`);
  $("#cancel", el).onclick = closeModal;
  $("#go", el).onclick = async () => {
    try { await api("/api/people/invite", { method: "POST", body: { query: $("#q", el).value, role: $("#role", el).value, parent_id: state.parentId } }); closeModal(); toast("Request sent. Waiting for the elder."); route(); }
    catch (e) { $("#err", el).textContent = e.message; $("#err", el).hidden = false; }
  };
}

function contactDialog() {
  const el = modal(`<h2>Add a contact</h2><p class="muted">Enter their phone number or Smriti ID.</p>
    <label class="field"><span>Phone or Smriti ID</span><input id="q" placeholder="SM-APPA74 or +91…"></label>
    <div class="err" id="err" hidden></div><div class="actions"><button class="btn quiet" id="cancel">Cancel</button><button class="btn" id="go">Add</button></div>`);
  $("#cancel", el).onclick = closeModal;
  $("#go", el).onclick = async () => {
    try { const c = await api("/api/people/contacts", { method: "POST", body: { query: $("#q", el).value } }); closeModal(); toast(c.mutual ? `You and ${c.name} are connected.` : `Added ${c.name}. You're connected once they add you too.`); route(); }
    catch (e) { $("#err", el).textContent = e.message; $("#err", el).hidden = false; }
  };
}

VIEWS.waiting = (main) => {
  const u = state.me.user;
  main.innerHTML = `<div class="card" style="max-width:640px;margin:6vh auto 0;padding:36px"><div class="eyebrow">Almost there</div>
    <h1>${tr("Waiting for your family's elder to say yes")}</h1>
    <p class="muted" style="margin-top:10px">You've been invited to a family circle. You'll see the timeline as soon as they agree, on their page or when Smriti asks them on a call. This page updates by itself.</p>
    <div class="row" style="gap:20px;margin-top:22px"><div id="qr"></div><div><div class="small muted">Your Smriti ID</div><div class="result-word">${esc(u.smriti_id)}</div></div></div></div>`;
  qr($("#qr"), u.smriti_id);
  // Not in any circle yet, so the live stream has nothing for us: check every few seconds instead.
  clearInterval(state.waitPoll);
  state.waitPoll = setInterval(async () => {
    const me = await fetch("/api/auth/me", { credentials: "same-origin" }).then((r) => r.json()).catch(() => null);
    if (me && me.user && me.parents && me.parents.length) { clearInterval(state.waitPoll); toast("You're in! The elder said yes."); boot(); }
  }, 3000);
};

/* ---------------------------------------------------------------- history (family and clinic) */
VIEWS.history = async (main) => {
  const r = await api("/api/family/history" + P());
  const p = state.parent || {};
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">History</div><h1>What happened</h1><p>Every call, review and change in ${esc(p.call_name || "this")}'s circle, live.</p></div></div>
    <div class="card">${historyList(r.items)}</div>`;
};

/* ---------------------------------------------------------------- elder app */
VIEWS.home = async (main) => {
  const [h, ppl, hist] = await Promise.all([api("/api/family/home" + P()), api("/api/people/me"), api("/api/family/history" + P())]);
  const p = h.parent, c = ppl.circles[0];
  state.parent = { ...state.parent, ...p };
  const pending = c ? c.members.filter((m) => m.status === "pending") : [];
  const langs = state.me.languages || LANG;
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">${fmtLong(new Date().toISOString())}</div><h1>${greeting()}, ${esc(p.honorific || p.call_name)}.</h1>
    <p>${tr("Smriti is here for you. You decide what is shared.")}</p></div></div>
    <div class="card flat" style="border-color:var(--marigold);background:var(--marigold-soft);margin-bottom:20px"><b>${tr("Smriti will never ask you for money, bank details or an OTP.")}</b></div>
    ${pending.map((m) => `<div class="card" style="margin-bottom:16px;border:2px solid var(--amber)"><h2>${tr("{a} wants to add {b}", { a: esc(m.invited_by || "Someone"), b: esc(m.name) })}</h2>
      <p class="muted" style="margin-top:6px">${m.member_role === "clinic" ? tr("{b} would see your check results and could order checks.", { b: esc(m.name) + (m.org ? " (" + esc(m.org) + ")" : "") }) : tr("{b} would see how you are doing, like the rest of your family.", { b: esc(m.name) })}</p>
      <div class="row" style="margin-top:16px"><button class="btn" data-yes="${m.member_id}">${tr("Yes, add them")}</button><button class="btn quiet" data-no="${m.member_id}">${tr("No")}</button></div></div>`).join("")}
    <div class="grid g2"><div class="card"><h2>${tr("Talk to Smriti now")}</h2><p class="muted" style="margin-top:6px">${tr("Smriti will call your phone for a short chat.")}</p>
      <button class="btn" id="callMe" style="margin-top:18px;min-height:64px;font-size:20px;width:100%">${ic("phone")} ${tr("Call me now")}</button></div>
      <div class="card"><h2>${tr("My language")}</h2><p class="muted" style="margin-top:6px">${tr("Smriti will speak this. You can also just ask her to switch on a call.")}</p>
      <select id="lang" class="big-select">${Object.entries(langs).map(([k, v]) => `<option value="${k}" ${k === p.language ? "selected" : ""}>${NATIVE[k] && NATIVE[k] !== v ? NATIVE[k] + " · " + v : v}</option>`).join("")}</select></div></div>
    <div class="card" style="margin-top:20px"><h2>${tr("What my family can see")}</h2><div class="share-opts">${Object.entries(SHARE).map(([k, [t, sub]]) => `<button class="share ${p.share_level === k ? "on" : ""}" data-share="${k}"><b>${tr(t)}</b><span>${tr(sub)}</span></button>`).join("")}</div>
      <p class="small muted" style="margin-top:10px">${tr("If you mention something that sounds like an emergency, our care team will always be told.")}</p></div>
    <div class="grid g2" style="margin-top:20px"><div class="card"><h2>${tr("Calls")}</h2><p class="muted" style="margin-top:6px">${tr(p.calls_paused ? "Calls are paused. Smriti won't call until you turn them back on." : "Smriti calls at the times your family set. You can pause them any time.")}</p>
      <button class="btn ${p.calls_paused ? "" : "quiet"}" id="pause" style="margin-top:16px;width:100%">${tr(p.calls_paused ? "Turn calls back on" : "Pause all calls")}</button></div>
      <div class="card"><h2>${tr("My Smriti ID")}</h2><div class="row" style="gap:18px;margin-top:8px"><div id="qr"></div><div class="result-word">${esc(ppl.me.smriti_id)}</div></div></div></div>
    <div class="card" style="margin-top:20px"><h2>${tr("Recently")}</h2>${historyList(hist.items.slice(0, 5))}</div>`;
  wireDecisions(main);
  qr($("#qr"), ppl.me.smriti_id);
  $("#callMe").onclick = () => callDialog("checkin");
  $("#lang").onchange = async (e) => { await api("/api/family/settings", { method: "PATCH", body: { language: e.target.value, parent_id: state.parentId } }); toast(tr("Smriti will speak {lang}.", { lang: langs[e.target.value] })); };
  main.querySelectorAll("[data-share]").forEach((b) => (b.onclick = async () => { await api("/api/family/settings", { method: "PATCH", body: { share_level: b.dataset.share, parent_id: state.parentId } }); route(); }));
  $("#pause").onclick = async () => { await api("/api/family/settings", { method: "PATCH", body: { calls_paused: !p.calls_paused, parent_id: state.parentId } }); await refreshMe(); route(); };
};

VIEWS.mycircle = async (main) => {
  const r = await api("/api/people/me");
  const c = r.circles[0];
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">${tr("My family")}</div><h1>${tr("Who can see how I am")}</h1><p>${tr("Only people you said yes to.")}</p></div></div>
    <div class="card">${c ? c.members.map((m) => memberRow(m, true)).join("") : `<p class="empty">Nobody yet.</p>`}</div>`;
  wireDecisions(main);
};

VIEWS.mycalls = async (main) => {
  const t = await api("/api/family/timeline" + P());
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">${tr("My calls")}</div><h1>${tr("My chats with Smriti")}</h1></div><button class="btn" id="callMe">${ic("phone")} ${tr("Call me now")}</button></div>
    <div class="thread">${t.items.filter((c) => c.kind !== "family").slice(0, 12).map((c) => knot(c, t.parent)).join("")}</div>`;
  $("#callMe").onclick = () => callDialog("checkin");
};

/* ---------------------------------------------------------------- clinic app */
VIEWS.patients = async (main) => {
  const r = await api("/api/care/patients");
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">Care team · ${esc((state.me.user || {}).org || "")}</div><h1>Patients</h1>
    <p>People whose families shared their Smriti results with you, with their agreement.</p></div><a class="btn" href="#/care">${ic("care")} Review queue</a></div>
    <div class="card"><table class="calls"><tr><th>Name</th><th>Age</th><th>Language</th><th>Last memory check</th><th>Open cases</th><th>Last contact</th><th></th></tr>
    ${r.items.map((p) => `<tr><td><b>${esc(p.full_name)}</b><div class="small muted">${esc(p.city)} · family: ${esc(p.family_name)}</div></td><td>${p.age || "—"}</td><td>${LANG[p.language] || p.language}</td>
      <td>${p.last_memory_outcome ? `<span class="chip ${OUTCOME[p.last_memory_outcome][1]}">${esc(p.last_memory_outcome)}</span>` : "—"}</td>
      <td>${p.open_cases ? `<span class="chip ${p.worst === "red" ? "red" : "yellow"}">${p.open_cases}</span>` : "0"}</td><td>${p.last_contact ? ago(p.last_contact) : "—"}</td>
      <td><a class="btn quiet sm" href="#/patient/${p.id}">Open</a></td></tr>`).join("")}</table></div>`;
};

VIEWS.patient = async (main, id) => {
  if (id) { state.parentId = id; store.set(`parent.${state.me.user.id}`, id); }
  const [t, s] = await Promise.all([api("/api/family/timeline" + P()), api("/api/family/doctor-summary" + P())]);
  const p = t.parent, m = s.memory;
  state.parent = p;
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow"><a href="#/patients">Patients</a> · ${esc(p.city)}</div><h1>${esc(p.full_name)}</h1>
    <p>${p.age ? p.age + " years · " : ""}${LANG[p.language] || p.language} · family contact ${esc(p.family_name)} (${esc(p.relation)})</p></div>
    <div class="row"><button class="btn" id="orderMem">${ic("brain")} Order a memory check</button><a class="btn quiet" href="#/doctor">${ic("print")} Summary</a></div></div>
    <div class="grid g2"><div class="card"><h3>Memory check</h3>${m ? `<div class="row" style="margin:6px 0 14px"><span class="chip ${OUTCOME[m.outcome][1]}">${esc(m.outcome)}</span><span class="muted small">${fmtDay(m.at)}</span></div>
      <table class="calls"><tr><th>Word learning</th><th>Delayed recall</th><th>Animals (60 s)</th><th>Orientation</th></tr><tr><td>${m.learning_total}/30</td><td>${m.delayed_recall}/10</td><td>${m.fluency_count}</td><td>${m.orientation_total}/5</td></tr></table>
      <p class="small muted" style="margin-top:10px">10/66-based tasks by phone · schooling band ${esc(m.schooling_band || "unknown")} · not validated against clinical assessment yet · <a target="_blank" rel="noopener" href="/report.html?id=${encodeURIComponent(m.session_id)}">full report</a></p>` : `<p class="empty">No memory check yet.</p>`}</div>
      <div class="card bars"><h3>What came up (8 weeks)</h3>${Object.entries(s.flags_by_category).map(([k, v]) => `<div class="b"><span>${esc(k)}</span><div class="track"><div class="fill" style="width:${Math.min(100, v * 25)}%"></div></div><b>${v}</b></div>`).join("") || `<p class="empty">Nothing.</p>`}
      <p class="small muted" style="margin-top:8px">${s.calls_completed} of ${s.calls_planned} check-ins completed.</p></div></div>
    <h2 style="margin:26px 0 14px">Timeline</h2><div class="thread">${t.items.slice(0, 10).map((c) => knot(c, p)).join("")}</div>`;
  $("#orderMem").onclick = () => callDialog("memory");
};

boot();
