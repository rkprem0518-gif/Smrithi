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
  document.body.classList.remove("setup");
  const res = await fetch("api/auth/me", { credentials: "same-origin" });
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
  document.body.classList.add("setup");
  $("#nav").innerHTML = ""; $("#tabbar").innerHTML = ""; $("#sideFoot").innerHTML = "";
  if (!store.get("ui")) setUiLang("en"); else setUiLang(store.get("ui"));
  clearInterval(state.loginPoll);
  const users = me.demo_users || [];
  if (me.app === "family" && !users.length) { welcome(1); return; }
  const ports = me.ports || {};
  const title = { family: "Who's using Smriti?", elder: "Who are you?", clinic: "Care team login" }[me.app] || "Who's using Smriti?";
  const list = users.map((u) => `<button class="case" data-id="${u.id}" style="grid-template-columns:44px 1fr;align-items:center">
    <div class="avatar sm">${esc(u.name[0])}</div><div><b>${esc(u.name)}</b><div class="small muted">${esc(u.role_label)}${u.org ? " · " + esc(u.org) : ""}${u.age ? " · " + u.age + " years" : ""} · ${esc(u.smriti_id)}</div></div></button>`).join("");
  let body;
  if (me.app === "elder") {
    body = users.length
      ? `<p class="muted" style="margin-top:6px">${tr("Tap your name.")}</p><div class="stack" style="margin-top:18px">${list}</div>`
      : `<div class="empty-state"><div class="big">👵🏽</div><h3>${tr("No one here yet")}</h3>
          <p class="muted">${tr("A son, daughter or grandchild adds their parent in the family app. Their name then appears here, ready to tap.")}</p>
          <a class="btn" style="margin-top:16px" href="${ports.family || "#"}">${tr("Open the family app")}</a>
          <p class="small muted" style="margin-top:12px">${tr("This page updates by itself.")}</p></div>`;
  } else if (me.app === "clinic") {
    body = `${users.length ? `<p class="muted" style="margin-top:6px">Pick your account. No password in the demo.</p><div class="stack" style="margin-top:18px">${list}</div>
        <button class="btn quiet" id="newAcct" style="margin-top:6px;width:100%">+ Create a care-team account</button>` : `<p class="muted" style="margin-top:6px">Smriti's care team reads every flagged call and decides when to call the family. Create your account to start.</p>${careSignup()}`}`;
  } else {
    body = `<p class="muted" style="margin-top:6px">Pick your account. No password in the demo.</p><div class="stack" style="margin-top:18px">${list}</div>
      <button class="btn quiet" id="newAcct" style="margin-top:6px;width:100%">+ I'm new: set up my family</button>`;
  }
  $("#view").innerHTML = `<div class="login"><div class="card" style="max-width:560px;margin:8vh auto 0;padding:36px">
      ${logoBlock()}
      <div style="margin-top:20px">${uiLangSwitch()}</div>
      <h2 style="margin-top:22px">${tr(title)}</h2>
      ${body}
      <p class="small muted" style="margin-top:22px">${tr("Other apps")}: <a href="${ports.family || "#"}">Family</a> · <a href="${ports.elder || "#"}">Elder</a> · <a href="${ports.clinic || "#"}">Care team</a></p>
    </div></div>`;
  $("#view").querySelectorAll(".case").forEach((b) => (b.onclick = async () => {
    await fetch("api/auth/demo-login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: b.dataset.id }) });
    location.hash = "";
    boot();
  }));
  const na = $("#newAcct");
  if (na) na.onclick = () => (me.app === "clinic" ? (na.outerHTML = careSignup(), wireCareSignup()) : welcome(2));
  wireCareSignup();
  if (!users.length) {
    // Nobody to log in as yet: check every few seconds, so a parent added in the family app shows up here.
    state.loginPoll = setInterval(async () => {
      const fresh = await fetch("api/auth/me", { credentials: "same-origin" }).then((r) => r.json()).catch(() => null);
      if (fresh && !fresh.user && (fresh.demo_users || []).length) { state.me = fresh; showLogin(); }
    }, 4000);
  }
}

function logoBlock() {
  return `<div class="row" style="gap:14px"><svg width="46" height="46" viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="18" fill="#0E5E63"/><path d="M9 24c5-9 17-9 22 0" stroke="#E3A72F" stroke-width="3" fill="none" stroke-linecap="round"/><circle cx="20" cy="15" r="3" fill="#fff"/></svg>
    <div><h1 style="font-size:30px">Smriti</h1><div class="muted">${tr("Every week, someone remembers")}</div></div></div>`;
}

function careSignup() {
  return `<div id="careForm" style="margin-top:8px"><label class="field"><span>Your name</span><input id="cName" placeholder="e.g. Dr. Meera Iyer" autocomplete="name"></label>
    <label class="field"><span>Clinic or organisation</span><input id="cOrg" placeholder="e.g. Jayanagar Memory Clinic"></label>
    <div class="err" id="cErr" hidden></div>
    <button class="btn" id="cGo" style="margin-top:16px;width:100%">Create my account</button></div>`;
}

function wireCareSignup() {
  const go = $("#cGo");
  if (!go) return;
  go.onclick = async () => {
    try {
      await api("api/auth/signup", { method: "POST", body: { name: $("#cName").value.trim(), org: $("#cOrg").value.trim() } });
      location.hash = ""; boot();
    } catch (err) { $("#cErr").textContent = friendly(err); $("#cErr").hidden = false; }
  };
}

function friendly(err) {
  const m = err.message || "";
  return /String should have at least|value_error|422/.test(m) ? "Please fill in the name (at least 2 letters)." : m;
}

/* ---------------------------------------------------------------- welcome: guided setup for a new family */
const SHARE_FAMILY = {
  okay_only: ["Only that they're okay", "You hear that they're doing well. Nothing more."],
  health: ["Health worries too", "You hear about their health worries, in their own words."],
  all: ["Everything they talk about", "You hear how they are and what they talked about."],
};
const WIZ = ["Welcome", "You", "Your parent", "Calls", "Done"];
const wiz = {};

function wizShell(step, inner) {
  document.body.classList.remove("elder-app");
  document.body.classList.add("setup");
  $("#nav").innerHTML = ""; $("#tabbar").innerHTML = ""; $("#sideFoot").innerHTML = "";
  $("#view").innerHTML = `<div class="wiz"><div class="card wiz-card">
      <div class="spread">${logoBlock()}<div>${uiLangSwitch()}</div></div>
      <ol class="wiz-steps" aria-label="Setup steps">${WIZ.map((s, i) => `<li class="${i + 1 < step ? "done" : i + 1 === step ? "now" : ""}"><i></i>${tr(s)}</li>`).join("")}</ol>
      ${inner}
      ${state.me && state.me.user ? `<p class="small muted wiz-foot">Logged in as <b>${esc(state.me.user.name)}</b> · <button type="button" class="linkish" id="wizLogout">Log out</button> · <button type="button" class="linkish" id="startOver">Start over</button></p>` : ""}</div></div>`;
  window.scrollTo(0, 0);
  const lo = $("#wizLogout");
  if (lo) lo.onclick = () => { Object.keys(wiz).forEach((k) => delete wiz[k]); logout(); };
}

