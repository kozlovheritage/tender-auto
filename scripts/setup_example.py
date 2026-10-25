"""Create an explicitly synthetic configuration without overwriting local files."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def copy_if_missing(source, destination):
    dst = ROOT / destination
    if dst.exists():
        print("Preserved:", destination)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / source, dst)
    print("Created example:", destination)


def main():
    for src, dst in (
        ("examples/sampler_config.txt", "sampler_config.txt"),
        ("examples/sampler_config.txt", "profiles/cemtorg/sampler_config.txt"),
        ("examples/sender_config.json.example", "sender_config.json"),
        ("examples/stop_factors.txt", "config/stop_factors.txt"),
        ("examples/stop_factors.txt", "profiles/cemtorg/stop_factors.txt"),
        ("profiles/cemtorg/profile.example.json", "profiles/cemtorg/profile.json"),
        ("profiles/cemtorg/catalog.example.json", "profiles/cemtorg/catalog.json"),
    ):
        copy_if_missing(src, dst)
    for name, content in (
        ("config/active_profile.txt", "cemtorg\n"),
        ("brands_extra.txt", "# Add your own additional brands here.\n"),
    ):
        path = ROOT / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print("Created example:", name)
    print("Examples only. Configure your own catalogue, AI and licence before use.")


if __name__ == "__main__":
    main()
