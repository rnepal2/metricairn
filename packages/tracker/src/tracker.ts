/**
 * AgentLens tracker — privacy-friendly, cookieless, <4KB minified.
 *
 * Usage (drop into <head>):
 *   <script defer src="https://cdn.agentlens.dev/agentlens.js"
 *           data-api="https://api.agentlens.dev/api/v1/ingest"
 *           data-key="alw_..."></script>
 *   <script>agentlens.event('signup', { plan: 'pro' })</script>
 *   <script>agentlens.revenue(49, { currency: 'USD' })</script>
 *
 * No cookies. Visitor identity is a random ID in localStorage (user can clear it).
 * Sessions expire after 30 minutes of inactivity.
 */
(function () {
  type Props = Record<string, string | number | boolean>;

  interface QueuedEvent {
    name: string;
    url: string;
    referrer: string;
    session_id: string;
    visitor_id: string;
    device: string;
    browser: string;
    os: string;
    props: Props;
    revenue_amount: number;
    revenue_currency: string;
    at: string;
  }

  const SCRIPT = document.currentScript as HTMLScriptElement | null;
  const API = SCRIPT?.dataset.api || (window as any).__AGENTLENS_API__ || "";
  const KEY = SCRIPT?.dataset.key || (window as any).__AGENTLENS_KEY__ || "";
  const SESSION_TTL_MS = 30 * 60 * 1000;

  function rand(): string {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function stored(k: string): string | null {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  }

  function store(k: string, v: string): void {
    try {
      localStorage.setItem(k, v);
    } catch {
      /* private mode — tracking still works per page load */
    }
  }

  function visitorId(): string {
    let id = stored("al_vid");
    if (!id) {
      id = rand();
      store("al_vid", id);
    }
    return id;
  }

  function sessionId(): { id: string; isNew: boolean } {
    const now = Date.now();
    const raw = stored("al_sid");
    if (raw) {
      try {
        const [id, ts] = JSON.parse(raw) as [string, number];
        if (now - ts < SESSION_TTL_MS) {
          store("al_sid", JSON.stringify([id, now]));
          return { id, isNew: false };
        }
      } catch {
        /* fall through */
      }
    }
    const id = rand();
    store("al_sid", JSON.stringify([id, now]));
    return { id, isNew: true };
  }

  // UTM params are landing attributes: capture them once per session and stamp
  // them onto every later event, so signups and revenue attribute back to the
  // campaign that brought the visitor — even when the checkout URL is clean.
  function sessionUtms(isNew: boolean): string {
    if (isNew) {
      const parts: string[] = [];
      new URLSearchParams(location.search).forEach((v, k) => {
        if (k.indexOf("utm_") === 0 && !parts.some((p) => p.indexOf(k + "=") === 0)) {
          parts.push(k + "=" + encodeURIComponent(v));
        }
      });
      store("al_utm", parts.join("&"));
    }
    return stored("al_utm") || "";
  }

  function eventUrl(utm: string): string {
    const href = location.href;
    if (!utm || /[?&]utm_/.test(href)) return href;
    return href + (href.indexOf("?") === -1 ? "?" : "&") + utm;
  }

  function deviceInfo(): { device: string; browser: string; os: string } {
    const ua = navigator.userAgent;
    const mobile = /android|iphone|ipad|ipod|mobile/i.test(ua);
    const tablet = /ipad|tablet/i.test(ua) && !/mobile/i.test(ua);
    const device = tablet ? "tablet" : mobile ? "mobile" : "desktop";
    let browser = "other";
    if (/edg/i.test(ua)) browser = "Edge";
    else if (/chrome|chromium|crios/i.test(ua)) browser = "Chrome";
    else if (/firefox|fxios/i.test(ua)) browser = "Firefox";
    else if (/safari/i.test(ua)) browser = "Safari";
    let os = "other";
    if (/windows/i.test(ua)) os = "Windows";
    else if (/mac os/i.test(ua)) os = "macOS";
    else if (/android/i.test(ua)) os = "Android";
    else if (/iphone|ipad|ios/i.test(ua)) os = "iOS";
    else if (/linux/i.test(ua)) os = "Linux";
    return { device, browser, os };
  }

  const queue: QueuedEvent[] = [];
  let flushing = false;

  function enqueue(name: string, props: Props = {}, revenue_amount = 0, revenue_currency = ""): void {
    if (!API || !KEY) return;
    const { device, browser, os } = deviceInfo();
    const { id: sid, isNew } = sessionId();
    queue.push({
      name,
      url: eventUrl(sessionUtms(isNew)),
      referrer: document.referrer,
      session_id: sid,
      visitor_id: visitorId(),
      device,
      browser,
      os,
      props,
      revenue_amount,
      revenue_currency,
      at: new Date().toISOString(),
    });
    scheduleFlush();
  }

  function scheduleFlush(): void {
    if (flushing || queue.length === 0) return;
    flushing = true;
    setTimeout(flush, 800); // batch rapid-fire events
  }

  function flush(): void {
    flushing = false;
    if (queue.length === 0 || !API || !KEY) return;
    const events = queue.splice(0, queue.length);
    // Note: navigator.sendBeacon can't set custom headers, so we use fetch with
    // keepalive — it survives page unload and carries the write key.
    fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Write-Key": KEY },
      body: JSON.stringify({ events }),
      keepalive: true,
    }).catch(() => {
      /* never break the host page */
    });
  }

  // Track SPA navigations too.
  function trackPageview(): void {
    enqueue("pageview");
  }

  let lastPath = location.pathname + location.search;
  const origPushState = history.pushState;
  history.pushState = function (...args: any[]) {
    const r = origPushState.apply(this, args as any);
    const path = location.pathname + location.search;
    if (path !== lastPath) {
      lastPath = path;
      trackPageview();
    }
    return r;
  };
  window.addEventListener("popstate", () => {
    const path = location.pathname + location.search;
    if (path !== lastPath) {
      lastPath = path;
      trackPageview();
    }
  });
  window.addEventListener("pagehide", flush);

  const api = {
    event: (name: string, props: Props = {}) => enqueue(name, props),
    revenue: (amount: number, opts: { currency?: string } & Props = {}) => {
      const { currency = "USD", ...props } = opts;
      enqueue("revenue", props, amount, currency);
    },
    pageview: () => trackPageview(),
  };

  (window as any).agentlens = api;
  (window as any).al = api; // short alias

  if (document.readyState === "complete") trackPageview();
  else window.addEventListener("load", trackPageview, { once: true });
})();
