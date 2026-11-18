# -*- coding: utf-8 -*-
"""ContextStruct — standalone VLM model pre-fetch for distributors (v2).

Downloads BOTH local VLM models (3B light + 7B high accuracy) plus the
llama.cpp runtime fallback, verifies the downloaded sizes against the
sizes verified from the Hugging Face API, and prints a summary.

Use case (site distribution): run this once on a PC, then re-zip the whole
ContextStruct folder — app + vlm_runtime/ + models/ — as ONE full package
for your own download site, so end users need no first-run download.

Models are downloaded into the standard app data dir
(%APPDATA%\\ContextStruct\\models on Windows,
~/Library/Application Support/ContextStruct/models on macOS,
~/.contextstruct/models on other systems). For a re-zipped full package, copy that models folder next to
app.py as ./models in the package: at runtime ContextStruct checks the
app data dir first and then the bundled ./models folder, so a package
that contains ./models works on end-user PCs with no download at all.
The full flow is documented in README.txt ("配布者向けフルパッケージ").

Exit code 0 when every file verifies, 1 otherwise. No GUI required.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vlm_local


def _fmt(n):
    return f"{n:,} bytes ({n / 1e9:.2f} GB)"


def main():
    mdir = vlm_local.models_dir()
    print("=" * 68)
    print(" ContextStruct — VLM model pre-fetch (3B + 7B)")
    print(f" Models dir: {mdir}")
    print("=" * 68)
    ok_all = True

    if not vlm_local.find_runtime_binary():
        print("\n[Runtime] bundled llama.cpp not found — downloading fallback runtime…")
        try:
            vlm_local.download_runtime(lambda d, t, f: print(f"  {f}: {d * 100 // t if t else 0}%", end="\r"))
            print("\n[Runtime] OK")
        except Exception as e:
            print(f"\n[Runtime] FAILED: {e}")
            ok_all = False
    else:
        print(f"\n[Runtime] bundled OK: {vlm_local.find_runtime_binary()}")

    for key in ("3b", "7b"):
        spec = vlm_local.model_spec(key)
        print(f"\n[{key.upper()}] {spec['repo']}  (total approx. {spec['approx_gb']} GB)")
        def cb(done, total, fname, _k=key):
            if total:
                print(f"  {fname}: {done * 100 // total}% ({done:,}/{total:,})", end="\r")
        try:
            st = vlm_local.download_models(cb, model_key=key)
        except Exception as e:
            print(f"\n[{key.upper()}] DOWNLOAD FAILED: {e}")
            ok_all = False
            continue
        print()
        for fname, expected in ((spec["model_file"], spec["model_bytes"]), (spec["mmproj_file"], spec["mmproj_bytes"])):
            info = st["files"][fname]
            real = info["size"]
            match = (real == expected)
            status = "OK (size verified)" if match else ("OK (present, size differs from API listing)" if info["ok"] else "MISSING/INCOMPLETE")
            if not info["ok"]:
                ok_all = False
            print(f"  {fname}\n    expected {_fmt(expected)}\n    on disk  {_fmt(real)}  -> {status}")
    print("\n" + "=" * 68)
    print(" RESULT:", "ALL MODELS READY" if ok_all else "SOME FILES FAILED — re-run to resume/complete")
    print("=" * 68)
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
