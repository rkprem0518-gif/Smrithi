/* Smriti UI: tiny vanilla JS, no build step. All user/transcript text is set via textContent. */
"use strict";

let LANG = safeGet("smriti_lang") || "en";
let T = {};
let HEALTH = { demo_mode: false };
let rerender = () => {};

function safeGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
function safeSet(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } }

function t(key) { return T[key] ?? key; }

async function loadLang(lang) {
  T = await fetch(`/i18n/${lang}.json`).then((r) => r.json());
  LANG = lang;
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
}

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
  });
  let body = null;
  if (res.status !== 204) {
    try { body = await res.json(); } catch { body = null; }
  }
  if (!res.ok) {
    let detail = body && body.detail;
    if (Array.isArray(detail)) detail = detail.map((d) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join("; ");
    const err = new Error(detail || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return body;
}

function param(name) { return new URLSearchParams(location.search).get(name); }

/* ------------------------------------------------------------------ home */

function pageHome() {
  rerender = () => {};
}

/* ------------------------------------------------------------------ start */

function pageStart() {
  const form = document.getElementById("start-form");
  const phoneField = document.getElementById("phone-field");
  const personaField = document.getElementById("persona-field");
  const errorBox = document.getElementById("form-error");
  const submit = document.getElementById("submit-btn");

  personaField.hidden = !HEALTH.demo_mode;
  const syncMode = () => {
    const mode = form.querySelector("input[name=mode]:checked").value;
    phoneField.hidden = mode !== "phone";
    document.getElementById("phone").required = mode === "phone" && !HEALTH.demo_mode;
  };
  form.querySelectorAll("input[name=mode]").forEach((r) => r.addEventListener("change", syncMode));
  syncMode();

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    errorBox.textContent = "";
    if (!form.consent.checked) { errorBox.textContent = t("consent_required"); form.consent.focus(); return; }
    const mode = form.querySelector("input[name=mode]:checked").value;
    const years = form.schooling.value.trim();
    const payload = {
      consent: true,
      language: form.language.value,
      mode,
      schooling_years: years === "" ? null : Number(years),
      phone: mode === "phone" && form.phone.value.trim() ? form.phone.value.trim().replace(/[\s-]/g, "") : null,
      demo_fixture: HEALTH.demo_mode ? form.persona.value : null,
    };
    submit.disabled = true;
    submit.textContent = t("starting");
    try {
      const res = await api("/api/sessions", { method: "POST", body: JSON.stringify(payload) });
      if (res.web_call && window.SmritiWebCall) {
        await window.SmritiWebCall.start(res.web_call, res.session_id, document.getElementById("webcall-box"));
      } else {
        location.href = `/live.html?id=${encodeURIComponent(res.session_id)}`;
      }
    } catch (err) {
      errorBox.textContent = err.message;
      submit.disabled = false;
      submit.textContent = t("submit");
    }
  });
  rerender = () => { submit.textContent = t("submit"); };
}

/* ------------------------------------------------------------------ live */

const LIVE_STEPS = ["calling", "in_progress", "call_ended", "scoring", "done"];
const DONE = new Set(["scored", "invalid", "stopped"]);
const ENDED = { declined: "end_declined", no_answer: "end_no_answer", busy: "end_busy", failed: "end_failed" };

function pageLive() {
  const id = param("id");
  const list = document.getElementById("stepper");
  const msg = document.getElementById("live-msg");
  let status = "calling";
  let error = null;

  const draw = () => {
    const idx = DONE.has(status) ? LIVE_STEPS.length - 1 : Math.max(0, LIVE_STEPS.indexOf(status));
    list.replaceChildren(...LIVE_STEPS.map((s, i) => el("li",
      { class: i < idx || DONE.has(status) ? "done" : i === idx ? "active" : "" },
      el("span", { class: "dot", "aria-hidden": "true" }), t(`st_${s}`))));
    if (ENDED[status]) {
      list.querySelectorAll("li.active").forEach((li) => li.classList.remove("active"));
      const h1 = document.querySelector("h1");
      if (h1) h1.textContent = t("live_ended_title");
      msg.replaceChildren(el("p", { class: "notice strong", text: t(ENDED[status]) + (error ? ` ${error}` : "") }),
        el("a", { class: "btn", href: "/start.html", text: t("try_again") }));
    }
  };
  rerender = draw;
  draw();

  const tick = async () => {
    try {
      const s = await api(`/api/sessions/${encodeURIComponent(id)}`);
      status = s.status;
      error = s.error;
      draw();
      if (DONE.has(status)) { setTimeout(() => { location.href = `/report.html?id=${encodeURIComponent(id)}`; }, 700); return; }
      if (ENDED[status]) return;
    } catch (err) {
      msg.textContent = err.message;
      if (err.status === 404) return;
    }
    setTimeout(tick, 2000);
  };
  tick();
}

