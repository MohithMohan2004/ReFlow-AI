// Phone / desktop notifications for things the user must not miss (OCEMS
// limit alerts). Inside the Android app they go through the native
// LocalNotifications plugin (app 1.7+); in a browser through the standard
// Notification API. Both need the user's permission once.

type Bridge = {
  isNativePlatform?: () => boolean;
  PluginHeaders?: { name: string }[];
  nativePromise: (plugin: string, method: string, options?: unknown) => Promise<unknown>;
};

const PLUGIN = "LocalNotifications";

function nativeBridge(): Bridge | null {
  const cap = (window as unknown as { Capacitor?: Bridge }).Capacitor;
  if (!cap?.isNativePlatform?.() || !cap.PluginHeaders?.some((h) => h.name === PLUGIN)) return null;
  return cap;
}

export type NotifyPermission = "granted" | "denied" | "prompt" | "unsupported";

export async function notifyPermission(): Promise<NotifyPermission> {
  const cap = nativeBridge();
  if (cap) {
    try {
      const r = (await cap.nativePromise(PLUGIN, "checkPermissions")) as { display?: string };
      return r.display === "granted" ? "granted" : r.display === "denied" ? "denied" : "prompt";
    } catch {
      return "unsupported";
    }
  }
  if (!("Notification" in window) || !window.isSecureContext) return "unsupported";
  return Notification.permission === "default" ? "prompt" : (Notification.permission as NotifyPermission);
}

export async function enableNotifications(): Promise<NotifyPermission> {
  const cap = nativeBridge();
  if (cap) {
    try {
      const r = (await cap.nativePromise(PLUGIN, "requestPermissions")) as { display?: string };
      return r.display === "granted" ? "granted" : "denied";
    } catch {
      return "unsupported";
    }
  }
  if (!("Notification" in window) || !window.isSecureContext) return "unsupported";
  const r = await Notification.requestPermission();
  return r === "default" ? "prompt" : (r as NotifyPermission);
}

let nextId = Math.floor(Date.now() / 1000) % 1_000_000;

/** Show a notification if the user allowed it; silently does nothing otherwise. */
export async function notify(title: string, body: string, tag?: string): Promise<void> {
  const cap = nativeBridge();
  if (cap) {
    try {
      await cap.nativePromise(PLUGIN, "schedule", {
        // Shown now, so no exact alarm (otherwise Android opens the "Alarms & reminders" screen).
        notifications: [{ id: nextId++, title, body, smallIcon: "ic_stat_reflow", isExactNotification: false }],
      });
    } catch { /* no permission */ }
    return;
  }
  if ("Notification" in window && window.isSecureContext && Notification.permission === "granted") {
    try {
      new Notification(title, { body, tag, icon: "/static/brand-mark.svg" });
    } catch { /* some mobile browsers only allow service-worker notifications */ }
  }
}
