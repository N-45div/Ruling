// Small client for the desk API.

export async function get(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status} ${await res.text()}`);
  return res.json();
}

// Follow a server-sent event stream; returns a function that stops following.
export function follow(path, onEvent) {
  const source = new EventSource(path);
  source.onmessage = (message) => onEvent(JSON.parse(message.data));
  return () => source.close();
}

export const params = new URLSearchParams(location.search);
