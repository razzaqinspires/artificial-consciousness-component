"""python tools/pack.py [--test] -> ac-kernel-nadi.zip"""
import os, sys, zipfile, hashlib, json, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILES = [
    "ac/__init__.py", "ac/__main__.py", "ac/config.py", "ac/util.py", "ac/neuro.py",
    "ac/nadi.py", "ac/intero.py", "ac/rasa.py", "ac/ingat.py", "ac/panggung.py",
    "ac/diri.py", "ac/kehendak.py", "ac/sapa.py", "ac/mimpi.py", "ac/appraise_llm.py",
    "ac/metrics.py", "ac/kernel.py", "ac/bridge.py", "ac/cli.py", "ac/selftest.py",
    "examples/integrate.py", "tools/pack.py", "requirements.txt", "README.md",
    "ac_config.example.json",
]
SKIP = ("mem", "state", "__pycache__", ".git", ".pytest_cache", "dist", "build")


def check():
    print("-- VALIDASI MANIFEST --")
    missing = []
    for f in FILES:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            print("OK   %s (%d B)" % (f, os.path.getsize(p)))
        else:
            print("HILANG %s" % f)
            missing.append(f)
    return missing


def build(out="ac-kernel-nadi.zip"):
    missing = check()
    if missing:
        print("\n%d file hilang. Lengkapi dulu." % len(missing))
        sys.exit(1)
    if "--test" in sys.argv:
        print("\n-- SELFTEST --")
        if os.system('"%s" -m ac.selftest' % sys.executable) != 0:
            print("selftest gagal - packing dibatalkan.")
            sys.exit(1)
    path = os.path.join(ROOT, out)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in FILES:
            z.write(os.path.join(ROOT, f), f)
        if os.path.exists(os.path.join(ROOT, "build_nadi.py")):
            z.write(os.path.join(ROOT, "build_nadi.py"), "build_nadi.py")
        manifest = {"built": time.time(),
                    "sha256": {f: hashlib.sha256(open(os.path.join(ROOT, f), "rb").read()).hexdigest()[:16]
                               for f in FILES}}
        z.writestr("BUILD_MANIFEST.json", json.dumps(manifest, indent=2))
    print("\nOK %s (%d B, %d file)" % (path, os.path.getsize(path), len(FILES)))
    print("Memori & state sengaja tidak ikut dikemas.")


if __name__ == "__main__":
    build()
