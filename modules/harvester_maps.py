import re
import time
import urllib.parse
from urllib.parse import urlparse
from typing import List, Generator
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth

from core.models import Lead
from core.utils import log, get_domain, is_seen, mark_seen, FRANCHISES

class MapsHarvester:
    """
    Harvests local business leads from Google Maps using Playwright.
    """
    name: str = "MapsHarvester"

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.db_file = self.config.get("db_file", "seen_leads.json")
        self.max_leads = self.config.get("max_leads", 0)

    def harvest(self, query: str, location: str) -> List[Lead]:
        leads: List[Lead] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            Stealth().apply_stealth_sync(context)
            page = context.new_page()

            search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query + ' in ' + location)}"
            log(f"Searching Google Maps: {query} in {location}")
            
            try:
                page.goto(search_url, timeout=30000)
                page.wait_for_selector("a[href*='https://www.google.com/maps/place/']", timeout=15000)
            except PlaywrightTimeoutError:
                log(f"[-] No results found or timeout for '{query}' in '{location}'.")
                browser.close()
                return leads

            try:
                first_el = page.locator("a[href*='https://www.google.com/maps/place/']").first
                first_el.hover()
            except Exception:
                pass

            last_count = 0
            retries = 0
            while True:
                page.mouse.wheel(0, 10000)
                time.sleep(1.5)
                count = page.locator("a[href*='https://www.google.com/maps/place/']").count()
                if count == last_count:
                    retries += 1
                    if retries >= 3:
                        break
                else:
                    retries = 0
                    last_count = count
                    if count > 40:
                        break

            links = page.locator("a[href*='https://www.google.com/maps/place/']").all()

            for l in links:
                parent = l.locator("xpath=..")
                website_loc = parent.locator("a[data-value='Website']")
                
                url = None
                if website_loc.count() > 0:
                    url = website_loc.first.get_attribute("href")
                else:
                    # Deep Harvest: Google Maps hid the Website button on the list view.
                    # Click into the profile and extract from the detail pane.
                    try:
                        l.click(force=True)
                        page.wait_for_timeout(1500) # Wait for pane to slide in
                        detail_website = page.locator("a[data-item-id='authority']:visible")
                        if detail_website.count() > 0:
                            url = detail_website.first.get_attribute("href")
                    except Exception:
                        pass
                
                if not url:
                    continue

                parsed = urlparse(url)
                if 'aclk' in parsed.path:
                    continue

                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                domain = get_domain(clean_url)
                business_name = l.get_attribute("aria-label") or "Unknown"
                text = parent.inner_text()

                rating, reviews = 0.0, "Unknown"
                
                # 1. Try to get the clean aria-label from the star span (e.g. "4.9 stars 684 reviews")
                try:
                    star_span = parent.locator("span[role='img'][aria-label*='stars']")
                    if star_span.count() > 0:
                        aria = star_span.first.get_attribute("aria-label")
                        if aria:
                            rmatch = re.search(r'([\d.]+)\s*stars?\s*([\d,]+)\s*reviews?', aria, re.IGNORECASE)
                            if rmatch:
                                rating = float(rmatch.group(1))
                                reviews = rmatch.group(2).replace(',', '')
                except Exception:
                    pass

                # 2. Try the new split layout
                if reviews == "Unknown":
                    try:
                        rev_span = parent.locator("span[role='img'][aria-label*='reviews']")
                        if rev_span.count() > 0:
                            aria = rev_span.first.get_attribute("aria-label")
                            m = re.search(r'([\d,]+)\s*reviews?', aria, re.IGNORECASE)
                            if m:
                                reviews = m.group(1).replace(',', '')
                        
                        rating_span = parent.locator("span[aria-hidden='true']")
                        for i in range(rating_span.count()):
                            txt = rating_span.nth(i).inner_text().strip()
                            if re.fullmatch(r'[\d.]+', txt):
                                rating = float(txt)
                                break
                    except Exception:
                        pass

                # 3. Fallback to full text regex
                if reviews == "Unknown":
                    print(f"DEBUG TEXT FOR {business_name}: {repr(text)}")
                    match = re.search(r'([\d.]+)[^\(\w]*\(([\d,]+)\)', text)
                    if match:
                        rating = float(match.group(1))
                        reviews = match.group(2).replace(',', '')
                    else:
                        match2 = re.search(r'([\d.]+)\s*\n?([\d,]+)\s*reviews?', text, re.IGNORECASE)
                        if match2:
                            rating = float(match2.group(1))
                            reviews = match2.group(2).replace(',', '')
                        else:
                            rmatch = re.search(r'([\d.]+)\s*\n', text)
                            if rmatch:
                                try:
                                    rating = float(rmatch.group(1))
                                except Exception:
                                    pass

                if is_seen(self.db_file, domain):
                    log(f"Skipped {domain}: already seen", domain)
                    continue

                if any(f in domain for f in FRANCHISES) or '/locations/' in parsed.path.lower():
                    mark_seen(self.db_file, domain, 0, "DISQUALIFIED_FRANCHISE")
                    log(f"Skipped {domain}: franchise", domain)
                    continue

                phone = ""
                pmatch = re.search(r'\(\d{3}\) \d{3}-\d{4}', text)
                if pmatch:
                    phone = pmatch.group(0)

                lead = Lead(
                    business_name=business_name,
                    website_url=clean_url,
                    category=query,
                    location=location,
                    phone=phone,
                    rating=rating,
                    review_count=str(reviews),
                    domain=domain
                )
                leads.append(lead)

                if self.max_leads and len(leads) >= self.max_leads:
                    break

            browser.close()
        return leads
