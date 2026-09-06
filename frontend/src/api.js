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
  if (response.status === 502) {
    return "Pit wall is waking up — the server cold-started and timed out. Retrying…";
  }
  try {
    const data = await response.json();
    return data.error || `Radio failed (${response.status})`;
  } catch {
    return `Radio failed (${response.status})`;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const CHAT_TIMEOUT_MS = 90_000;
const CHAT_RETRY_STATUSES = new Set([502, 503, 504]);
const CHAT_MAX_ATTEMPTS = 3;
const CHAT_RETRY_DELAY_MS = 4000;

async function postChat(message, signal) {
  return fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: getSessionId(),
    }),
    signal,
  });
}

export async function sendMessage(message) {
  let lastError = "Radio failed.";

  for (let attempt = 1; attempt <= CHAT_MAX_ATTEMPTS; attempt += 1) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
    let response;
    try {
      response = await postChat(message, controller.signal);
    } catch (err) {
      lastError =
        err.name === "AbortError"
          ? "Pit wall timed out while waking up. Trying again…"
          : err.message || lastError;
      if (attempt < CHAT_MAX_ATTEMPTS) {
        await sleep(CHAT_RETRY_DELAY_MS);
        continue;
      }
      throw new Error(
        "Pit wall could not connect. Render free tier sleeps after inactivity — refresh the page and try again."
      );
    } finally {
      clearTimeout(timeoutId);
    }

    if (response.ok) {
      const data = await response.json();
      if (data.session_id) {
        localStorage.setItem(SESSION_KEY, data.session_id);
      }
      return data;
    }

    lastError = await parseError(response);
    if (CHAT_RETRY_STATUSES.has(response.status) && attempt < CHAT_MAX_ATTEMPTS) {
      await sleep(CHAT_RETRY_DELAY_MS);
      continue;
    }
    throw new Error(lastError.replace(/Retrying…$/, "Send again in a few seconds."));
  }

  throw new Error(lastError);
}

export async function fetchHealth() {
  const response = await fetch("/api/health");
  if (!response.ok) {
    throw new Error(await parseError(response));
  }
  return response.json();
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