function welcome(step) {
  clearInterval(state.loginPoll);
  ({ 1: wizWelcome, 2: wizYou, 3: wizParent, 4: wizCalls, 5: wizDone }[step] || wizWelcome)();
}

function wizWelcome() {
  const ports = (state.me && state.me.ports) || {};
  wizShell(1, `<h2 class="wiz-title">${tr("Your parents, looked after every week.")}</h2>
    <p class="muted wiz-lead">${tr("Smriti phones your mother or father every week, in their own language, for a friendly chat. You hear what matters, and a real person checks every worry.")}</p>
    <div class="wiz-points">
      <div><b>${ic("phone")} ${tr("A warm weekly call")}</b><span>${tr("In Kannada, Hindi, Tamil and 8 more languages. They can interrupt, change language or say not today.")}</span></div>
      <div><b>${ic("thread")} ${tr("You hear what matters")}</b><span>${tr("A timeline of how they've been, in their own words: sleep, pain, mood, memory.")}</span></div>
      <div><b>${ic("care")} ${tr("A person checks every worry")}</b><span>${tr("Fixed rules flag a concern; the care team decides; Smriti calls you and helps book a doctor.")}</span></div>
      <div><b>${ic("brain")} ${tr("A memory check every few weeks")}</b><span>${tr("A short check on the phone, scored by fixed rules. Never a diagnosis.")}</span></div>
    </div>
    <p class="small muted">${tr("Setup takes about two minutes. Calls are simulated (free) until you connect Bolna.")}</p>
    <div class="actions" style="justify-content:space-between;flex-wrap:wrap"><button class="btn quiet" id="sample">${tr("Explore a sample family instead")}</button><button class="btn" id="next">${tr("Set up my family")} →</button></div>
    <p class="small muted" style="margin-top:14px">${tr("Other apps")}: <a href="${ports.elder || "#"}">Elder</a> · <a href="${ports.clinic || "#"}">Care team</a></p>`);
  $("#next").onclick = () => welcome(2);
  $("#sample").onclick = async () => {
    $("#sample").disabled = true; $("#sample").textContent = "Adding the sample family…";
    await api("api/auth/sample-family", { method: "POST" });
    state.me = await fetch("api/auth/me", { credentials: "same-origin" }).then((r) => r.json());
    toast("Sample family added: log in as Ravi or Priya.");
    showLogin();
  };
}

function wizYou() {
  wizShell(2, `<h2 class="wiz-title">${tr("First, about you")}</h2>
    <p class="muted wiz-lead">${tr("Smriti says your name on calls (\"Is there anything you'd like me to tell Ravi?\").")}</p>
    <label class="field"><span>${tr("Your name")}</span><input id="yName" placeholder="e.g. Ravi Rao" autocomplete="name" value="${esc(wiz.name || "")}"></label>
    <label class="field"><span>${tr("You are their")}</span><select id="yRel">${["son", "daughter", "grandson", "granddaughter", "daughter-in-law", "son-in-law", "relative", "friend"].map((r) => `<option ${r === wiz.relation ? "selected" : ""}>${r}</option>`).join("")}</select></label>
    <div class="err" id="err" hidden></div>
    <div class="actions" style="justify-content:space-between"><button class="btn quiet" id="back">← ${tr("Back")}</button><button class="btn" id="next">${tr("Next")} →</button></div>`);
  $("#yName").focus();
  $("#back").onclick = () => (state.me && (state.me.demo_users || []).length ? showLogin() : welcome(1));
  $("#next").onclick = async () => {
    wiz.name = $("#yName").value.trim(); wiz.relation = $("#yRel").value;
    if (wiz.name.length < 2) { $("#err").textContent = "Please type your name."; $("#err").hidden = false; return; }
    try {
      await api("api/auth/signup", { method: "POST", body: { name: wiz.name, relation: wiz.relation } });
      state.me = await fetch("api/auth/me", { credentials: "same-origin" }).then((r) => r.json());
      welcome(3);
    } catch (err) { $("#err").textContent = friendly(err); $("#err").hidden = false; }
  };
}

function wizParent() {
  const rel = (state.me && state.me.user && state.me.user.title) || wiz.relation || "son";
  wizShell(3, `<h2 class="wiz-title">${tr("Who should Smriti call?")}</h2>
    <p class="muted wiz-lead">${tr("Add your mother, father or grandparent. They get their own simple page in the elder app.")}</p>
    <label class="field"><span>${tr("Their full name")}</span><input id="fn" placeholder="e.g. Kamala Sharma"></label>
    <div class="grid g2" style="gap:12px"><label class="field"><span>${tr("What you call them")}</span><input id="cn" placeholder="Amma, Papa, Ajji…"></label>
      <label class="field"><span>${tr("Age")}</span><input id="age" type="number" min="40" max="120" placeholder="72"></label></div>
    <label class="field"><span>${tr("City or village")}</span><input id="city" placeholder="Mysuru"></label>
    <div class="field"><span>${tr("Language Smriti speaks with them")}</span><div class="lang-grid" id="langs">${Object.keys(NATIVE).map((k) => `<button type="button" class="chip ${k === "kn" ? "peacock" : ""}" data-l="${k}">${NATIVE[k]}${NATIVE[k] !== LANG[k] ? ` <span class="small">${LANG[k]}</span>` : ""}</button>`).join("")}</div></div>
    <div class="field"><span>${tr("What can the family see? (they can change this on their own page)")}</span><div class="share-pick">${Object.entries(SHARE_FAMILY).map(([k, v]) => `<label class="choice"><input type="radio" name="share" value="${k}" ${k === "health" ? "checked" : ""}><b>${tr(v[0])}</b><small>${tr(v[1])}</small></label>`).join("")}</div></div>
    <label class="field"><span>${tr("Their phone number (optional, kept only in this browser)")}</span><input id="ph" inputmode="tel" placeholder="+91 98765 43210"></label>
    <div class="err" id="err" hidden></div>
    <div class="actions" style="justify-content:space-between;flex-wrap:wrap"><button class="btn quiet" id="join">${tr("Joining a family already on Smriti?")}</button><button class="btn" id="next">${tr("Add them")} →</button></div>`);
  let lang = "kn";
  $("#langs").querySelectorAll("[data-l]").forEach((b) => (b.onclick = () => { lang = b.dataset.l; $("#langs").querySelectorAll("[data-l]").forEach((x) => x.classList.toggle("peacock", x === b)); }));
  $("#fn").focus();
  $("#join").onclick = () => { wiz.joining = true; location.hash = "#/today"; boot(); };
  $("#next").onclick = async () => {
    const age = parseInt($("#age").value, 10);
    if ($("#fn").value.trim().length < 2) { $("#err").textContent = "Please type their name."; $("#err").hidden = false; return; }
    try {
      const p = await api("api/people/parents", { method: "POST", body: {
        full_name: $("#fn").value.trim(), call_name: $("#cn").value.trim(), age: Number.isFinite(age) ? age : null,
        city: $("#city").value.trim(), language: lang, relation: rel, share_level: (document.querySelector("input[name=share]:checked") || {}).value || "health" } });
      const phone = $("#ph").value.replace(/[\s-]/g, "");
      if (phone) store.set("parentPhone." + p.id, phone);
      wiz.parent = p;
      state.parentId = p.id; state.parent = p;
      store.set(`parent.${state.me.user.id}`, p.id);
      welcome(4);
    } catch (err) { $("#err").textContent = friendly(err); $("#err").hidden = false; }
  };
}

