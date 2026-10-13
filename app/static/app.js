const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v); else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat(Infinity)) if (k !== false && k != null) el.append(k instanceof Node ? k : document.createTextNode(k));
  return el;
}
const auth = {
  get token() { return sessionStorage.getItem("token"); },
  save(r) { sessionStorage.setItem("token", r.token); },
  clear() { sessionStorage.removeItem("token"); },
};
// Each role has its own address: /student, /teacher, /admin (log in) and /<role>/app (the portal itself).
const ROLES = ["student", "teacher", "admin"];
const PORTAL = ROLES.includes(location.pathname.split("/")[1]) ? location.pathname.split("/")[1]
  : ROLES.includes(new URLSearchParams(location.search).get("role")) ? new URLSearchParams(location.search).get("role") : "student";
const HOME = { admin: "/admin/app", teacher: "/teacher/app", student: "/student/app" };
const ROLE_NAME = { admin: "Admin", teacher: "Teacher", student: "Student" };
document.documentElement.dataset.role = PORTAL;   // picks the portal's lighting theme in style.css
// The school shown on the log-in pages. A made-up placeholder: change the name and motto here,
// and replace /static/school/crest.svg with the real logo (a .png works too; change the path).
const SCHOOL = { name: "SMK Taman Harmoni", short: "SMKTH", motto: "Ilmu · Disiplin · Bakti", logo: "/static/school/crest.svg" };
addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-school]").forEach(el => { el.textContent = SCHOOL[el.dataset.school]; });
  document.querySelectorAll("img[data-school-logo]").forEach(el => { el.src = SCHOOL.logo; });
});

// ---------------------------------------------------------------- percentage bars fill in when they come into view
(function bars() {
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const seen = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in-view"); seen.unobserve(e.target); } }),
    { threshold: 0, rootMargin: "0px 0px -8% 0px" });
  const watch = root => root.querySelectorAll?.(".bar").forEach(el => still ? el.classList.add("in-view") : seen.observe(el));
  new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => { if (n.nodeType === 1) { if (n.matches(".bar")) watch(n.parentNode); watch(n); } })))
    .observe(document.documentElement, { childList: true, subtree: true });
  addEventListener("DOMContentLoaded", () => watch(document));
})();

async function api(path, { method = "GET", body, blob = false } = {}) {
  const headers = {};
  if (auth.token) headers.Authorization = "Bearer " + auth.token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!res.ok) {
    let detail = res.statusText, data = null;
    try {
      const j = await res.json();
      if (j.detail && typeof j.detail === "object" && !Array.isArray(j.detail)) { data = j.detail; detail = j.detail.message || detail; }   // e.g. {message, session_id}
      else detail = typeof j.detail === "string" ? j.detail : fieldError(j.detail) || detail;
    } catch (e) {}
    const err = new Error(detail); err.status = res.status; err.data = data; throw err;
  }
  return blob ? res.blob() : res.json();
}
// FastAPI validation errors arrive as a list; turn the first one into a readable sentence.
function fieldError(list) {
  if (!Array.isArray(list) || !list.length) return "";
  const f = list[0], field = String(f.loc?.[f.loc.length - 1] ?? "").replace(/_/g, " ");
  if (/password/.test(field) && f.type === "string_too_short") return "The password needs 8 or more characters.";
  if (/email/.test(field)) return "Please enter a valid email address.";
  if (/student no/.test(field) && f.type === "string_pattern_mismatch") return "Student ID can only use letters, numbers and . _ / -";
  if (/username/.test(field) && f.type === "string_pattern_mismatch") return "Username can only use letters, numbers and . _ -";
  if (/username/.test(field) && f.type === "string_too_short") return "Username needs 3 or more characters.";
  if (/code/.test(field)) return "The reset code has 6 digits.";
  if (/class ids/.test(field)) return "Choose at least one class.";
  return `Please check the ${field} field.`;
}
// Portal pages call this first. Not logged in: go to this portal's log-in page. Logged in with another role
// (e.g. a teacher opens /admin/app): go to that person's own portal.
async function requireRole(role) {
  if (!auth.token) { location.href = "/" + role; return new Promise(() => {}); }
  try {
    const me = await api("/api/me");
    if (me.role !== role) { location.href = HOME[me.role]; return new Promise(() => {}); }
    setupHeader(me);
    return me;
  } catch (e) { auth.clear(); location.href = "/" + role; return new Promise(() => {}); }
}
// The header of every portal: picture and name, then "Change password" and "Log out".
function setupHeader(me) {
  const who = $("#whoami");
  if (who) who.replaceChildren(avatar(me), h("span", {}, me.name));
  const pw = $("#cpwBtn"), out = $("#logout");
  if (pw) pw.onclick = openPasswordDialog;
  if (out) out.onclick = e => { e.preventDefault(); logout(); };
}
function openPasswordDialog() {
  const d = h("dialog", { "aria-labelledby": "cpTitle" });
  d.innerHTML = `<form method="dialog" class="form"><h2 id="cpTitle">Change password</h2>
    <div><label for="cpCur">Current password</label><input id="cpCur" type="password" autocomplete="current-password" required></div>
    <div><label for="cpNew">New password (8 or more characters)</label><input id="cpNew" type="password" autocomplete="new-password" minlength="8" required></div>
    <div><label for="cpNew2">New password again</label><input id="cpNew2" type="password" autocomplete="new-password" required></div>
    <div id="cpMsg" class="msg" role="status"></div>
    <div class="row"><div class="fit"><button id="cpGo" value="go">Change password</button></div><div class="fit"><button type="button" class="ghost" id="cpClose">Close</button></div></div></form>`;
  document.body.append(d);
  d.addEventListener("close", () => d.remove());
  d.querySelector("#cpClose").onclick = () => d.close();
  d.querySelector("form").onsubmit = async e => {
    e.preventDefault();
    const m = d.querySelector("#cpMsg");
    if (d.querySelector("#cpNew").value !== d.querySelector("#cpNew2").value) return say(m, "The new passwords are not the same.", "err");
    try { await api("/api/me/password", { method: "POST", body: { current_password: d.querySelector("#cpCur").value, new_password: d.querySelector("#cpNew").value } });
      d.querySelectorAll("input").forEach(i => i.value = ""); say(m, "Password changed.", "ok"); }
    catch (err) { say(m, err.message, "err"); }
  };
  d.showModal();
}

