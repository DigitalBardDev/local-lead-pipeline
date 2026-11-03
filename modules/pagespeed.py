import os
import urllib.parse
import requests
import time
import threading

from core.models import Lead
from modules.base_module import BaseModule
from core.utils import log

_PSI_LOCK = threading.Lock()

class PageSpeedModule(BaseModule):
    name: str = "PageSpeedModule"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.api_key = self.config.get("psi_api_key") or os.environ.get("PSI_API_KEY")

    def process(self, lead: Lead) -> Lead:
        if lead.is_disqualified or not lead.website_url:
            return lead

        if lead.builder_detected == "Social Media":
            return lead

        log(f"Running PageSpeed Insights on {lead.website_url}", lead.domain)
        psi_data, psi_err = self._run_psi(lead.website_url)

        flaws = []
        if lead.audit_bullet_points:
            flaws = [f.strip() for f in lead.audit_bullet_points.split(" | ")]

        if psi_err:
            lead.psi_performance = f"Error: {psi_err}"
            lead.psi_accessibility = f"Error: {psi_err}"
            lead.psi_best_practices = f"Error: {psi_err}"
            lead.psi_seo = f"Error: {psi_err}"
            lead.psi_lcp = f"Error: {psi_err}"
            lead.psi_fcp = f"Error: {psi_err}"
            return lead

        if psi_data:
            try:
                lighthouse = psi_data.get('lighthouseResult', {})
                categories = lighthouse.get('categories', {})
                
                scores = {}
                for c_key in ['performance', 'accessibility', 'best-practices', 'seo']:
                    cat = categories.get(c_key)
                    if cat and cat.get('score') is not None:
                        scores[c_key] = str(int(cat.get('score') * 100))
                    else:
                        scores[c_key] = "Missing in API response"

                lead.psi_performance = scores.get('performance', '')
                lead.psi_accessibility = scores.get('accessibility', '')
                lead.psi_best_practices = scores.get('best-practices', '')
                lead.psi_seo = scores.get('seo', '')

                audits = lighthouse.get('audits', {})
                lead.psi_lcp = audits.get('largest-contentful-paint', {}).get('displayValue', 'N/A')
                lead.psi_fcp = audits.get('first-contentful-paint', {}).get('displayValue', 'N/A')

                tap_targets = audits.get('tap-targets', {}).get('score')
                font_size = audits.get('font-size', {}).get('score')
                if (tap_targets is not None and tap_targets < 0.9) or (font_size is not None and font_size < 0.9):
                    lead.html_score += 2.0
                    flaws.append("Mobile Tap Target/Font Size Failure")

                third_party = audits.get('third-party-summary', {}).get('score')
                if third_party is not None and third_party <= 0.5:
                    lead.html_score += 1.0
                    flaws.append("Third-Party Script Bloat")

                is_crawlable = audits.get('is-crawlable', {}).get('score')
                robots_txt = audits.get('robots-txt', {}).get('score')
                if (is_crawlable == 0) or (robots_txt == 0):
                    lead.html_score += 3.0
                    flaws.append("SEO Fatal Errors (Uncrawlable)")

            except Exception as e:
                log(f"Error parsing PSI data: {e}", lead.domain)
                lead.psi_performance = "Parse Error"
                lead.psi_accessibility = "Parse Error"
                lead.psi_best_practices = "Parse Error"
                lead.psi_seo = "Parse Error"
                lead.psi_lcp = "Parse Error"
                lead.psi_fcp = "Parse Error"

        lead.audit_bullet_points = " | ".join(flaws)
        return lead

    def _run_psi(self, url: str, retries: int = 5):
        api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={urllib.parse.quote(url)}&strategy=mobile&category=performance&category=accessibility&category=best-practices&category=seo"
        if self.api_key:
            api_url += f"&key={self.api_key}"

        for attempt in range(retries):
            try:
                # Completely serialize PSI requests to prevent 429 Rate Limits
                with _PSI_LOCK:
                    time.sleep(1) # Small buffer between requests
                    resp = requests.get(api_url, timeout=120)
                    
                if resp.status_code == 200:
                    return resp.json(), None
                elif resp.status_code == 429:
                    import random
                    sleep_time = 10 + random.uniform(1, 5)
                    log(f"PSI Rate Limit Hit (429). Sleeping {sleep_time:.1f}s... (Attempt {attempt+1}/{retries})", url)
                    time.sleep(sleep_time)
                    continue
                elif resp.status_code == 400:
                    return None, "HTTP 400 (Invalid/Unreachable URL)"
                else:
                    return None, f"HTTP {resp.status_code}"
            except requests.exceptions.Timeout:
                if attempt == retries - 1:
                    return None, "Connection Timeout (120s)"
            except Exception as e:
                return None, f"Request Failed ({type(e).__name__})"

        return None, "Max Retries Exceeded"
