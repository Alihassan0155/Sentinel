import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
const allowed = new Set(["auth", "watches", "changes", "profile", "actions", "notifications", "digests", "memory"]);
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (!allowed.has(path[0]) || path.some(part => !/^[a-zA-Z0-9_-]+$/.test(part))) {
    return Response.json({ detail: "Not found" }, { status: 404 });
  }
  if (!["GET", "HEAD"].includes(request.method)) {
    const origin = request.headers.get("origin");
    let sameHost = false;
    try { sameHost = !!origin && new URL(origin).host === request.headers.get("host") && new URL(origin).origin === origin; } catch { /* Invalid Origin */ }
    if (!sameHost || request.headers.get("X-Sentinel-CSRF") !== "1") {
      return Response.json({ detail: "Untrusted request" }, { status: 403 });
    }
  }
  const headers = new Headers({ "X-Sentinel-CSRF": "1" });
  for (const name of ["cookie", "content-type", "origin"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const base = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
    const upstream = await fetch(`${base}/${path.join("/")}${request.nextUrl.search}`, {
      method: request.method, headers, cache: "no-store", redirect: "manual",
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.text(),
      signal: AbortSignal.timeout(60000),
    });
    const outgoing = new Headers({ "Cache-Control": "no-store" });
    outgoing.set("Content-Type", upstream.headers.get("content-type") || "application/json");
    for (const cookie of upstream.headers.getSetCookie()) outgoing.append("Set-Cookie", cookie);
    return new Response(upstream.body, { status: upstream.status, headers: outgoing });
  } catch {
    return Response.json({ detail: "The backend is unavailable. Check that the API and database are running." }, { status: 502 });
  }
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
