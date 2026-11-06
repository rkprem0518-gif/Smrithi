/* Smriti family app: one page, hash routes, no build step. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(k, d = "") { try { return localStorage.getItem("smriti." + k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("smriti." + k, v); } catch { /* private mode */ } },
};

/* ---------------------------------------------------------------- icons */
const I = {
  home: '<path d="M4 11l8-7 8 7v9a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z"/>',
  thread: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="12" r="2.5"/><circle cx="8" cy="19" r="2.5"/><path d="M8 7.5c6 1 10 1.5 10 2M16 13.5c-3 2-6 3-6 3.5"/>',
  cal: '<rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
  brain: '<path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 3 3h1V4zM15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-3 3h-1V4z"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  care: '<path d="M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"/>',
  pulse: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a1 1 0 0 1-1 1A16 16 0 0 1 4 5a1 1 0 0 1 1-1z"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  down: '<path d="M12 4v12M6 11l6 6 6-6M5 20h14"/>',
  print: '<path d="M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4.5 4.5-7 8-7s7 2.5 8 7"/>',
};
const ic = (name, extra = "") => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ${extra}>${I[name]}</svg>`;

/* ---------------------------------------------------------------- words */
const LANG = { en: "English", hi: "Hindi", kn: "Kannada", ta: "Tamil", te: "Telugu", ml: "Malayalam", mr: "Marathi", bn: "Bengali", gu: "Gujarati", pa: "Punjabi", od: "Odia" };
const MOOD = new Proxy({ cheerful: "Cheerful", okay: "Calm", low: "Low" }, { get: (o, k) => (o[k] ? tr(o[k]) : undefined) });
const KIND = { checkin: "Check-in", memory: "Memory check", family: "Call to family" };
const OUTCOME = {
  NORMAL: ["No memory concerns showed up", "green"],
  UNCERTAIN: ["Unclear: a recheck is suggested", "yellow"],
  REFER: ["Worth seeing a doctor for a proper check", "red"],
  INVALID: ["Couldn't get a reliable result", "missed"],
};
const LEVEL = { green: "Noted", yellow: "Worth a look", red: "Act now" };
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

const d = (iso) => new Date(iso);
const fmtDay = (iso) => { const t = d(iso); return `${DAYS[t.getDay()]} ${t.getDate()} ${MONTHS[t.getMonth()].slice(0, 3)}`; };
const fmtTime = (iso) => d(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
const fmtLong = (iso) => { const t = d(iso); return `${["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][t.getDay()]} ${t.getDate()} ${MONTHS[t.getMonth()]}`; };
function ago(iso) {
  const days = Math.round((Date.now() - d(iso)) / 864e5);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  const w = Math.round(days / 7);
  return w === 1 ? "last week" : `${w} weeks ago`;
}
function inDays(iso) {
  const days = Math.ceil((d(iso) - Date.now()) / 864e5);
  return days <= 0 ? "today" : days === 1 ? "tomorrow" : `in ${days} days`;
}
const mins = (s) => (s ? `${Math.max(1, Math.round(s / 60))} min` : "");
const greeting = () => { const h = new Date().getHours(); return tr(h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"); };

/* ---------------------------------------------------------------- api */
const state = { parent: null, parentId: null, fresh: null, live: null, app: "family", me: null };

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 401) { showLogin(); throw new Error("LOGIN"); }
  const data = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Something went wrong (${res.status})`);
  return data;
}
const withKey = (path) => path;
const P = (sep = "?") => (state.parentId ? `${sep}parent_id=${encodeURIComponent(state.parentId)}` : "");

/* ---------------------------------------------------------------- shell */
const NAV = {
  family: [["today", "Today", "home"], ["timeline", "Timeline", "thread"], ["calendar", "Calendar", "cal"],
    ["memory", "Memory", "brain"], ["reports", "Reports", "chart"], ["schedules", "Schedules", "spark"],
    ["circle", "Family circle", "user"], ["history", "History", "pulse"]],
  elder: [["home", "Home", "home"], ["mycircle", "My family", "user"], ["mycalls", "My calls", "phone"]],
  clinic: [["patients", "Patients", "user"], ["care", "Review queue", "care"], ["behind", "Behind the call", "pulse"],
    ["history", "History", "thread"]],
};
const HOME = { family: "today", elder: "home", clinic: "patients" };
const APP_NAME = { family: "Family", elder: "For Appa", clinic: "Care team" };

function renderNav(route) {
  const nav = NAV[state.app] || NAV.family;
  const link = ([r, label, icon]) => `<a href="#/${r}" class="${route === r ? "on" : ""}">${ic(icon)}<span>${tr(label)}</span></a>`;
  $("#nav").innerHTML = `<div class="group">${tr(APP_NAME[state.app])}</div>${nav.map(link).join("")}`;
  $("#tabbar").innerHTML = nav.slice(0, 5).map(link).join("");
  const u = state.me && state.me.user;
  const p = state.parent;
  const ports = state.me && state.me.ports;
  $("#sideFoot").innerHTML = u ? `${typeof parentSwitcher === "function" ? parentSwitcher() : ""}<div class="who"><div class="avatar sm">${esc(u.name[0])}</div><div><b>${esc(u.name)}</b><small>${esc(u.role_label)}${u.org ? " · " + esc(u.org) : ""}</small></div></div>
    ${p ? `<div class="small muted" style="margin-top:10px">${esc(p.call_name)} speaks ${LANG[p.language] || p.language}${p.calls_paused ? " · <b>calls paused</b>" : ""}</div>` : ""}
    <div class="small muted" style="margin-top:6px">${tr("Smriti ID")} <b>${esc(u.smriti_id)}</b></div>
    ${typeof callModeSwitch === "function" ? callModeSwitch() : ""}
    <div style="margin-top:12px">${uiLangSwitch()}</div>
    <button class="btn quiet sm" id="logout" style="margin-top:12px;width:100%">${tr("Log out")}</button>
    ${ports ? `<div class="small muted" style="margin-top:12px">${tr("Demo apps")}: <a href="${ports.family}">Family</a> · <a href="${ports.elder}">Elder</a> · <a href="${ports.clinic}">Clinic</a></div>` : ""}` : "";
  const lo = $("#logout");
  if (lo) lo.onclick = logout;
}

const VIEWS = {};
async function route() {
  if (!state.me || !state.me.user) return;
  const nav = NAV[state.app] || NAV.family;
  const [name, arg] = (location.hash.replace(/^#\/?/, "") || HOME[state.app]).split("/");
  const allowed = new Set([...nav.map((n) => n[0]), ...(EXTRA_ROUTES[state.app] || [])]);
  const view = VIEWS[name] && allowed.has(name) ? name : HOME[state.app];
  renderNav(view);
  const main = $("#view");
  if (!state.parentId && state.app !== "clinic") { VIEWS.waiting(main); return; }
  try {
    await VIEWS[view](main, arg);
  } catch (e) {
    if (e.message !== "LOGIN") main.innerHTML = `<div class="card"><h2>Couldn't load this</h2><p class="muted" style="margin-top:8px">${esc(e.message)}</p></div>`;
  }
  renderNav(view);
}
const EXTRA_ROUTES = { family: ["doctor"], elder: [], clinic: ["patient", "doctor"] };
window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });

