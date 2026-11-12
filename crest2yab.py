#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["cryptography>=41"]
# ///
"""crest2yab - move spaces, tabs and cookies from the Crest browser to the Yab browser (macOS).

Unofficial. Not affiliated with, endorsed by, or supported by the makers of Crest or Yab.
Use at your own risk - see README.md and LICENSE.

Steps (run in order):
  plan              dry run: show what would move, write a preview, change nothing
  check-keys        read both browsers' Keychain keys and prove cookies decrypt (no values shown)
  write-spaces      [Yab quit] back up Yab, then REPLACE its spaces and tabs with Crest's
  profiles          show which Yab cookie store each space uses
  inject-cookies    [both quit] copy each Crest space's cookies into its Yab space

Cookie values are only ever held in memory. Nothing decrypted is printed, logged or written
anywhere except back into Yab's own (encrypted) cookie database. No network access.
"""
import argparse, hashlib, json, os, shutil, sqlite3, subprocess, sys, time
from collections import Counter

try:
    from cryptography.hazmat.primitives import hashes, padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    sys.exit("missing dependency: run with `uv run crest2yab.py ...` or `pip install cryptography`")

TESTED = "Crest 0.9.1 and Yab 0.47.10 on macOS"
AS = os.path.expanduser("~/Library/Application Support")
CREST, YAB = f"{AS}/Crest", f"{AS}/Yab"
CREST_APP, YAB_APP = "/Applications/Crest.app", "/Applications/yab.app"
APPLE_EPOCH = 978307200                           # Crest stores times as seconds since 2001
SHARED = "00000000-0000-0000-0000-000000000001"   # Yab's built-in space / shared cookie store
GLOBAL_PINS = "00000000-0000-0000-0000-000000000A11"
SF_EMOJI = {"globe": "🌎", "square.grid": "🧩", "sidebar": "💼", "house": "🏠", "briefcase": "💼",
            "star": "⭐", "heart": "❤️", "book": "📚", "hammer": "🔨", "gamecontroller": "🎮"}


def die(msg):
    sys.exit(f"error: {msg}")


def running(app_path):
    return subprocess.run(["pgrep", "-f", f"{app_path}/"], capture_output=True).returncode == 0


def require_quit(*apps):
    for app in apps:
        if running(app):
            die(f"{os.path.basename(app)} is running - quit it with Cmd+Q first")


