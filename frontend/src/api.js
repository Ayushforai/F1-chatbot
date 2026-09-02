const SESSION_KEY = "f1-pit-wall-session";

function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export function newSessionId() {
  const id = crypto.randomUUID();
  localStorage.setItem(SESSION_KEY, id);
  return id;
}

async function parseError(response) {
  try {
    const data = await response.json();
    return data.error || `Radio failed (${response.status})`;
  } catch {
    return `Radio failed (${response.status})`;
  }
}

export async function fetchHealth() {
  const response = await fetch("/api/health");
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}

export async function sendMessage(message) {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: getSessionId(),
    }),
  });
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  const data = await response.json();
  if (data.session_id) {
    localStorage.setItem(SESSION_KEY, data.session_id);
  }
  return data;
}

export async function resetChat() {
  const sessionId = getSessionId();
  await fetch("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  return newSessionId();
}

export async function fetchCalendar(year) {
  const query = year ? `?year=${year}` : "";
  const response = await fetch(`/api/calendar${query}`);
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
}
