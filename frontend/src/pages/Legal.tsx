import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { publicNav, roleNav } from "../components/nav";
import { LegalFooter } from "../components/LegalFooter";
import { useSession } from "../lib/session";
import { LEGAL_LINKS, LEGAL_UPDATED, LEGAL_VERSION, OPERATOR } from "../lib/legal";
import "./legal.css";

/*
 * Privacy Policy, Terms of Use, Cookie Policy, Refunds & Cancellations and
 * the Accessibility statement. Written for ReFlow as it really works today:
 * a non-commercial pilot by a student team, no payments taken, no analytics.
 * If any of that changes (payments, analytics, a company is formed), these
 * pages must change too, and LEGAL_VERSION with them.
 */

const Mail = () => <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>;

function Contact() {
  return (
    <p>
      {OPERATOR.grievanceOfficer} &middot; <Mail /> &middot; {OPERATOR.city}. We acknowledge complaints within 24 hours and
      resolve them within {OPERATOR.grievanceDays} days.
    </p>
  );
}

const PAGES: Record<string, { title: string; intro: string; body: () => ReactNode }> = {
  "/privacy": {
    title: "Privacy Policy",
    intro: "What personal data ReFlow collects, why, who sees it, how long it is kept and how to exercise your rights.",
    body: () => (
      <>
        <h2>1. Who we are</h2>
        <p>
          ReFlow is {OPERATOR.status}, based in {OPERATOR.city}. The project team decides why and how your personal
          data is used, which makes it the &ldquo;Data Fiduciary&rdquo; under India&rsquo;s Digital Personal Data
          Protection Act, 2023. Contact: <Mail />.
        </p>

        <h2>2. What we collect and why</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th scope="col">Data</th><th scope="col">Why we need it</th></tr></thead>
            <tbody>
              <tr><td>Name, email, mobile number, username, account type, password</td><td>To create and secure your account and contact you about your orders. Passwords are stored only as a one-way hash by our login provider.</td></tr>
              <tr><td>Orders: delivery location, quantity, quality grade, water type, order history</td><td>To match you with a plant, plan the route and deliver the water.</td></tr>
              <tr><td>Plant operators: the plant you run, its capacity, pricing and quality grade, and the OCEMS feed address and API key you connect</td><td>To show the plant to buyers, take orders and show water-quality readings and alerts. API keys are stored encrypted.</td></tr>
              <tr><td>Tanker partners: operator name, phone, email, area, pincode, base location, vehicle registration numbers, capacities and models, vehicle documents (RC, insurance, PUC, permit)</td><td>To check that vehicles are roadworthy and permitted, and to offer you pickups.</td></tr>
              <tr><td>Tanker location (GPS), only while you have started a trip</td><td>To show the buyer and plant where their delivery is. Sharing stops when the trip ends or you close the trip screen.</td></tr>
              <tr><td>Your device location, only when you tap &ldquo;Use my location&rdquo;</td><td>To fill in a delivery or base location. It is not tracked in the background.</td></tr>
              <tr><td>Messages to the Juno assistant</td><td>To answer your question. Messages are not saved; our server log may keep what the assistant understood (for example a place name) for troubleshooting.</td></tr>
              <tr><td>Technical data: IP address, sign-in times, pages requested, error and security logs, the session cookie</td><td>To keep you signed in, protect accounts against abuse and fix problems.</td></tr>
              <tr><td>Your acceptance of these documents (date and version)</td><td>To show what you agreed to.</td></tr>
            </tbody>
          </table>
        </div>
        <p>
          We collect only what these purposes need. We don&rsquo;t collect Aadhaar or bank details, we don&rsquo;t take card
          payments, and we don&rsquo;t use advertising or analytics trackers.
        </p>

        <h2>3. Our basis for using your data</h2>
        <p>
          We use your data with your consent, which you give when you create an account, register a plant or fleet, or
          place an order, and for the purposes you provided it for. You can withdraw consent at any time by writing
          to <Mail />; we will then stop using your data and delete it as described in section 7, except where the law
          requires us to keep it. Withdrawing consent means we can no longer provide the service to you.
        </p>

        <h2>4. Who can see your data</h2>
        <ul>
          <li><strong>Other people in your order:</strong> the plant sees the buyer&rsquo;s name, phone number and delivery location; the tanker partner sees pickup and drop-off points and the buyer&rsquo;s contact details; the buyer sees the plant, the tanker partner, the vehicle and its live location during delivery.</li>
          <li><strong>Our service providers,</strong> who process data only on our instructions:
            <ul>
              <li>Microsoft Azure (Central India): hosts the ReFlow website and app server.</li>
              <li>Supabase (servers in Singapore): sign-in, accounts and the database.</li>
              <li>Brevo (servers in the European Union): sends sign-up confirmation and password-reset emails.</li>
              <li>OpenStreetMap Foundation (United Kingdom; map tiles served worldwide): map images and address search. Your browser contacts them directly and they see your IP address and the area you view or search for.</li>
              <li>FOSSGIS e.V. (Germany), operator of the OSRM routing server: road routes. Your browser sends it the start and end points of a route.</li>
              <li>jsDelivr and cdnjs (Cloudflare): deliver the map and chart software on some pages; they see your IP address.</li>
              <li>The plant&rsquo;s OCEMS vendor: only for plants that connect a feed; our server fetches readings from it.</li>
              <li>GitHub (United States): hosts the Android app download.</li>
              <li>Google Maps: only if a tanker partner taps &ldquo;Navigate&rdquo;, which opens Google Maps with the route.</li>
            </ul>
          </li>
          <li><strong>The ReFlow team,</strong> to run the service, approve plant and tanker registrations and handle complaints.</li>
          <li><strong>Authorities,</strong> when the law requires it.</li>
        </ul>
        <p>We never sell your personal data or share it for advertising.</p>

        <h2>5. Data stored outside India</h2>
        <p>
          Some providers above store or process data outside India (Singapore, the European Union, the United Kingdom,
          Germany and the United States). We use them only as the law permits.
        </p>

        <h2>6. How we protect it</h2>
        <p>
          Connections use HTTPS, passwords are hashed, vendor API keys are encrypted, accounts are protected against
          repeated sign-in attempts, and order details are shown only to the people in that order and the ReFlow team. No system is completely
          secure. If a breach affects your data, we will tell you and the authorities as the law requires.
        </p>

        <h2>7. How long we keep it</h2>
        <ul>
          <li>Account data: while your account is open. When you ask us to delete your account we delete it, unless we must keep something to resolve a dispute or meet a legal obligation.</li>
          <li>Order records: as long as needed for disputes and legal obligations, then deleted.</li>
          <li>Tanker locations: only the latest position of each tanker is kept; it is overwritten on the next trip, and no route history is stored.</li>
          <li>Security and error logs: up to one year.</li>
          <li>When the pilot ends, we delete pilot data that we no longer need, and tell account holders before we do.</li>
        </ul>

        <h2>8. Your rights</h2>
        <p>Under the Digital Personal Data Protection Act, 2023 you can:</p>
        <ul>
          <li>get a summary of the personal data we hold about you and who we shared it with;</li>
          <li>have it corrected, completed or updated (most of it you can change yourself on your Profile page);</li>
          <li>have it erased, and withdraw your consent;</li>
          <li>nominate someone to exercise these rights if you die or become unable to;</li>
          <li>complain to us, and if you are not satisfied with our answer, to the Data Protection Board of India.</li>
        </ul>
        <p>Write to <Mail /> from the email address on your account. We may ask you to confirm your identity.</p>

        <h2>9. Children</h2>
        <p>ReFlow is for businesses and adults. You must be 18 or older to use it, and we don&rsquo;t knowingly collect data about children.</p>

        <h2>10. Cookies</h2>
        <p>We use one essential cookie to keep you signed in. See the <a href="/cookies">Cookie Policy</a>.</p>

        <h2>11. Changes</h2>
        <p>
          If we change this policy in a way that affects you, we will show the new version and, where the law requires,
          ask for your consent again. The date and version are at the top of this page.
        </p>

        <h2>12. Contact and complaints (Grievance Officer)</h2>
        <Contact />
      </>
    ),
  },

  "/terms": {
    title: "Terms of Use",
    intro: "The rules for using ReFlow. By creating an account, registering, or placing an order you agree to them.",
    body: () => (
      <>
        <h2>1. About ReFlow</h2>
        <p>
          ReFlow is {OPERATOR.status}, based in {OPERATOR.city}. In these terms &ldquo;ReFlow&rdquo;,
          &ldquo;we&rdquo; and &ldquo;us&rdquo; mean {OPERATOR.name}. It is a pilot: features may change or stop, and the
          service may be unavailable at times. ReFlow is free to use.
        </p>

        <h2>2. What ReFlow does, and what it doesn&rsquo;t</h2>
        <p>
          ReFlow is a platform that helps buyers find treated water at sewage treatment plants and arranges delivery with
          independent tanker partners. ReFlow does not own the plants or the tankers, does not treat, sell or transport
          water itself, and is not a party to the sale between the buyer and the plant. Each plant sells its own water at
          its own prices; each tanker partner is responsible for its own transport.
        </p>

        <h2>3. Treated water is not for drinking</h2>
        <p className="callout">
          Treated water ordered through ReFlow must not be used for drinking, cooking, bathing, washing food or any other
          use where people may swallow it. It is meant for permitted non-potable uses such as construction, landscaping
          and gardening, toilet flushing, cooling and industrial processes.
        </p>
        <p>
          The buyer is responsible for using, storing and distributing the water lawfully and safely, including keeping
          it separate from drinking-water lines and tanks.
        </p>

        <h2>4. Water quality information</h2>
        <p>
          Quality grades, OCEMS readings and alerts come from the plants and their monitoring equipment. ReFlow shows them
          as reported and does not test, certify or guarantee water quality. The limits ReFlow uses for its alerts are a
          reference; each plant must meet the conditions of its own consent from the Karnataka State Pollution Control
          Board and other applicable rules.
        </p>

        <h2>5. Accounts</h2>
        <ul>
          <li>You must be 18 or older and able to make a binding agreement, for yourself or the business you represent.</li>
          <li>Give accurate information and keep it up to date. Keep your password secret; you are responsible for what happens in your account.</li>
          <li>Plant accounts are activated only after the ReFlow team checks that you operate the plant. Tanker partners can take trips only after the ReFlow team approves their registration and vehicle documents.</li>
        </ul>

        <h2>6. Responsibilities</h2>
        <ul>
          <li><strong>Plants</strong> confirm that they hold the consents needed to treat and supply treated water, that their listed capacity, prices and quality are accurate, and that they will refund any amount paid for water that was not delivered.</li>
          <li><strong>Tanker partners</strong> confirm that their vehicles and drivers hold valid registration, insurance, PUC certificates, permits and licences, that tanks used for treated water are clean and marked, and that they follow traffic and safety laws.</li>
          <li><strong>Buyers</strong> confirm that their site can receive the water safely and that they will use it as described in section 3.</li>
        </ul>

        <h2>7. Prices and payment</h2>
        <p>
          Prices are set by each plant and shown before you order. ReFlow does not collect payments. You pay the plant
          directly, either on delivery (UPI or cash to the tanker partner) or by bank transfer against the plant&rsquo;s
          invoice. ReFlow will never ask you to pay into a ReFlow account. The order summary that ReFlow prepares is not
          a tax invoice; GST shown on it is an estimate and the plant issues its own invoice if it is registered for GST.
        </p>

        <h2>8. Cancellations and refunds</h2>
        <p>See <a href="/refunds">Refunds &amp; Cancellations</a>.</p>

        <h2>9. Acceptable use</h2>
        <p>Don&rsquo;t:</p>
        <ul>
          <li>give false information, pose as someone else or use another person&rsquo;s account;</li>
          <li>place orders you don&rsquo;t intend to receive or pay for;</li>
          <li>copy, scrape or resell data from ReFlow, or use it to contact users for other purposes;</li>
          <li>try to break, overload or get around ReFlow&rsquo;s security, or access data that isn&rsquo;t yours;</li>
          <li>use ReFlow for anything unlawful.</li>
        </ul>
        <p>We may suspend or close accounts that break these terms, and will tell you why unless the law prevents us.</p>

        <h2>10. Intellectual property</h2>
        <p>
          The ReFlow name, logo, design and software belong to the ReFlow project team. Map data is &copy; OpenStreetMap
          contributors, available under the Open Database License. ReFlow uses open-source software under its own
          licences, including React, Leaflet, Lucide icons and the Inter and Sora fonts (SIL Open Font License).
        </p>

        <h2>11. Liability</h2>
        <p>
          ReFlow is a free pilot provided &ldquo;as is&rdquo;. To the extent the law allows, the ReFlow team is not liable
          for the quality, quantity, timing or use of water bought from plants, for the acts of plants, tanker partners or
          buyers, or for indirect losses such as lost profits. Nothing in these terms limits liability that cannot be
          limited by law, such as for fraud or for our own gross negligence.
        </p>

        <h2>12. Changes to these terms</h2>
        <p>
          We may update these terms. If a change matters, we will tell you on the website and ask you to accept the new
          version before your next order. The date and version are at the top of this page.
        </p>

        <h2>13. Governing law and disputes</h2>
        <p>
          These terms are governed by the laws of India. Please contact us first so we can try to resolve any problem.
          Otherwise the courts at Bengaluru, Karnataka have jurisdiction, without affecting any right you have to
          approach a consumer commission or other forum under Indian law.
        </p>

        <h2>14. Contact and complaints (Grievance Officer)</h2>
        <Contact />
      </>
    ),
  },

  "/cookies": {
    title: "Cookie Policy",
    intro: "ReFlow uses one essential cookie and a few settings stored in your browser. No analytics or advertising cookies.",
    body: () => (
      <>
        <h2>Cookies we set</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th scope="col">Name</th><th scope="col">Purpose</th><th scope="col">Type</th><th scope="col">Lasts</th></tr></thead>
            <tbody>
              <tr><td><code>session</code></td><td>Keeps you signed in and protects your account. Signed, sent only over HTTPS and not readable by scripts.</td><td>Strictly necessary</td><td>Until you sign out, at most 7 days</td></tr>
            </tbody>
          </table>
        </div>

        <h2>Settings stored on your device</h2>
        <p>These stay in your browser, are never sent to us and contain no personal data:</p>
        <div className="table-wrap">
          <table>
            <thead><tr><th scope="col">Name</th><th scope="col">Purpose</th></tr></thead>
            <tbody>
              <tr><td><code>reflow-theme</code></td><td>Light or dark mode.</td></tr>
              <tr><td><code>reflow-ocems-alerts-seen-…</code></td><td>Which water-quality alerts this device has already shown you.</td></tr>
              <tr><td><code>reflow-ocems-scroll</code></td><td>Your place on the OCEMS readings page.</td></tr>
              <tr><td><code>reflow-update-snooze-…</code></td><td>When you chose &ldquo;Later&rdquo; on an app update message (Android app).</td></tr>
            </tbody>
          </table>
        </div>

        <h2>Third parties</h2>
        <p>
          ReFlow has no analytics, advertising, social media or tracking cookies, and does not let other companies set
          cookies through it. Maps, address search and routes load from OpenStreetMap and OSRM servers, which see your IP
          address (see the <a href="/privacy">Privacy Policy</a>).
        </p>

        <h2>Do I need to accept cookies?</h2>
        <p>
          No consent banner is needed, because the only cookie is strictly necessary to provide the service you ask for.
          If we ever add optional cookies, such as analytics, we will ask for your permission first and you will be able
          to refuse them.
        </p>

        <h2>Controlling cookies</h2>
        <p>
          You can delete or block cookies in your browser settings. If you block the <code>session</code> cookie you
          won&rsquo;t be able to sign in.
        </p>
      </>
    ),
  },

  "/refunds": {
    title: "Refunds & Cancellations",
    intro: "How cancellations, failed deliveries and refunds work while ReFlow is a pilot.",
    body: () => (
      <>
        <h2>ReFlow doesn&rsquo;t take your money</h2>
        <p>
          You pay the plant directly: on delivery (UPI or cash to the tanker partner), or by bank transfer against the
          plant&rsquo;s invoice after delivery. ReFlow charges no fees and never asks you to pay into a ReFlow account.
        </p>

        <h2>Cancelling an order</h2>
        <ul>
          <li><strong>Before you confirm:</strong> just leave the order summary page; nothing is booked.</li>
          <li><strong>After you confirm, before the plant accepts:</strong> write to <Mail /> with your order number and we will cancel it at no charge.</li>
          <li><strong>After the plant has accepted:</strong> contact us as soon as possible. If the tanker has not left the plant, we will ask the plant to cancel without charge. Once the tanker is on its way, the order can be cancelled only if the plant agrees.</li>
        </ul>

        <h2>If the water doesn&rsquo;t arrive</h2>
        <p>
          If a delivery fails for any reason (breakdown, accident, blocked road or anything else), you owe nothing for
          that order. If you had already paid the plant for it, the plant refunds the full amount by the same method
          within 7 working days.
        </p>

        <h2>Wrong quantity or quality</h2>
        <p>
          Check the delivery when it arrives. If the quantity is short or the water looks or smells wrong, don&rsquo;t
          accept it, or tell us within 24 hours with your order number and photos. We will raise it with the plant, and
          you will not be charged for water that was short or not fit for the agreed use. Refunds for amounts already
          paid are made by the plant within 7 working days.
        </p>

        <h2>Disputes</h2>
        <p>
          Write to <Mail />. We acknowledge within 24 hours and work with the plant and tanker partner to resolve the
          issue within {OPERATOR.grievanceDays} days. You keep all your rights under the Consumer Protection Act, 2019.
        </p>
      </>
    ),
  },

  "/accessibility": {
    title: "Accessibility",
    intro: "We want everyone to be able to use ReFlow.",
    body: () => (
      <>
        <h2>Our aim</h2>
        <p>
          ReFlow aims to meet the Web Content Accessibility Guidelines (WCAG) 2.1 at level AA. We design pages to work
          with a keyboard, give images text alternatives, label form fields, keep text contrast at 4.5:1 or more in light
          and dark mode, respect &ldquo;reduce motion&rdquo; settings, and offer a &ldquo;Skip to main content&rdquo;
          link. We haven&rsquo;t yet had an independent accessibility audit.
        </p>

        <h2>Known limitations</h2>
        <ul>
          <li>Maps are hard to use without sight or a mouse. Every map task has a text alternative: type an address instead of clicking the map, and order and trip details are listed as text.</li>
          <li>Some dashboard charts have a text summary next to them, but individual data points may not be read out.</li>
        </ul>

        <h2>Tell us about a problem</h2>
        <p>
          If something on ReFlow is hard to use, write to <Mail /> and tell us the page and what happened. We will reply
          within 7 days and help you complete your task another way in the meantime.
        </p>
      </>
    ),
  },
};

export default function Legal() {
  const { pathname } = useLocation();
  const user = useSession();
  const page = PAGES[pathname] ?? PAGES["/privacy"]!;
  const nav = user?.logged_in && roleNav[user.role] ? [...roleNav[user.role]!, publicNav[0]!] : publicNav;

  return (
    <AppShell nav={nav} title={page.title} subtitle="ReFlow legal information">
      <main className="page legal">
        <article className="card legal-doc" aria-labelledby="legal-title">
          <header>
            <h1 id="legal-title">{page.title}</h1>
            <p className="legal-intro">{page.intro}</p>
            <p className="legal-meta">Last updated {LEGAL_UPDATED} &middot; Version {LEGAL_VERSION}</p>
          </header>
          {page.body()}
        </article>
        <nav className="legal-index" aria-label="Other legal pages">
          {LEGAL_LINKS.filter((l) => l.href !== pathname).map((l) => (
            <a key={l.href} href={l.href}>{l.label}</a>
          ))}
        </nav>
        <LegalFooter />
      </main>
    </AppShell>
  );
}