/* ---------------------------------------------------------------- pieces */
function flagBlock(f, opts = {}) {
  return `<div class="flag-card"><span class="dot ${f.level}"></span><div>
    <div class="flag-head"><b>${esc(f.label)}</b><span class="chip ${f.level}">${LEVEL[f.level]}</span><span class="small muted">${ago(f.at)}</span></div>
    <div class="words" lang="kn">${esc(f.quote)}</div>${f.quote_en ? `<div class="words-en">${esc(f.quote_en)}</div>` : ""}
    ${opts.rule === false ? "" : `<div class="rule">Rule: ${esc(f.rule)}${f.status === "open" ? " · the care team is reviewing" : f.status === "approved" ? " · reviewed by the care team" : ""}</div>`}
  </div></div>`;
}

function knot(c, p) {
  const worst = c.flags.some((f) => f.level === "red") ? "red" : c.flags.some((f) => f.level === "yellow") ? "yellow" : "green";
  const live = ["calling", "talking", "writing"].includes(c.status);
  const pin = live ? "live" : c.status === "missed" ? "missed" : c.kind === "memory" ? "memory" : c.kind === "family" ? "family" : worst;
  const out = c.kind === "memory" && c.outcome ? OUTCOME[c.outcome] : null;
  const head = `<div class="knot-head"><div><span class="when">${fmtDay(c.at)}</span> <span class="muted small">· ${fmtTime(c.at)} · ${ago(c.at)}</span></div>
    <div class="row">${c.kind !== "checkin" ? `<span class="chip ${c.kind === "memory" ? "peacock" : "marigold"}">${KIND[c.kind]}</span>` : ""}
    ${c.mood ? `<span class="chip">${MOOD[c.mood]}</span>` : ""}${c.duration_s ? `<span class="chip">${mins(c.duration_s)}</span>` : ""}
    <span class="chip">${LANG[c.language] || c.language}</span></div></div>`;
  let body = "";
  if (live) body = `<p class="summary"><b>Live now.</b> ${c.status === "calling" ? "Smriti is calling…" : c.status === "talking" ? "Smriti and " + esc(p.call_name) + " are talking." : "Smriti is writing the notes…"}</p>`;
  else if (c.status === "missed") body = `<p class="summary">${esc(c.summary || "No answer. Smriti will try again.")}</p>`;
  else {
    body = out ? `<p class="summary"><span class="dot ${out[1]}" style="margin-right:8px"></span><b>${out[0]}.</b> ${c.review_status === "pending" ? "Waiting for the care team." : c.review_status === "reviewed" ? "Reviewed by the care team." : ""} <a href="#/memory">Details</a></p>` : `<p class="summary">${esc(c.summary)}</p>`;
    if (c.remembered) body += `<div class="remember-row">${ic("spark")}<span>Smriti remembered: <span class="remembered">${esc(c.remembered)}</span></span></div>`;
    if (c.quotes && c.quotes.length) body += c.quotes.slice(0, 2).map((q) => `<div class="quote"><div class="words">${esc(q.text)}</div>${q.en ? `<div class="words-en">${esc(q.en)}</div>` : ""}</div>`).join("");
    if (c.message_for_family) body += `<div class="message" style="margin-top:14px"><div class="small muted">${esc(p.call_name)} asked Smriti to tell you</div><div class="words" style="font-size:19px">${esc(c.message_for_family)}</div></div>`;
    if (c.flags.length) body += `<div class="flag-row">${c.flags.map((f) => `<span class="chip ${f.level}"><span class="dot ${f.level}"></span>${esc(f.label)}</span>`).join("")}</div>`;
    if (c.topics && c.topics.length && c.kind === "checkin") body += `<div class="small muted" style="margin-top:10px">Talked about: ${c.topics.map((t) => esc(t.split(".")[0].replace(/^Ask (warmly )?(about |if they |how |what )?/i, ""))).join(" · ")}</div>`;
  }
  return `<div class="knot ${state.fresh === c.id ? "fresh" : ""}" id="k-${c.id}"><span class="pin ${pin}"></span><div class="card">${head}${body}</div></div>`;
}