function wizCalls() {
  const p = wiz.parent || {};
  wizShell(4, `<h2 class="wiz-title">${tr("When should Smriti call {name}?", { name: esc(p.call_name || "them") })}</h2>
    <p class="muted wiz-lead">${tr("Pick the days and a time they're usually free. Nothing dials by itself in this demo: you press Run now, or Call now.")}</p>
    <div class="field"><span>${tr("Days")}</span><div class="row" style="gap:6px;flex-wrap:wrap" id="days">${WEEKDAYS.map((d, i) => `<button type="button" class="chip ${i === 6 ? "peacock" : ""}" data-d="${i}">${tr(d)}</button>`).join("")}</div></div>
    <label class="field"><span>${tr("Time")}</span><input id="time" type="time" value="10:30"></label>
    <label class="field"><span>${tr("Anything you'd like Smriti to ask? (optional, one per line)")}</span><textarea id="qs" rows="3" placeholder="Did you take your BP tablet?&#10;How was the temple visit?"></textarea></label>
    <div class="err" id="err" hidden></div>
    <div class="actions" style="justify-content:space-between"><button class="btn quiet" id="skip">${tr("Skip for now")}</button><button class="btn" id="next">${tr("Save")} →</button></div>`);
  const days = new Set([6]);
  $("#days").querySelectorAll("[data-d]").forEach((b) => (b.onclick = () => { const d = +b.dataset.d; days.has(d) ? days.delete(d) : days.add(d); b.classList.toggle("peacock", days.has(d)); }));
  $("#skip").onclick = () => { wiz.schedule = null; welcome(5); };
  $("#next").onclick = async () => {
    try {
      const qs = $("#qs").value.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 5);
      await api("api/family/schedules", { method: "POST", body: { label: "Weekly chat", time: $("#time").value || "10:30", days: [...days].sort(), questions: qs, parent_id: p.id } });
      wiz.schedule = { days: [...days].sort(), time: $("#time").value || "10:30" };
      welcome(5);
    } catch (err) { $("#err").textContent = friendly(err); $("#err").hidden = false; }
  };
}

function wizDone() {
  const p = wiz.parent || {};
  const s = wiz.schedule;
  const ports = (state.me && state.me.ports) || {};
  wizShell(5, `<h2 class="wiz-title">${tr("You're all set")} 🎉</h2>
    <ul class="wiz-done">
      <li>✓ ${tr("Your account")}: <b>${esc((state.me.user || {}).name || "")}</b> · ${tr("Smriti ID")} ${esc((state.me.user || {}).smriti_id || "")}</li>
      <li>✓ <b>${esc(p.call_name || "")}</b> (${esc(p.full_name || "")}) · ${tr("Smriti speaks {lang}", { lang: esc(LANG[p.language] || p.language || "") })}</li>
      <li>${s ? `✓ ${tr("Calls")}: ${s.days.length ? s.days.map((d) => tr(WEEKDAYS[d])).join(", ") : tr("every day")} ${tr("at")} ${esc(s.time)}` : `○ ${tr("No call times yet (add them under Schedules)")}`}</li>
    </ul>
    <h3 style="margin-top:22px">${tr("What next?")}</h3>
    <div class="wiz-next">
      <button class="wiz-tile" id="tryCall"><b>${ic("phone")} ${tr("Try a call now")}</b><span>${tr("A simulated call (free). Watch it live, then see it on the timeline.")}</span></button>
      <button class="wiz-tile" data-bolna><b>${ic("phone")} ${tr("Make calls real")}</b><span>${tr("Connect your Bolna API key. Until then, calls are simulated.")}</span></button>
      <a class="wiz-tile" href="${ports.elder || "#"}" target="_blank" rel="noopener"><b>${ic("user")} ${tr("See {name}'s page", { name: esc(p.call_name || "their") })}</b><span>${tr("The elder app: big text, their language, their choices.")}</span></a>
      <a class="wiz-tile" href="${ports.clinic || "#"}" target="_blank" rel="noopener"><b>${ic("care")} ${tr("Open the care team app")}</b><span>${tr("Where a person reviews every worry before you hear about it.")}</span></a>
    </div>
    <p class="notice-box" style="margin-top:16px">${BOLNA_NOTE}</p>
    <div class="actions"><button class="btn" id="go">${tr("Go to my dashboard")} →</button></div>`);
  const finish = async (thenCall) => { history.replaceState(null, "", "#/today"); await boot(); if (thenCall) callDialog("checkin"); };
  $("#go").onclick = () => finish(false);
  $("#tryCall").onclick = () => finish(true);
}

/* ---------------------------------------------------------------- remove one profile, or start over */
function myRole() {
  const mine = ((state.me && state.me.parents) || []).find((x) => x.id === state.parentId);
  return mine ? mine.my_role : "";
}

function removeProfileDialog() {
  const p = state.parent;
  if (!p) return;
  const el = modal(`<h2>Remove ${esc(p.call_name)}'s profile?</h2>
    <p class="muted">This deletes ${esc(p.full_name)} from Smriti: every call, flag, note, visit and schedule, their family circle and their login in the elder app. It can't be undone.</p>
    <div class="actions"><button class="btn quiet" id="cancel">Keep</button><button class="btn danger" id="go">Remove ${esc(p.call_name)}</button></div>`);
  $("#cancel", el).onclick = closeModal;
  $("#go", el).onclick = async () => {
    try {
      await api(`api/people/parents/${encodeURIComponent(p.id)}`, { method: "DELETE" });
      closeModal();
      toast(`${p.call_name}'s profile was removed.`);
      await afterProfilesChanged();
    } catch (err) { toast(err.message); }
  };
}

