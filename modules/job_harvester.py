import time
import urllib.parse
from playwright.sync_api import sync_playwright
from core.utils import log
from core.models import Lead

class JobHarvester:
    """
    Harvests job listings from LinkedIn Public Jobs UI using Playwright.
    """
    name: str = "JobHarvester"

    def __init__(self, config: dict = None):
        self.config = config or {}

    def harvest(self, query: str, location: str) -> list[Lead]:
        limit = self.config.get("max_leads", 10)
        
        is_all_search = query.strip().lower() in ["all", "everything", "any"]
        if is_all_search:
            log(f"WARNING: Searching for 'ALL' jobs in '{location}'. This may take a very long time and consume heavy API quota!", "WARNING")
            q = ""
        else:
            q = urllib.parse.quote(query)
            
        loc = urllib.parse.quote(location)
        url = f"https://www.linkedin.com/jobs/search/?keywords={q}&location={loc}"

        job_type = str(self.config.get("job_type", "ANY")).upper()
        if job_type == "FULLTIME":
            url += "&f_JT=F"
        elif job_type == "PARTTIME":
            url += "&f_JT=P"
        elif job_type == "CONTRACT":
            url += "&f_JT=C"
        elif job_type == "INTERNSHIP":
            url += "&f_JT=I"
            
        radius = str(self.config.get("radius_miles", "25"))
        url += f"&distance={radius}"

        log(f"Searching LinkedIn Jobs: '{query}' in '{location}'", "HARVESTER")

        jobs_found = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(3)

                try:
                    page.wait_for_selector('.base-search-card', timeout=10000)
                except Exception:
                    log("Could not find job listings on page.", "HARVESTER")
                    browser.close()
                    return jobs_found

                job_cards = page.query_selector_all('.base-search-card')
                
                for card in job_cards:
                    if len(jobs_found) >= limit and limit > 0:
                        break

                    try:
                        title_el = card.query_selector('.base-search-card__title')
                        company_el = card.query_selector('.base-search-card__subtitle')
                        location_el = card.query_selector('.job-search-card__location')
                        link_el = card.query_selector('a.base-card__full-link')

                        if not title_el or not company_el:
                            continue

                        job_title = title_el.inner_text().strip()
                        company_name = company_el.inner_text().strip()
                        job_location = location_el.inner_text().strip() if location_el else location
                        apply_link = link_el.get_attribute('href') if link_el else page.url

                        # Strict Location Filtering to prevent LinkedIn from injecting Promoted nationwide/distant jobs
                        import re
                        target_city = re.sub(r'(?i)\s+[a-z]{2}$', '', location).split(',')[0].strip().lower()
                        if target_city not in job_location.lower() and "remote" not in job_location.lower() and "florida" not in job_location.lower() and job_location.lower() not in ["fl", "usa", "united states"]:
                            continue

                        lead = Lead()
                        lead.business_name = company_name
                        lead.category = job_title
                        lead.location = job_location
                        lead.phone = "See Listing" # LinkedIn doesn't always show salary on the card
                        lead.website_url = apply_link.split('?')[0] # Clean tracking params
                        lead.domain = company_name.lower().replace(" ", "")

                        jobs_found.append(lead)
                        log(f"Found Job: {job_title} at {company_name}", "HARVESTER")

                    except Exception as e:
                        continue

            except Exception as e:
                log(f"Error during job harvesting: {e}", "HARVESTER")
            finally:
                browser.close()

        log(f"Job Harvester returned {len(jobs_found)} potential openings.", "HARVESTER")
        return jobs_found

