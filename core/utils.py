import os
import re
import json
import time
import smtplib
import threading
from datetime import datetime
from urllib.parse import urlparse
import dns.resolver
from PIL import Image
from supabase import create_client, Client
from google import genai

# Load .env safely
if os.path.exists('.env'):
    with open('.env', 'r', encoding='utf-8') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k.strip()] = v.strip()

# Global Gemini rate limiting lock
GEMINI_LOCK = threading.Lock()

def get_supabase_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if url and key:
        return create_client(url, key)
    return None

def get_gemini_client():
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return genai.Client(api_key=key)
    return None

def log(msg: str, domain: str = "SYSTEM"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{domain}] {msg}")

def get_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
            
        social_sites = ['instagram.com', 'facebook.com', 'twitter.com', 'x.com', 'linkedin.com', 'youtube.com', 'pinterest.com']
        if domain in social_sites:
            path = parsed.path.strip('/')
            if path:
                account = path.split('/')[0]
                domain = f"{domain}/{account}"
                
        return domain
    except Exception:
        return ""

def enforce_image_limits(image_path: str, max_height: int = 8000):
    try:
        with Image.open(image_path) as img:
            if img.height > max_height:
                cropped = img.crop((0, 0, img.width, max_height))
                cropped.save(image_path)
    except Exception:
        pass

def _acquire_lock(lock_file: str):
    while True:
        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            time.sleep(0.1)

def _release_lock(lock_file: str):
    if os.path.exists(lock_file):
        os.remove(lock_file)

