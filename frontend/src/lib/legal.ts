// Who runs ReFlow and the version of the legal documents. Shown on the
// legal pages, the home page and the footer. Keep LEGAL_VERSION in sync with
// LEGAL_VERSION in app.py: it is recorded with every acceptance.

export const LEGAL_VERSION = "2026-11-24";
export const LEGAL_UPDATED = "24 November 2026";

export const OPERATOR = {
  /** How the operator is named on every page. */
  name: "the ReFlow student project team",
  /** Short form for headings. */
  short: "ReFlow",
  status: "a non-commercial pilot run by a student project team; ReFlow is not a registered company",
  city: "Bengaluru, Karnataka, India",
  email: "reflow.circularity@gmail.com",
  /** Person who answers privacy questions and complaints (Grievance Officer). */
  grievanceOfficer: "Grievance Officer, ReFlow project team",
  /** Days within which a complaint is answered. */
  grievanceDays: 15,
} as const;

export const LEGAL_LINKS = [
  { href: "/privacy", label: "Privacy Policy" },
  { href: "/terms", label: "Terms of Use" },
  { href: "/cookies", label: "Cookie Policy" },
  { href: "/refunds", label: "Refunds & Cancellations" },
  { href: "/accessibility", label: "Accessibility" },
] as const;
