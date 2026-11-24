import { own } from "../lib/lookup";
import { OPERATOR } from "../lib/legal";
import { LegalFooter } from "../components/LegalFooter";
import { useEffect, useMemo } from "react";
import { useLocation } from "react-router-dom";
import { Marker, Popup } from "react-leaflet";
import {
  ArrowRight, Building2, ChartLine, Droplets, Factory, Gauge, LogIn, Mail, MapPin, Recycle, Route, ScanSearch, Truck,
} from "lucide-react";
import { AppShell } from "../components/AppShell";
import { publicNav, roleNav } from "../components/nav";
import { FitBounds, MapFrame, pinIcon } from "../components/map";
import { getJSON } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import { useSession } from "../lib/session";
import { num } from "../lib/format";
import type { Stp } from "../lib/types";
import "./landing.css";

const HOME_FOR_ROLE: Record<string, string> = { demand: "/demand", stp: "/supply", tanker: "/tanker", admin: "/admin", superadmin: "/admin" };

/** Grade → colour. Categorical only; status colours stay reserved. */
const GRADES: { name: string; color: string }[] = [
  { name: "Platinum", color: "#7c3aed" },
  { name: "Gold", color: "#d97706" },
  { name: "Silver", color: "#64748b" },
  { name: "General", color: "#0d9488" },
];
const gradeColor = (g?: string) => GRADES.find((x) => x.name === g)?.color ?? "#0d9488";

