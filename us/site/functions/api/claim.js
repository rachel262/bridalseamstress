// US site copy (us/site). Same as site/functions/api/claim.js, but marks each request "USA" so Rachel can tell them apart.
// Cloudflare Pages Function: receives the claim / add / featured / fix form.
// Every request is saved in the CLAIMS_KV namespace, then passed to the
// bridalseamstress-mailer Worker (service binding MAILER), which emails it to Rachel.
const LABELS = { claim: "Claim listing", add: "Add business", featured: "Featured spot", fix: "Fix or remove" };

export async function onRequestPost({ request, env }) {
  const f = await request.formData();
  if (f.get("website_url")) return Response.redirect(new URL("/thanks/", request.url), 303); // bot trap
  const get = (k) => String(f.get(k) || "").slice(0, 2000).replace(/[\r\n]+/g, k === "services" ? "\n" : " ").trim();
  const d = {
    request: "USA " + (LABELS[get("request")] || "Claim listing"),
    business: get("business"), name: get("name"), email: get("email"), town: get("town"),
    services: get("services"), lead_time: get("lead_time"), photos: get("photos"), updates: get("updates") === "yes" ? "yes" : "no", listing: get("listing"),
    at: new Date().toISOString(),
  };
  if (!d.business || !d.name || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(d.email)) {
    return new Response("Please go back and fill in your business name, your name and a valid email.", { status: 400 });
  }
  // Ignore repeat submits (double clicks) of the same request within 2 minutes.
  const dupKey = `recent:${d.email.toLowerCase()}:${d.business.toLowerCase()}:${d.request}`.slice(0, 480);
  if (env.CLAIMS_KV) {
    if (await env.CLAIMS_KV.get(dupKey)) return Response.redirect(new URL("/thanks/", request.url), 303);
    await env.CLAIMS_KV.put(dupKey, "1", { expirationTtl: 120 });
  }
  const key = `us-${d.at}-${crypto.randomUUID()}`;
  if (env.CLAIMS_KV) await env.CLAIMS_KV.put(key, JSON.stringify(d));
  if (env.MAILER) {
    try {
      const r = await env.MAILER.fetch("https://mailer/send", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(d) });
      if (!r.ok && env.CLAIMS_KV) await env.CLAIMS_KV.put(`unsent-${key}`, String(r.status));
    } catch (err) {
      if (env.CLAIMS_KV) await env.CLAIMS_KV.put(`unsent-${key}`, String(err));
    }
  }
  return Response.redirect(new URL("/thanks/", request.url), 303);
}