/* ---------------------------------------------------------------- Today */
VIEWS.today = async (main) => {
  const h = await api("/api/family/home" + P());
  state.parent = h.parent;
  const p = h.parent, last = (h.recent || []).find((c) => c.kind === "checkin" && c.status === "done");
  const memo = (h.recent || []).find((c) => c.kind === "memory");
  const flags = h.week.flags;
  main.innerHTML = `
  <div class="page-head"><div><div class="eyebrow">${fmtLong(new Date().toISOString())}</div><h1>${greeting()}, ${esc(p.family_name)}.</h1>
    <p>${tr("Here's how {name} has been.", { name: esc(p.call_name) })}</p></div></div>
  <div class="card hero">
    <div class="avatar lg">${esc(p.call_name[0])}</div>
    <div><h2>${esc(p.call_name)} <span class="muted" style="font-size:18px">· ${esc(p.full_name)}, ${esc(p.city)}</span></h2>
      ${last ? `<div class="mood" style="margin-top:8px">${MOOD[last.mood] || "—"} on ${ago(last.at) === "today" ? "today" : fmtLong(last.at).split(" ")[0]}'s chat</div>` : ""}
      <div class="meta"><span>${tr("Last chat")} <b>${last ? ago(last.at) : "—"}</b></span><span>${tr("Next chat")} <b>${fmtDay(p.next_call_at)}, ${fmtTime(p.next_call_at)}</b></span><span>${tr("Speaks")} <b>${LANG[p.language]}</b></span></div></div>
    <div class="hero-actions"><button class="btn" id="callNow">${ic("phone")} ${tr("Call {name} now", { name: esc(p.call_name) })}</button>
      <a class="btn ghost sm" href="${withKey("/api/family/smriti.vcf")}">${ic("user")} ${tr("Save Smriti's number")}</a></div>
  </div>
  <div class="grid g2" style="margin-top:20px">
    <div class="card"><div class="spread"><h3>${tr("This week")}</h3><a href="#/timeline" class="small">${tr("See the timeline")}</a></div>
      ${flags.length ? flags.map((f) => flagBlock(f)).join("") : `<p class="empty">${tr("Nothing worrying came up this week.")}</p>`}</div>
    <div class="grid" style="align-content:start">
      ${h.week.messages.length ? `<div class="card"><h3>${tr("{name} wants you to know", { name: esc(p.call_name) })}</h3><div class="message"><div class="words" style="font-size:20px">${esc(h.week.messages[0].text)}</div><div class="small muted" style="margin-top:6px">Said ${ago(h.week.messages[0].at)}</div></div></div>` : ""}
      ${memo ? `<div class="card"><div class="spread"><h3>${tr("Memory")}</h3><a class="small" href="#/memory">${tr("Details")}</a></div>
        <div class="row"><span class="dot ${OUTCOME[memo.outcome]?.[1] || "memory"}"></span><b>${OUTCOME[memo.outcome]?.[0] || "Memory check"}</b></div>
        <p class="small muted" style="margin-top:6px">Memory check ${ago(memo.at)}${memo.review_status === "pending" ? " · the care team is reviewing it" : memo.review_status === "reviewed" ? " · reviewed by the care team" : ""}. Never a diagnosis.</p></div>` : ""}
      <div class="card upcoming"><h3>${tr("Coming up")}</h3><ul>
        ${h.visits.map((v) => `<li><div class="datebox"><div class="d">${d(v.at).getDate()}</div><div class="m">${MONTHS[d(v.at).getMonth()].slice(0, 3)}</div></div><div><b>${esc(v.title)}</b><div class="small muted">${fmtTime(v.at)} · ${esc(v.place)}</div><a class="small" target="_blank" rel="noopener" href="${v.google_calendar_url}">Add to Google Calendar</a></div></li>`).join("")}
        <li><div class="datebox"><div class="d">${d(p.next_call_at).getDate()}</div><div class="m">${MONTHS[d(p.next_call_at).getMonth()].slice(0, 3)}</div></div><div><b>${tr("Weekly chat")}</b><div class="small muted">${fmtDay(p.next_call_at)}, ${fmtTime(p.next_call_at)} · ${inDays(p.next_call_at)}</div></div></li>
        <li><div class="datebox"><div class="d">${d(p.memory_check_due).getDate()}</div><div class="m">${MONTHS[d(p.memory_check_due).getMonth()].slice(0, 3)}</div></div><div><b>${tr("Next memory check")}</b><div class="small muted">${inDays(p.memory_check_due)}</div></div></li>
      </ul></div>
    </div>
  </div>`;
  $("#callNow").onclick = () => callDialog("checkin");
};

/* ---------------------------------------------------------------- Timeline */
VIEWS.timeline = async (main) => {
  const t = await api("/api/family/timeline" + P());
  state.parent = t.parent;
  const p = t.parent, items = t.items;
  const weeks = [];
  for (let i = 8; i >= 0; i--) {
    const start = Date.now() - (i + 1) * 7 * 864e5, end = Date.now() - i * 7 * 864e5;
    const inWeek = items.filter((c) => c.kind === "checkin" && d(c.at) >= start && d(c.at) < end);
    const lv = inWeek.some((c) => c.status === "missed") && !inWeek.some((c) => c.status === "done") ? "missed"
      : inWeek.some((c) => c.flags.some((f) => f.level === "red")) ? "red" : inWeek.some((c) => c.flags.some((f) => f.level === "yellow")) ? "yellow" : inWeek.length ? "green" : "";
    weeks.push(`<div class="wk"><div class="bar ${lv}" title="${inWeek[0] && inWeek[0].mood ? MOOD[inWeek[0].mood] : ""}"></div>${i === 0 ? "This week" : `${i}w ago`}</div>`);
  }
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">The thread</div><h1>${esc(p.call_name)}'s weeks</h1>
    <p>Every chat is a knot on the thread. Colour only when something needs attention.</p></div>
    <button class="btn" id="callNow">${ic("phone")} Call ${esc(p.call_name)} now</button></div>
    <div class="weekstrip" aria-label="Last nine weeks">${weeks.join("")}</div>
    <div class="row small muted" style="margin:-10px 0 22px"><span class="dot green"></span>All well <span class="dot yellow"></span>Worth a look <span class="dot red"></span>Act now <span class="dot memory"></span>Memory check <span class="dot missed"></span>Missed</div>
    <div class="thread">${items.map((c) => knot(c, p)).join("")}</div>`;
  $("#callNow").onclick = () => callDialog("checkin");
  if (state.fresh) { const el = $(`#k-${state.fresh}`); if (el) el.scrollIntoView({ behavior: "smooth", block: "center" }); }
};

