// Pure game logic: daily prompts, scoring, persistence.
import STATS from "./stats.json";
import SCHEDULE from "./schedule.json";
import CENTROIDS from "./centroids.json";

export const statById = Object.fromEntries(STATS.stats.map((s) => [s.id, s]));
export const promptById = Object.fromEntries(STATS.prompts.map((p) => [p.id, p]));
export const PICKABLE = Object.keys(CENTROIDS).filter((a) => a !== "AQ");

const names = new Intl.DisplayNames(["en"], { type: "region" });
const OVERRIDES = { CD: "DR Congo", CG: "Republic of the Congo", PS: "Palestine", MM: "Myanmar", CI: "Côte d’Ivoire" };
export const nameOf = (a2) => { if (OVERRIDES[a2]) return OVERRIDES[a2]; try { return names.of(a2); } catch { return a2; } };

// ---- day ----
export const todayKey = (d = new Date()) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const dayIndex = (key) => Math.round((Date.parse(key) - Date.parse(SCHEDULE.start)) / 864e5);
export const dayNumber = (key) => dayIndex(key) + 1;

function hash(str) {
  let h = 2166136261;
  for (const c of str) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  return h >>> 0;
}

/** Three prompts for a date: scheduled if available, otherwise seeded by the date. */
export function promptsFor(key) {
  const ids = SCHEDULE.days[key];
  if (ids) return ids.map((id) => promptById[id]);
  const used = new Set();
  return [1, 2, 3].map((tier) => {
    const pool = STATS.prompts.filter((p) => p.tier === tier && !used.has(p.stat));
    const p = pool[hash(key + tier) % pool.length];
    used.add(p.stat);
    return p;
  });
}

// ---- ranking ----
export function ranked(prompt) {
  const rows = Object.entries(statById[prompt.stat].values);
  rows.sort((a, b) => (prompt.dir === "most" ? b[1] - a[1] : a[1] - b[1]));
  return rows; // [[alpha2, value]] best first
}

// ---- scoring ----
const R = 6371;
export function km(a, b) {
  const [la1, lo1] = CENTROIDS[a].map((x) => (x * Math.PI) / 180);
  const [la2, lo2] = CENTROIDS[b].map((x) => (x * Math.PI) / 180);
  const h = Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

const ZERO_AT_KM = 8000;
const CAPS = [100, 95, 90]; // max score for landing on #1, #2, #3
const falloff = (d) => Math.max(0, 1 - d / ZERO_AT_KM) ** 1.5;

/** Score = best over the top 3 of cap × falloff(distance). Returns score + which target it counted against. */
export function score(pick, prompt) {
  const top = prompt.top;
  let best = { score: 0, target: top[0], km: km(pick, top[0]) };
  top.forEach((t, i) => {
    const d = pick === t ? 0 : km(pick, t);
    const s = Math.round(CAPS[i] * falloff(d));
    if (s > best.score) best = { score: s, target: t, km: d };
  });
  return best;
}

export const emoji = (s) => (s >= 95 ? "🎯" : s >= 80 ? "🔥" : s >= 60 ? "🙂" : s >= 30 ? "🤨" : "🥶");

export function formatValue(stat, v) {
  if (v == null) return "no data";
  const n = v.toLocaleString("en-US", { maximumFractionDigits: stat.dec, minimumFractionDigits: stat.dec });
  return `${n} ${stat.unit}`;
}

// ---- storage (best effort; artifact/private mode may throw) ----
const KEY = "globe-stats:v1";
export function load() {
  try { return JSON.parse(localStorage.getItem(KEY)) || { days: {} }; } catch { return { days: {} }; }
}
export function save(state) {
  try { localStorage.setItem(KEY, JSON.stringify(state)); } catch {}
}

export function streaks(state, today) {
  const done = new Set(Object.entries(state.days).filter(([, d]) => d.picks.length === 3).map(([k]) => k));
  const prev = (k) => { const d = new Date(k + "T12:00:00"); d.setDate(d.getDate() - 1); return todayKey(d); };
  let cur = 0, k = done.has(today) ? today : prev(today);
  while (done.has(k)) { cur++; k = prev(k); }
  let max = 0, run = 0;
  [...done].sort().forEach((d, i, arr) => { run = i && prev(d) === arr[i - 1] ? run + 1 : 1; max = Math.max(max, run); });
  return { current: cur, max, played: done.size };
}
