import sys, os
sys.path.insert(0, '.')
from api import auth  # importing this loads .env
# clear AFTER import, so the real .env values don't leak into the assertions
for v in ("APP_USERNAME","APP_PASSWORD","USER_NAME","PASSWORD","USERNAME",
          "APP_USER","APP_PASS","AUTH_SECRET"):
    os.environ.pop(v, None)
ok = fail = 0
def chk(l, c, x=""):
    global ok, fail
    (globals().__setitem__('ok', ok+1), print(f"  PASS {l}")) if c else (globals().__setitem__('fail', fail+1), print(f"  FAIL {l} {x}"))

print("1. no creds -> auth off (local dev stays open)")
chk("disabled", auth.auth_enabled() is False)

print("2. the .env spelling you actually use")
os.environ["USER_NAME"] = "yavor"; os.environ["PASSWORD"] = "s3cret-pass"
chk("USER_NAME/PASSWORD enables auth", auth.auth_enabled() is True)
chk("creds read", auth.__dict__["_creds"]() == ("yavor", "s3cret-pass"))

print("3. documented spelling still wins")
os.environ["APP_USERNAME"] = "judges"; os.environ["APP_PASSWORD"] = "judge-pass"
chk("APP_* takes precedence", auth._creds() == ("judges", "judge-pass"))

print("4. token round-trip")
t = auth.create_token("judges")
chk("valid token verifies", auth.verify_token(t) == "judges")
chk("tampered token rejected", auth.verify_token(t[:-4] + "aaaa") is None)
chk("garbage rejected", auth.verify_token("not-a-token") is None)

print("5. login endpoint")
from fastapi import HTTPException
chk("correct creds -> token", auth.login(username="judges", password="judge-pass")["token"] is not None)
for u, p, label in [("judges","wrong","bad password"), ("nope","judge-pass","bad user")]:
    try:
        auth.login(username=u, password=p); chk(label+" rejected", False, "no raise")
    except HTTPException as e:
        chk(label+" -> 401", e.status_code == 401)

print("6. non-ASCII password returns 401, not 500")
os.environ["APP_PASSWORD"] = "парола-кирилица"
try:
    auth.login(username="judges", password="wrong"); chk("non-ascii", False, "no raise")
except HTTPException as e:
    chk("non-ascii -> 401 not 500", e.status_code == 401, f"got {e.status_code}")
except TypeError as e:
    chk("non-ascii -> 401 not 500", False, f"TypeError: {e}")
chk("non-ascii correct password works", auth.login(username="judges", password="парола-кирилица")["token"] is not None)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
