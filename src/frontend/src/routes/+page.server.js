export async function load({ fetch }) {
  const [leaderboard, meta] = await Promise.all([
    fetch("/api/v1/leaderboard").then((r) => (r.ok ? r.json() : [])),
    fetch("/api/v1/meta").then((r) => (r.ok ? r.json() : { track_directions: { 1: [], 2: [] } })),
  ]);
  return { leaderboard, meta };
}