/* ---------------------------------------------------------------- Calendar */
VIEWS.calendar = async (main) => {
  const [c, v] = await Promise.all([api("/api/family/calendar" + P()), api("/api/family/visits" + P())]);
  state.parent = c.parent;
  const p = c.parent, now = new Date();
  let ym = store.get("calMonth") ? new Date(store.get("calMonth")) : new Date(now.getFullYear(), now.getMonth(), 1);
  const draw = () => {
    const first = new Date(ym.getFullYear(), ym.getMonth(), 1), start = new Date(first);
    start.setDate(1 - first.getDay());
    const cells = [];
    for (let i = 0; i < 42; i++) {
      const day = new Date(start); day.setDate(start.getDate() + i);
      if (i >= 35 && day.getMonth() !== ym.getMonth()) break;
      const evs = c.events.filter((e) => { const t = d(e.at); return t.toDateString() === day.toDateString(); });
      const label = (e) => e.type === "checkin" ? `Chat ${e.status === "missed" ? "· missed" : ""}` : e.type === "planned" ? "Weekly chat" : e.type === "memory_due" ? "Memory check due" : e.type === "memory" ? "Memory check" : e.type === "family" ? `Smriti called ${p.family_name}` : e.title;
      cells.push(`<div class="day ${day.getMonth() !== ym.getMonth() ? "out" : ""} ${day.toDateString() === now.toDateString() ? "today" : ""}"><div class="n">${day.getDate()}</div>
        ${evs.map((e) => `<span class="ev ${e.type} ${e.level || ""}" title="${esc(e.title)} · ${fmtTime(e.at)}">${esc(label(e))}</span>`).join("")}</div>`);
    }
    $("#calGrid").innerHTML = DAYS.map((x) => `<div class="dow">${x}</div>`).join("") + cells.join("");
    $("#calTitle").textContent = `${MONTHS[ym.getMonth()]} ${ym.getFullYear()}`;
  };
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">Calendar</div><h1>What's happening</h1><p>Weekly chats, memory checks and doctor's visits in one place.</p></div>
    <div class="row"><a class="btn quiet sm" href="${"/api/family/calendar.ics" + P()}">${ic("down")} Download .ics</a><button class="btn sm" id="reqVisit">Request a doctor's visit</button></div></div>
    <div class="grid"><div class="card"><div class="spread" style="margin-bottom:12px"><button class="btn quiet sm" id="prevM">‹</button><h3 id="calTitle" style="margin:0"></h3><button class="btn quiet sm" id="nextM">›</button></div><div class="cal" id="calGrid"></div>
      <div class="row small muted" style="margin-top:14px"><span class="chip green">Chat</span><span class="chip">Planned chat</span><span class="chip peacock">Memory check</span><span class="chip marigold">Call to family</span><span class="chip" style="background:var(--marigold);color:var(--ink)">Doctor's visit</span></div></div>
    <div class="card upcoming"><h3>Doctor's visits</h3>${v.items.length ? `<ul>${v.items.map((a) => `<li><div class="datebox"><div class="d">${d(a.at).getDate()}</div><div class="m">${MONTHS[d(a.at).getMonth()].slice(0, 3)}</div></div>
      <div><b>${esc(a.title)}</b><div class="small muted">${fmtDay(a.at)}, ${fmtTime(a.at)} · ${esc(a.place)}</div><div class="small muted">${a.status === "requested" ? "Requested" : "Confirmed"} · ${esc(a.source)}</div>
      <a class="btn ghost sm" style="margin-top:8px" target="_blank" rel="noopener" href="${a.google_calendar_url}">${ic("cal")} Add to Google Calendar</a></div></li>`).join("")}</ul>` : `<p class="empty">No visits yet. When the care team flags something, Smriti calls ${esc(p.family_name)} and can set one up.</p>`}</div></div>`;
  $("#prevM").onclick = () => { ym = new Date(ym.getFullYear(), ym.getMonth() - 1, 1); store.set("calMonth", ym.toISOString()); draw(); };
  $("#nextM").onclick = () => { ym = new Date(ym.getFullYear(), ym.getMonth() + 1, 1); store.set("calMonth", ym.toISOString()); draw(); };
  $("#reqVisit").onclick = async () => { await api("/api/family/visits", { method: "POST", body: { title: "Doctor visit", parent_id: state.parentId } }); toast("Visit requested. It's on the calendar."); route(); };
  draw();
};

/* ---------------------------------------------------------------- Memory */
VIEWS.memory = async (main) => {
  const r = await api("/api/family/report" + P());
  state.parent = r.parent;
  const p = r.parent, mem = r.memory.slice().reverse(), last = mem[0];
  const out = last && OUTCOME[last.outcome];
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">Memory</div><h1>${esc(p.call_name)}'s memory checks</h1>
    <p>A short, structured check on the phone, every few months. Scored by fixed rules. Never a diagnosis.</p></div>
    <button class="btn ghost" id="runMemory">${ic("brain")} Start a memory check</button></div>
    <div class="grid g2"><div class="card">${last ? `<div class="eyebrow">Latest · ${fmtLong(last.at)}</div><div class="row" style="margin:6px 0 10px"><span class="dot ${out[1]}" style="width:14px;height:14px"></span><span class="result-word">${out[0]}</span></div>
      <p class="muted">${last.review_status === "pending" ? "Our care team is reviewing this now. If they agree, Smriti will call " + esc(p.family_name) + " to explain and help book a visit." : last.review_status === "reviewed" ? "Reviewed by the care team." : ""}</p>
      ${last.session_id ? `<a class="btn quiet sm" style="margin-top:16px" href="/report.html?id=${encodeURIComponent(last.session_id)}" target="_blank" rel="noopener">See the full report</a>` : ""}` : `<p class="empty">No memory check yet.</p>`}
      <div class="history">${mem.slice().reverse().map((m) => `<div class="h"><span class="dot ${OUTCOME[m.outcome]?.[1] || "memory"}"></span><br>${MONTHS[d(m.at).getMonth()].slice(0, 3)} ${d(m.at).getFullYear()}</div>`).join("")}
        <div class="h"><span class="dot missed"></span><br>Next: ${MONTHS[d(p.memory_check_due).getMonth()].slice(0, 3)}</div></div></div>
      <div class="card"><h3>How the weekly chats connect</h3><p class="muted">If ${esc(p.call_name)} mentions forgetting things twice in a month, the next memory check comes sooner. Recently:</p>
        ${Object.keys(r.flags_by_category).includes("memory") ? `<p style="margin-top:12px"><span class="chip yellow">Memory slips mentioned ${r.flags_by_category.memory}× in 8 weeks</span></p>` : `<p class="empty">No forgetting mentioned lately.</p>`}</div></div>
    <div class="card" style="margin-top:20px"><div class="two-col"><div><h3>What this means</h3><ul><li>Some answers were worth a closer look by a doctor.</li><li>Many causes of memory changes can be treated: hearing, sleep, mood, thyroid, vitamins, medicines.</li><li>A person on our care team checks every result before you hear about it.</li></ul></div>
      <div><h3>What it does not mean</h3><ul><li>It is not a diagnosis of dementia or any illness.</li><li>One phone check can be thrown off by a bad line, tiredness or worry.</li><li>Only a doctor can say what is going on.</li></ul></div></div></div>`;
  $("#runMemory").onclick = () => callDialog("memory");
};

