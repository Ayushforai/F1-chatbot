export function parseIsoDate(iso) {
  if (!iso) return null;
  const date = new Date(`${iso}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatWeekend(startIso, endIso) {
  const start = parseIsoDate(startIso) || parseIsoDate(endIso);
  const end = parseIsoDate(endIso) || start;
  if (!start || !end) return "";
  const startDay = String(start.getDate()).padStart(2, "0");
  const endDay = String(end.getDate()).padStart(2, "0");
  const startMon = start.toLocaleDateString("en-GB", { month: "short" }).toUpperCase();
  const endMon = end.toLocaleDateString("en-GB", { month: "short" }).toUpperCase();
  if (startMon === endMon && start.getFullYear() === end.getFullYear()) {
    if (startDay === endDay) return `${endDay} ${endMon}`;
    return `${startDay} - ${endDay} ${endMon}`;
  }
  return `${startDay} ${startMon} - ${endDay} ${endMon}`;
}

export function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/** Index of the upcoming round: stays on race day until the main race date has passed. */
export function nextRoundIndex(races, now = new Date()) {
  const today = startOfDay(now);
  const idx = races.findIndex((race) => {
    const raceDay = parseIsoDate(race.date) || parseIsoDate(race.weekend_end);
    return raceDay && raceDay >= today;
  });
  return idx === -1 ? Math.max(0, races.length - 1) : idx;
}