function startOverDialog() {
  const el = modal(`<h2>Start over?</h2>
    <p class="muted">Deletes <b>every</b> profile and account on this Smriti: all parents, family members, care-team accounts, calls and history. Everyone is logged out and Smriti opens at the welcome screen. Your Bolna connection stays.</p>
    <div class="actions"><button class="btn quiet" id="cancel">Cancel</button><button class="btn danger" id="go">Delete everything</button></div>`);
  $("#cancel", el).onclick = closeModal;
  $("#go", el).onclick = async () => {
    try {
      await api("api/people/start-over", { method: "POST" });
      closeModal();
      Object.keys(wiz).forEach((k) => delete wiz[k]);
      await afterProfilesChanged();
    } catch (err) { toast(err.message); }
  };
}

async function afterProfilesChanged() {
  const me = await fetch("api/auth/me", { credentials: "same-origin" }).then((r) => r.json());
  state.me = me;
  if (!me.user) { if (state.sync) state.sync.close(); state.parent = null; state.parentId = null; location.hash = ""; showLogin(); return; }
  location.hash = "#/today";
  boot();
}

document.addEventListener("click", (e) => {
  if (!e.target.closest) return;
  if (e.target.closest("#removeProfile")) removeProfileDialog();
  if (e.target.closest("#startOver")) startOverDialog();
});

async function logout() {
  await fetch("api/auth/logout", { method: "POST", credentials: "same-origin" });
  if (state.sync) state.sync.close();
  state.me = null; state.parent = null; state.parentId = null;
  const me = await fetch("api/auth/me", { credentials: "same-origin" }).then((r) => r.json());
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
    <div class="row" style="margin-top:8px;gap:6px"><button type="button" class="btn sm" id="addParent">+ Add a parent</button><button type="button" class="btn quiet sm" id="startOver" title="Delete every profile and account, back to the welcome screen">Start over</button></div></div>`;
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
      const p = await api("api/people/parents", { method: "POST", body: {
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
  try { state.callMode = await api("api/auth/call-mode"); } catch { state.callMode = { live: false, available: false }; }
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
    <div class="small">${m.live ? `Using Bolna credits${m.wallet !== null && m.wallet !== undefined ? " · " + usd(m.wallet) + " left" : ""}` : m.available ? "No credits used. Switch on to place real calls." : bolnaHint(m)}</div>
    ${bolnaLink(m)}
    <p class="bolna-note">${BOLNA_NOTE}</p></div>`;
}

const BOLNA_NOTE = "Real calls only work after you connect your own Bolna API key. Bolna trial accounts can call only numbers verified in your Bolna dashboard (Profile → Verified numbers).";

/* ---------------------------------------------------------------- connect a Bolna account (API key) */
function bolnaHint(m) {
  const b = m.bolna || {};
  if (b.can_connect) return m.can_manage ? "Calls are simulated. Connect your Bolna account to place real calls." : "Calls are simulated. The family can connect Bolna for real calls.";
  return "This server is offline-only (started with --offline).";
}

function bolnaLink(m) {
  const b = m.bolna || {};
  if (!m.can_manage) return "";
  const style = 'style="margin-top:10px;width:100%"';
  if (b.source === "app") return `<button type="button" class="btn quiet sm" data-bolna ${style}>✓ Bolna connected ${esc(b.key_hint || "")} · Manage</button>`;
  if (b.source === "env") return `<button type="button" class="btn sm" data-bolna ${style}>${ic("phone")} Connect Bolna API key</button><div class="small" style="margin-top:6px">Now using the key from .env ${esc(b.key_hint || "")}</div>`;
  if (b.can_connect) return `<button type="button" class="btn sm" data-bolna ${style}>${ic("phone")} Connect Bolna API key</button>`;
  return "";
}

function bolnaDialog() {
  const m = state.callMode || {};
  const b = m.bolna || {};
  if (b.source === "app") {
    const agents = Object.entries(b.agents || {}).map(([k, v]) => `${{ checkin: "Weekly check-in", family: "Call to the family", memory: "Memory check" }[k] || k}: ${v ? "ready" : "missing"}`).join(" · ");
    const el = modal(`<h2>Your Bolna account</h2>
      <p class="muted">Key ${esc(b.key_hint || "")} · ${esc(agents)}${b.from_number ? " · calls from " + esc(b.from_number) : ""}</p>
      <p class="small muted" style="margin-top:10px">Real calls are ${m.live ? "<b>on</b>" : "off"}. Disconnecting deletes the key from this server${b.env_key ? " and goes back to the key in .env" : " and makes every call simulated again"}. The agents stay on your Bolna account.</p>
      <p class="notice-box" style="margin-top:12px">${BOLNA_NOTE}</p>
      <div class="actions"><button class="btn quiet" id="cancel">Close</button><button class="btn danger" id="go">Disconnect</button></div>`);
    $("#cancel", el).onclick = closeModal;
    $("#go", el).onclick = async () => {
      try { await api("api/auth/bolna", { method: "DELETE" }); closeModal(); await loadCallMode(); renderNav(currentRoute()); toast("Bolna disconnected. Calls are simulated."); }
      catch (err) { toast(err.message); }
    };
    return;
  }
  const el = modal(`<h2>Connect your Bolna account</h2>
    <p class="notice-box">${BOLNA_NOTE}</p>
    ${b.source === "env" ? `<p class="small muted" style="margin-top:10px">Right now this server uses the key in <code>.env</code> (${esc(b.key_hint || "")}). A key you paste here takes priority until you disconnect it.</p>` : ""}
    <p class="muted" style="margin-top:12px">Paste your Bolna API key (Bolna dashboard → Developers → API keys). Smriti then sets up its three voice agents on your account: the weekly check-in, the call to the family and the memory check.</p>
    <label class="field" style="margin-top:14px"><span>Bolna API key</span><input id="bk" type="password" autocomplete="off" spellcheck="false" placeholder="bn-…"></label>
    <details style="margin-top:12px"><summary class="small">I already have Smriti agents on Bolna (optional)</summary>
      <div class="stack" style="margin-top:10px">
        <label class="field"><span>Check-in agent ID</span><input id="bc" autocomplete="off" spellcheck="false"></label>
        <label class="field"><span>Family-call agent ID</span><input id="bf" autocomplete="off" spellcheck="false"></label>
        <label class="field"><span>Memory-check agent ID</span><input id="bm" autocomplete="off" spellcheck="false"></label>
        <label class="field"><span>Call from this number (optional)</span><input id="bn" autocomplete="off" placeholder="+91…"></label>
        <p class="small muted">Leave an agent empty and Smriti creates it.</p></div></details>
    <ul class="small muted" style="margin:14px 0 0 18px;line-height:1.5">
      <li>Connecting places no call and uses no credits. Calls stay simulated until you switch on <b>Real calls</b>.</li>
      <li>The key stays on this server and is never shown in the browser again.${location.hostname === "localhost" || location.hostname === "127.0.0.1" ? "" : " On a shared server anyone using it could place calls with your key, so disconnect when you're done."}</li>
      <li>No Bolna account yet? Sign up at bolna.ai, then copy the key from Developers → API keys.</li></ul>
    <div class="actions"><button class="btn quiet" id="cancel">Cancel</button><button class="btn" id="go">Connect</button></div>`);
  $("#cancel", el).onclick = closeModal;
  $("#bk", el).focus();
  $("#go", el).onclick = async () => {
    const key = $("#bk", el).value.trim();
    if (!key) { toast("Paste your Bolna API key first."); return; }
    const go = $("#go", el);
    go.disabled = true; go.textContent = "Connecting…";
    try {
      const r = await api("api/auth/bolna", { method: "POST", body: { api_key: key, checkin_agent_id: $("#bc", el).value, family_agent_id: $("#bf", el).value, memory_agent_id: $("#bm", el).value, from_number: $("#bn", el).value } });
      closeModal(); await loadCallMode(); renderNav(currentRoute());
      toast(`Bolna connected${r.created && r.created.length ? ` · ${r.created.length} agent${r.created.length > 1 ? "s" : ""} created` : ""}. Switch on Real calls to use it.`);
    } catch (err) { go.disabled = false; go.textContent = "Connect"; toast(err.message); }
  };
}

