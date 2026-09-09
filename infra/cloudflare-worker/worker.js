/**
 * NexivoReach catalog fetch proxy.
 *
 * Shared hosts (CSF/LFD, Imunify360) firewall-ban Render's egress IPs, which drops
 * catalog scrapes at the TCP layer. This Worker relays those GETs from Cloudflare's
 * network, which hosts almost never block.
 *
 *   Deploy: npx wrangler deploy
 *   Secret: npx wrangler secret put PROXY_TOKEN
 *   Call:   GET https://<worker>.workers.dev/?url=<encoded>  with header X-Proxy-Token
 */

// Keeps the Worker from being used to reach Cloudflare's or a cloud provider's internals.
const BLOCKED_HOST = /^(localhost$|127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|0\.|\[?::1\]?$)/i;

// X-WP-TotalPages drives our REST pagination, so it has to survive the relay.
const PASS_THROUGH = ["content-type", "x-wp-total", "x-wp-totalpages", "link"];

const BROWSER_HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  Accept: "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
  "Accept-Language": "en-US,en;q=0.9",
};

export default {
  async fetch(request, env) {
    if (request.method !== "GET") {
      return new Response("Only GET is supported", { status: 405 });
    }

    if (env.PROXY_TOKEN && request.headers.get("X-Proxy-Token") !== env.PROXY_TOKEN) {
      return new Response("Forbidden", { status: 403 });
    }

    const target = new URL(request.url).searchParams.get("url");
    if (!target) {
      return new Response("Missing ?url=", { status: 400 });
    }

    let parsed;
    try {
      parsed = new URL(target);
    } catch {
      return new Response("Malformed ?url=", { status: 400 });
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return new Response("Only http/https targets", { status: 400 });
    }
    if (BLOCKED_HOST.test(parsed.hostname)) {
      return new Response("Blocked host", { status: 403 });
    }

    let upstream;
    try {
      upstream = await fetch(parsed.toString(), {
        redirect: "follow",
        headers: BROWSER_HEADERS,
      });
    } catch (err) {
      return new Response(`Upstream fetch failed: ${err}`, { status: 502 });
    }

    const headers = new Headers();
    for (const name of PASS_THROUGH) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    headers.set("X-Proxy-Final-Url", upstream.url);

    return new Response(upstream.body, { status: upstream.status, headers });
  },
};