def is_seen(db_file: str, domain: str) -> bool:
    lock_file = db_file + ".lock"
    _acquire_lock(lock_file)
    try:
        if not os.path.exists(db_file):
            return False
        with open(db_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return domain in data
    except Exception:
        return False
    finally:
        _release_lock(lock_file)

def mark_seen(db_file: str, domain: str, score: float, status: str):
    lock_file = db_file + ".lock"
    _acquire_lock(lock_file)
    try:
        data = {}
        if os.path.exists(db_file):
            try:
                with open(db_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data[domain] = {
            'timestamp': datetime.now().isoformat(),
            'score': score,
            'status': status
        }
        with open(db_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    finally:
        _release_lock(lock_file)

def clear_low_scores(db_file: str):
    lock_file = db_file + ".lock"
    _acquire_lock(lock_file)
    try:
        if os.path.exists(db_file):
            with open(db_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            new_data = {k: v for k, v in data.items() if v.get('status') != 'LOW_SCORE'}
            with open(db_file, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, indent=2)
            log("Low scores cleared from database.")
    finally:
        _release_lock(lock_file)

def extract_emails(html: str):
    import urllib.parse
    html = urllib.parse.unquote(html)
    emails = set(re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', html))
    fp = ['sentry.io', 'wixpress.com', 'example.com', '.png', '.jpg', '.jpeg']
    return [e for e in emails if not any(x in e.lower() for x in fp)]

def verify_email(email: str) -> str:
    try:
        domain = email.split('@')[1]
        resolver = dns.resolver.Resolver()
        resolver.timeout = 5
        resolver.lifetime = 5
        records = resolver.resolve(domain, 'MX')
        mxRecord = str(records[0].exchange)
    except Exception:
        return "NONE_FOUND"
    
    try:
        server = smtplib.SMTP(timeout=5)
        server.set_debuglevel(0)
        server.connect(mxRecord)
        server.helo(server.local_hostname)
        server.mail('test@example.com')
        code, _ = server.rcpt(str(email))
        server.quit()
        if code == 250:
            return "VERIFIED"
        elif code == 550:
            return "DEAD_BOUNCE"
        else:
            return "MX_VALID"
    except Exception:
        return "MX_VALID"

def translate_flaws(flaws: list):
    translated = []
    for flaw in flaws:
        if "Template text found" in flaw:
            exact = flaw.split(": ", 1)[-1] if ":" in flaw else flaw
            translated.append((flaw, f"Shows up on Google search results as an unfinished template ('{exact}'), which hurts how Google matches your services and makes customers wonder if the site is still active."))
        elif "Outdated Copyright" in flaw or "Broken Links or Missing Images" in flaw:
            translated.append((flaw, "Creates an 'Are they still in business?' hesitation when new customers click over from Google Maps and see outdated dates or broken page elements."))
        elif "Missing SSL" in flaw:
            translated.append((flaw, "Triggers a 'Not Secure' warning in Chrome and Safari before customers even read the page, scaring homeowners away from submitting the contact form."))
        elif "Mobile-Only Site Stretched on Desktop" in flaw or "Broken Mobile Layout (Overflow)" in flaw:
            translated.append((flaw, "Forces customers to pinch-and-zoom on phones (or stretches a mobile column across office desktops), causing visitors to bounce back to Google Maps."))
        elif "Fake/Basic Quote Form" in flaw:
            translated.append((flaw, "Forces you into manual phone and email tag just to collect basic job details that an interactive estimate builder could price and qualify automatically."))
        elif "PDF Trap for Pricing/Services" in flaw:
            translated.append((flaw, "Forces mobile customers to download a static PDF file they can't click or book from, instead of letting them tap their options in an interactive calculator."))
        elif "Critical Accessibility Issues" in flaw:
            translated.append((flaw, "Creates a massive legal liability under the ADA, and literally blocks screen-reader users from navigating or buying from the site."))
        elif "Serious Accessibility Issues" in flaw:
            translated.append((flaw, "Color contrast or text readability is so poor that elderly customers or those with visual impairments will leave the site rather than struggle to read it."))
        elif "A11y Audit Blocked" in flaw:
            translated.append((flaw, "The site's security policy blocked our accessibility scan, but this usually points to older, inflexible code that is difficult to update or integrate with modern marketing tools."))
        elif "Cluttered Image Gallery" in flaw:
            translated.append((flaw, "Dumps too many photos onto the page at once instead of using a modern swipeable slider, making the site look cheap and slowing down the load time on phones."))
        elif "Duplicated Navigation Links" in flaw:
            translated.append((flaw, "Confuses Google's SEO bots and clutters the menu, dropping the site's ranking potential for local searches."))
        elif "Unclickable Phone Number" in flaw:
            translated.append((flaw, "Forces mobile users to memorize and manually dial your number instead of tapping to call, which is a proven conversion killer."))
        elif "SEO Fatal Errors" in flaw:
            translated.append((flaw, "Google's own PageSpeed Insights API flagged this site as literally uncrawlable or heavily penalized, meaning it is bleeding free traffic every single day."))
        elif "Third-Party Script Bloat" in flaw:
            translated.append((flaw, "Overloaded with tracking scripts and plugins that drag down the loading speed and hurt mobile conversions (Google penalizes slow sites)."))
        elif "Mobile Tap Target" in flaw:
            translated.append((flaw, "Buttons and links are too small or too close together for human thumbs to reliably tap on a phone, causing accidental clicks and frustration."))
        else:
            translated.append((flaw, f"Technical flaw: {flaw}"))
    return translated

# Blocklists and Known Platforms
MARKETPLACES = [
    'angi.com', 'thumbtack.com', 'homeadvisor.com', 'lawnstarter.com', 'houzz.com', 'porch.com'
]

FRANCHISES = [
    'midas.com', 'trugreen.com', 'mrhandyman.com', 'mosquitojoe.com', 
    'twomenandatruck.com', 'meineke.com', 'yelp.com', 'nextdoor.com', 
    'walmart.com', 'tractorsupply.com', 'dollargeneral.com', 'wyndhamhotels.com', 
    'wyndham.com', 'hilton.com', 'marriott.com', 'homedepot.com', 'lowes.com', 
    'target.com', 'bestbuy.com', 'cvs.com', 'walgreens.com', 'autozone.com', 
    'oreillyauto.com', 'advanceautoparts.com', 'napaonline.com',
    
    # Thrift / Consignment
    'goodwill.org', 'goodwill.com', 'salvationarmy.org', 'salvationarmyusa.org',
    'platoscloset.com', 'styleencore.com', 'clothesmentor.com', 'uptowncheapskate.com',
    
    # Hardware
    'acehardware.com', 'truevalue.com', 'harborfreight.com', 'northerntool.com',
    
    # Pawn Shops
    'firstcash.com', 'ezpawn.com', 'cashamerica.com', 'valuepawnandjewelry.com',
    
    # Bookstores
    'barnesandnoble.com', 'booksamillion.com', 'hpb.com',
    
    # Bike Shops / Sporting Goods
    'trekbikes.com', 'specialized.com', 'giant-bicycles.com', 'performancebike.com', 'rei.com', 'dickssportinggoods.com'
]

SAAS_DOMAINS = [
    'getjobber.com', 'clienthub.getjobber.com', 'housecallpro.com', 
    'servicetitan.com', 'vagaro.com', 'mindbodyonline.com', 
    'acuityscheduling.com', 'squarespace.com/appointments', 
    'squareup.com/appointments', 'calendly.com', 'tekmetric.com', 'shop-ware.com',
    'savvycal.com', 'staysavvy.com', 'savvy.pet'
]
