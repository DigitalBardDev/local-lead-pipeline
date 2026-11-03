import time
import requests
import json
import os
import threading
import urllib.parse
from bs4 import BeautifulSoup
from google import genai
from pydantic import BaseModel, Field

from core.models import Lead
from modules.base_module import BaseModule
from core.utils import log, get_domain

_SEARCH_LOCK = threading.Lock()
_LAST_SEARCH = 0.0
GEMINI_LOCK = threading.Lock()
LAST_API_CALL = 0.0

class WTXLAISchema(BaseModel):
    wtxl_market_summary: str = Field(description="A detailed humanized paragraph summarizing the business's local roots, community involvement, local TV/radio/news mentions, and general market familiarity based on the evidence.")
    high_margin_services: list[str] = Field(description="List up to 3 specific high-ticket or high-margin services mentioned on their website (e.g., 'Outdoor Kitchens', 'Retaining Walls', 'Full Roof Replacement', 'Deep Tissue Massage'). These are prime candidates for TV advertising because just 1 or 2 sales pays for the entire ad run.")
    company_scale: str = Field(description="Strictly one of: 'Local', 'Regional', 'National', 'Franchise'.")
    recommended_trend_queries: list[str] = Field(description="List exactly 2 broad macro-industry keywords (e.g., 'Roofing', 'HVAC repair') that an ad rep could look up on Google Trends to show search demand. Keep them short.")
    claimed_years_in_business: str = Field(description="If the website text explicitly claims when they were founded or how many years they have been in business, extract it (e.g. 'Since 1993' or '25 years'). Otherwise output 'Unknown'.")

