const SECURITY = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Frame-Options": "DENY",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Cache-Control": "public, max-age=300",
};

const TYPES = {
  "index.html": "text/html; charset=utf-8",
  "styles/main.css": "text/css; charset=utf-8",
  "assets/favicon.svg": "image/svg+xml",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname === "www.livingprooflabs.com") {
      url.hostname = "livingprooflabs.com";
      return Response.redirect(url.toString(), 301);
    }

    let path = url.pathname;
    if (path.length > 1 && path.endsWith("/")) path = path.slice(0, -1);

    let key;
    if (path === "/" || path === "/index.html") key = "index.html";
    else if (path === "/styles/main.css") key = "styles/main.css";
    else if (path === "/assets/favicon.svg") key = "assets/favicon.svg";
    else return new Response("Not found", { status: 404, headers: SECURITY });

    const body = await env.SITE.get(key);
    if (body == null) {
      return new Response("Not found", { status: 404, headers: SECURITY });
    }

    return new Response(body, {
      headers: { "Content-Type": TYPES[key], ...SECURITY },
    });
  },
};
