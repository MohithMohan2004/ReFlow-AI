import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, BellRing, TriangleAlert } from "lucide-react";
import { getJSON, postJSON } from "../lib/api";
import { useToast } from "../lib/toast";
import { enableNotifications, notify, notifyPermission, type NotifyPermission } from "../lib/notify";
import { Dialog } from "./Dialog";
import { Badge } from "./ui";

export interface OcemsAlert {
  alert_id: string;
  parameter: string;
  unit: string;
  limit: string;
  status: "open" | "resolved";
  started_at: string;
  first_value: string;
  worst_value: string;
  last_value: string;
  last_seen_at: string;
  resolved_at: string | null;
  read: boolean;
  message: string;
}

interface AlertsResponse {
  open: number;
  unread: number;
  limits: Record<string, string>;
  alerts: OcemsAlert[];
}

const POLL_MS = 60_000;

const pretty = (limit: string) => limit.replace("<=", "≤").replace(">=", "≥").replace(/\s*-\s*/, "–");

/** "2026-11-24 10:15:00" -> "24 Nov, 10:15" */
function when(ts: string | null | undefined) {
  if (!ts) return "";
  const d = new Date(ts.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
}

function seenKey(stpId: string) {
  return `reflow-ocems-alerts-seen-${stpId}`;
}

function loadSeen(stpId: string): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(seenKey(stpId)) || "[]") as string[]);
  } catch {
    return new Set();
  }
}

function saveSeen(stpId: string, seen: Set<string>) {
  try {
    localStorage.setItem(seenKey(stpId), JSON.stringify([...seen].slice(-200)));
  } catch { /* private mode */ }
}

/**
 * Polls the plant's OCEMS limit alerts every minute (the server checks the
 * feed on each poll) and raises a toast plus a phone/desktop notification
 * the first time this device sees a new alert.
 */
export function useOcemsAlerts(stpId: string | null | undefined) {
  const toast = useToast();
  const [data, setData] = useState<AlertsResponse | null>(null);
  const seen = useRef<Set<string>>(new Set());

  const load = useCallback(async () => {
    if (!stpId) return;
    try {
      const next = await getJSON<AlertsResponse>("/api/ocems_alerts");
      setData(next);
      const fresh = next.alerts.filter((a) => a.status === "open" && !a.read && !seen.current.has(a.alert_id));
      for (const a of fresh) {
        seen.current.add(a.alert_id);
        toast(`OCEMS alert: ${a.message}`, "danger");
        void notify("OCEMS limit exceeded", a.message, a.alert_id);
      }
      if (fresh.length) saveSeen(stpId, seen.current);
    } catch { /* try again next poll */ }
  }, [stpId, toast]);

  useEffect(() => {
    if (!stpId) return;
    seen.current = loadSeen(stpId);
    void load();
    const id = window.setInterval(() => { if (!document.hidden) void load(); }, POLL_MS);
    const onVisible = () => { if (!document.hidden) void load(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { window.clearInterval(id); document.removeEventListener("visibilitychange", onVisible); };
  }, [stpId, load]);

  const markRead = useCallback(async () => {
    if (!data?.unread) return;
    try {
      await postJSON("/api/ocems_alerts/read", {});
      setData((d) => (d ? { ...d, unread: 0, alerts: d.alerts.map((a) => ({ ...a, read: true })) } : d));
    } catch { /* stays unread */ }
  }, [data?.unread]);

  return { data, reload: load, markRead };
}

/** Top-bar bell: unread count, opens the alert list. */
export function OcemsAlertsButton({ alerts }: { alerts: ReturnType<typeof useOcemsAlerts> }) {
  const [open, setOpen] = useState(false);
  const unread = alerts.data?.unread ?? 0;
  const active = (alerts.data?.open ?? 0) > 0;
  const Icon = active ? BellRing : Bell;
  return (
    <>
      <button
        type="button"
        className="btn btn-ghost btn-icon alert-bell"
        data-active={active || undefined}
        onClick={() => { setOpen(true); void alerts.markRead(); }}
        aria-label={unread ? `Quality alerts, ${unread} new` : "Quality alerts"}
        title="Quality alerts"
      >
        <Icon />
        {unread > 0 && <span className="alert-bell-count">{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && <OcemsAlertsDialog data={alerts.data} onClose={() => setOpen(false)} />}
    </>
  );
}

function OcemsAlertsDialog({ data, onClose }: { data: AlertsResponse | null; onClose: () => void }) {
  const [permission, setPermission] = useState<NotifyPermission | null>(null);
  useEffect(() => { void notifyPermission().then(setPermission); }, []);

  return (
    <Dialog title="Quality alerts" onClose={onClose}>
      <div className="stack" style={{ gap: 14 }}>
        {permission === "prompt" && (
          <div className="alert-enable">
            <span>Get a notification on this device when a reading goes outside its limit.</span>
            <button type="button" className="btn btn-sm btn-primary" onClick={() => void enableNotifications().then(setPermission)}>
              <Bell size={15} /> Turn on
            </button>
          </div>
        )}
        {permission === "denied" && (
          <p className="muted" style={{ fontSize: 13 }}>
            Notifications are blocked for ReFlow on this device. Allow them in the device or browser settings to be alerted.
          </p>
        )}

        {!data?.alerts.length ? (
          <p className="muted" style={{ fontSize: 13.5 }}>No readings outside the limits so far.</p>
        ) : (
          <ul className="alert-list">
            {data.alerts.map((a) => (
              <li key={a.alert_id} data-status={a.status}>
                <div className="row-between">
                  <strong>{a.parameter}</strong>
                  <Badge tone={a.status === "open" ? "danger" : "success"}>{a.status === "open" ? "Outside limit" : "Back in limit"}</Badge>
                </div>
                <span>
                  {a.status === "open" ? `Now ${a.last_value}` : `Peaked at ${a.worst_value}`}
                  {a.unit ? ` ${a.unit}` : ""} · limit {pretty(a.limit)}{a.unit ? ` ${a.unit}` : ""}
                  {a.status === "open" && a.worst_value !== a.last_value ? ` · worst ${a.worst_value}` : ""}
                </span>
                <small className="muted">
                  {a.status === "open" ? `Since ${when(a.started_at)}` : `${when(a.started_at)} – ${when(a.resolved_at)}`}
                </small>
              </li>
            ))}
          </ul>
        )}

        {data?.limits && (
          <p className="muted" style={{ fontSize: 12.5 }}>
            Alert limits (reference values; your plant&rsquo;s KSPCB consent conditions apply):{" "}
            {Object.entries(data.limits).map(([p, l]) => `${p} ${pretty(l)}${p === "pH" ? "" : " mg/L"}`).join(" · ")}
          </p>
        )}
      </div>
    </Dialog>
  );
}

/** Red banner above the OCEMS tiles while any parameter is outside its limit. */
export function OcemsAlertBanner({ alerts }: { alerts: ReturnType<typeof useOcemsAlerts> }) {
  const open = alerts.data?.alerts.filter((a) => a.status === "open") ?? [];
  if (!open.length) return null;
  return (
    <div className="alert-banner" role="alert">
      <TriangleAlert size={16} />
      <div>
        <strong>{open.length === 1 ? "A reading is outside its limit" : `${open.length} readings are outside their limits`}</strong>
        <ul>
          {open.map((a) => (
            <li key={a.alert_id}>{a.message}, since {when(a.started_at)}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