# ---------------------------------------------------------------- Crest -> Yab model
def crest_core():
    db = f"{CREST}/ControlPlane/session.sqlite"
    if not os.path.exists(db):
        die(f"Crest data not found at {db}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    row = con.execute("select data from checkpoint where part='core'").fetchone()
    if not row:
        die("Crest's space data has an unexpected format (newer Crest version?)")
    return json.loads(row[0])


def rid(x):
    return x.get("rawValue") if isinstance(x, dict) else x


def hexcolor(c):
    return "".join(f"{round(max(0, min(1, c[k])) * 255):02X}" for k in ("red", "green", "blue"))


def first_letter(s):
    return next((ch.upper() for ch in s or "" if ch.isalnum()), "•")


def convert_space(space, yab_id):
    folders = {rid(f["id"]): f for f in space.get("folders", [])}

    def chain(fid):  # [root, ..., immediate folder]
        out, seen = [], set()
        while fid and fid in folders and fid not in seen:
            seen.add(fid)
            out.insert(0, folders[fid])
            fid = rid(folders[fid].get("parentID"))
        return out

    def base(t):
        url = t.get("url") or t.get("savedURL")
        if not url:
            return None
        d = {"id": rid(t["id"]), "title": t.get("title") or url, "url": url, "engine": "chromium",
             "seen": t.get("lastActivatedAt", 0) + APPLE_EPOCH}
        if t.get("customTitle"):
            d["name"] = t["customTitle"]
        return d

    pins, kept, opened, saved, skipped = [], [], [], [], 0
    for t in space.get("tabs", []):
        b = base(t)
        if not b:
            skipped += 1                      # Start Page / Settings - nothing to restore
            continue
        home = t.get("savedURL") or b["url"]
        if t.get("placement") == "pinned":
            b.update(home=home, homeTitle=b["title"], pin=first_letter(b.get("name") or b["title"]))
            pins.append(b)
        elif t.get("placement") == "saved":
            b.update(home=home, homeTitle=b["title"], kept=True)
            fc = chain(rid(t.get("folderID")))
            if fc:
                imm = fc[-1]
                b.update(folder=rid(imm["id"]), folderName=imm["title"],
                         folderOpen=not imm.get("isCollapsed", True))
                if len(fc) > 1:
                    b["folderPath"] = [{"id": rid(f["id"]), "name": f["title"],
                                        "open": not f.get("isCollapsed", True)} for f in fc[:-1]]
            saved.append((b, [rid(f["id"]) for f in fc]))
        else:
            opened.append(b)

    def emit(items, depth):  # keep each folder's tabs together, in order of first appearance
        groups = {}
        for b, path in items:
            groups.setdefault(path[depth] if len(path) > depth else ("tab", b["id"]), []).append((b, path))
        for key, grp in groups.items():
            if isinstance(key, tuple):
                kept.append(grp[0][0])
            else:
                kept.extend(b for b, p in grp if len(p) == depth + 1)
                emit([(b, p) for b, p in grp if len(p) > depth + 1], depth + 1)
    emit(saved, 0)

    session = {"tabs": pins + kept + opened, "active": len(pins) + len(kept) if opened else 0}
    if not opened:
        session["nothingInFront"] = True
    sym = space.get("symbol", "")
    icon = (sym.split("crest.emoji:", 1)[1] if sym.startswith("crest.emoji:")
            else next((e for k, e in SF_EMOJI.items() if sym.startswith(k)), "🌐"))
    colors = (space.get("branding") or {}).get("colors") or []
    yspace = {"id": yab_id, "name": space["name"], "icon": icon, "ownSignIns": yab_id != SHARED,
              "paint": {"grain": False, "grainAmount": 0, "transparency": 0, "swatch": "custom",
                        "color": hexcolor(colors[0]) if colors else "333333"}}
    stats = dict(pinned=len(pins), saved=len(kept), open=len(opened), folders=len(folders), skipped=skipped)
    return yspace, session, stats


def build(shared_name=None, only=None):
    core = crest_core()
    spaces = core.get("spaces") or die("no spaces found in Crest")
    if shared_name:
        hits = [s for s in spaces if s["name"] == shared_name]
        if len(hits) != 1:
            die(f"--shared {shared_name!r} must match exactly one Crest space: "
                f"{[s['name'] for s in spaces]}")
        shared = hits[0]
    else:  # default: Crest's default space, else the first one
        dflt = rid(core.get("defaultSpaceID"))
        shared = next((s for s in spaces if rid(s["id"]) == dflt), spaces[0])
    dupes = [n for n, c in Counter(s["name"] for s in spaces).items() if c > 1]
    plan = []
    for s in spaces:
        yid = SHARED if s is shared else rid(s["id"])
        ys, sess, st = convert_space(s, yid)
        plan.append(dict(name=s["name"], yab=ys, session=sess, stats=st,
                         crest_cookies=f"{CREST}/Chromium/Crest-{s['profile']['id']}/Cookies"))
    if only:
        if dupes and set(only) & set(dupes):
            die(f"space names are not unique ({dupes}); rename them in Crest first")
        unknown = set(only) - {p["name"] for p in plan}
        if unknown:
            die(f"unknown space(s) {sorted(unknown)}; Crest has {[p['name'] for p in plan]}")
        plan = [p for p in plan if p["name"] in only]
    return plan


# ---------------------------------------------------------------- Chromium cookie crypto (macOS)
IV = b" " * 16


def keychain_key(service):
    r = subprocess.run(["security", "find-generic-password", "-w", "-s", service],
                       capture_output=True, text=True)
    if r.returncode:
        die(f"could not read Keychain item {service!r} - did you click Deny? ({r.stderr.strip()})")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt", iterations=1003)
    return kdf.derive(r.stdout.strip().encode())


def decrypt(key, blob, host, version):
    if blob[:3] != b"v10":
        raise ValueError("unsupported cookie encryption")
    d = Cipher(algorithms.AES(key), modes.CBC(IV)).decryptor()
    u = padding.PKCS7(128).unpadder()
    plain = u.update(d.update(blob[3:]) + d.finalize()) + u.finalize()
    if version >= 24:  # newer Chromium prefixes the value with sha256(host) - a free key check
        if plain[:32] != hashlib.sha256(host.encode()).digest():
            raise ValueError("wrong key")
        plain = plain[32:]
    return plain


def encrypt(key, value, host, version):
    if version >= 24:
        value = hashlib.sha256(host.encode()).digest() + value
    p = padding.PKCS7(128).padder()
    e = Cipher(algorithms.AES(key), modes.CBC(IV)).encryptor()
    return b"v10" + e.update(p.update(value) + p.finalize()) + e.finalize()


def db_version(con):
    return int(con.execute("select value from meta where key='version'").fetchone()[0])


def verify_db(path, key):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    v, ok, bad = db_version(con), 0, 0
    for host, blob in con.execute("select host_key, encrypted_value from cookies where length(encrypted_value)>0"):
        try:
            decrypt(key, blob, host, v)
            ok += 1
        except Exception:
            bad += 1
    con.close()
    return v, ok, bad


def profile_map():
    """Yab space id -> its Chromium profile folder, from Yab's own ChromiumProfiles records."""
    m, d = {}, f"{YAB}/ChromiumProfiles"
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if f.endswith(".json"):
            rec = json.load(open(f"{d}/{f}"))
            m[rec.get("logical")] = f"{YAB}/Chromium/space-{rec.get('physical')}"
    return m


# ---------------------------------------------------------------- commands
def cmd_plan(a):
    prev = os.path.abspath(a.preview)
    os.makedirs(prev, exist_ok=True)
    plan = build(a.shared)
    json.dump([p["yab"] for p in plan], open(f"{prev}/spaces.json", "w"), ensure_ascii=False, indent=1)
    for p in plan:
        json.dump(p["session"], open(f"{prev}/session-{p['yab']['id']}.json", "w"), ensure_ascii=False, indent=1)
        n = hosts = "?"
        if os.path.exists(p["crest_cookies"]):
            con = sqlite3.connect(f"file:{p['crest_cookies']}?mode=ro", uri=True)
            n, hosts = con.execute("select count(*), count(distinct host_key) from cookies").fetchone()
        tag = "shared sign-ins" if p["yab"]["id"] == SHARED else "own sign-ins"
        print(f"{p['name']:<16} [{tag}] {p['stats']}  cookies={n} ({hosts} sites)")
    print(f"\nTested with {TESTED}. Preview (nothing changed): {prev}")


def cmd_check_keys(a):
    ck = keychain_key("Crest Safe Storage")
    for p in build(a.shared):
        if os.path.exists(p["crest_cookies"]):
            v, ok, bad = verify_db(p["crest_cookies"], ck)
            print(f"Crest {p['name']:<16} {ok} cookies decrypt OK, {bad} failed")
    yk = keychain_key("Yab Safe Storage")
    for d in sorted(os.listdir(f"{YAB}/Chromium")):
        c = f"{YAB}/Chromium/{d}/Cookies"
        if d.startswith("space-") and os.path.exists(c):
            v, ok, bad = verify_db(c, yk)
            print(f"Yab   {d:<16} {ok} cookies decrypt OK, {bad} failed")


def cmd_write_spaces(a):
    require_quit(YAB_APP)
    if not os.path.isdir(YAB):
        die("Yab data not found - open Yab once, finish its setup, quit it, then retry")
    if not a.yes:
        ans = input("This REPLACES all spaces and tabs in Yab (a backup is made first). Type 'yes': ")
        if ans.strip().lower() != "yes":
            die("aborted")
    plan = build(a.shared)
    bak = f"{AS}/Yab.backup-{time.strftime('%Y%m%d-%H%M%S')}"
    subprocess.run(["cp", "-Rc", YAB, bak], check=True)  # APFS clone: instant, no extra space
    print(f"backup: {bak}")
    for f in os.listdir(YAB):
        if f.startswith("session-") and f.endswith(".json"):
            os.remove(f"{YAB}/{f}")
    shutil.rmtree(f"{YAB}/crash-sessions", ignore_errors=True)
    pdir = f"{YAB}/ChromiumProfiles"
    for f in os.listdir(pdir) if os.path.isdir(pdir) else []:
        if not f.startswith(SHARED):
            os.remove(f"{pdir}/{f}")

    def w(name, obj):
        json.dump(obj, open(f"{YAB}/{name}", "w"), ensure_ascii=False)
    w("spaces.json", [p["yab"] for p in plan])
    for p in plan:
        w(f"session-{p['yab']['id']}.json", p["session"])
        print(f"wrote {p['name']}: {p['stats']}")
    w(f"session-{GLOBAL_PINS}.json", {"tabs": [], "active": 0})
    w("session.json", {"nothingInFront": True, "tabs": [], "active": 0})
    w("windows.json", {"open": [], "closed": []})
    print("\nNext: open Yab, click into EVERY space and let one page load in each, quit Yab (Cmd+Q),"
          "\nthen run `profiles` and `inject-cookies`.")


def cmd_profiles(a):
    m = profile_map()
    for p in build(a.shared):
        d = m.get(p["yab"]["id"])
        state = "ready" if d and os.path.exists(f"{d}/Cookies") else "NOT YET - load a page in this space in Yab"
        print(f"{p['name']:<16} {state}")


def cmd_inject(a):
    require_quit(YAB_APP, CREST_APP)
    m = profile_map()
    plan = build(a.shared, a.spaces or None)
    missing = [p["name"] for p in plan if not os.path.exists(f"{m.get(p['yab']['id'], '')}/Cookies")]
    if missing:
        print(f"SKIPPING {missing}: Yab has no cookie store for it yet. Load a page in that space,"
              f" quit Yab, then rerun: inject-cookies {' '.join(repr(n) for n in missing)}")
        plan = [p for p in plan if p["name"] not in missing]
    if not plan:
        return
    ck, yk = keychain_key("Crest Safe Storage"), keychain_key("Yab Safe Storage")
    for p in plan:
        if not os.path.exists(p["crest_cookies"]):
            print(f"{p['name']:<16} no cookies in Crest, skipped")
            continue
        src = sqlite3.connect(f"file:{p['crest_cookies']}?mode=ro", uri=True)
        dst_path = f"{m[p['yab']['id']]}/Cookies"
        shutil.copy2(dst_path, dst_path + ".pre-crest")
        dst = sqlite3.connect(dst_path)
        sv, dv = db_version(src), db_version(dst)
        dcols = {r[1] for r in dst.execute("pragma table_info(cookies)")}
        cols = [r[1] for r in src.execute("pragma table_info(cookies)") if r[1] in dcols]
        ei, hi = cols.index("encrypted_value"), cols.index("host_key")
        rows, bad = [], 0
        for r in src.execute(f"select {','.join(cols)} from cookies"):
            r = list(r)
            if r[ei]:
                try:
                    r[ei] = encrypt(yk, decrypt(ck, r[ei], r[hi], sv), r[hi], dv)
                except Exception:
                    bad += 1
                    continue
            rows.append(r)
        with dst:
            dst.execute("delete from cookies")
            dst.executemany(f"insert or replace into cookies ({','.join(cols)}) "
                            f"values ({','.join('?' * len(cols))})", rows)
        dst.close()
        _, ok, fail = verify_db(dst_path, yk)
        print(f"{p['name']:<16} copied {len(rows)} cookies (skipped {bad}); check in Yab: {ok} OK, {fail} failed")
    ec = f"{YAB}/engine-cookies"  # Yab's cross-engine bookkeeping for the old cookies; let it rebuild
    if os.path.isdir(ec) and not os.path.exists(ec + ".pre-crest"):
        shutil.move(ec, ec + ".pre-crest")
    print("\nDone. Open Yab and check a few sites you were logged into. Google may ask you to sign in again.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shared", metavar="SPACE",
                    help="Crest space that takes Yab's built-in shared space (default: Crest's default space)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="dry run")
    p.add_argument("--preview", default="crest2yab-preview", help="folder for the preview JSON")
    p.set_defaults(fn=cmd_plan)
    sub.add_parser("check-keys", help="test cookie decryption").set_defaults(fn=cmd_check_keys)
    p = sub.add_parser("write-spaces", help="replace Yab's spaces and tabs with Crest's")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.set_defaults(fn=cmd_write_spaces)
    sub.add_parser("profiles", help="show cookie store status per space").set_defaults(fn=cmd_profiles)
    p = sub.add_parser("inject-cookies", help="copy cookies into Yab")
    p.add_argument("spaces", nargs="*", help="only these Crest space names (default: all)")
    p.set_defaults(fn=cmd_inject)
    if sys.platform != "darwin":
        die("macOS only")
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
