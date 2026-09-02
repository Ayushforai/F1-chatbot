import { useEffect, useRef, useState } from "react";
import { fetchHealth, resetChat, sendMessage } from "../api.js";
import AnswerBody from "./AnswerBody.jsx";

const SUGGESTIONS = [
  "What is the cost cap for 2026?",
  "Results of Monaco GP 2021",
  "Which team did Hamilton drive for in 2012?",
  "What was Verstappen's lap 12 time at Monza 2024?",
];

const CATEGORY_LABELS = {
  quantitative: "Telemetry",
  historical: "Archive",
  sporting: "Sporting",
  technical: "Technical",
  financial: "Financial",
  operational: "Operational",
  general: "General",
  help: "Pit wall",
  error: "Alert",
};

function Message({ role, text, category, citation }) {
  return (
    <article className={`message ${role}`}>
      {role === "assistant" && category ? (
        <div className="meta-row">
          <span className={`badge ${category}`}>{CATEGORY_LABELS[category] || category}</span>
        </div>
      ) : null}
      <div className="bubble">
        {role === "assistant" ? <AnswerBody text={text} /> : text}
      </div>
      {citation ? <div className="citation">Source: {citation}</div> : null}
    </article>
  );
}

export default function Chat({ pendingQuery, onPendingConsumed }) {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState({ ready: false, error: null, model: "" });
  const [banner, setBanner] = useState("Warming telemetry and embedding model…");
  const scroller = useRef(null);
  const input = useRef(null);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const data = await fetchHealth();
        if (cancelled) return;
        setHealth(data);
        if (data.ready) {
          setBanner("Pit wall active");
        } else if (data.error) {
          setBanner(data.error);
        } else {
          setBanner("Warming telemetry and embedding model…");
          setTimeout(poll, 2000);
        }
      } catch (err) {
        if (cancelled) return;
        setHealth({ ready: false, error: err.message, model: "" });
        setBanner("Cannot reach pit wall. Start `python server.py` on port 5001.");
        setTimeout(poll, 3000);
      }
    }
    poll();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  async function submit(text) {
    const query = (text ?? draft).trim();
    if (!query || busy) return;
    setDraft("");
    setMessages((prev) => [...prev, { role: "user", text: query }]);
    setBusy(true);
    try {
      const data = await sendMessage(query);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: data.body || data.answer || "",
          category: data.category,
          citation: data.citation,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: err.message, category: "error" },
      ]);
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  }

  useEffect(() => {
    if (!pendingQuery || !health.ready || busy) return;
    const query = pendingQuery;
    onPendingConsumed?.();
    submit(query);
  }, [pendingQuery, health.ready, busy]);

  async function onReset() {
    if (busy) return;
    try {
      await resetChat();
    } catch {
      /* still clear the local transcript */
    }
    setMessages([]);
    setDraft("");
    input.current?.focus();
  }

  function onKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  const bannerClass = health.ready ? "ready" : health.error ? "error" : "";

  return (
    <div className="chat-shell page-pad">
      <div className={`status-line ${bannerClass}`}>
        {!health.ready && !health.error ? <span className="pulse" /> : null}
        <span>{banner}</span>
      </div>

      {messages.length === 0 ? (
        <div className="suggestions">
          {SUGGESTIONS.map((item) => (
            <button key={item} className="chip" onClick={() => submit(item)} disabled={busy || !health.ready}>
              {item}
            </button>
          ))}
        </div>
      ) : null}

      <div className="transcript" ref={scroller}>
        {messages.length === 0 ? (
          <div className="empty-state">
            <h2>Pit wall radio</h2>
            <p>
              Ask about live telemetry, race results, driver careers, or FIA regulations.
              Follow-ups stay in session — try “who finished second?” after a results query.
            </p>
          </div>
        ) : (
          messages.map((msg, i) => <Message key={i} {...msg} />)
        )}
        {busy ? (
          <article className="message assistant">
            <div className="bubble">
              <div className="typing">
                <span />
                <span />
                <span />
              </div>
            </div>
          </article>
        ) : null}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          ref={input}
          rows={1}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Engineer query…"
          disabled={busy}
        />
        <button className="reset-btn" type="button" onClick={onReset} disabled={busy}>
          Reset
        </button>
        <button className="send-btn" type="submit" disabled={busy || !draft.trim() || !health.ready}>
          Send
        </button>
      </form>
    </div>
  );
}

export function About() {
  const cards = [
    {
      title: "Live & laps",
      body: "OpenF1 telemetry, fastest laps, and specific lap times when a session exists. Live data only while cars are on track.",
    },
    {
      title: "Race archive",
      body: "Full classifications, DNFs, driver-team careers, and lap deltas from historical CSVs plus vector search over race documents.",
    },
    {
      title: "FIA regulations",
      body: "Sporting, technical, financial, operational, and general regulations with article-aware RAG and source citations.",
    },
    {
      title: "Clarifications",
      body: "Asks for season, circuit, or driver when the query is ambiguous — no silent Hamilton default, no guessed Italian GP.",
    },
  ];

  return (
    <div className="about-grid page-pad">
      {cards.map((card) => (
        <article className="about-card" key={card.title}>
          <h3>{card.title}</h3>
          <p>{card.body}</p>
        </article>
      ))}
    </div>
  );
}