document.addEventListener("click", (e) => {
  if (e.target.closest && e.target.closest("[data-bolna]")) bolnaDialog();
});

function callModeNote() {
  const m = state.callMode || {};
  return m.live
    ? `<p class="mode-note live">Real call · uses Bolna credits (about $0.06 a minute). On a Bolna trial account, only numbers verified in your Bolna dashboard can be called.</p>`
    : `<p class="mode-note">Simulated call · no credits used. For a real phone call, connect your Bolna API key and turn on “Real calls” (in the sidebar, or under More on small screens).</p>`;
}

document.addEventListener("click", async (e) => {
  const t = e.target.closest && e.target.closest("#creditsToggle");
  if (!t || t.disabled) return;
  const m = state.callMode || {};
  if (!m.live) {
    const el = modal(`<h2>Use Bolna credits?</h2><p class="muted">Calls from all three apps will become real phone calls and use your Bolna balance${m.wallet !== null && m.wallet !== undefined ? " (" + usd(m.wallet) + " left)" : ""}. About $0.06 a minute.</p>
      <p class="notice-box" style="margin-top:12px">On a Bolna trial account, only numbers verified in your Bolna dashboard can be called. Other numbers fail without ringing.</p>
      <div class="actions"><button class="btn quiet" id="cancel">Keep simulated</button><button class="btn" id="go">Turn on real calls</button></div>`);
    $("#cancel", el).onclick = closeModal;
    $("#go", el).onclick = async () => {
      try { state.callMode = { ...m, ...(await api("api/auth/call-mode", { method: "PUT", body: { live: true } })) }; closeModal(); await loadCallMode(); renderNav(currentRoute()); }
      catch (err) { closeModal(); toast(err.message); }
    };
  } else {
    state.callMode = { ...m, ...(await api("api/auth/call-mode", { method: "PUT", body: { live: false } })) };
    renderNav(currentRoute());
  }
});

/* ---------------------------------------------------------------- live sync across the three apps */
function startLiveSync() {
  if (state.sync) state.sync.close();
  let timer = null;
  try {
    state.sync = new EventSource("api/auth/live");
    state.sync.onmessage = (e) => {
      let ev;
      try { ev = JSON.parse(e.data); } catch { return; }
      if (ev.type === "profiles") { afterProfilesChanged(); return; }
      if (ev.type === "call_mode" && ev.connected !== undefined) { loadCallMode().then(() => renderNav(currentRoute())); toast(ev.connected ? `${ev.by} connected Bolna. Real calls can be switched on.` : `${ev.by} disconnected Bolna: calls are simulated.`); return; }
      if (ev.type === "call_mode") { state.callMode = { ...(state.callMode || {}), live: ev.live }; renderNav(currentRoute()); toast(ev.live ? "Real calls are ON: calls use Bolna credits." : "Real calls are OFF: calls are simulated."); return; }
      if (ev.type === "activity") toast(ev.text);
      if ($(".scrim")) return; // don't redraw under an open dialog
      clearTimeout(timer);
      timer = setTimeout(() => { if (!$(".scrim")) refreshMe().then(route); }, 700);
    };
  } catch { /* the page still works without live updates */ }
}

async function refreshMe() {
  const me = await fetch("api/auth/me", { credentials: "same-origin" }).then((r) => r.json());
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
    await api(`api/people/members/${id}/decide`, { method: "POST", body: { accept: Boolean(b.dataset.yes) } });
    toast(tr(b.dataset.yes ? "Done. They're in your circle." : "Okay. They won't be added."));
    route();
  }));
}

function qr(el, text) {
  if (window.QRCode && el) { el.innerHTML = ""; new QRCode(el, { text, width: 132, height: 132, colorDark: "#1C2B2D", colorLight: "#FFFFFF" }); }
}

/* ---------------------------------------------------------------- family: schedules */
VIEWS.schedules = async (main) => {
  const r = await api("api/family/schedules" + P());
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
    await api(`api/family/schedules/${s.id}`, { method: "PATCH", body: { ...s, active: !s.active } });
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
      await api("api/family/schedules", { method: "POST", body: { label: $("#sl", el).value || "Check-in", time: $("#st", el).value || "20:00", days: [...days], questions: $("#sq", el).value.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 5), parent_id: state.parentId } });
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
      const r = await api(`api/family/schedules/${s.id}/run`, { method: "POST", body: { phone: phone || null, language: $("#callLang", el) ? $("#callLang", el).value || null : null } });
      closeModal();
      showLive(r.session_id, r.checkin_id, `${s.label}: calling ${p.call_name}`, s.kind === "memory" ? "memory" : "checkin");
    } catch (e) { $("#err", el).textContent = e.message; $("#err", el).hidden = false; $("#go", el).disabled = false; }
  };
}

