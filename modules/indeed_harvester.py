import time
import urllib.parse
from playwright.sync_api import sync_playwright
from core.utils import log
from core.models import Lead

class IndeedHarvester:
    """
    Harvests job listings from Indeed Public Jobs UI using Playwright.
    """
    name: str = "IndeedHarvester"

    def __init__(self, config: dict = None):
        self.config = config or {}

    def harvest(self, query: str, location: str) -> list[Lead]:
        limit = self.config.get("max_leads", 10)
        
        is_all_search = query.strip().lower() in ["all", "everything", "any"]
        if is_all_search:
            log(f"WARNING: Searching for 'ALL' jobs in '{location}' on Indeed. This may take a long time!", "WARNING")
            q = ""
        else:
            q = urllib.parse.quote(query)
            
        loc = urllib.parse.quote(location)
        url = f"https://www.indeed.com/jobs?q={q}&l={loc}"

        job_type = str(self.config.get("job_type", "ANY")).upper()
        if job_type == "FULLTIME":
            url += "&sc=0kf%3Ajt(fulltime)%3B"
        elif job_type == "PARTTIME":
            url += "&sc=0kf%3Ajt(parttime)%3B"
        elif job_type == "CONTRACT":
            url += "&sc=0kf%3Ajt(contract)%3B"
        elif job_type == "INTERNSHIP":
            url += "&sc=0kf%3Ajt(internship)%3B"
            
        radius = str(self.config.get("radius_miles", "25"))
        url += f"&radius={radius}"

        log(f"Searching Indeed Jobs: '{query}' in '{location}'", "HARVESTER")

        jobs_found = []
        
        with sync_playwright() as p:
            # Indeed is aggressive with bot protection, adding a stealthy user agent
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(4) # Let Cloudflare/Indeed settle

                try:
                    page.wait_for_selector('.job_seen_beacon', timeout=10000)
                except Exception:
                    log("Could not find job listings on Indeed (possible Captcha or no results).", "HARVESTER")
                    browser.close()
                    return jobs_found

                job_cards = page.query_selector_all('.job_seen_beacon')
                
                for card in job_cards:
                    if len(jobs_found) >= limit and limit > 0:
                        break

                    try:
                        title_el = card.query_selector('h2.jobTitle span[title]')
                        company_el = card.query_selector('[data-testid="company-name"]')
                        location_el = card.query_selector('[data-testid="text-location"]')
                        link_el = card.query_selector('h2.jobTitle a')

                        if not title_el or not company_el:
                            continue

                        job_title = title_el.inner_text().strip()
                        company_name = company_el.inner_text().strip()
                        job_location = location_el.inner_text().strip() if location_el else location
                        apply_link = "https://www.indeed.com" + link_el.get_attribute('href') if link_el else page.url

                        # Strict Location Filtering to prevent Indeed from injecting Promoted nationwide/distant jobs
                        import re
                        target_city = re.sub(r'(?i)\s+[a-z]{2}$', '', location).split(',')[0].strip().lower()
                        if target_city not in job_location.lower() and "remote" not in job_location.lower() and "florida" not in job_location.lower() and job_location.lower() not in ["fl", "usa", "united states"]:
                            continue

                        lead = Lead()
                        lead.business_name = company_name
                        lead.category = job_title
                        lead.location = job_location
                        lead.phone = "See Listing"
                        lead.website_url = apply_link.split('?')[0] if '?' in apply_link else apply_link
                        lead.domain = company_name.lower().replace(" ", "")

                        jobs_found.append(lead)
                        log(f"Found Indeed Job: {job_title} at {company_name}", "HARVESTER")

                    except Exception as e:
                        continue

            except Exception as e:
                log(f"Error during Indeed harvesting: {e}", "HARVESTER")
            finally:
                browser.close()

        return jobs_found
