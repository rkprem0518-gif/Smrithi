/* Optional: Bolna Web Call SDK (@bolna/web-call v3.0.1, per bolna.ai/docs/developer-resources/sdks/web-call).
   The backend mints a single-use session (POST /web-call/session) so the browser never sees the API key. */
"use strict";

window.SmritiWebCall = {
  SDK_URL: "https://cdn.jsdelivr.net/gh/bolna-ai/web-call@v3.0.1/dist/bolna-web-call.min.js",

  loadSdk() {
    if (window.BolnaWebCall) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = this.SDK_URL;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error("Could not load the Bolna Web Call SDK"));
      document.head.append(s);
    });
  },

  async start(session, sessionId, box) {
    await this.loadSdk();
    const call = new window.BolnaWebCall({ session });
    const goLive = () => { location.href = `/live.html?id=${encodeURIComponent(sessionId)}`; };
    box.hidden = false;
    box.replaceChildren(
      el("p", { class: "notice strong", text: t("webcall_live") }),
      el("button", { class: "btn danger", type: "button", text: t("webcall_hangup"), onclick: () => call.stop() }),
    );
    call.on("call-end", goLive);
    call.on("error", (e) => {
      box.append(el("p", { class: "error", text: `${e.code}: ${e.message}` }));
    });
    await call.start();
  },
};
