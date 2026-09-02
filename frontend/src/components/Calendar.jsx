import { useEffect, useState } from "react";
import { fetchCalendar } from "../api.js";
import { CountryFlag } from "../flags.jsx";

function formatRaceDate(iso) {
  if (!iso) return "";
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function raceStatus(iso) {
  if (!iso) return "scheduled";
  const raceDay = new Date(`${iso}T23:59:59`);
  return raceDay < new Date() ? "complete" : "upcoming";
}

export default function Calendar({ onAsk }) {
  const [year, setYear] = useState(null);
  const [years, setYears] = useState([]);
  const [races, setRaces] = useState([]);
  const [source, setSource] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const data = await fetchCalendar(year);
        if (cancelled) return;
        setYears(data.years || []);
        setRaces(data.races || []);
        setSource(data.source);
        if (year == null && data.year) setYear(data.year);
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [year]);

  return (
    <div className="calendar-shell page-pad">
      <div className="calendar-toolbar">
        <label>
          Season
          <select
            value={year ?? ""}
            onChange={(event) => setYear(Number(event.target.value))}
          >
            {years.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        {source ? (
          <span className="calendar-source">
            {source === "csv" ? "Historical CSV" : "OpenF1 meetings"}
          </span>
        ) : null}
      </div>

      {loading ? <p className="calendar-status">Loading calendar…</p> : null}
      {error ? <p className="calendar-status error">{error}</p> : null}
      {!loading && !error && races.length === 0 ? (
        <p className="calendar-status">No races published for this season yet.</p>
      ) : null}

      <ol className="calendar-list">
        {races.map((race, i) => {
          const status = raceStatus(race.date);
          return (
            <li key={`${race.round}-${race.name}`} style={{ animationDelay: `${i * 35}ms` }}>
              <button
                type="button"
                className={`calendar-row ${status}`}
                onClick={() =>
                  onAsk(`Results of ${race.name.replace(/ Grand Prix$/i, " GP")} ${year}`)
                }
              >
                <span className="round">R{race.round}</span>
                <CountryFlag country={race.country} />
                <span className="race-copy">
                  <strong>{race.name}</strong>
                  <em>
                    {[race.circuit, race.location, race.country].filter(Boolean).join(" · ")}
                  </em>
                </span>
                <span className="race-when">
                  <b>{formatRaceDate(race.date)}</b>
                  <span className={`race-flag ${status}`}>
                    {status === "complete" ? "Complete" : "Upcoming"}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
