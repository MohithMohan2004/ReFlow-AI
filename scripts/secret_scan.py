"""Scan every blob in every commit (all refs) for likely secrets.
Run: python3 scripts/secret_scan.py   (prints REDACTED previews only)
Use it where gitleaks/trufflehog are not available.
Prints commit, path, rule and a REDACTED preview only."""
import re, subprocess, sys
RULES = {
    "supabase-publishable": re.compile(r"sb_publishable_[A-Za-z0-9_-]{10,}"),
    "supabase-secret": re.compile(r"sb_secret_[A-Za-z0-9_-]{10,}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "postgres-url-with-password": re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:[^@\s]{6,}@"),
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    "aws-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "google-api-key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "github-token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "openai-key": re.compile(r"sk-[A-Za-z0-9]{32,}"),
    "azure-conn-string": re.compile(r"AccountKey=[A-Za-z0-9+/=]{40,}"),
    "env-assignment": re.compile(r"^(?:FLASK_SECRET_KEY|OCEMS_KEY_SECRET|SUPABASE_KEY|DATABASE_URL|RENDER_API_KEY|AZURE_[A-Z_]*SECRET|[A-Z_]*PASSWORD)\s*=\s*['\"]?[^\s'\"#]{8,}", re.M),
    "keystore-password": re.compile(r"(?:storePassword|keyPassword)\s*=\s*\S{6,}"),
}
SKIP = re.compile(r"(^|/)(node_modules|venv)/|\.(png|jpg|jpeg|gif|ico|pdf|xlsx|graphml|pkl|json\.gz|woff2?|ttf|apk|jar|keystore|jks)$")
blobs = {}
for line in subprocess.run(["git", "rev-list", "--all", "--objects"], capture_output=True, text=True).stdout.splitlines():
    parts = line.split(" ", 1)
    if len(parts) == 2 and not SKIP.search(parts[1]):
        blobs.setdefault(parts[0], parts[1])
types = subprocess.run(["git", "cat-file", "--batch-check"], input="\n".join(blobs), capture_output=True, text=True).stdout.splitlines()
hits = []
for t in types:
    sha, kind, size = t.split()
    if kind != "blob" or int(size) > 5_000_000:
        continue
    data = subprocess.run(["git", "cat-file", "-p", sha], capture_output=True).stdout.decode("utf-8", "ignore")
    for rule, rx in RULES.items():
        for m in rx.finditer(data):
            v = m.group(0)
            hits.append((rule, blobs[sha], sha[:10], v[:6] + "…" + f"[{len(v)} chars]"))
seen = set()
for h in hits:
    key = (h[0], h[1], h[3])
    if key not in seen:
        seen.add(key)
        print(*h, sep=" | ")
print(f"scanned {len(types)} objects, {len(seen)} distinct hits", file=sys.stderr)
