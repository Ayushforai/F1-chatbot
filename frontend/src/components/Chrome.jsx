import { useEffect, useState } from "react";
import { fetchCalendarWithFallback } from "../api.js";
import { formatWeekend, nextRoundIndex } from "../calendarUi.js";
import { CountryFlag } from "../flags.jsx";
import rcLogo from "../assets/rc-logo.png";
import racecoeLogo from "../assets/racecoe-logo.png";

export function F1Mark() {
  return <img className="f1-mark" src={rcLogo} alt="" aria-hidden="true" />;
}

const NAV_ITEMS = ["Schedule", "Results", "Standings", "Drivers", "Teams"];

export default function TopNav({ tab, onTab, onReset }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <header className="top-nav">
        <button className="brand" onClick={() => onTab("chat")} aria-label="Racecoe home">
          <F1Mark />
        </button>
        <nav className="nav-links">
          {NAV_ITEMS.map((item) => (
            <a
              key={item}
              href="#chat"
              className={item === "Schedule" && tab === "schedule" ? "active" : ""}
              onClick={(e) => {
                e.preventDefault();
                onTab(item === "Schedule" ? "schedule" : "chat");
              }}
            >
              {item}
            </a>
          ))}
          <button
            className={`nav-link ${tab === "chat" ? "active" : ""}`}
            onClick={() => onTab("chat")}
          >
            Pit Wall
          </button>
        </nav>
        <div className="nav-right">
          <button className="icon-btn" onClick={onReset} title="New session" aria-label="New session">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12a9 9 0 1 0 3-6.7" />
              <path d="M3 4v5h5" />
            </svg>
          </button>
          <button
            className="icon-btn"
            onClick={() => setOpen((v) => !v)}
            aria-label="Open menu"
          >
            <span className="hamburger">
              <span />
              <span />
              <span />
            </span>
          </button>
        </div>
      </header>
      <div className={`mobile-menu ${open ? "open" : ""}`}>
        {NAV_ITEMS.map((item) => (
          <button
            key={item}
            onClick={() => {
              setOpen(false);
              onTab(item === "Schedule" ? "schedule" : "chat");
            }}
          >
            {item}
          </button>
        ))}
        <button
          onClick={() => {
            setOpen(false);
            onTab("chat");
          }}
        >
          Pit Wall
        </button>
        <button
          onClick={() => {
            setOpen(false);
            onTab("about");
          }}
        >
          About
        </button>
      </div>
    </>
  );
}

function formatClock(date) {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function RaceBar({ onOpenSchedule, onSeasonYear }) {
  const [now, setNow] = useState(new Date());
  const [races, setRaces] = useState([]);
  const [year, setYear] = useState(null);
  const [index, setIndex] = useState(0);
  const [dir, setDir] = useState(1);

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const data = await fetchCalendarWithFallback();
      if (cancelled || !data.races?.length) return;
      setRaces(data.races);
      setYear(data.year);
      setIndex(nextRoundIndex(data.races));
      onSeasonYear?.(data.year);
    }
    load().catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [onSeasonYear]);

  function step(delta) {
    if (!races.length) return;
    setDir(delta);
    setIndex((current) => (current + delta + races.length) % races.length);
  }

  const race = races[index];

  return (
    <div className="race-bar">
      <div className="race-left">
        <button
          type="button"
          className="round-arrow"
          onClick={() => step(-1)}
          disabled={!races.length}
          aria-label="Previous round"
        >
          ‹
        </button>
        {race ? (
          <button
            type="button"
            className={`race-slide ${dir >= 0 ? "from-right" : "from-left"}`}
            key={`${year}-${race.round}-${race.name}`}
            onClick={onOpenSchedule}
          >
            <span className="race-meta">
              R{race.round} | {formatWeekend(race.weekend_start, race.weekend_end || race.date)}
            </span>
            <CountryFlag country={race.country} />
            <span className="gp-link">
              {race.country || race.location || race.name}
            </span>
          </button>
        ) : (
          <span className="race-meta">Loading calendar…</span>
        )}
        <button
          type="button"
          className="round-arrow next"
          onClick={() => step(1)}
          disabled={!races.length}
          aria-label="Next round"
        >
          ›
        </button>
      </div>
      <div className="race-right">
        <div className="clock-block">
          <span>
            Local time <b>{formatClock(now)}</b>
          </span>
          <span className="clock-icon" aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}

export function Hero({ tab, onTab, year }) {
  return (
    <section className="hero page-pad">
      <div className="speed-lines" />
      <h1>
        <img className="hero-logo" src={racecoeLogo} alt="Racecoe" />
      </h1>
      <p className="hero-tagline">Hybrid Formula 1 chatbot: Live telemetry, race history, and FIA regulations</p>
      <div className="tabs">
        <button className={tab === "chat" ? "active" : ""} onClick={() => onTab("chat")}>
          Chat
        </button>
        <button className={tab === "schedule" ? "active" : ""} onClick={() => onTab("schedule")}>
          Schedule
        </button>
        <button className={tab === "about" ? "active" : ""} onClick={() => onTab("about")}>
          About
        </button>
      </div>
    </section>
  );
}
