import json
import shutil
import zipfile

from pathlib import Path


def create_firefox_proxy_addon(out_dir: str, proxy: str) -> str:
    proxy = proxy.replace("://", "://", 1)
    creds, hostport = proxy.split("@")
    proxy_user, proxy_pass = creds.split("://", 1)[1].split(":", 1)
    proxy_host, proxy_port = hostport.split(":")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = out_dir / f"proxy_addon_{proxy_user}"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir()

    manifest = {
        "manifest_version": 2,
        "name": "Proxy+Stealth (Firefox)",
        "version": "1.0.1",
        "permissions": [
            "proxy",
            "webRequest",
            "webRequestBlocking",
            "<all_urls>"
        ],
        "background": {"scripts": ["background.js"]},
        "content_scripts": [
            {
                "matches": ["<all_urls>"],
                "js": ["stealth.js"],
                "run_at": "document_start",
                "all_frames": True
            }
        ],
        "applications": {
            "gecko": {"id": "proxy-stealth-evirma@example.com"}
        }
    }

    background_js = f"""
    // Настройка прокси
    browser.proxy.onRequest.addListener(
      () => ({{ type: "http", host: "{proxy_host}", port: {int(proxy_port)} }}),
      {{ urls: ["<all_urls>"] }}
    );
    browser.proxy.onError.addListener(e => console.error("proxy error", e));

    // Авторизация (Basic/Proxy-Auth)
    browser.webRequest.onAuthRequired.addListener(
      details => {{
        return {{ authCredentials: {{ username: "{proxy_user}", password: "{proxy_pass}" }} }};
      }},
      {{ urls: ["<all_urls>"] }},
      ["blocking"]
    );
    """.strip()

    stealth_page_js = r"""
    try {
      Object.defineProperty(Navigator.prototype, 'webdriver', {
        get: () => undefined,
        configurable: true
      });
    } catch(e) {}

    // permissions.query (аккуратно)
    try {
      if (navigator.permissions && navigator.permissions.query) {
        const originalQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = function(parameters) {
          if (parameters && parameters.name === 'notifications') {
            return Promise.resolve({ state: Notification.permission });
          }
          return originalQuery(parameters);
        };
      }
    } catch(e) {}

    // canvas noise (минимальный, ок)
    try {
      const toDataURL = HTMLCanvasElement.prototype.toDataURL;
      HTMLCanvasElement.prototype.toDataURL = function() {
        try {
          const ctx = this.getContext('2d');
          if (ctx) {
            ctx.fillStyle = 'rgba(1,1,1,0.001)';
            ctx.fillRect(0, 0, this.width, this.height);
          }
        } catch(e) {}
        return toDataURL.apply(this, arguments);
      };
    } catch(e) {}
    """.strip()

    stealth_js = f"""
    (function inject(){{
      const code =
    {json.dumps(stealth_page_js)};
    const
    s = document.createElement('script');
    s.textContent = code;
    (document.documentElement || document.head || document.documentElement).appendChild(s);
    s.remove();
    }})();
    """

    (work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    (work_dir / "background.js").write_text(background_js, "utf-8")
    (work_dir / "stealth.js").write_text(stealth_js, "utf-8")

    xpi_path = out_dir / f"proxy_{proxy_user}.xpi"
    with zipfile.ZipFile(xpi_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(work_dir / "manifest.json", "manifest.json")
        z.write(work_dir / "background.js", "background.js")
        z.write(work_dir / "stealth.js", "stealth.js")

    return str(xpi_path)
