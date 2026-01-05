from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    targets = [
        root / "work_tracker" / "tracker" / "templates" / "tracker" / "map_gl_pilot.html",
        root / "work_tracker" / "tracker" / "templates" / "tracker" / "partials" / "map_ui.html",
        root / "work_tracker" / "tracker" / "templates" / "tracker" / "base.html",
    ]
    encodings = ["utf-8", "utf-8-sig", "cp1250", "cp1252"]
    success = []

    for path in targets:
        if not path.exists():
            print(f"Skipping {path} (not found)")
            continue

        text = None
        used = None
        for enc in encodings:
            try:
                text = path.read_text(encoding=enc)
                used = enc
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            print(f"Could not decode {path} with any supported encoding")
            return 1

        path.write_text(text, encoding="utf-8")
        success.append((path, used))

    for item, encoding in success:
        print(f"Re-saved {item} as UTF-8 (read with {encoding})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