/* ---------------------------------------------------------------- Reports */
function moodChart(weeks) {
  const W = 640, H = 200, pad = 34, n = weeks.length;
  const x = (i) => pad + (i * (W - pad * 2)) / Math.max(1, n - 1);
  const y = (v) => H - pad - ((v - 1) / 2) * (H - pad * 2);
  const pts = weeks.map((w, i) => (w.mood ? [x(i), y(w.mood)] : null));
  const path = pts.filter(Boolean).map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const grid = [1, 2, 3].map((v) => `<line x1="${pad}" x2="${W - pad}" y1="${y(v)}" y2="${y(v)}" stroke="#E4E9E6"/><text x="0" y="${y(v) + 4}" font-size="12" fill="#7A8889">${["Low", "Calm", "Cheerful"][v - 1]}</text>`).join("");
  const dots = weeks.map((w, i) => w.mood ? `<circle cx="${x(i)}" cy="${y(w.mood)}" r="6" fill="#fff" stroke="${w.flags.red ? "#B8432F" : w.flags.yellow ? "#C98A1B" : "#0E5E63"}" stroke-width="3"><title>Week of ${w.week_start}</title></circle>`
    : `<circle cx="${x(i)}" cy="${y(2)}" r="5" fill="none" stroke="#7A8889" stroke-dasharray="2 2"><title>Missed week</title></circle>`).join("");
  const labels = weeks.map((w, i) => `<text x="${x(i)}" y="${H - 6}" font-size="11.5" fill="#7A8889" text-anchor="middle">${d(w.week_start).getDate()} ${MONTHS[d(w.week_start).getMonth()].slice(0, 3)}</text>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Mood across eight weeks">${grid}<path d="${path}" fill="none" stroke="#0E5E63" stroke-width="2.5" stroke-linejoin="round"/>${dots}${labels}</svg>`;
}

VIEWS.reports = async (main) => {
  const r = await api("/api/family/report" + P());
  state.parent = r.parent;
  const p = r.parent;
  const cats = Object.entries(r.flags_by_category).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...cats.map((c) => c[1]));
  const LABEL = { pain: "Pain", sleep: "Poor sleep", appetite: "Appetite", mood: "Low mood", loneliness: "Loneliness", medicines: "Missed medicines", memory: "Memory slips", fall: "Falls", chest: "Chest pain", breath: "Breathlessness", confusion: "Confusion", self_harm: "Not wanting to live" };
  const yellows = r.weeks.reduce((s, w) => s + w.flags.yellow + w.flags.red, 0);
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">Reports · last 8 weeks</div><h1>How ${esc(p.call_name)} has been</h1><p>Patterns matter more than any single call.</p></div>
    <a class="btn" href="#/doctor">${ic("print")} Doctor summary</a></div>
    <div class="grid g3"><div class="card kpi"><div class="v">${r.calls_completed}<span class="muted" style="font-size:22px"> / ${r.calls_planned}</span></div><div class="l">weekly chats completed</div></div>
      <div class="card kpi"><div class="v">${r.streak}</div><div class="l">weeks in a row</div></div>
      <div class="card kpi"><div class="v">${yellows}</div><div class="l">things worth a look</div></div></div>
    <div class="grid g2" style="margin-top:20px"><div class="card chart"><h3>Mood across the weeks</h3>${moodChart(r.weeks)}<p class="small muted" style="margin-top:8px">From ${esc(p.call_name)}'s own words in each chat. Ring colour shows that week's flags.</p></div>
      <div class="card bars"><h3>What came up</h3>${cats.length ? cats.map(([k, v]) => `<div class="b"><span>${LABEL[k] || k}</span><div class="track"><div class="fill" style="width:${(v / max) * 100}%"></div></div><b>${v}</b></div>`).join("") : `<p class="empty">Nothing came up.</p>`}
      <p class="small muted" style="margin-top:12px">Counted by fixed rules from ${esc(p.call_name)}'s words. Shared because ${esc(p.call_name)} chose to share health worries.</p></div></div>
    <div class="card" style="margin-top:20px"><h3>For clinics and care partners</h3><p class="muted">With ${esc(p.call_name)}'s consent, the doctor summary gives a clinician the last 8 weeks on one page: what was said, when, and the memory check scores, in plain words.</p></div>`;
};

