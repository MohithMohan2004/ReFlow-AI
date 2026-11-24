import { LEGAL_LINKS, OPERATOR } from "../lib/legal";

/** Footer with the legal links and who runs ReFlow. */
export function LegalFooter() {
  return (
    <footer className="legal-foot">
      <nav aria-label="Legal">
        <ul>
          {LEGAL_LINKS.map((l) => (
            <li key={l.href}><a href={l.href}>{l.label}</a></li>
          ))}
        </ul>
      </nav>
      <p>
        &copy; {new Date().getFullYear()} ReFlow &middot; A pilot run by {OPERATOR.name}, {OPERATOR.city} &middot;{" "}
        <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>
      </p>
      <p>Treated water is for non-drinking uses only. Map data &copy; OpenStreetMap contributors.</p>
    </footer>
  );
}
