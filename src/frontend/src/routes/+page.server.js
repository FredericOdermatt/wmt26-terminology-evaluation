export async function load({ fetch }) {
  const response = await fetch("/api/v1/leaderboard");
  return { leaderboard: response.ok ? await response.json() : [] };
}