// ---------------------------------------------------------------- profile pictures
// Pictures need the login token, so they are fetched with api() and shown from a blob URL.
const photoCache = {};
function avatar(person, size = "", id = person.id) {
  const el = h("span", { class: "avatar " + size, "aria-hidden": "true" }, initials(person.name));
  if (person.has_photo) {
    (photoCache[id] ||= api(`/api/photos/${id}`, { blob: true }).then(b => URL.createObjectURL(b)).catch(() => null))
      .then(url => { if (url) el.replaceChildren(h("img", { src: url, alt: "" })); });
  }
  return el;
}
function forgetPhoto(id) { delete photoCache[id]; }
// Asks for a picture, crops it to a square and shrinks it to 360 px, then uploads it.
function choosePhoto(onDone) {
  const input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp" });
  input.onchange = () => {
    const f = input.files[0]; if (!f) return;
    const img = new Image();
    img.onload = async () => {
      const S = 360, side = Math.min(img.width, img.height), c = h("canvas", { width: S, height: S });
      c.getContext("2d").drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, S, S);
      URL.revokeObjectURL(img.src);
      try { await api("/api/me/photo", { method: "POST", body: { data_url: c.toDataURL("image/jpeg", 0.85) } }); onDone(null); }
      catch (e) { onDone(e); }
    };
    img.onerror = () => onDone(new Error("That file is not a picture."));
    img.src = URL.createObjectURL(f);
  };
  input.click();
}
async function logout() { try { await api("/api/logout", { method: "POST" }); } catch (e) {} auth.clear(); location.href = "/" + PORTAL; }
function say(el, text, kind = "") { el.textContent = text; el.className = "msg " + kind; }
function download(blob, name) { const a = h("a", { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); a.remove(); }
const fmtDateTime = iso => iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "";
const fmtTime = iso => iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
const fmtDate = ymd => new Date(ymd + "T00:00").toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric" });
const timeRange = s => s.start_time ? s.start_time + (s.end_time ? "–" + s.end_time : "") : "";
const isoDate = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const empty = (cols, text) => h("tr", {}, h("td", { colspan: cols, class: "note" }, text));
const pill = (kind, text) => h("span", { class: "pill " + kind }, text);
// percentage bar for reports: green, amber below `low`+10, red below `low`
const bar = (p, low = 75) => p == null ? h("span", { class: "bar none" }, "no sessions")
  : h("span", { class: "bar" + (p < low ? " low" : p < low + 10 ? " mid" : ""), title: p + "%" },
      h("i", {}, h("b", { style: `width:${Math.min(100, p)}%` })), Math.round(p) + "%");
const fmtSize = n => n < 1024 * 1024 ? Math.max(1, Math.round(n / 1024)) + " KB" : (n / 1024 / 1024).toFixed(1) + " MB";
const initials = name => (name || "?").split(/\s+/).filter(w => w && !/^(bin|binti|a\/l|a\/p)$/i.test(w)).slice(0, 2).map(w => w[0].toUpperCase()).join("");

// Co-curriculum types from the master list ('' = an old teacher-made group) and achievement levels.
const CAT = { uniform: "Uniform body", club: "Club / society", sport: "Sport / game", "": "Group" };
const catPill = c => h("span", { class: "pill cat-" + (c || "group") }, CAT[c || ""] || c);
const LEVEL_ORDER = ["School", "Zone", "District", "State", "National", "International"];
const levelPill = l => h("span", { class: "pill lvl lvl-" + Math.max(0, LEVEL_ORDER.indexOf(l)) }, l);
// A tab bar from [[key, label], ...]; the current key is marked.
const tabBar = (el, tabs, current, go) => el.replaceChildren(...tabs.map(([k, label]) =>
  h("button", { class: k === current ? "on" : "", "data-tab": k, onclick: () => go(k) }, label)));

// ---------------------------------------------------------------- calendar (teachers: their sessions; admin: all)
function calendar(el, { onOpen, onNew }) {
  let month = new Date(); month.setDate(1);
  el.innerHTML = `<div class="cal-head"><button class="ghost" data-m="-1" aria-label="Previous month">&larr;</button>
    <h2 class="cal-title"></h2><button class="ghost" data-m="1" aria-label="Next month">&rarr;</button>
    <button class="ghost" data-m="0">Today</button>${onNew ? '<button class="cal-new">+ New session</button>' : ""}</div>
    <div class="cal-grid" role="grid"></div><h3>This month</h3><div class="cal-list"></div>`;
  el.querySelectorAll("[data-m]").forEach(b => b.onclick = () => {
    const m = +b.dataset.m; if (m === 0) { month = new Date(); month.setDate(1); } else month.setMonth(month.getMonth() + m); load(); });
  if (onNew) el.querySelector(".cal-new").onclick = () => onNew(isoDate(new Date()));
  async function load() {
    // both at midnight, so the day loop below reaches the last cell of the grid
    const first = new Date(month.getFullYear(), month.getMonth(), 1), last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
    const gridStart = new Date(first); gridStart.setDate(1 - ((first.getDay() + 6) % 7));     // weeks start on Monday
    const gridEnd = new Date(last); gridEnd.setDate(last.getDate() + (6 - ((last.getDay() + 6) % 7)));
    el.querySelector(".cal-title").textContent = first.toLocaleDateString([], { month: "long", year: "numeric" });
    const list = await api(`/api/sessions?start=${isoDate(gridStart)}&end=${isoDate(gridEnd)}`), byDay = {};
    list.forEach(s => (byDay[s.session_date] ||= []).push(s));
    const today = isoDate(new Date()), cells = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(d => h("div", { class: "cal-dow" }, d));
    for (let d = new Date(gridStart); d <= gridEnd; d.setDate(d.getDate() + 1)) {
      const key = isoDate(d), items = byDay[key] || [];
      cells.push(h("div", { class: "cal-day" + (d.getMonth() !== first.getMonth() ? " out" : "") + (key === today ? " today" : "") },
        h("div", { class: "cal-num" }, onNew ? h("button", { class: "link", title: "New session on this day", onclick: () => onNew(key) }, String(d.getDate())) : String(d.getDate())),
        items.map(s => h("button", { class: "cal-ev" + (s.closed ? " closed" : ""), title: `${s.title} · ${s.venue} · ${s.classes}`, onclick: () => onOpen(s) },
          h("b", {}, s.start_time || ""), " ", s.title))));
    }
    el.querySelector(".cal-grid").replaceChildren(...cells);
    const inMonth = list.filter(s => s.session_date.slice(0, 7) === key7(first));
    el.querySelector(".cal-list").replaceChildren(...(inMonth.length ? inMonth.map(s => h("button", { class: "agenda" + (s.closed ? " closed" : ""), onclick: () => onOpen(s) },
      h("span", { class: "a-date" }, fmtDate(s.session_date)), h("span", { class: "a-time" }, timeRange(s) || "all day"),
      h("span", { class: "a-main" }, h("b", {}, s.title), " · ", s.venue, h("br"), h("span", { class: "note" }, s.classes || "")),
      h("span", { class: "note" }, `${s.present} present`))) : [h("p", { class: "note" }, "No sessions this month.")]));
  }
  const key7 = d => isoDate(d).slice(0, 7);
  load();
  return { reload: load };
}

// ---------------------------------------------------------------- student list (teachers and admin)
const QR_LABEL = s => s.qr_status === "unregistered" ? pill("warn", "not registered yet")
  : s.qr_status === "terminated" ? pill("absent", "terminated, must register again")
  : s.qr_printed_at ? pill("present", "QR printed " + new Date(s.qr_printed_at).toLocaleDateString()) : pill("present", "registered, QR not printed");
// The students of a teacher's own co-curricula, with Reset code and Terminate QR.
function studentList(el) {
  el.innerHTML = `<div class="row"><div><input class="sq" placeholder="Search name, student ID or class ID" aria-label="Search students"></div>
    <div class="fit"><label class="inline"><input type="checkbox" class="sreq"> Only password reset requests</label></div></div>
    <p class="note scount"></p>
    <div class="msg" data-msg role="status"></div>
    <div class="scroll"><table><thead><tr><th></th><th>Name</th><th>Student ID</th><th>Class ID</th><th>In your co-curricula</th><th>Account / QR</th><th>Attended</th><th></th></tr></thead><tbody></tbody></table></div>`;
  let list = [];
  const msg = el.querySelector("[data-msg]"), body = el.querySelector("tbody");
  const act = (label, fn, cls = "ghost") => h("button", { class: cls, onclick: async () => { try { await fn(); } catch (e) { say(msg, e.message, "err"); } } }, label);
  function render() {
    const q = el.querySelector(".sq").value.toLowerCase(), onlyReq = el.querySelector(".sreq").checked;
    const rows = list.filter(s => (s.name + " " + s.student_no + " " + s.class_name + " " + (s.classes || "")).toLowerCase().includes(q) && (!onlyReq || s.reset_requested));
    const reg = list.filter(s => s.qr_status !== "unregistered").length;
    el.querySelector(".scount").textContent = `${list.length} students · ${reg} registered · ${list.length - reg} not registered yet · showing ${Math.min(rows.length, 500)}`;
    body.replaceChildren(...(rows.length ? rows.slice(0, 500).map(s => h("tr", { class: s.active ? "" : "dim" },
      h("td", {}, avatar(s)), h("td", {}, s.name,s.reset_requested ? h("div", {}, pill("warn", "asked for password reset")) : "", s.active ? "" : h("div", {}, pill("absent", "disabled"))),
      h("td", {}, s.student_no), h("td", {}, s.class_name || h("span", { class: "note" }, "—")), h("td", { class: "small" }, s.classes || ""),
      h("td", {}, QR_LABEL(s)), h("td", {}, String(s.attended)),
      h("td", { class: "actions" },
        s.qr_status === "active" ? act("Reset code", async () => { const r = await api(`/api/students/${s.id}/reset-code`, { method: "POST" });
          say(msg, `Reset code for ${r.name} (${r.student_no}): ${r.code}  · Give it to the student in person. It works once, for 30 minutes.`, "ok code"); load(); }) : "",
        s.qr_status === "active" ? act("Terminate QR", async () => {
          if (!confirm(`Terminate the QR of ${s.name}?\n\nUse this when the student reports the QR missing. The QR stops working at once, the student is logged out and must register again with the same student ID and name to get a new QR. Classes and past attendance are kept.`)) return;
          await api(`/api/students/${s.id}/terminate`, { method: "POST" }); say(msg, `${s.name}'s QR was terminated. They can now register again.`, "ok"); load(); }, "danger-ghost") : "")))
      : [empty(8, list.length ? "No match." : "No students yet. They come from the school's master list.")]));
  }
  async function load() { list = await api("/api/students"); render(); }
  el.querySelector(".sq").oninput = render; el.querySelector(".sreq").onchange = render;
  load();
  return { reload: load };
}