/* ---------------------------------------------------------------- family: circle and contacts */
VIEWS.circle = async (main) => {
  const r = await api("api/people/me");
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
  const p = state.parent || {};
  const names = document.createElement("div");
  names.className = "card";
  names.style.marginTop = "20px";
  names.innerHTML = `<div class="spread"><h3 style="margin:0">Names Smriti uses</h3><span class="small muted">Said out loud on every call</span></div>
    <div class="grid g2" style="gap:12px;margin-top:6px">
      <label class="field"><span>Your name (as Smriti says it)</span><input id="nFamily" value="${esc(p.family_name || "")}" placeholder="e.g. Arjun"></label>
      <label class="field"><span>You are their</span><input id="nRelation" value="${esc(p.relation || "")}" placeholder="son, daughter, grandchild"></label>
      <label class="field"><span>Their full name</span><input id="nFull" value="${esc(p.full_name || "")}"></label>
      <label class="field"><span>What you call them</span><input id="nCall" value="${esc(p.call_name || "")}" placeholder="Amma, Appa, Ajji"></label>
      <label class="field"><span>How Smriti greets them</span><input id="nHon" value="${esc(p.honorific || "")}" placeholder="Kamala ji"></label>
      <label class="field"><span>Your display name in the apps</span><input id="nMe" value="${esc(me.name)}"></label>
    </div>
    <p class="small muted" style="margin-top:10px">For example: “Is there anything you’d like me to tell <b>${esc(p.family_name || "you")}</b>?” and “Hello, <b>${esc(p.honorific || p.call_name || "")}</b>!”</p>
    <div class="err" id="nErr" hidden></div>
    <div class="row" style="margin-top:14px"><button class="btn" id="nSave">Save names</button></div>`;
  main.appendChild(names);
  $("#nSave").onclick = async () => {
    const val = (id) => $(id).value.trim();
    try {
      await api("api/family/settings", { method: "PATCH", body: { parent_id: state.parentId, family_name: val("#nFamily") || null,
        relation: val("#nRelation") || null, full_name: val("#nFull") || null, call_name: val("#nCall") || null, honorific: val("#nHon") || null } });
      if (val("#nMe") && val("#nMe") !== me.name) await api("api/people/me", { method: "PATCH", body: { name: val("#nMe") } });
      await refreshMe();
      toast("Saved. Smriti will use these names on the next call.");
      route();
    } catch (e) { $("#nErr").textContent = e.message; $("#nErr").hidden = false; }
  };
  if (state.app === "family" && state.parent && myRole() === "family") {
    const danger = document.createElement("div");
    danger.className = "card danger-zone";
    danger.style.marginTop = "20px";
    danger.innerHTML = `<h3 style="margin:0">Remove ${esc(state.parent.call_name)}'s profile</h3>
      <p class="muted" style="margin-top:6px">Deletes ${esc(state.parent.full_name)} and everything about them from Smriti. To delete every profile at once, use <b>Start over</b> in the sidebar.</p>
      <button class="btn danger" id="removeProfile" style="margin-top:12px">Remove ${esc(state.parent.call_name)}</button>`;
    main.appendChild(danger);
  }
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
    try { await api("api/people/invite", { method: "POST", body: { query: $("#q", el).value, role: $("#role", el).value, parent_id: state.parentId } }); closeModal(); toast("Request sent. Waiting for the elder."); route(); }
    catch (e) { $("#err", el).textContent = e.message; $("#err", el).hidden = false; }
  };
}

function contactDialog() {
  const el = modal(`<h2>Add a contact</h2><p class="muted">Enter their phone number or Smriti ID.</p>
    <label class="field"><span>Phone or Smriti ID</span><input id="q" placeholder="SM-APPA74 or +91…"></label>
    <div class="err" id="err" hidden></div><div class="actions"><button class="btn quiet" id="cancel">Cancel</button><button class="btn" id="go">Add</button></div>`);
  $("#cancel", el).onclick = closeModal;
  $("#go", el).onclick = async () => {
    try { const c = await api("api/people/contacts", { method: "POST", body: { query: $("#q", el).value } }); closeModal(); toast(c.mutual ? `You and ${c.name} are connected.` : `Added ${c.name}. You're connected once they add you too.`); route(); }
    catch (e) { $("#err", el).textContent = e.message; $("#err", el).hidden = false; }
  };
}

VIEWS.waiting = (main) => {
  const u = state.me.user;
  main.innerHTML = `<div class="card" style="max-width:640px;margin:6vh auto 0;padding:36px"><div class="eyebrow">Almost there</div>
    <h1>${tr("Waiting for your family's elder to say yes")}</h1>
    <p class="muted" style="margin-top:10px">You've been invited to a family circle. You'll see the timeline as soon as they agree, on their page or when Smriti asks them on a call. This page updates by itself.</p>
    <div class="row" style="gap:20px;margin-top:22px"><div id="qr"></div><div><div class="small muted">Your Smriti ID</div><div class="result-word">${esc(u.smriti_id)}</div></div></div>
    ${state.app === "family" ? `<button class="btn quiet" id="addInstead" style="margin-top:20px">Add a parent myself instead</button>` : ""}</div>`;
  qr($("#qr"), u.smriti_id);
  if ($("#addInstead")) $("#addInstead").onclick = () => { clearInterval(state.waitPoll); wiz.joining = false; welcome(3); };
  // Not in any circle yet, so the live stream has nothing for us: check every few seconds instead.
  clearInterval(state.waitPoll);
  state.waitPoll = setInterval(async () => {
    const me = await fetch("api/auth/me", { credentials: "same-origin" }).then((r) => r.json()).catch(() => null);
    if (me && me.user && me.parents && me.parents.length) { clearInterval(state.waitPoll); toast("You're in! The elder said yes."); boot(); }
  }, 3000);
};

/* ---------------------------------------------------------------- history (family and clinic) */
VIEWS.history = async (main) => {
  const r = await api("api/family/history" + P());
  const p = state.parent || {};
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">History</div><h1>What happened</h1><p>Every call, review and change in ${esc(p.call_name || "this")}'s circle, live.</p></div></div>
    <div class="card">${historyList(r.items)}</div>`;
};

/* ---------------------------------------------------------------- elder app */
VIEWS.home = async (main) => {
  const [h, ppl, hist] = await Promise.all([api("api/family/home" + P()), api("api/people/me"), api("api/family/history" + P())]);
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
  $("#lang").onchange = async (e) => { await api("api/family/settings", { method: "PATCH", body: { language: e.target.value, parent_id: state.parentId } }); toast(tr("Smriti will speak {lang}.", { lang: langs[e.target.value] })); };
  main.querySelectorAll("[data-share]").forEach((b) => (b.onclick = async () => { await api("api/family/settings", { method: "PATCH", body: { share_level: b.dataset.share, parent_id: state.parentId } }); route(); }));
  $("#pause").onclick = async () => { await api("api/family/settings", { method: "PATCH", body: { calls_paused: !p.calls_paused, parent_id: state.parentId } }); await refreshMe(); route(); };
};

VIEWS.mycircle = async (main) => {
  const r = await api("api/people/me");
  const c = r.circles[0];
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">${tr("My family")}</div><h1>${tr("Who can see how I am")}</h1><p>${tr("Only people you said yes to.")}</p></div></div>
    <div class="card">${c ? c.members.map((m) => memberRow(m, true)).join("") : `<p class="empty">Nobody yet.</p>`}</div>`;
  wireDecisions(main);
};

