import time
import requests
from bs4 import BeautifulSoup
from core.models import Lead
from modules.base_module import BaseModule
from core.utils import log
import threading

_SEARCH_LOCK = threading.Lock()
_LAST_SEARCH = 0.0

class CompanyReconModule(BaseModule):
    name: str = "CompanyRecon"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

    def process(self, lead: Lead) -> Lead:
        if lead.is_disqualified or not lead.business_name:
            return lead

        log(f"Searching web for Glassdoor & Reddit sentiment on '{lead.business_name}'...", lead.domain)
        
        snippets = self._search_reputation(lead.business_name, lead.location)
        
        # We use backstory_hooks since Lead is a Pydantic model and doesn't allow dynamic attrs
        lead.backstory_hooks = "\n".join(snippets) if snippets else ""
        
        log(f"Found {len(snippets)} reputation snippets for {lead.business_name}", lead.domain)
        return lead

    def _search_reputation(self, company_name: str, location: str) -> list[str]:
        global _LAST_SEARCH
        
        # Broaden search to catch discussions, explicitly append location and employee-centric phrases
        clean_name = company_name.replace('"', '').replace("'", "")
        employee_phrases = '("I work at" OR "used to work" OR "former employee" OR "current employee" OR "my boss" OR "management" OR "coworkers" OR "pay" OR "salary")'
        query = f'"{clean_name}" {location} {employee_phrases} (site:reddit.com OR site:glassdoor.com)'
        snippets = []

        import os
        import json
        serper_key = os.getenv("SERPER_API_KEY")
        if serper_key:
            try:
                headers = {
                    'X-API-KEY': serper_key,
                    'Content-Type': 'application/json'
                }
                payload = json.dumps({"q": query})
                resp = requests.post("https://google.serper.dev/search", headers=headers, data=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for org in data.get("organic", []):
                        snip = org.get("snippet", "")
                        link = org.get("link", "")
                        if snip and len(snip) > 10:
                            if link:
                                snip += f" <a href='{link}' target='_blank' style='text-decoration:none; font-size:0.8em;'>[🔗Source]</a>"
                            snippets.append(snip)
                    return snippets[:10]
                else:
                    error_msg = f"Serper Error {resp.status_code}: {resp.text}"
                    log(error_msg, "WARNING")
                    snippets.append(f"API_ERROR: {error_msg}")
            except Exception as e:
                error_msg = f"Serper Exception: {e}"
                log(error_msg, "WARNING")
                snippets.append(f"API_ERROR: {error_msg}")

        # Fallback to Bing
        url = f"https://www.bing.com/search?q={requests.utils.quote(query)}"
        
        with _SEARCH_LOCK:
            now = time.time()
            if now - _LAST_SEARCH < 2.0:
                time.sleep(2.0 - (now - _LAST_SEARCH))
            _LAST_SEARCH = time.time()

        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                results = soup.find_all('p')
                for res in results:
                    text = res.get_text(strip=True)
                    if text and len(text) > 30 and "Bing" not in text and "JavaScript" not in text:
                        snippets.append(text)
        except Exception as e:
            pass

        return snippets[:10]
