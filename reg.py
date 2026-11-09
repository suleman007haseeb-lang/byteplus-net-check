
import requests, json, re, time, random, string, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

def log(m):
    print(str(m), flush=True)

log("=== GITHUB ACTIONS BYTEPLUS REGISTRATION ===")

try:
    my_ip = requests.get("https://api.ipify.org", timeout=10).text.strip()
    log(f"IP: {my_ip}")
except Exception as e:
    log(f"IP: {e}")
    my_ip = "unknown"

# Check __spti fingerprint
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
try:
    r0 = S.get("https://console.byteplus.com/auth/signup", timeout=15, headers={"Accept": "text/html"})
    spti = S.cookies.get("__spti", "unknown")
    log(f"__spti: {spti}")
    log(f"BytePlus: {r0.status_code}")
except Exception as e:
    log(f"BytePlus GET: {e}")
    spti = "error"

OUR_SUFFIX = "bapxu9rXuEQMtPL"
if OUR_SUFFIX in spti:
    log("SAME fingerprint - GitHub Actions in same risk bucket as Oracle!")
else:
    log(f"DIFFERENT fingerprint! {spti} vs expected {OUR_SUFFIX}")

# Generate identity
USERNAME = "bp" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
PASSWORD = "ByteP1us!2026#"
log(f"Username: {USERNAME}")

# Get email
gm = requests.get("https://api.guerrillamail.com/ajax.php?f=get_email_address",
                  headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
gm_data = gm.json()
email = gm_data.get("email_addr", "")
sid = gm_data.get("sid_token", "")
log(f"Email: {email}")

# Setup session
S.headers.update({
    "Accept": "application/json",
    "Origin": "https://console.byteplus.com",
    "Referer": "https://console.byteplus.com/auth/signup",
    "X-Csrf-Token": "8b13c7ddf17a645320fff792b453c01c",
})

# Send OTP
r2 = S.post("https://console.byteplus.com/api/passport/login/sendSignupEmailforBP",
            json={"Email": email, "AccountType": "byteplus"}, timeout=15)
err = r2.json().get("ResponseMetadata", {}).get("Error", {}).get("Code", "")
log(f"sendEmail: {r2.status_code} ec={err!r}")

if err:
    log(f"BLOCKED: {err}")
    print(json.dumps({"phase": "otp_send", "error": err, "ip": my_ip, "spti": spti}))
    sys.exit(0)

# Wait for OTP
otp = None
for i in range(30):
    time.sleep(5)
    gm2 = requests.get(f"https://api.guerrillamail.com/ajax.php?f=check_email&seq=0&sid_token={sid}",
                       headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    mails = gm2.json().get("list", [])
    for mail in mails:
        subj = mail.get("mail_subject", "")
        if any(x in subj.lower() for x in ["byteplus", "verify", "code"]):
            mid = mail.get("mail_id")
            br = requests.get(f"https://api.guerrillamail.com/ajax.php?f=fetch_email&email_id={mid}&sid_token={sid}",
                              headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            body = br.json().get("mail_body", "") + br.json().get("mail_body_html", "")
            codes = re.findall(r'\b(\d{6})\b', re.sub(r'<[^>]+>', ' ', body))
            if codes:
                otp = codes[0]
                log(f"OTP: {otp}")
                break
    if otp:
        break
    if i < 3:
        log(f"  checking {(i+1)*5}s...")

if not otp:
    log("No OTP")
    print(json.dumps({"phase": "otp_wait", "error": "no_otp", "ip": my_ip, "spti": spti}))
    sys.exit(0)

# Playwright
reg_response = {}

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    )

    def on_resp(resp):
        if "signup" in resp.url and "api" in resp.url and "byteplus" in resp.url:
            try:
                txt = resp.text()
                reg_response["body"] = txt
                reg_response["status"] = resp.status
                log(f"SIGNUP RESP [{resp.status}]: {txt[:300]}")
            except:
                pass

    page = context.new_page()
    page.on("response", on_resp)
    page.goto("https://console.byteplus.com/auth/signup", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    log(f"Loaded: {page.url}")

    # Check browser spti
    bcs = context.cookies("https://console.byteplus.com")
    bspti = next((c["value"] for c in bcs if c["name"] == "__spti"), "")
    log(f"Browser __spti: {bspti}")

    page.evaluate("""() => { document.querySelectorAll('#cookiebanner,[id*="garfish"]').forEach(e=>e.remove()); }""")
    try:
        page.fill("#Email_input", email)
        page.fill("#Identity_input", USERNAME)
        page.fill("#Password_input", PASSWORD)
    except:
        try:
            page.locator('input[placeholder*="email" i]').first.fill(email)
            page.locator('input[placeholder*="user" i]').first.fill(USERNAME)
            page.locator('input[type="password"]').first.fill(PASSWORD)
        except:
            pass

    for cb in page.locator('input[type="checkbox"]').all():
        try:
            if not cb.is_checked(): cb.check(force=True)
        except: pass

    page.locator('button[type="submit"]').first.click(force=True)
    page.wait_for_timeout(2500)
    page.evaluate("""() => { document.querySelectorAll('#cookiebanner,[id*="garfish"]').forEach(e=>e.remove()); }""")

    for _ in range(15):
        if page.locator('input[maxlength="6"]:visible').count() > 0:
            break
        page.wait_for_timeout(1000)

    otp_inp = page.locator('input[maxlength="6"]')
    if otp_inp.count() > 0:
        otp_inp.first.fill(otp, force=True)
        log(f"OTP filled: {otp}")

    page.wait_for_timeout(300)
    page.evaluate("""() => { document.querySelectorAll('#cookiebanner,[id*="garfish"]').forEach(e=>e.remove()); }""")
    page.evaluate("""() => {
        const btn = [...document.querySelectorAll('button')].find(b=>/verify/i.test(b.textContent));
        if(btn){btn.click();}else{const s=document.querySelector('button[type="submit"]');if(s)s.click();}
    }""")
    page.wait_for_timeout(7000)
    final_url = page.url
    log(f"Final URL: {final_url}")
    browser.close()

success = "auth" not in final_url and "byteplus" in final_url
result = {
    "ip": my_ip, "spti": spti, "browser_spti": bspti,
    "email": email, "password": PASSWORD, "username": USERNAME,
    "final_url": final_url, "success": success,
}
if success:
    log("SUCCESS!")
else:
    err_body = reg_response.get("body", "")
    try:
        d = json.loads(err_body)
        ec = d.get("ResponseMetadata", {}).get("Error", {}).get("Code", "")
        result["error_code"] = ec
        log(f"Error: {ec}")
    except:
        result["error_body"] = err_body[:200]

print(json.dumps(result, indent=2))