VIEWS.mycalls = async (main) => {
  const t = await api("api/family/timeline" + P());
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">${tr("My calls")}</div><h1>${tr("My chats with Smriti")}</h1></div><button class="btn" id="callMe">${ic("phone")} ${tr("Call me now")}</button></div>
    <div class="thread">${t.items.filter((c) => c.kind !== "family").slice(0, 12).map((c) => knot(c, t.parent)).join("")}</div>`;
  $("#callMe").onclick = () => callDialog("checkin");
};

/* ---------------------------------------------------------------- clinic app */
VIEWS.patients = async (main) => {
  const r = await api("api/care/patients");
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">Care team${(state.me.user || {}).org ? " · " + esc(state.me.user.org) : ""}</div><h1>Patients</h1>
    <p>Every family on Smriti. You review their flags before the family hears about them.</p></div><a class="btn" href="#/care">${ic("care")} Review queue</a></div>
    <div class="card"><table class="calls"><tr><th>Name</th><th>Age</th><th>Language</th><th>Last memory check</th><th>Open cases</th><th>Last contact</th><th></th></tr>
    ${r.items.map((p) => `<tr><td><b>${esc(p.full_name)}</b><div class="small muted">${esc(p.city)} · family: ${esc(p.family_name)}</div></td><td>${p.age || "—"}</td><td>${LANG[p.language] || p.language}</td>
      <td>${p.last_memory_outcome ? `<span class="chip ${OUTCOME[p.last_memory_outcome][1]}">${esc(p.last_memory_outcome)}</span>` : "—"}</td>
      <td>${p.open_cases ? `<span class="chip ${p.worst === "red" ? "red" : "yellow"}">${p.open_cases}</span>` : "0"}</td><td>${p.last_contact ? ago(p.last_contact) : "—"}</td>
      <td><a class="btn quiet sm" href="#/patient/${p.id}">Open</a></td></tr>`).join("") || `<tr><td colspan="7"><p class="empty">No families yet. When a family sets up Smriti in the family app, their parent appears here by itself.</p></td></tr>`}</table></div>`;
};

