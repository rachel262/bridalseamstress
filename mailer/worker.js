// bridalseamstress-mailer: only reachable from the Pages site through a service binding
// (no workers.dev or custom route). Turns a form submission into an email to Rachel.
import { EmailMessage } from "cloudflare:email";

const FROM = "listings@bridalseamstress.com.au";

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("Not found", { status: 404 });
    const d = await request.json();
    const clean = (v) => String(v || "").replace(/[\r\n]+/g, " ").slice(0, 300);
    const to = env.TO_ADDRESS;
    const body = Object.entries(d).map(([k, v]) => `${k}: ${v}`).join("\n");
    const raw = [
      `From: Bridal Seamstress <${FROM}>`, `To: ${to}`, `Reply-To: ${clean(d.email)}`,
      `Subject: ${clean(d.request)}: ${clean(d.business)}`,
      `Message-ID: <${crypto.randomUUID()}@bridalseamstress.com.au>`,
      `Date: ${new Date().toUTCString()}`, "MIME-Version: 1.0", "Content-Type: text/plain; charset=utf-8", "", body,
    ].join("\r\n");
    await env.CLAIMS.send(new EmailMessage(FROM, to, raw));
    return new Response("ok");
  },
};