export default function Landing() {
  const user = useSession();
  const location = useLocation();
  const { data: stps, loading } = useAsync((s) => getJSON<Stp[]>("/api/stps", s));

  useEffect(() => {
    if (!location.hash) return;
    document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [location.hash, loading]);

  const located = useMemo(() => (stps ?? []).filter((s) => s.latitude && s.longitude), [stps]);
  const totals = useMemo(() => {
    const list = stps ?? [];
    const total = list.reduce((a, s) => a + (Number(s.total_capacity_mld) || 0), 0) * 1000;
    const avail = list.reduce((a, s) => a + (Number(s.available_capacity_mld) || 0), 0) * 1000;
    return { count: list.length, total, avail, pct: total > 0 ? (avail / total) * 100 : 0 };
  }, [stps]);
  const gradesPresent = GRADES.filter((g) => located.some((s) => (s.quality_grade || "General") === g.name));
  const bounds = located.length ? (located.map((s) => [s.latitude!, s.longitude!]) as [number, number][]) : null;

  const dashboard = user?.logged_in ? own(HOME_FOR_ROLE, user.role) : undefined;
  const nav = user?.logged_in && roleNav[user.role] ? [...roleNav[user.role]!, publicNav[0]!] : publicNav;

  return (
    <AppShell
      nav={nav}
      title="Overview"
      subtitle="Treated water network · Bengaluru"
      actions={dashboard ? (
        <a className="btn btn-sm btn-primary" href={dashboard}>Open dashboard <ArrowRight /></a>
      ) : (
        <>
          <a className="btn btn-sm btn-ghost" href="/login">Sign in</a>
          <a className="btn btn-sm btn-primary" href="/signup">Create account</a>
        </>
      )}
      sidebarFoot={!user?.logged_in && (
        <>
          <span className="sidebar-foot-text">Already on the network?</span>
          <a className="btn btn-light btn-sm btn-block nav-cta" href="/login" title="Sign in">
            <LogIn /> <span className="nav-text">Sign in</span>
          </a>
        </>
      )}
    >
      <main className="page landing">
        {/* HERO */}
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-bg" aria-hidden="true">
            <svg viewBox="0 0 800 400" preserveAspectRatio="none">
              <path d="M0 300 C 150 250, 260 340, 420 300 S 680 240, 800 280" fill="none" stroke="#1463d6" strokeOpacity="0.08" strokeWidth="2" />
              <path d="M0 330 C 160 290, 280 370, 440 330 S 690 280, 800 312" fill="none" stroke="#0d9488" strokeOpacity="0.08" strokeWidth="2" />
              <path d="M0 360 C 170 330, 300 395, 460 360 S 700 320, 800 345" fill="none" stroke="#7c3aed" strokeOpacity="0.07" strokeWidth="2" />
            </svg>
          </div>

          <div className="hero-copy">
            <span className="hero-pill"><span className="live-dot" /> Pilot in Bengaluru</span>
            <h1 id="hero-title">Treated wastewater, <span className="grad-text">routed where it&rsquo;s needed.</span></h1>
            <p className="hero-lede">
              ReFlow matches each demand site with a nearby treatment plant that lists the capacity and
              quality it needs, then offers the delivery to a tanker partner.
            </p>
            <div className="hero-actions">
              <a className="btn btn-lg btn-primary" href={dashboard ?? "/login"}>
                {dashboard ? "Open dashboard" : "Request treated water"} <ArrowRight />
              </a>
              <a className="btn btn-lg btn-secondary" href="/stp/register">Register a plant</a>
            </div>
            <ul className="hero-trust">
              <li data-tone="teal"><Recycle size={15} /> Reuses treated water</li>
              <li data-tone="sky"><Route size={15} /> Road-optimised routing</li>
              <li data-tone="violet"><Truck size={15} /> Live tanker tracking</li>
            </ul>
          </div>

          <figure className="hero-visual">
            <div className="map-shell">
              <MapFrame className="hero-map-frame" zoomControl={false} scrollZoom={false}>
                <FitBounds bounds={bounds} fitKey={String(located.length)} maxZoom={12} />
                {located.map((s) => (
                  <Marker key={s.stp_id} position={[s.latitude!, s.longitude!]} icon={pinIcon("plant", "brand", gradeColor(s.quality_grade || "General"))}>
                    <Popup>
                      <strong>{s.stp_name}</strong>
                      <br />
                      {s.quality_grade || "General"} grade · {num((Number(s.available_capacity_mld) || 0) * 1000)} KLD available
                    </Popup>
                  </Marker>
                ))}
              </MapFrame>
              <div className="float-chip float-top">
                <span className="live-dot" />
                <span><b className="num">{loading ? "—" : located.length}</b> plants on the map</span>
              </div>
              <div className="float-card float-bottom">
                <span className="float-icon"><Droplets size={16} /></span>
                <div>
                  <span className="float-label">Listed capacity available</span>
                  <strong className="num">{loading ? "—" : num(totals.avail)} <small>KLD</small></strong>
                  <span className="float-bar" aria-hidden="true"><span style={{ width: `${totals.pct}%` }} /></span>
                </div>
              </div>
              {gradesPresent.length > 0 && (
                <div className="float-legend" aria-label="Quality grades">
                  {gradesPresent.map((g) => (
                    <span key={g.name}><i style={{ background: g.color }} />{g.name}</span>
                  ))}
                </div>
              )}
            </div>
          </figure>
        </section>

        {/* LIVE FIGURES */}
        <section className="figures" aria-label="Network figures">
          <Figure tone="blue" icon={Factory} label="Treatment plants" value={loading ? null : num(totals.count)} hint="Listed on the map" />
          <Figure tone="teal" icon={Gauge} label="Treatment capacity" value={loading ? null : num(totals.total)} unit="KLD" hint="Combined daily capacity" />
          <Figure tone="violet" icon={Droplets} label="Listed as available" value={loading ? null : num(totals.avail)} unit="KLD" hint={`${Math.round(totals.pct)}% of listed capacity`} bar={totals.pct} />
        </section>
        <p className="figures-note">
          Pilot figures. Plant locations and capacities come from public records and from plants on ReFlow, are
          indicative, and don&rsquo;t mean a plant has joined ReFlow or will accept an order.
        </p>

        {/* HOW IT WORKS */}
        <section id="how-it-works" className="block" aria-labelledby="how-title">
          <header className="block-head">
            <div>
              <span className="eyebrow">How it works</span>
              <h2 id="how-title">From treatment plant to site in four steps</h2>
            </div>
            <p>Every request runs through the same steps, so you can see why a plant was suggested.</p>
          </header>
          <ol className="steps">
            <Step n={1} tone="sky" icon={ScanSearch} title="Search">Enter the delivery point, quantity, quality grade and water type.</Step>
            <Step n={2} tone="teal" icon={ChartLine} title="Match">Plants with enough listed capacity, the right grade and water type are sorted by road distance.</Step>
            <Step n={3} tone="amber" icon={Truck} title="Dispatch">Once the plant accepts, a nearby tanker partner is offered the pickup.</Step>
            <Step n={4} tone="violet" icon={Route} title="Track">Follow the tanker live until the delivery is confirmed.</Step>
          </ol>
        </section>

        {/* ROLES */}
        <section className="block" aria-labelledby="roles-title">
          <header className="block-head">
            <div>
              <span className="eyebrow">Who it&rsquo;s for</span>
              <h2 id="roles-title">One network, three roles</h2>
            </div>
          </header>
          <div className="roles">
            <Role tone="sky" icon={MapPin} title="Demand sites" href="/login" cta="Request water" art="drop">
              Find treated water by location, quantity and quality, place an order and track the delivery.
            </Role>
            <Role tone="teal" icon={Building2} title="Plant operators" href="/stp/register" cta="Register a plant" art="plant">
              Publish capacity and pricing, accept incoming orders and connect your OCEMS feed.
            </Role>
            <Role tone="violet" icon={Truck} title="Tanker partners" href="/tanker/register" cta="Become a partner" art="truck">
              Receive pickups near you, follow the route and log every trip.
            </Role>
          </div>
        </section>

        {/* CTA BAND */}
        <section className="cta-band" aria-labelledby="cta-title">
          <svg className="cta-waves" viewBox="0 0 1200 200" preserveAspectRatio="none" aria-hidden="true">
            <path d="M0 140 C 200 100, 380 180, 600 140 S 1000 90, 1200 130 V200 H0 Z" fill="rgba(255,255,255,0.08)" />
            <path d="M0 165 C 220 135, 420 200, 640 165 S 1020 125, 1200 158 V200 H0 Z" fill="rgba(255,255,255,0.08)" />
          </svg>
          <div className="cta-copy">
            <h2 id="cta-title">Ready to put treated water to work?</h2>
            <p>Using treated water for non-drinking needs such as construction, landscaping and cooling can reduce the demand on fresh water.</p>
          </div>
          <div className="cta-actions">
            <a className="btn btn-lg btn-light" href={dashboard ?? "/signup"}>{dashboard ? "Open dashboard" : "Create an account"} <ArrowRight /></a>
            <a className="btn btn-lg cta-ghost" href="/tanker/register">Become a tanker partner</a>
          </div>
        </section>

        {/* ABOUT + CONTACT */}
        <section className="about-grid block">
          <article id="about" className="card about" aria-labelledby="about-title">
            <span className="eyebrow">About</span>
            <h2 id="about-title">About ReFlow</h2>
            <p>
              ReFlow is a pilot run by a student project team in Bengaluru. It connects sites that need water for
              non-drinking uses with sewage treatment plants that have treated water to spare, and with the tanker
              partners who carry it.
            </p>
            <p>
              It uses road distances to suggest plants and tankers, and gives plants a demand forecast. The pilot is a
              working prototype: suggestions, forecasts and quality figures are indicative.
            </p>
            <p className="about-note">
              Treated water from ReFlow is not for drinking, cooking or bathing.
            </p>
          </article>
          <article id="contact" className="card contact" aria-labelledby="contact-title">
            <span className="eyebrow">Contact</span>
            <h2 id="contact-title">Talk to the team</h2>
            <p>For questions, privacy requests, complaints or collaboration, write to the project team.</p>
            <dl className="contact-list">
              <div>
                <dt><span className="contact-icon" data-tone="sky"><Mail size={14} /></span> Email</dt>
                <dd><a href="mailto:reflow.circularity@gmail.com">reflow.circularity@gmail.com</a></dd>
              </div>
              <div>
                <dt><span className="contact-icon" data-tone="teal"><Building2 size={14} /></span> Run by</dt>
                <dd>ReFlow student project team, {OPERATOR.city}</dd>
              </div>
            </dl>
          </article>
        </section>

        <LegalFooter />
      </main>
    </AppShell>
  );
}

function Figure({ tone, icon: Icon, label, value, unit, hint, bar }: {
  tone: string; icon: typeof Factory; label: string; value: string | null; unit?: string; hint: string; bar?: number;
}) {
  return (
    <div className="card figure" data-tone={tone}>
      <span className="figure-icon"><Icon size={19} /></span>
      <div className="figure-body">
        <div className="stat-label">{label}</div>
        {value === null ? (
          <div key="loading" className="skeleton" style={{ height: 30, width: 110, margin: "4px 0" }} />
        ) : (
          <div key="value" className="stat-value">{value}{unit && <small>{unit}</small>}</div>
        )}
        <div className="stat-hint">{hint}</div>
        {bar !== undefined && <span className="figure-bar" aria-hidden="true"><span style={{ width: `${bar}%` }} /></span>}
      </div>
    </div>
  );
}

function Step({ n, tone, icon: Icon, title, children }: { n: number; tone: string; icon: typeof Factory; title: string; children: string }) {
  return (
    <li className="step" data-tone={tone}>
      <div className="step-top">
        <span className="step-icon"><Icon size={20} /></span>
        <span className="step-n num">{n}</span>
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
    </li>
  );
}

const ROLE_ART: Record<string, string> = {
  drop: '<circle cx="70" cy="58" r="34" fill="currentColor" opacity=".12"/><path d="M70 30c-10 13-17 21-17 30a17 17 0 0 0 34 0c0-9-7-17-17-30z" fill="currentColor" opacity=".9"/><path d="M62 62a8 8 0 0 0 8 8" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round"/><circle cx="128" cy="40" r="6" fill="currentColor" opacity=".35"/><circle cx="20" cy="86" r="5" fill="currentColor" opacity=".3"/>',
  plant: '<circle cx="74" cy="58" r="34" fill="currentColor" opacity=".12"/><path d="M44 84V54l14 9v-9l14 9v-9l14 9V36h12v48z" fill="currentColor" opacity=".9"/><rect x="40" y="84" width="72" height="4" rx="2" fill="currentColor"/><path d="M118 70c6 6 12 6 18 0" stroke="currentColor" stroke-width="3" fill="none" stroke-linecap="round" opacity=".4"/>',
  truck: '<circle cx="72" cy="56" r="34" fill="currentColor" opacity=".12"/><rect x="30" y="44" width="60" height="26" rx="13" fill="currentColor" opacity=".9"/><path d="M92 70V50a5 5 0 0 1 5-5h9l10 12v13z" fill="currentColor"/><rect x="26" y="70" width="94" height="4" rx="2" fill="currentColor" opacity=".6"/><circle cx="44" cy="78" r="7" fill="#1d2a3d"/><circle cx="100" cy="78" r="7" fill="#1d2a3d"/>',
};

function Role({ tone, icon: Icon, title, href, cta, art, children }: {
  tone: string; icon: typeof Factory; title: string; href: string; cta: string; art: keyof typeof ROLE_ART; children: string;
}) {
  return (
    <a className="role card" href={href} data-tone={tone}>
      <div className="role-art" aria-hidden="true">
        <svg viewBox="0 0 150 100" dangerouslySetInnerHTML={{ __html: ROLE_ART[art]! }} />
        <span className="role-icon"><Icon size={18} /></span>
      </div>
      <div className="role-body">
        <h3>{title}</h3>
        <p>{children}</p>
        <span className="role-cta">{cta} <ArrowRight size={15} /></span>
      </div>
    </a>
  );
}