VIEWS.patient = async (main, id) => {
  if (id) { state.parentId = id; store.set(`parent.${state.me.user.id}`, id); }
  const [t, s] = await Promise.all([api("api/family/timeline" + P()), api("api/family/doctor-summary" + P())]);
  const p = t.parent, m = s.memory;
  state.parent = p;
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow"><a href="#/patients">Patients</a> · ${esc(p.city)}</div><h1>${esc(p.full_name)}</h1>
    <p>${p.age ? p.age + " years · " : ""}${LANG[p.language] || p.language} · family contact ${esc(p.family_name)} (${esc(p.relation)})</p></div>
    <div class="row"><button class="btn" id="orderMem">${ic("brain")} Order a memory check</button><a class="btn quiet" href="#/doctor">${ic("print")} Summary</a></div></div>
    <div class="grid g2"><div class="card"><h3>Memory check</h3>${m ? `<div class="row" style="margin:6px 0 14px"><span class="chip ${OUTCOME[m.outcome][1]}">${esc(m.outcome)}</span><span class="muted small">${fmtDay(m.at)}</span></div>
      <table class="calls"><tr><th>Word learning</th><th>Delayed recall</th><th>Animals (60 s)</th><th>Orientation</th></tr><tr><td>${m.learning_total}/30</td><td>${m.delayed_recall}/10</td><td>${m.fluency_count}</td><td>${m.orientation_total}/5</td></tr></table>
      <p class="small muted" style="margin-top:10px">10/66-based tasks by phone · schooling band ${esc(m.schooling_band || "unknown")} · not validated against clinical assessment yet · <a href="#/memreport/${encodeURIComponent(m.session_id)}">full report</a></p>` : `<p class="empty">No memory check yet.</p>`}</div>
      <div class="card bars"><h3>What came up (8 weeks)</h3>${Object.entries(s.flags_by_category).map(([k, v]) => `<div class="b"><span>${esc(k)}</span><div class="track"><div class="fill" style="width:${Math.min(100, v * 25)}%"></div></div><b>${v}</b></div>`).join("") || `<p class="empty">Nothing.</p>`}
      <p class="small muted" style="margin-top:8px">${s.calls_completed} of ${s.calls_planned} check-ins completed.</p></div></div>
    <h2 style="margin:26px 0 14px">Timeline</h2><div class="thread">${t.items.slice(0, 10).map((c) => knot(c, p)).join("")}</div>`;
  $("#orderMem").onclick = () => callDialog("memory");
};

boot();

/* ---------------------------------------------------------------- full memory-check report (#/memreport/<session id>) */
VIEWS.memreport = async (main, id) => {
  const s = await api(`api/sessions/${encodeURIComponent(id || "")}`);
  const back = state.app === "clinic" ? "#/care" : "#/memory";
  const head = `<div class="page-head"><div><div class="eyebrow"><a href="${back}">${state.app === "clinic" ? "Review queue" : "Memory"}</a> · full report</div><h1>Memory check report</h1>
    <p>Pilot: not a validated test and not a diagnosis.</p></div>`;
  if (!s.report) {
    const why = { declined: "The person said no to the check.", no_answer: "Nobody answered.", busy: "The line was busy.", failed: "The call failed." }[s.status];
    main.innerHTML = `${head}</div><div class="card"><p class="muted">${why || "The report isn't ready yet: the call is still going or being scored."}</p></div>`;
    return;
  }
  const r = s.report, dm = r.domains;
  const out = OUTCOME[r.outcome] || [r.outcome, "missed"];
  const BAND = { LOW: "up to 10 years of school", HIGH: "more than 10 years of school" };
  const SRC = { ui: "entered on the form", call: "said on the call", assumed: "unknown, assumed" };
  const ITEM = { day: "Day of the week", month: "Month", season: "Season", time_of_day: "Time of day", place: "Town / village" };
  const MON = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const REVIEW = { pending: "waiting for the care team", reviewed: "reviewed", not_needed: "not needed" };
  const answer = (item, v) => (v === null || v === undefined ? "–"
    : item === "day" && /^\d$/.test(v) ? WEEK[Number(v)]
    : item === "month" && /^\d{1,2}$/.test(v) ? MON[Number(v) - 1] : String(v));
  const label = (w) => (r.language === "kn" && w.kn ? `${w.kn} (${w.en})` : `${w.id} (${w.en})`);
  const words = (hits) => {
    const set = new Set(hits);
    return `<div class="row" style="flex-wrap:wrap;gap:6px;margin-top:8px">${r.word_list.map((w) => `<span class="chip ${set.has(w.id) ? "green" : ""}" title="${set.has(w.id) ? "remembered" : "not remembered"}">${set.has(w.id) ? "✓ " : ""}${esc(label(w))}</span>`).join("")}</div>`;
  };
  const score = (a, b) => `<div class="kpi"><div class="v">${a}<span class="muted" style="font-size:22px"> / ${b}</span></div></div>`;
  const extra = (list) => (list && list.length ? `<p class="small muted" style="margin-top:6px">Other words said (not counted): ${esc(list.join(", "))}</p>` : "");
  const sm = r.speech_markers || {};
  const markers = [["Answers given", sm.user_turns], ["Average words per answer", sm.mean_words_per_turn], ["Filler-word rate", sm.filler_rate],
    ["“I don't know” answers", sm.dont_know_count], ["Average response delay (s)", sm.mean_response_latency_s]];
  const an = dm.animal_naming;
  main.innerHTML = `${head}<button class="btn quiet" id="printReport">${ic("print")} Print / save PDF</button></div>
    <div class="card"><div class="row" style="gap:10px;flex-wrap:wrap"><span class="chip ${out[1]}">${esc((r.outcome_label && r.outcome_label.en) || r.outcome)}</span><span class="result-word">${esc(out[0])}</span>${s.is_demo ? `<span class="chip">sample</span>` : ""}</div>
      <p class="muted" style="margin-top:10px">Rule: <code>${esc(r.rule_fired)}</code> · schooling: ${BAND[r.band] || esc(r.band)} (${SRC[r.band_source] || esc(r.band_source)}) · human review: ${REVIEW[s.review_status] || esc(s.review_status || "")}</p>
      ${r.invalid_reason_text && r.invalid_reason_text.length ? `<h3 style="margin-top:14px">Why the call is invalid</h3><ul>${r.invalid_reason_text.map((x) => `<li>${esc(x.en)}</li>`).join("")}</ul><p class="small muted">The scores below are shown only for transparency. Don't read them as a result.</p>` : ""}
      <h3 style="margin-top:14px">Suggested next step</h3><p>${esc((r.next_step_text && r.next_step_text.en) || "")}</p>
      ${r.helpline_text ? `<p class="small" style="margin-top:8px"><b>Support:</b> ${esc(r.helpline_text)}</p>` : ""}</div>
    <div class="grid g2" style="margin-top:20px">
      <div class="card"><h3>Remembering the words later</h3>${score(dm.delayed_recall.score, dm.delayed_recall.max)}${words(dm.delayed_recall.words)}${extra(dm.delayed_recall.intrusions)}</div>
      <div class="card"><h3>Word learning (3 tries)</h3>${score(dm.word_learning.total, dm.word_learning.max)}${dm.word_learning.trials.map((hits, i) => `<p class="small muted" style="margin-top:12px">Try ${i + 1}: ${hits.length}/10</p>${words(hits)}${extra(dm.word_learning.intrusions[i])}`).join("")}</div>
      <div class="card"><h3>Naming animals</h3><div class="kpi"><div class="v">${an.count}</div></div><p class="small muted">Animals counted (synonyms once)</p>
        <div class="row" style="flex-wrap:wrap;gap:6px;margin-top:8px">${an.words.map((w) => `<span class="chip green">${esc(w)}</span>`).join("")}</div>
        ${an.non_animals.length ? `<p class="small muted" style="margin-top:6px">Not counted: ${esc(an.non_animals.join(", "))}</p>` : ""}
        <p class="small muted" style="margin-top:8px">${an.experimental_timing ? "Timing is experimental: the whole naming part was counted, not exactly 60 seconds." : "Counted within 60 seconds using the call recording."}</p></div>
      <div class="card"><h3>Day, month and place</h3>${score(dm.orientation.score, dm.orientation.max)}
        <table class="calls">${Object.keys(ITEM).map((k) => `<tr><td>${ITEM[k]}</td><td>${esc(answer(k, dm.orientation.answers[k]))}</td><td>${dm.orientation.items[k] ? "✓" : "✗"}</td></tr>`).join("")}</table>
        <p class="small muted" style="margin-top:8px">The town or village answer is accepted if given; a reviewer can check it.</p></div></div>
    <div class="card" style="margin-top:20px"><h3>Hearing / line check</h3>${score(r.hearing.correct, r.hearing.max)}
      <table class="calls">${r.hearing.items.map((it) => `<tr><td>${esc(it.expected.split("").join("-"))}</td><td>${esc(it.heard.join(" / ") || "–")}</td><td>${it.correct ? "✓" : "✗"}</td></tr>`).join("")}</table></div>
    <details class="card" style="margin-top:20px"><summary><b>Experimental speech markers</b> <span class="small muted">(not used for the result)</span></summary>
      <table class="calls" style="margin-top:10px">${markers.map(([k, v]) => `<tr><td>${k}</td><td>${esc(v === null || v === undefined ? "–" : String(v))}</td></tr>`).join("")}</table></details>
    <p class="small muted" style="margin-top:16px">Every score comes from the words in the call transcript, matched by fixed rules (no AI judgement). Scorer ${esc(r.scorer_version || "")}${r.call_time ? " · " + esc(r.call_time) : ""}.</p>`;
  $("#printReport").onclick = () => window.print();
};

/* ---------------------------------------------------------------- "More": every page and every account action
   (the bottom tab bar on narrow screens has room for four pages plus this one) */
VIEWS.more = async (main) => {
  const u = state.me.user;
  const nav = NAV[state.app] || NAV.family;
  const p = state.parent;
  const ports = state.me.ports || {};
  const canRemove = state.app === "family" && p && myRole() === "family";
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">${tr(APP_NAME[state.app])}</div><h1>${tr("More")}</h1></div></div>
    <div class="card"><h3>${tr("Pages")}</h3><div class="more-links">${nav.map(([r, label, icon]) => `<a href="#/${r}">${ic(icon)}<span>${tr(label)}</span></a>`).join("")}</div></div>
    ${state.app === "elder" ? "" : `<div class="card" style="margin-top:16px"><h3>${tr("Calls")}</h3>${callModeSwitch()}</div>`}
    ${state.app === "family" ? `<div class="card" style="margin-top:16px"><h3>${tr("Profiles")}</h3>${parentSwitcher()}
      ${canRemove ? `<button type="button" class="btn danger sm" id="removeProfile" style="margin-top:12px">Remove ${esc(p.call_name)}'s profile</button>` : ""}</div>` : ""}
    <div class="card" style="margin-top:16px"><h3>${tr("You")}</h3>
      <div class="who"><div class="avatar sm">${esc(u.name[0])}</div><div><b>${esc(u.name)}</b><small>${esc(u.role_label)} · ${tr("Smriti ID")} ${esc(u.smriti_id)}</small></div></div>
      <div style="margin-top:12px">${uiLangSwitch()}</div>
      <button type="button" class="btn quiet" id="moreLogout" style="margin-top:14px;width:100%">${tr("Log out")}</button>
      <p class="small muted" style="margin-top:12px">${tr("Demo apps")}: <a href="${ports.family}">Family</a> · <a href="${ports.elder}">Elder</a> · <a href="${ports.clinic}">Care team</a></p></div>`;
  $("#moreLogout").onclick = logout;
};