class WTXLReconModule(BaseModule):
    name: str = "WTXLRecon"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.serper_key = os.getenv("SERPER_API_KEY")
        self.gemini_client = genai.Client() if os.getenv("GEMINI_API_KEY") else None
        self.model_name = self.config.get("gemini_model", "gemini-2.5-flash")

    def process(self, lead: Lead) -> Lead:
        if lead.is_disqualified or not lead.business_name:
            return lead

        log(f"Running WTXL Programmatic Recon on '{lead.business_name}'...", lead.domain)
        
        all_snippets = []

        if not self.serper_key:
            log("SERPER_API_KEY missing. Skipping WTXL Programmatic Recon.", "WARNING")
        else:
            clean_name = lead.business_name.replace('"', '').replace("'", "")
            loc = lead.location.replace(',', '')
            city = loc.split(' ')[0] if ' ' in loc else loc
            
            # 1. Google News Search
            news_query = f'"{clean_name}" {loc}'
            all_snippets.extend(self._serper_search(news_query, endpoint="news", label="Local News"))
            
            # 2. Local Sponsorships & Community (TV Ad Buyers want legacy brand awareness)
            sponsor_query = f'"{clean_name}" {loc} (sponsor OR "chamber of commerce" OR "proud partner" OR donation)'
            all_snippets.extend(self._serper_search(sponsor_query, endpoint="search", label="Community"))
            
            # 3. YouTube / Video Marketing (If they have videos, they have TV Ad assets ready!)
            yt_query = f'site:youtube.com "{clean_name}" {city}'
            all_snippets.extend(self._serper_search(yt_query, endpoint="search", label="YouTube"))
            
            # 4. Local Reddit Chatter
            reddit_query = f'site:reddit.com "{clean_name}" "{city}"'
            all_snippets.extend(self._serper_search(reddit_query, endpoint="search", label="Reddit"))
            
            # 5. Facebook Ads Library
            fb_query = f'site:facebook.com/ads/library "{clean_name}"'
            all_snippets.extend(self._serper_search(fb_query, endpoint="search", label="FB Ads"))
            
            # 6. Fix Google Maps Reviews (Headless Maps DOM hides review count sometimes)
            if lead.review_count == "Unknown" or not lead.review_count:
                places_query = f'{clean_name} {loc}'
                places_res = self._serper_search(places_query, endpoint="places", label="Places")
                if places_res and isinstance(places_res, list) and len(places_res) > 0:
                    first_place = places_res[0]
                    rc = first_place.get("ratingCount")
                    r = first_place.get("rating")
                    if rc is not None:
                        lead.review_count = str(rc)
                    if r is not None:
                        lead.rating = float(r)
            
        # Deduplicate snippets based on URL if present, or text
        seen_texts = set()
        unique_snippets = []
        for s in all_snippets:
            if s['text'] not in seen_texts:
                seen_texts.add(s['text'])
                unique_snippets.append(s)
                
        # Format for UI display (Expandable Div)
        if not unique_snippets:
            lead.backstory_hooks = "<i>No local market intel found.</i>"
            snippet_text = "None"
        else:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            formatted_html = "<div style='max-height: 150px; overflow-y: auto; border: 1px solid #eee; padding: 5px;'><ul style='margin:0; padding-left:15px;'>"
            for s in unique_snippets:
                # 1. Check Date
                date_str = f" | {s.get('date')}" if s.get('date') else ""
                
                # 2. Confidence Check
                text_lower = s['text'].lower()
                city_lower = city.lower()
                conf = "🟡" # Default verify
                
                # Instant Green if city in snippet or URL matches domain
                if city_lower in text_lower or (lead.website_url and get_domain(lead.website_url) in s['link']):
                    conf = "🟢"
                elif s['link'] and "facebook.com" not in s['link']:
                    # Deep Scan the source URL
                    try:
                        resp = requests.get(s['link'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=2.5, verify=False)
                        if resp.status_code == 200 and city_lower in resp.text.lower():
                            conf = "🟢"
                    except Exception:
                        pass
                
                link_html = f" <a href='{s['link']}' target='_blank' style='text-decoration:none; font-size:0.8em;'>[🔗Source]</a>" if s['link'] else ""
                formatted_html += f"<li style='margin-bottom:5px; font-size: 0.9em;' title='Green: Confirmed Local | Yellow: Verify Location'>{conf} <strong>[{s['label']}{date_str}]</strong> {s['text']}{link_html}</li>"
            formatted_html += "</ul></div>"
            lead.backstory_hooks = formatted_html
            
            # Prepare plain text for Gemini Context
            snippet_text = "\n".join([f"[{s['label']}] {s['text']}" for s in unique_snippets])
            
        # 5. Gemini Summarization
        if not self.gemini_client:
            log("Gemini client missing. Skipping WTXL AI Summary.", "WARNING")
            lead.wtxl_market_summary = "AI Summary Skipped (No Key)"
            return lead
            
        log(f"Running WTXL Gemini Analysis on {lead.business_name}...", lead.domain)
        
        # We also feed the raw website text if tech_stack grabbed it!
        website_context = "No website text extracted."
        try:
            import urllib.parse
            import requests
            from bs4 import BeautifulSoup
            
            combined_text = ""
            if lead.raw_html:
                soup = BeautifulSoup(lead.raw_html, "html.parser")
                combined_text += "HOMEPAGE:\n" + soup.get_text(separator=" ", strip=True) + "\n\n"
            
            if lead.website_url:
                for path in ["/about", "/about-us", "/our-story", "/story"]:
                    try:
                        about_url = urllib.parse.urljoin(lead.website_url, path)
                        resp = requests.get(about_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3, verify=False)
                        if resp.status_code == 200:
                            about_soup = BeautifulSoup(resp.text, "html.parser")
                            combined_text += f"\n\nABOUT PAGE ({path}):\n" + about_soup.get_text(separator=" ", strip=True)
                            break # Only need one successful about page
                    except Exception:
                        pass
            
            if combined_text:
                website_context = combined_text[:30000]
        except Exception:
            pass
            
        prompt = f"""You are a brilliant TV Ad Sales Director for a local news station (WTXL). 
Analyze the following business to determine if they are a strong prospect for a local TV ad buy.

Employer: {lead.business_name}
Location: {lead.location}

--- RAW WEBSITE HOMEPAGE TEXT ---
{website_context}
---------------------------------

--- OSINT & SOCIAL RECON SNIPPETS ---
{snippet_text}
-------------------------------------

Based on the evidence above, generate the requested JSON schema.
Focus specifically on identifying their roots in the local community, any competitor advertising footprints (like Facebook ads), and explicitly whether they are a local Mom-and-Pop, a Regional powerhouse, or a National Franchise.
"""

        success = False
        retries = 0
        global LAST_API_CALL
        
        while not success and retries < 3:
            try:
                with GEMINI_LOCK:
                    now = time.time()
                    if now - LAST_API_CALL < 4.0:
                        time.sleep(4.0 - (now - LAST_API_CALL))
                    LAST_API_CALL = time.time()
                    
                    resp = self.gemini_client.models.generate_content(
                        model=self.model_name,
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=WTXLAISchema,
                            temperature=0.2,
                        ),
                    )
                
                data = json.loads(resp.text)
                summary = data.get("wtxl_market_summary", "No summary.")
                
                high_margin = data.get("high_margin_services", [])
                if high_margin:
                    summary += "<br><br><b>High-Margin Target Services:</b><ul>"
                    for svc in high_margin:
                        summary += f"<li>{svc}</li>"
                    summary += "</ul>"
                
                lead.company_scale = data.get("company_scale", "Unknown")
                
                # Update years in business combining Sunbiz and Website Claims
                claimed_years = data.get("claimed_years_in_business", "Unknown")
                if claimed_years != "Unknown":
                    lead.years_in_business = f"{lead.years_in_business} (SunBiz) | {claimed_years} (Website)"
                else:
                    lead.years_in_business = f"{lead.years_in_business} (SunBiz)"
                
                if lead.owner_source == "State SOS":
                    lead.owner_source = "SunBiz"
                
                # Check Google Ads Transparency (Headless Playwright)
                g_ads_result = "Unknown"
                if lead.website_url:
                    domain = urllib.parse.urlparse(lead.website_url).netloc.replace('www.', '')
                    g_ads_result = self._check_google_ads(domain)
                
                fb_url = f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&q={urllib.parse.quote(lead.business_name)}"
                fb_link = f"<br><br><b>Facebook Ads:</b> <a href='{fb_url}' target='_blank'>Click to Validate</a>"
                
                lead.wtxl_ad_spend = f"<b>Google Ads (Automated):</b> {g_ads_result}{fb_link}"
                
                # Format Google Trends Links
                trends = data.get("recommended_trend_queries", [])
                if trends:
                    # Attempt to extract state from location (e.g. 'Tallahassee, FL' -> 'FL')
                    state_code = "FL"
                    if "," in lead.location:
                        possible_state = lead.location.split(",")[-1].strip().upper()
                        if len(possible_state) == 2:
                            state_code = possible_state
                    
                    links_html = f"<br><br><b>Google Trends ({state_code}):</b><br>"
                    for t in trends:
                        t_enc = urllib.parse.quote(t)
                        url = f"https://trends.google.com/trends/explore?q={t_enc}&geo=US-{state_code}"
                        links_html += f"• <a href='{url}' target='_blank'>{t}</a><br>"
                    summary += links_html
                
                lead.wtxl_market_summary = summary
                
                
                # === WTXL CUSTOM SCORING ALGORITHM ===
                wtxl_score = float(lead.html_score)
                try:
                    if lead.review_count and lead.review_count != "Unknown":
                        rc = int(str(lead.review_count).replace(',', ''))
                        wtxl_score += min(20.0, rc / 20.0)
                except Exception:
                    pass
                try:
                    if lead.rating:
                        rt = float(lead.rating)
                        if rt >= 4.5:
                            wtxl_score += 10.0
                        elif rt >= 4.0:
                            wtxl_score += 5.0
                except Exception:
                    pass
                if "color:green" in lead.wtxl_ad_spend or "ads detected" in lead.wtxl_ad_spend.lower():
                    wtxl_score += 15.0
                bh_lower = lead.backstory_hooks.lower()
                if "sponsor" in bh_lower or "chamber" in bh_lower or "donate" in bh_lower or "award" in bh_lower:
                    wtxl_score += 15.0
                try:
                    if lead.gemini_score:
                        gs = int(lead.gemini_score)
                        if gs <= 5: 
                            wtxl_score += 5.0
                except Exception:
                    pass
                if lead.audit_bullet_points:
                    ab_lower = lead.audit_bullet_points.lower()
                    if "no custom domain" in ab_lower:
                        wtxl_score -= 25.0
                    if "shared leads" in ab_lower or "homeadvisor" in ab_lower or "angi" in ab_lower:
                        wtxl_score -= 15.0
                lead.html_score = max(0.0, round(wtxl_score, 1))
                log(f"WTXL Analysis Complete | Scale: {lead.company_scale} | Score: {lead.html_score}", lead.domain)
                success = True

            except Exception as e:
                err_str = str(e).lower()
                if '429' in err_str or '503' in err_str or 'quota' in err_str or 'resource_exhausted' in err_str:
                    log(f"WTXL Analysis Rate limit hit. Retrying...", lead.domain)
                    time.sleep(10)
                else:
                    log(f"WTXL AI Error: {e}", "WARNING")
                    lead.wtxl_market_summary = f"API_ERROR: {e}"
                    break
            retries += 1

        return lead

    def _serper_search(self, query: str, endpoint: str = "search", label: str = "Search") -> list[dict]:
        global _LAST_SEARCH
        
        with _SEARCH_LOCK:
            now = time.time()
            if now - _LAST_SEARCH < 1.0:
                time.sleep(1.0 - (now - _LAST_SEARCH))
            _LAST_SEARCH = time.time()
            
        results = []
        try:
            headers = {
                'X-API-KEY': self.serper_key,
                'Content-Type': 'application/json'
            }
            payload = json.dumps({"q": query})
            resp = requests.post(f"https://google.serper.dev/{endpoint}", headers=headers, data=payload, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                
                if endpoint == "places":
                    return data.get("places", [])
                    
                items = data.get("organic", []) if endpoint == "search" else data.get("news", [])
                
                for item in items:
                    snip = item.get("snippet", "")
                    link = item.get("link", "")
                    date = item.get("date", "")
                    if snip and len(snip) > 10:
                        results.append({
                            "text": snip.replace("\n", " "),
                            "link": link,
                            "label": label,
                            "date": date
                        })
                return results[:5] # Take top 5 per category
            else:
                log(f"Serper Error {resp.status_code} on {endpoint}: {resp.text}", "WARNING")
        except Exception as e:
            log(f"Serper Exception on {endpoint}: {e}", "WARNING")
            
        return results

    def _check_google_ads(self, domain: str) -> str:
        from playwright.sync_api import sync_playwright
        import re
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(f"https://adstransparency.google.com/?region=any&domain={domain}", timeout=20000)
                page.wait_for_timeout(3500)
                text = page.inner_text("body")
                browser.close()
                
                if "0 ads" in text or "No ads found" in text or "couldn't find anything" in text:
                    return "<span style='color:red;'>0 Active Ads</span>"
                
                m = re.search(r'([\dK~,]+)\s*ads', text)
                if m:
                    return f"<span style='color:green;'><b>{m.group(0)}</b> detected!</span>"
                
                return "None Detected"
        except Exception as e:
            return f"Check failed: {str(e)[:30]}"

