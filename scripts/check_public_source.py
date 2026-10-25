"""Check tracked/public files; never prints matched credential values."""
import ast
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{15,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b"
)
FORBIDDEN = {
    "secrets.txt", "sender_config.json", "settings.toml", "key.txt", ".env",
}
EXTENSIONS = {".db", ".sqlite", ".sqlite3", ".log", ".zip", ".exe", ".pem", ".key"}


def public_paths():
    if (ROOT / ".git").exists():
        p = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                           capture_output=True)
        return [ROOT / b.decode("utf-8") for b in p.stdout.split(b"\0") if b]
    # Export review before the directory is a Git working tree.
    return [p for p in ROOT.rglob("*") if p.is_file() and "__pycache__" not in p.parts]


def main():
    findings = []
    files = public_paths()
    for path in files:
        rel = path.relative_to(ROOT)
        if path.name in FORBIDDEN or path.suffix in EXTENSIONS or (
            rel.parts[0] in {"data", "output", "logs", "temp_files", "license"}
        ):
            findings.append(str(rel) + ": private/runtime path")
            continue
        if path.suffix in {".ttf", ".png"}:
            continue
        text = path.read_text(encoding="utf-8-sig")
        if TOKEN.search(text) or re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", text):
            findings.append(str(rel) + ": credential-like material")
        if path.suffix in {".py", ".spec"}:
            tree = ast.parse(text, filename=str(rel))
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                    names = [n.id for n in node.targets if isinstance(n, ast.Name)]
                    if (isinstance(node.value.value, (str, bytes))
                        and len(node.value.value) >= 16
                        and any(re.fullmatch(r"(?:SECRET|.*PASSWORD|.*API_KEY|.*ACCESS_TOKEN)", n)
                                for n in names)
                        and not str(rel).startswith("tests/")):
                        findings.append(f"{rel}:{node.lineno}: literal credential assignment")
    if findings:
        for finding in findings:
            print(finding)
        raise SystemExit("Public-source check FAILED; values were not displayed.")
    print(f"Public-source check OK: {len(files)} files. Heuristic check, not a security guarantee.")


if __name__ == "__main__":
    main()
