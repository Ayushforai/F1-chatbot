import { useState } from "react";
import TopNav, { Hero, RaceBar } from "./components/Chrome.jsx";
import Chat, { About } from "./components/Chat.jsx";
import Calendar from "./components/Calendar.jsx";
import Footer from "./components/Footer.jsx";
import { resetChat } from "./api.js";
import "./App.css";

export default function App() {
  const [tab, setTab] = useState("chat");
  const [chatKey, setChatKey] = useState(0);
  const [pendingQuery, setPendingQuery] = useState(null);
  const [seasonYear, setSeasonYear] = useState(2026);

  async function handleReset() {
    try {
      await resetChat();
    } catch {
      /* still clear the local transcript */
    }
    setChatKey((k) => k + 1);
    setPendingQuery(null);
    setTab("chat");
  }

  function askAboutRace(query) {
    setPendingQuery(query);
    setTab("chat");
  }

  return (
    <div className="app">
      <TopNav tab={tab} onTab={setTab} onReset={handleReset} />
      <RaceBar onOpenSchedule={() => setTab("schedule")} onSeasonYear={setSeasonYear} />
      <div className="main-stage">
        <Hero tab={tab} onTab={setTab} year={seasonYear} />
        {tab === "chat" ? (
          <div className="stage-panel" key={`chat-${chatKey}`}>
            <Chat
              pendingQuery={pendingQuery}
              onPendingConsumed={() => setPendingQuery(null)}
            />
          </div>
        ) : null}
        {tab === "schedule" ? (
          <div className="stage-panel" key="schedule">
            <Calendar onAsk={askAboutRace} />
          </div>
        ) : null}
        {tab === "about" ? (
          <div className="stage-panel" key="about">
            <About />
          </div>
        ) : null}
      </div>
      <Footer />
    </div>
  );
}
