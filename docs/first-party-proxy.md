# First-party tracker proxy

Ad-blockers don't block *analytics* — they block *third-party analytics
domains and known script URLs*. AgentLens defeats both by serving the tracker
script and the ingest endpoint from **your own domain**: to a blocker,
`your-domain.com/al/ingest` is indistinguishable from your own API.

Without this, expect 20–50% of client-side events to never arrive (blocker
usage varies by audience — tech audiences are the worst). Server-side
`POST /api/v1/ingest` is unaffected either way; the proxy is for the browser
snippet.

## How it works

The snippet already supports first-party paths — no tracker changes needed:

```html
<script defer src="https://your-domain.com/al/script.js"
  data-api="https://your-domain.com/al/ingest"
  data-key="alw_YOUR_WRITE_KEY"></script>
```

You proxy two paths on your domain to the AgentLens API:

| Your path            | → AgentLens API             |
|----------------------|-----------------------------|
| `/al/script.js`      | `/static/agentlens.js`      |
| `/al/ingest` (+ ping)| `/api/v1/ingest` (+ `/ping`) |

## Verify before you ship

```bash
curl https://your-domain.com/al/ingest/ping
# {"ok":true,"service":"agentlens-ingest","version":"0.1.0"}
```

A 200 here proves the proxy path works end-to-end. Then load your site and
watch events arrive on the dashboard's Realtime page.

## Configs

Replace `api.yourhost.com` with wherever your AgentLens API runs
(`localhost:8000` for local dev).

### nginx

```nginx
# tracker script
location = /al/script.js {
    proxy_pass http://api.yourhost.com/static/agentlens.js;
}
# ingest (+ /al/ingest/ping for verification)
location /al/ {
    proxy_pass http://api.yourhost.com/api/v1/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

### Caddy

```caddy
your-domain.com {
    handle /al/script.js {
        reverse_proxy api.yourhost.com {
            rewrite /static/agentlens.js
        }
    }
    handle /al/* {
        uri strip_prefix /al
        uri prefix /api/v1
        reverse_proxy api.yourhost.com
    }
    handle {
        # ... your normal site
    }
}
```

### Next.js (`next.config.js`)

```js
/** @type {import('next').NextConfig} */
module.exports = {
  async rewrites() {
    const api = 'https://api.yourhost.com';
    return [
      { source: '/al/script.js', destination: `${api}/static/agentlens.js` },
      { source: '/al/ingest', destination: `${api}/api/v1/ingest` },
      { source: '/al/ingest/ping', destination: `${api}/api/v1/ingest/ping` },
    ];
  },
};
```

### Vercel (`vercel.json`)

```json
{
  "rewrites": [
    { "source": "/al/script.js", "destination": "https://api.yourhost.com/static/agentlens.js" },
    { "source": "/al/ingest", "destination": "https://api.yourhost.com/api/v1/ingest" },
    { "source": "/al/ingest/ping", "destination": "https://api.yourhost.com/api/v1/ingest/ping" }
  ]
}
```

### Cloudflare Worker

```js
const API = 'https://api.yourhost.com';
export default {
  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === '/al/script.js')
      return fetch(API + '/static/agentlens.js');
    if (url.pathname.startsWith('/al/'))
      return fetch(API + '/api/v1/' + url.pathname.slice(4) + url.search, {
        method: req.method,
        headers: req.headers,
        body: req.body,
      });
    return fetch(req);
  },
};
```

## Troubleshooting

- **Ping 404s**: your proxy isn't stripping/adding prefixes correctly — check that `/al/ingest/ping` reaches `/api/v1/ingest/ping` (note the trailing slash in the nginx `proxy_pass`).
- **Ping works but no events**: check the `data-key` (write key, `alw_…`) and the browser console for CORS errors. The ingest endpoint accepts your write key from any origin; if you lock down `cors_origins`, add your domain.
- **Script 404s**: `/al/script.js` must serve the built tracker (`/static/agentlens.js` on the API). Rebuild it with `npm run build` in `packages/tracker` if missing.
- **Still seeing blocked requests**: some aggressive blockers filter by script *content* signatures. Renaming the path (e.g. `/al/a.js`) is the next step — the mapping is arbitrary as long as snippet and proxy agree.