/* ------------------------------------------------------------------ report */

const DAYS = {
  en: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
  hi: ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
};
const MONTHS = {
  en: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
  hi: ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"],
};
const NAMED = {
  hi: { winter: "सर्दी", summer: "गर्मी", monsoon: "बरसात", spring: "बसंत", autumn: "शरद",
        morning: "सुबह", afternoon: "दोपहर", evening: "शाम", night: "रात" },
};

let REPORT_LANG = "hi";
function wordLabel(w) {
  if (REPORT_LANG === "kn" && w.kn) return `${w.kn} (${w.en})`;
  return LANG === "hi" ? `${w.hi} (${w.id})` : `${w.id} (${w.en})`;
}

function wordChips(wordList, hits) {
  const set = new Set(hits);
  return el("ul", { class: "chips" }, wordList.map((w) => el("li", {
    class: `chip ${set.has(w.id) ? "hit" : "miss"}`,
    title: set.has(w.id) ? t("recalled") : t("not_recalled"),
    "aria-label": `${wordLabel(w)}: ${set.has(w.id) ? t("recalled") : t("not_recalled")}`,
    text: `${set.has(w.id) ? "✓ " : ""}${wordLabel(w)}`,
  })));
}

function extraChips(words, cls = "intrusion") {
  if (!words || !words.length) return null;
  return el("ul", { class: "chips" }, words.map((w) => el("li", { class: `chip ${cls}`, text: w })));
}

function scoreLine(score, max) { return el("div", { class: "score" }, String(score), el("small", {}, ` / ${max}`)); }

function orientationAnswer(item, value) {
  if (value === null || value === undefined) return "-";
  if (item === "day" && /^\d$/.test(value)) return DAYS[LANG][Number(value)];
  if (item === "month" && /^\d{1,2}$/.test(value)) return MONTHS[LANG][Number(value) - 1];
  return (NAMED[LANG] || {})[value] || value;
}

