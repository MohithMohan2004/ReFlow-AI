/* ReFlow Android app: "update available" prompt.
 *
 * Runs on every page (React shell and Flask templates) but only does
 * anything inside the native app (Capacitor). It asks the server for the
 * newest GitHub release (/api/app/latest) and, when that is newer than the
 * installed app, offers to download the APK.
 *
 * The installed version comes from the WebView user agent ("ReFlowApp/1.7",
 * added by mobile/capacitor.config.ts from 1.7 on). Builds up to 1.6 don't
 * send it, so a native app without it counts as 1.6.
 */
(function () {
  "use strict";

  var LEGACY_VERSION = "1.6";
  var SNOOZE_MS = 24 * 60 * 60 * 1000; // "Later" hides the prompt for a day

  var cap = window.Capacitor;
  var isNative = !!(cap && (typeof cap.isNativePlatform === "function" ? cap.isNativePlatform() : cap.isNative));
  if (!isNative || window.__reflowUpdateChecked) return;
  window.__reflowUpdateChecked = true;

  var match = /ReFlowApp\/([0-9][0-9.]*)/.exec(navigator.userAgent || "");
  var installed = match ? match[1] : LEGACY_VERSION;

  function parts(v) {
    return String(v || "").replace(/^v/i, "").split(".").map(function (n) { return parseInt(n, 10) || 0; });
  }

  function newer(a, b) { // is a newer than b?
    var x = parts(a), y = parts(b);
    for (var i = 0; i < Math.max(x.length, y.length); i++) {
      var d = (x[i] || 0) - (y[i] || 0);
      if (d) return d > 0;
    }
    return false;
  }

  function snoozed(version) {
    try {
      var until = Number(localStorage.getItem("reflow-update-snooze-" + version) || 0);
      return until > Date.now();
    } catch (e) { return false; }
  }

  function snooze(version) {
    try { localStorage.setItem("reflow-update-snooze-" + version, String(Date.now() + SNOOZE_MS)); } catch (e) {}
  }

  var CSS =
    ".rf-update{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:flex-end;justify-content:center;" +
    "padding:16px;background:rgba(8,15,28,.45);font-family:Inter,system-ui,sans-serif}" +
    "@media (min-width:600px){.rf-update{align-items:center}}" +
    ".rf-update__card{width:100%;max-width:400px;background:var(--surface,#fff);color:var(--ink-900,#0f1b2d);" +
    "border:1px solid var(--line,#e2e8f0);border-radius:16px;padding:20px;box-shadow:0 20px 50px rgba(8,15,28,.3);" +
    "animation:rf-update-in .22s ease-out}" +
    "@keyframes rf-update-in{from{transform:translateY(16px)}to{transform:none}}" +
    "@media (prefers-reduced-motion:reduce){.rf-update__card{animation:none}}" +
    ".rf-update__head{display:flex;gap:12px;align-items:center;margin-bottom:10px}" +
    ".rf-update__icon{flex:none;width:40px;height:40px;border-radius:12px;display:grid;place-items:center;" +
    "background:rgba(20,99,214,.12);color:#1463d6}" +
    ".rf-update__icon svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}" +
    ".rf-update h2{margin:0;font-size:17px;line-height:1.3}" +
    ".rf-update p{margin:0 0 16px;font-size:14px;line-height:1.5;color:var(--ink-500,#64748b)}" +
    ".rf-update__actions{display:flex;gap:10px}" +
    ".rf-update__actions button{flex:1;min-height:44px;border-radius:11px;font:600 15px/1 Inter,system-ui,sans-serif;cursor:pointer}" +
    ".rf-update__later{background:transparent;color:var(--ink-700,#334155);border:1px solid var(--line,#e2e8f0)}" +
    ".rf-update__go{background:#1463d6;color:#fff;border:0}";

  function show(release) {
    if (document.querySelector(".rf-update")) return;

    var style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);

    var wrap = document.createElement("div");
    wrap.className = "rf-update";
    wrap.setAttribute("role", "dialog");
    wrap.setAttribute("aria-modal", "true");
    wrap.setAttribute("aria-labelledby", "rf-update-title");

    var card = document.createElement("div");
    card.className = "rf-update__card";
    card.innerHTML =
      '<div class="rf-update__head"><span class="rf-update__icon" aria-hidden="true">' +
      '<svg viewBox="0 0 24 24"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg></span>' +
      '<h2 id="rf-update-title"></h2></div><p></p>' +
      '<div class="rf-update__actions"><button type="button" class="rf-update__later">Later</button>' +
      '<button type="button" class="rf-update__go">Update</button></div>';
    card.querySelector("h2").textContent = "Update available";
    card.querySelector("p").textContent =
      "ReFlow " + release.version + " is out. You have " + installed +
      ". Download the new version and install it over this one; you stay signed in.";

    function close() { wrap.remove(); style.remove(); }

    card.querySelector(".rf-update__later").addEventListener("click", function () {
      snooze(release.version);
      close();
    });
    card.querySelector(".rf-update__go").addEventListener("click", function () {
      // Off-site links leave the app's WebView and open in the phone's
      // browser, which downloads the APK.
      window.location.href = release.download_url || release.page_url;
      close();
    });

    wrap.appendChild(card);
    document.body.appendChild(wrap);
    card.querySelector(".rf-update__go").focus();
  }

  function check() {
    fetch("/api/app/latest", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (release) {
        if (!release || !release.version || !(release.download_url || release.page_url)) return;
        if (!newer(release.version, installed) || snoozed(release.version)) return;
        show(release);
      })
      .catch(function () {});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", check);
  else check();
})();
