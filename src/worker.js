export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.hostname === "www.livingprooflabs.com") {
      url.hostname = "livingprooflabs.com";
      url.protocol = "https:";
      return Response.redirect(url.toString(), 301);
    }

    const path = url.pathname === "/" ? "/" : url.pathname;
    const target = new URL(`https://living-proof-labs.github.io/website${path}`);
    target.search = url.search;

    const origin = await fetch(target, {
      method: request.method,
      redirect: "follow",
      headers: {
        Accept: request.headers.get("Accept") || "*/*",
        "User-Agent": request.headers.get("User-Agent") || "LivingProofLabs",
      },
    });

    const headers = new Headers(origin.headers);
    headers.delete("content-security-policy");
    headers.set("strict-transport-security", "max-age=31536000");
    return new Response(origin.body, {
      status: origin.status,
      headers,
    });
  },
};
