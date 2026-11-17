import { useMemo, useRef, useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { ChoroplethGlobe } from "@lachlanjc/chlobe";
import {
  PICKABLE, statById, nameOf, todayKey, dayNumber, promptsFor, ranked, score, emoji, formatValue, load, save, streaks,
} from "./game.js";
import "./style.css";

const GUESS_COLORS = { filled: [[203, 213, 225], [234, 88, 12]], missing: [148, 163, 184], missingAlpha: 0.3 };
const REVEAL_COLORS = { filled: [[219, 234, 254], [29, 78, 216]], missing: [148, 163, 184], missingAlpha: 0.3 };
const km = (d) => `${Math.round(d).toLocaleString()} km`;

// chlobe has no click event: turn a short tap into a synthetic pointermove so its hit-test reports the country.
function useTap(wrapRef, onTap) {
  const hover = useRef(null);
  const cb = useRef(onTap);
  cb.current = onTap;
  useEffect(() => {
    const el = wrapRef.current;
    let down = null;
    const pd = (e) => (down = { x: e.clientX, y: e.clientY });
    const pu = (e) => {
      if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6) return;
      const canvas = el.querySelector("canvas");
      setTimeout(() => {
        hover.current = null;
        canvas?.dispatchEvent(new PointerEvent("pointermove", { clientX: e.clientX, clientY: e.clientY, bubbles: true }));
        if (hover.current) cb.current(hover.current);
      }, 0);
    };
    el.addEventListener("pointerdown", pd, true);
    el.addEventListener("pointerup", pu, true);
    return () => { el.removeEventListener("pointerdown", pd, true); el.removeEventListener("pointerup", pu, true); };
  }, [wrapRef]);
  return (a) => (hover.current = a);
}

function Globe({ data, colors, active, onTap, tip }) {
  const wrap = useRef(null);
  const onHover = useTap(wrap, onTap);
  return (
    <div ref={wrap} className="globe">
      <ChoroplethGlobe
        aria-label="World globe"
        data={data}
        colors={colors}
        activeEntryId={active}
        globe={{ autoRotate: !active }}
        onCountryHover={onHover}
        renderTooltip={(t) => <div className="tip" style={{ left: t.x, top: t.y }}>{tip(t.alpha2)}</div>}
      />
    </div>
  );
}

