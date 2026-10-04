# First-party collection

Serve the tracker and ingestion through your own HTTPS origin when desired. Example Nginx routes; replace the upstream with your installation:

```nginx
location = /analytics/script.js {
    proxy_pass http://127.0.0.1:8000/static/metricairn.js;
}
location = /analytics/events {
    client_max_body_size 1m;
    proxy_pass http://127.0.0.1:8000/api/v1/ingest;
}
```

```html
<script defer src="/analytics/script.js"
  data-api="/analytics/events" data-key="alw_YOUR_TRACKING_KEY"></script>
```

Allow these paths in your site’s content security policy. Verify the script loads and a pageview arrives in the dashboard. Avoid caching ingestion responses or logging credential-bearing query parameters. Preserve POST bodies/headers; do not proxy management endpoints publicly. First-party routing does not override consent, DNT/GPC, or guarantee collection past blockers.