VIEWS.doctor = async (main) => {
  const s = await api("/api/family/doctor-summary" + P());
  const p = s.parent, m = s.memory;
  main.innerHTML = `<div class="row no-print" style="margin-bottom:18px"><a class="btn quiet sm" href="#/reports">‹ Back</a><button class="btn sm" onclick="window.print()">${ic("print")} Print</button></div>
  <article class="doc"><div class="spread"><div><div class="eyebrow">Smriti · summary for a doctor</div><h1>${esc(p.full_name)}</h1><p class="muted">${esc(p.city)} · speaks ${LANG[p.language]} · prepared ${fmtLong(s.generated_at)}</p></div>
    <svg width="44" height="44" viewBox="0 0 40 40" aria-hidden="true"><circle cx="20" cy="20" r="18" fill="#0E5E63"/><path d="M9 24c5-9 17-9 22 0" stroke="#E3A72F" stroke-width="3" fill="none" stroke-linecap="round"/><circle cx="20" cy="15" r="3" fill="#fff"/></svg></div>
  <section><h3>Memory check (phone, 10/66-based tasks)</h3>${m ? `<table><tr><th>Date</th><th>Result</th><th>Word learning</th><th>Delayed recall</th><th>Animal naming</th><th>Orientation</th></tr>
    <tr><td>${fmtDay(m.at)}</td><td><b>${esc(m.outcome)}</b></td><td>${m.learning_total} / 30</td><td>${m.delayed_recall} / 10</td><td>${m.fluency_count} in 60 s</td><td>${m.orientation_total} / 5</td></tr></table>
    <p class="small muted" style="margin-top:6px">Schooling band: ${esc(m.schooling_band || "not known")}. Phone administration has not yet been validated against clinical assessment.</p>` : `<p class="muted">No memory check yet.</p>`}</section>
  <section><h3>Weekly check-ins</h3><p>${s.calls_completed} of ${s.calls_planned} weekly calls completed in the last 8 weeks.</p></section>
  <section><h3>What the person mentioned (own words)</h3><table><tr><th>Date</th><th>Topic</th><th>Words</th><th>Rule</th></tr>
    ${s.flags.map((f) => `<tr><td>${fmtDay(f.at)}</td><td>${esc(f.label)}</td><td>${esc(f.quote)}${f.quote_en ? `<br><span class="muted">${esc(f.quote_en)}</span>` : ""}</td><td class="small">${esc(f.rule)}</td></tr>`).join("")}</table></section>
  <p class="disclaimer">${esc(s.note)}</p></article>`;
};

/* ---------------------------------------------------------------- Care desk */
VIEWS.care = async (main, sel) => {
  const q = await api("/api/care/queue");
  state.parent = q.parent;
  const p = q.parent, items = q.items;
  const cur = items.find((i) => i.id === sel) || items[0];
  const title = (i) => i.type === "memory" ? "Memory check" : i.title;
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">Smriti team · care desk</div><h1>Review before anyone worries</h1>
    <p>Red first, then memory checks, then things worth a look. Nothing reaches the family until a person approves it.</p></div></div>
    ${items.length ? `<div class="care"><div>${items.map((i) => `<button class="case ${cur && i.id === cur.id ? "on" : ""}" data-id="${i.id}"><span class="dot ${i.level}"></span><div><b>${esc(title(i))}</b>
      <div class="small muted">${esc(p.call_name)} · ${ago(i.at)}</div>${i.quote ? `<div class="small" style="margin-top:4px">“${esc(i.quote_en || i.quote)}”</div>` : i.outcome ? `<div class="small" style="margin-top:4px">${OUTCOME[i.outcome]?.[0] || ""}</div>` : ""}</div></button>`).join("")}</div>
      <div class="card" id="caseView"></div></div>` : `<div class="card"><h3>All clear</h3><p class="muted">No open cases. Everything has been reviewed.</p></div>`}`;
  main.querySelectorAll(".case").forEach((b) => (b.onclick = () => (location.hash = `#/care/${b.dataset.id}`)));
  if (!cur) return;
  const words = cur.quote || "";
  const tr = (cur.transcript || []).map((t) => `<p class="${t.role === "agent" ? "a" : ""} ${words && t.text.includes(words.replace(/…$/, "").slice(0, 25)) ? "hl" : ""}"><b>${t.role === "agent" ? "Smriti" : esc(p.call_name)}:</b> ${esc(t.text)}</p>`).join("");
  $("#caseView").innerHTML = `<div class="spread"><div><div class="eyebrow">${cur.type === "memory" ? "Memory check" : "Flag"} · ${fmtDay(cur.at)}</div><h2>${esc(title(cur))}</h2></div><span class="chip ${cur.level === "memory" ? "peacock" : cur.level}">${cur.level === "memory" ? esc(cur.outcome || "") : LEVEL[cur.level]}</span></div>
    ${cur.quote ? `<div style="margin-top:16px"><div class="words">${esc(cur.quote)}</div>${cur.quote_en ? `<div class="words-en">${esc(cur.quote_en)}</div>` : ""}</div>` : ""}
    <p class="rule" style="margin-top:12px">Rule that fired: ${esc(cur.rule)}</p>
    ${cur.safety_only ? `<p class="chip red" style="margin-top:12px">Safety concern: never shared with the family. Route: Elder Line 14567.</p>` : ""}
    ${cur.recording_url ? `<audio controls src="${esc(cur.recording_url)}" style="width:100%;margin-top:14px"></audio>` : ""}
    ${tr ? `<h3 style="margin-top:20px">Transcript</h3><div class="transcript">${tr}</div>` : ""}
    ${cur.type === "memory" && cur.session_id ? `<a class="small" style="display:inline-block;margin-top:12px" target="_blank" rel="noopener" href="/report.html?id=${encodeURIComponent(cur.session_id)}">Open the full memory report</a>` : ""}
    <div class="row" style="margin-top:24px"><button class="btn" id="approve">${ic("check")} Approve and call ${esc(p.family_name)}</button><button class="btn quiet" id="dismiss">Dismiss</button></div>
    <p class="small muted" style="margin-top:10px">Smriti will explain in plain words, never as a diagnosis, and offer to put a doctor's visit on the calendar.</p>`;
  $("#approve").onclick = () => approveDialog(cur, cur.parent || p);
  $("#dismiss").onclick = async () => { await api(`/api/care/${cur.type}/${cur.id}/dismiss`, { method: "POST", body: { note: "Dismissed on the care desk" } }); toast("Dismissed."); location.hash = "#/care"; route(); };
};

