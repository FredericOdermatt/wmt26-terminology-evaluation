import { env } from "$env/dynamic/private";

const BACKEND = env.BACKEND_URL ?? "http://localhost:8000";

// BFF proxy: the browser only talks same-origin; the backend URL and the
// docker network stay server-side.
async function proxy({ params, request, url }) {
  const headers = new Headers();
  for (const name of ["authorization", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const forwarded = request.headers.get("x-forwarded-for") ?? "";
  headers.set("x-forwarded-for", forwarded);
  const response = await fetch(`${BACKEND}/${params.path}${url.search}`, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
    duplex: "half",
  });
  return new Response(response.body, {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}

export const GET = proxy;
export const POST = proxy;
