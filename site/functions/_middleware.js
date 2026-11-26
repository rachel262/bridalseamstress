// Send anyone on the bridalseamstress.pages.dev address (or a preview deploy) to the real domain,
// so Google and AI tools only ever see and link bridalseamstress.com.au.
export async function onRequest({ request, next }) {
  const url = new URL(request.url);
  if (url.hostname.endsWith(".pages.dev") && (request.method === "GET" || request.method === "HEAD")) {
    url.hostname = "bridalseamstress.com.au";
    url.protocol = "https:";
    url.port = "";
    return Response.redirect(url.toString(), 301);
  }
  return next();
}