/* ---------------------------------------------------------------- Behind the call */
VIEWS.behind = async (main) => {
  const o = await api("/api/care/ops");
  const s = o.sessions || {}, b = o.bolna || {};
  const n = (v, digits = 2) => (v === null || v === undefined ? "—" : Number(v).toFixed(digits));
  // Bolna reports cost in US cents (33 for a 5-minute call matches its ~$0.06/min rate).
  const usd = (cents) => (cents === null || cents === undefined ? "—" : `$${(Number(cents) / 100).toFixed(2)}`);
  const perMin = s.avg_call_duration && s.avg_cost ? ` · about ${usd(s.avg_cost / (s.avg_call_duration / 60))} a minute` : "";
  const FEATURES = ["Multilingual agent: Hindi, Kannada, English, switches mid-call", "Sarvam saaras v4 speech-to-text, bulbul v3 voice", "Noise cancellation (level 85)", "Ends the call cleanly after the goodbye", "“Are you there?” check in the caller's language", "Post-call results by webhook, with polling as backup", "Variables per call: notes from last week, topic cards", "Cost and duration of every call, from Bolna's records"];
  main.innerHTML = `<div class="page-head"><div><div class="eyebrow">Smriti team · behind the call</div><h1>What each call takes</h1><p>Every call runs on Bolna. These numbers come straight from Bolna's call records.</p></div></div>
    <div class="grid g3"><div class="card kpi"><div class="v">${s.count ?? 0}</div><div class="l">recent calls · ${s.completed ?? 0} completed</div></div>
      <div class="card kpi"><div class="v">${n(s.avg_call_duration ? s.avg_call_duration / 60 : null, 1)}<span class="muted" style="font-size:20px"> min</span></div><div class="l">average call length</div></div>
      <div class="card kpi"><div class="v">${usd(s.avg_cost)}</div><div class="l">average cost per call${perMin}${b.wallet !== null && b.wallet !== undefined ? ` · wallet ${usd(b.wallet)}` : ""}</div></div></div>
    <div class="grid g2" style="margin-top:20px"><div class="card"><h3>Recent calls</h3><table class="calls"><tr><th>When</th><th>Status</th><th>Length</th><th>Cost</th></tr>
      ${(s.recent || []).map((c) => `<tr><td>${fmtDay(c.created_at)} ${fmtTime(c.created_at)}</td><td>${esc(c.status)}${c.simulated ? " (demo)" : ""}</td><td>${c.call_duration ? mins(c.call_duration) : "—"}</td><td>${usd(c.total_cost)}</td></tr>`).join("")}</table>
      <p class="small muted" style="margin-top:10px">Cost as Bolna reports it for each call.${s.simulated_ops ? " Rows marked (demo) are simulated." : ""}</p></div>
      <div class="card"><h3>Bolna features in use</h3><div class="feature-list">${FEATURES.map((f) => `<div>${ic("check")}<span>${esc(f)}</span></div>`).join("")}</div>
      <h3 style="margin-top:22px">Next on Bolna</h3><p class="muted small">Scheduled batches with calling hours, auto-retry, voicemail detection, “call me at 5” rescheduling, post-call extraction, Cal.com booking, transfer to a human, Truecaller-verified caller ID.</p></div></div>`;
};

/* ---------------------------------------------------------------- dialogs */
function modal(html) {
  $("#overlay").innerHTML = `<div class="scrim" role="dialog" aria-modal="true"><div class="modal">${html}</div></div>`;
  const scrim = $(".scrim");
  scrim.onclick = (e) => { if (e.target === scrim) closeModal(); };
  const first = scrim.querySelector("input, button");
  if (first) first.focus();
  return scrim;
}
const closeModal = () => { $("#overlay").innerHTML = ""; };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

function callDialog(kind) {
  const p = state.parent;
  const memory = kind === "memory";
  const el = modal(`<h2>${memory ? "Start a memory check" : `Call ${esc(p.call_name)} now`}</h2>
    ${typeof callModeNote === "function" ? callModeNote() : ""}
    <p class="muted">${memory ? "About 5 minutes. Smriti asks which language to use, then runs the memory check." : `Smriti will ask how ${esc(p.call_name)} has been, remember last week, and write notes here when the call ends.`}</p>
    <label class="field"><span>${tr("Phone number")}</span><input id="ph" inputmode="tel" autocomplete="off" placeholder="+91 98765 43210" value="${esc(store.get("parentPhone." + state.parentId))}"></label>
    ${memory ? "" : `<label class="field"><span>${tr("Who will pick up?")}</span><input id="nm" value="${esc(store.get("parentName." + state.parentId, p.honorific || p.call_name))}"></label>`}
    ${memory ? `<p class="small muted" style="margin-top:12px">Smriti opens in English and asks which language to use (English, Hindi or Kannada).</p>` : (typeof languagePicker === "function" ? languagePicker(p) : "")}
    ${memory || state.app !== "family" ? "" : `<label class="field"><span>Anything Smriti should ask? (optional, one per line)</span><textarea id="qs" rows="2" style="width:100%;border-radius:12px;border:1.5px solid var(--line);padding:10px 14px;font:inherit;background:var(--paper)" placeholder="Did you take your BP tablet today?"></textarea></label>`}
    <p class="small muted" style="margin-top:12px">The number stays in this browser. Smriti's server only keeps a scrambled form of it.</p>
    <div class="err" id="err" hidden></div>
    <div class="actions"><button class="btn quiet" id="cancel">${tr("Cancel")}</button><button class="btn" id="go">${ic("phone")} ${tr("Call now")}</button></div>`);
  $("#cancel", el).onclick = closeModal;
  $("#go", el).onclick = async () => {
    const phone = $("#ph", el).value.replace(/[\s-]/g, "");
    const name = memory ? null : $("#nm", el).value.trim();
    store.set("parentPhone." + state.parentId, phone);
    if (name) store.set("parentName." + state.parentId, name);
    $("#go", el).disabled = true;
    try {
      const qs = $("#qs", el) ? $("#qs", el).value.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 5) : [];
      const r = await api(memory ? "/api/family/memory-check" : "/api/family/call", { method: "POST", body: { phone: phone || null, name, questions: qs, parent_id: state.parentId, language: $("#callLang", el) ? $("#callLang", el).value || null : null } });
      closeModal();
      showLive(r.session_id, r.checkin_id, memory ? `Memory check with ${p.call_name}` : `Smriti is calling ${name || p.call_name}`, kind);
    } catch (e) {
      $("#err", el).textContent = e.message; $("#err", el).hidden = false; $("#go", el).disabled = false;
    }
  };
}