function renderReport(root, s) {
  const r = s.report;
  const d = r.domains;
  const nextStep = r.next_step_text[LANG] || r.next_step_text.en;
  const bandText = `${t(`band_${r.band}`)} (${t(`band_src_${r.band_source}`)}${r.schooling_years !== null && r.schooling_years !== undefined ? `: ${r.schooling_years} ${t("years")}` : ""})`;

  const learning = el("section", { class: "card" },
    el("h2", { text: t("word_learning") }), scoreLine(d.word_learning.total, d.word_learning.max),
    d.word_learning.trials.map((hits, i) => el("div", { class: "trial" },
      el("div", { class: "trial-label", text: `${t("trial")} ${i + 1}: ${hits.length}/10` }),
      wordChips(r.word_list, hits),
      (d.word_learning.intrusions[i] || []).length
        ? el("div", { class: "small muted" }, `${t("intrusions")}: `, (d.word_learning.intrusions[i] || []).join(", ")) : null)));

  const recall = el("section", { class: "card" },
    el("h2", { text: t("delayed_recall") }), scoreLine(d.delayed_recall.score, d.delayed_recall.max),
    wordChips(r.word_list, d.delayed_recall.words),
    d.delayed_recall.intrusions.length ? el("div", { class: "small muted" }, `${t("intrusions")}: `, d.delayed_recall.intrusions.join(", ")) : null);

  const animals = el("section", { class: "card" },
    el("h2", { text: t("animal_naming") }), el("div", { class: "score", text: String(d.animal_naming.count) }),
    el("div", { class: "small muted", text: t("animals_counted") }),
    extraChips(d.animal_naming.words.map((w) => (LANG === "hi" && r.animal_names && r.animal_names[w]) || w), "hit"),
    d.animal_naming.non_animals.length ? el("div", { class: "small muted" }, `${t("not_animals")}: `, d.animal_naming.non_animals.join(", ")) : null,
    el("p", { class: "small muted", text: d.animal_naming.experimental_timing ? t("timing_experimental") : t("timing_asr") }));

  const items = ["day", "month", "season", "time_of_day", "place"];
  const orientation = el("section", { class: "card" },
    el("h2", { text: t("orientation") }), scoreLine(d.orientation.score, d.orientation.max),
    el("table", { class: "items" }, el("tbody", {}, items.map((item) => el("tr", {},
      el("td", { text: t(`item_${item}`) }),
      el("td", { text: orientationAnswer(item, d.orientation.answers[item]) }),
      el("td", { class: d.orientation.items[item] ? "ok" : "no", text: d.orientation.items[item] ? "✓" : "✗",
                 "aria-label": d.orientation.items[item] ? t("yes") : t("no") }))))),
    el("p", { class: "small muted", text: t("place_note") }));

  const hearing = el("section", { class: "card" },
    el("h2", { text: t("hearing") }), scoreLine(r.hearing.correct, r.hearing.max),
    el("table", { class: "items" }, el("tbody", {}, r.hearing.items.map((it) => el("tr", {},
      el("td", { text: it.expected.split("").join("-") }),
      el("td", { text: it.heard.join(" / ") || "-" }),
      el("td", { class: it.correct ? "ok" : "no", text: it.correct ? "✓" : "✗" }))))));

  const sm = r.speech_markers;
  const markers = el("details", { class: "card" },
    el("summary", { text: t("speech_markers") }),
    el("table", { class: "items" }, el("tbody", {},
      [["sm_turns", sm.user_turns], ["sm_words", sm.mean_words_per_turn], ["sm_fillers", sm.filler_rate],
       ["sm_dontknow", sm.dont_know_count], ["sm_latency", sm.mean_response_latency_s ?? "-"]]
        .map(([k, v]) => el("tr", {}, el("td", { text: t(k) }), el("td", { text: String(v) }))))));

  root.replaceChildren(
    el("p", { class: "notice strong", text: `${t("pilot")}. ${r.pilot_notice[LANG] || r.pilot_notice.en}` }),
    el("section", { class: "card" },
      el("div", { class: "outcome-hero" },
        el("span", { class: `badge ${r.outcome}`, text: r.outcome_label[LANG] || r.outcome_label.en }),
        s.is_demo ? el("span", { class: "chip", text: t("demo_label") }) : null),
      el("p", {}, `${t("rule")}: `, el("span", { class: "rule", text: r.rule_fired })),
      el("p", { class: "muted" }, `${t("band")}: ${bandText}`),
      el("p", { class: "muted" }, `${t("review_status")}: ${t(`rv_${s.review_status}`)}`),
      r.invalid_reason_text.length ? el("div", {},
        el("h3", { text: t("invalid_reasons") }),
        el("ul", {}, r.invalid_reason_text.map((x) => el("li", { text: x[LANG] || x.en })))) : null,
      el("h3", { text: t("next_step") }), el("p", { text: nextStep }),
      r.outcome === "INVALID" ? el("p", { class: "notice", text: t("invalid_caveat") }) : null,
      r.helpline_text ? el("p", { class: "notice" }, el("b", { text: `${t("helpline")}: ` }), r.helpline_text) : null),
    el("div", { class: "grid" }, recall, learning),
    el("div", { class: "grid" }, animals, orientation),
    hearing,
    el("p", { class: "small muted", text: t("evidence_note") }),
    markers,
    el("div", { class: "no-print", style: "display:flex;gap:10px;flex-wrap:wrap;margin-top:12px" },
      el("button", { class: "btn secondary", type: "button", onclick: () => window.print(), text: t("print_btn") }),
      s.is_demo ? null : el("button", { class: "btn danger", type: "button", onclick: () => deleteSession(s.session_id, root), text: t("delete_btn") })),
    el("p", { class: "small muted", text: `${t("scorer")}: ${r.scorer_version} · ${r.call_time || ""}` }),
  );
}

