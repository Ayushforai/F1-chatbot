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

export function nextRoundIndex(races) {
  const today = new Date();
  const idx = races.findIndex((race) => {
    const date = parseIsoDate(race.date || race.weekend_end);
    return date && date >= new Date(today.getFullYear(), today.getMonth(), today.getDate());
  });
  return idx === -1 ? Math.max(0, races.length - 1) : idx;
}