function approveDialog(c, p) {
  const el = modal(`<h2>Approve and call ${esc(p.family_name)}</h2>${typeof callModeNote === "function" ? callModeNote() : ""}
    <p class="muted">Smriti will explain ${c.type === "memory" ? "the memory check result" : "what " + esc(p.call_name) + " said"} in plain words and offer a doctor's visit on Saturday.</p>
    <label class="field"><span>${esc(p.family_name)}'s phone number</span><input id="fph" inputmode="tel" placeholder="+91 98765 43210" value="${esc(store.get("familyPhone"))}"></label>
    <label class="field"><span>Language for the call to ${esc(p.family_name)}</span><select id="famLang"><option value="en">English</option><option value="hi">हिंदी · Hindi</option><option value="kn">ಕನ್ನಡ · Kannada</option></select></label>
    <label class="field"><span>Note for the record (optional)</span><input id="note" placeholder="e.g. agree with the result"></label>
    <div class="err" id="err" hidden></div>
    <div class="actions"><button class="btn quiet" id="cancel">Cancel</button><button class="btn" id="go">${ic("phone")} Approve and call</button></div>`);
  $("#cancel", el).onclick = closeModal;
  $("#go", el).onclick = async () => {
    const phone = $("#fph", el).value.replace(/[\s-]/g, "");
    store.set("familyPhone", phone);
    $("#go", el).disabled = true;
    try {
      const r = await api(`/api/care/${c.type}/${c.id}/approve`, { method: "POST", body: { family_phone: phone || null, note: $("#note", el).value, language: $("#famLang", el).value } });
      closeModal();
      if (r.family_call) showLive(r.family_call.session_id, r.family_call.checkin_id, `Smriti is calling ${p.family_name}`, "family");
      else { toast(r.note || "Approved."); route(); }
    } catch (e) {
      $("#err", el).textContent = e.message; $("#err", el).hidden = false; $("#go", el).disabled = false;
    }
  };
}

function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast"; t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

/* ---------------------------------------------------------------- live call panel */
const STEPS = [["calling", "Dialling"], ["in_progress", "Talking"], ["writing", "Writing notes"], ["done", "Done"]];
const FINAL = ["scored", "stopped", "invalid", "declined", "failed", "no_answer", "busy"];

function showLive(sessionId, checkinId, title, kind) {
  if (state.live && state.live.es) state.live.es.close();
  const panel = document.createElement("div");
  panel.className = "live"; panel.setAttribute("role", "status");
  panel.innerHTML = `<div class="top"><div class="wave" id="wave"><i></i><i></i><i></i><i></i><i></i></div><div><div class="title">${esc(title)}</div><div class="sub" id="liveSub">Dialling…</div></div><button class="close" aria-label="Hide">×</button></div>
    <div class="steps">${STEPS.map(([k, l]) => `<div class="s" data-k="${k}"><i></i>${l}</div>`).join("")}</div>`;
  document.querySelectorAll(".live").forEach((x) => x.remove());
  document.body.appendChild(panel);
  panel.querySelector(".close").onclick = () => panel.remove();
  const live = { sessionId, checkinId, kind, panel, done: false };
  state.live = live;

  const set = (status) => {
    if (live.done) return;
    const step = status === "calling" || status === "created" ? 0 : status === "in_progress" ? 1 : status === "call_ended" || status === "scoring" ? 2 : FINAL.includes(status) ? 3 : 0;
    panel.querySelectorAll(".s").forEach((s, i) => { s.className = `s ${i < step ? "done" : i === step ? "now" : ""}`; });
    $("#wave", panel).className = `wave ${step === 1 ? "on" : ""}`;
    const sub = { 0: "Ringing… ask them to pick up", 1: "On the call now", 2: "Call ended. Smriti is writing the notes…", 3: "" }[step];
    if (step < 3) $("#liveSub", panel).textContent = sub;
    if (step === 3) finish(status);
  };

  const finish = async (status) => {
    live.done = true;
    if (live.es) live.es.close();
    clearInterval(live.poll);
    panel.querySelectorAll(".s").forEach((s) => (s.className = "s done"));
    $("#wave", panel).className = "wave";
    let msg = { no_answer: "No answer. Smriti will try again later.", busy: "The line was busy. Smriti will try again.", failed: "The call didn't go through." }[status];
    try {
      const c = await api(`/api/family/checkins/${checkinId}`);
      state.fresh = c.id;
      if (!msg) msg = kind === "memory" ? (c.outcome ? `Done: ${OUTCOME[c.outcome][0].toLowerCase()}.` : "Done.") : c.summary || "Done.";
    } catch { /* keep the generic message */ }
    $("#liveSub", panel).textContent = msg || "Done.";
    const target = state.app === "elder" ? "#/mycalls" : state.app === "clinic" ? `#/patient/${state.parentId}` : kind === "family" ? "#/calendar" : "#/timeline";
    if (location.hash !== target) location.hash = target; else route();
    setTimeout(() => panel.remove(), 9000);
  };

  try {
    live.es = new EventSource(`/api/events?session_id=${encodeURIComponent(sessionId)}`);
    live.es.onmessage = (e) => { try { const ev = JSON.parse(e.data); if (ev.status) set(ev.status); } catch { /* keep-alive */ } };
  } catch { /* fall back to polling */ }
  // Polling backup: the event stream can drop on flaky Wi-Fi.
  live.poll = setInterval(async () => {
    try { const s = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`).then((r) => r.json()); if (s.status) set(s.status); } catch { /* next tick */ }
  }, 5000);
  set("calling");
  if (location.hash.startsWith("#/timeline")) route();
}

/* start: see smriti-apps.js (boot) */