async function deleteSession(id, root) {
  if (!confirm(t("delete_confirm"))) return;
  await api(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
  root.replaceChildren(el("p", { class: "notice strong", text: t("deleted") }));
  rerender = () => {};
}

async function pageReport() {
  const root = document.getElementById("report");
  const id = param("id");
  let data;
  try {
    data = await api(`/api/sessions/${encodeURIComponent(id)}`);
  } catch (err) {
    root.replaceChildren(el("p", { class: "notice", text: err.status === 404 ? t("not_found") : t("load_error") }));
    return;
  }
  if (ENDED[data.status]) {
    root.replaceChildren(el("p", { class: "notice strong", text: t(ENDED[data.status]) }),
      el("a", { class: "btn", href: "/start.html", text: t("try_again") }));
    return;
  }
  if (!data.report) {
    root.replaceChildren(el("p", { class: "notice", text: t("not_ready") }),
      el("a", { class: "btn", href: `/live.html?id=${encodeURIComponent(id)}`, text: t("live_title") }));
    return;
  }
  REPORT_LANG = data.report.language;
  rerender = () => renderReport(root, data);
  rerender();
}

/* ------------------------------------------------------------------ review */

function pageReview() {
  const form = document.getElementById("token-form");
  const list = document.getElementById("queue");
  let token = "";
  try { token = sessionStorage.getItem("smriti_review_token") || ""; } catch { /* ignore */ }
  form.token.value = token;
  let items = [];

  const draw = () => {
    if (!items.length) { list.replaceChildren(el("p", { class: "muted", text: t("queue_empty") })); return; }
    list.replaceChildren(...items.map((it) => {
      const r = it.report || {};
      const status = el("p", { class: "small", role: "status" });
      const fid = (name) => `${name}-${it.session_id}`;
      const decisionForm = el("form", { class: "no-print" },
        el("div", { class: "field" }, el("label", { for: fid("decision"), text: t("decision") }),
          el("select", { id: fid("decision"), name: "decision" }, ["agree", "retest", "override_normal", "override_refer"]
            .map((v) => el("option", { value: v, text: t(`dec_${v}`) })))),
        el("div", { class: "field" }, el("label", { for: fid("reviewer"), text: t("reviewer_name") }),
          el("input", { id: fid("reviewer"), type: "text", name: "reviewer", required: true, maxlength: "80" })),
        el("div", { class: "field" }, el("label", { for: fid("note"), text: t("note") }),
          el("textarea", { id: fid("note"), name: "note", maxlength: "2000" })),
        el("button", { class: "btn", type: "submit", text: t("save") }), status);
      decisionForm.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        try {
          await api(`/api/review/${encodeURIComponent(it.session_id)}`, {
            method: "POST", headers: { Authorization: `Bearer ${token}` },
            body: JSON.stringify({ reviewer: decisionForm.reviewer.value, decision: decisionForm.decision.value,
                                   note: decisionForm.note.value }),
          });
          status.textContent = t("saved");
          if (!form.all.checked) {
            items = items.filter((x) => x.session_id !== it.session_id);
            setTimeout(draw, 900);
          }
        } catch (err) { status.textContent = err.message; }
      });
      return el("article", { class: "card" },
        el("div", { class: "outcome-hero" },
          r.outcome ? el("span", { class: `badge ${r.outcome}`, text: (r.outcome_label || {})[LANG] || r.outcome }) : null,
          it.is_demo ? el("span", { class: "chip", text: t("demo_label") }) : null,
          el("a", { href: `/report.html?id=${encodeURIComponent(it.session_id)}`, text: t("view_report") })),
        el("p", {}, el("span", { class: "rule", text: it.rule_fired || it.status })),
        el("p", { class: "small muted", text: `${new Date(it.created_at).toLocaleString()} · ${it.language} · ${t(`rv_${it.review_status}`)}` }),
        it.reviews.length ? el("ul", { class: "small" }, it.reviews.map((rv) => el("li", { text: `${rv.reviewer}: ${t(`dec_${rv.decision}`)} ${rv.note ? `- ${rv.note}` : ""}` }))) : null,
        it.recording_url ? el("div", {}, el("h3", { text: t("recording") }),
          el("audio", { controls: true, preload: "none", src: it.recording_url, style: "width:100%" })) : null,
        el("details", {}, el("summary", { text: t("transcript") }),
          el("div", { class: "transcript" }, (it.transcript || []).map((turn) => el("p", { class: turn.role },
            el("b", { text: turn.role === "agent" ? `${t("brand")}: ` : `${t("speaker_user")}: ` }), turn.text)))),
        decisionForm);
    }));
  };
  rerender = draw;

  const load = async () => {
    token = form.token.value.trim();
    try { sessionStorage.setItem("smriti_review_token", token); } catch { /* ignore */ }
    const status = form.all.checked ? "all" : "pending";
    try {
      const res = await api(`/api/review?status=${status}`, { headers: { Authorization: `Bearer ${token}` } });
      items = res.items;
      draw();
    } catch (err) {
      list.replaceChildren(el("p", { class: "error", text: err.status === 401 ? t("bad_token") : err.message }));
    }
  };
  form.addEventListener("submit", (ev) => { ev.preventDefault(); load(); });
  if (token) load();
}

/* ------------------------------------------------------------------ boot */

const PAGES = { home: pageHome, start: pageStart, live: pageLive, report: pageReport, review: pageReview };

document.addEventListener("DOMContentLoaded", async () => {
  await loadLang(LANG);
  const toggle = document.getElementById("lang-toggle");
  if (toggle) {
    toggle.addEventListener("click", async () => {
      const next = LANG === "en" ? "hi" : "en";
      safeSet("smriti_lang", next);
      await loadLang(next);
      rerender();
    });
  }
  try { HEALTH = await api("/api/health"); } catch { /* offline page still renders */ }
  const banner = document.getElementById("demo-banner");
  if (banner) banner.hidden = !HEALTH.demo_mode;
  const page = PAGES[document.body.dataset.page];
  if (page) await page();
});