function Results({ day, prompts, entry, stats }) {
  const [copied, setCopied] = useState(false);
  const total = entry.scores.reduce((s, r) => s + r.score, 0);
  const date = new Date(day + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const share = `Globe Stats #${dayNumber(day)} · ${date}\n${entry.scores.map((r) => `${r.score}${emoji(r.score)}`).join(" ")}\nTotal: ${total}/300`;
  return (
    <div className="card">
      <div className="big">{total}<small>/300</small></div>
      {prompts.map((p, k) => (
        <div key={p.id} className="res">
          <div className="muted small-l">The {p.label}</div>
          <div className="row">
            <span>You: {nameOf(entry.picks[k])} · Answer: {nameOf(p.top[0])}</span>
            <b>{entry.scores[k].score}{emoji(entry.scores[k].score)}</b>
          </div>
        </div>
      ))}
      <pre>{share}</pre>
      <button onClick={() => navigator.clipboard?.writeText(share).then(() => setCopied(true)).catch(() => {})}>
        {copied ? "Copied" : "Copy result"}
      </button>
      <div className="stats">
        <div><b>{stats.played}</b><span>played</span></div>
        <div><b>{stats.current}</b><span>streak</span></div>
        <div><b>{stats.max}</b><span>best streak</span></div>
      </div>
      <p className="muted center">New stats tomorrow.</p>
    </div>
  );
}

function App() {
  const day = todayKey();
  const prompts = useMemo(() => promptsFor(day), [day]);
  const [state, setState] = useState(load);
  const entry = state.days[day] || { picks: [], scores: [] };
  const [pick, setPick] = useState(null);
  const [revealed, setRevealed] = useState(false);

  const i = revealed ? entry.picks.length - 1 : entry.picks.length;
  const done = entry.picks.length === 3 && !revealed;
  const prompt = prompts[Math.min(i, 2)];
  const stat = statById[prompt.stat];
  const order = useMemo(() => ranked(prompt), [prompt]);

  // chlobe centers on data[0] when nothing is active, so start each round at a random country.
  const offset = useMemo(() => Math.floor(Math.random() * PICKABLE.length), [i]);
  const guessData = useMemo(
    () => [...PICKABLE.slice(offset), ...PICKABLE.slice(0, offset)].map((a) => ({ alpha2: a, value: a === pick ? 1 : 0 })),
    [pick, offset]
  );
  const revealData = useMemo(() => {
    const t = (v) => (stat.log ? Math.log1p(Math.max(0, v)) : v);
    const ts = order.map(([, v]) => t(v));
    const lo = Math.min(...ts), hi = Math.max(...ts);
    // chlobe shades by |value|: map so darker = closer to the answer end.
    return order.map(([a, v]) => ({ alpha2: a, value: (prompt.dir === "most" ? t(v) - lo : hi - t(v)) + 1e-3 }));
  }, [order, stat, prompt]);

  const update = (fn) => setState((s) => { const n = fn(structuredClone(s)); save(n); return n; });

  const lockIn = () => {
    const result = score(pick, prompt);
    update((s) => {
      const e = s.days[day] || { picks: [], scores: [] };
      e.picks.push(pick); e.scores.push(result);
      s.days[day] = e;
      return s;
    });
    setRevealed(true);
  };
  const next = () => { setPick(null); setRevealed(false); };

  const total = entry.scores.reduce((s, r) => s + r.score, 0);
  const header = (
    <header>
      <h1>Globe Stats <span className="muted">#{dayNumber(day)}</span></h1>
      {!done && <span className="muted">Round {i + 1}/3 · {total} pts</span>}
    </header>
  );

  if (done) {
    return <main>{header}<Results day={day} prompts={prompts} entry={entry} stats={streaks(state, day)} /></main>;
  }

  const last = revealed ? entry.scores[i] : null;
  const myPick = revealed ? entry.picks[i] : pick;
  const rankOf = (a) => order.findIndex(([c]) => c === a);

  return (
    <main>
      {header}
      <p className="prompt">Tap the country with the <b>{prompt.label}</b></p>

      <Globe
        data={revealed ? revealData : guessData}
        colors={revealed ? REVEAL_COLORS : GUESS_COLORS}
        active={revealed ? prompt.top[0] : pick}
        onTap={(a) => !revealed && setPick(a)}
        tip={(a) => (revealed ? `${nameOf(a)} · ${formatValue(stat, stat.values[a])}` : nameOf(a))}
      />

      <div className="card">
        {!revealed ? (
          <>
            <div className="row"><span>{pick ? nameOf(pick) : "Drag to spin, tap a country"}</span></div>
            <button disabled={!pick} onClick={lockIn}>Lock in</button>
          </>
        ) : (
          <>
            <div className="row">
              <span>
                {myPick === last.target
                  ? <>Spot on: {nameOf(myPick)}</>
                  : <>{nameOf(myPick)} is {km(last.km)} from {nameOf(last.target)}</>}
              </span>
              <b>{last.score} {emoji(last.score)}</b>
            </div>
            <div className="muted small-l">
              {nameOf(myPick)}: {stat.values[myPick] == null ? "no data" : `#${rankOf(myPick) + 1} of ${order.length} · ${formatValue(stat, stat.values[myPick])}`}
            </div>
            <ol>
              {order.slice(0, 3).map(([a, v]) => <li key={a}>{nameOf(a)} — {formatValue(stat, v)}</li>)}
            </ol>
            <p className="muted small-l">
              Darker = closer to the answer. Source: <a href={stat.url} target="_blank" rel="noreferrer">{stat.source}</a>, {stat.year}
            </p>
            <button onClick={next}>{i === 2 ? "See results" : "Next"}</button>
          </>
        )}
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
