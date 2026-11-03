import time
import json
from core.models import Lead
from modules.base_module import BaseModule
from core.utils import log, get_gemini_client
import threading

GEMINI_LOCK = threading.Lock()
LAST_API_CALL = 0.0

class JobAiAuditModule(BaseModule):
    name: str = "JobAiAudit"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.gemini_client = get_gemini_client()
        self.model_name = self.config.get("gemini_model", "gemini-3.5-flash-lite")
        self.max_retries = 3

    def process(self, lead: Lead) -> Lead:
        global LAST_API_CALL
        if lead.is_disqualified:
            return lead

        raw_snippets = lead.backstory_hooks.split("\n") if lead.backstory_hooks else []
        
        # 1. Programmatic Formatting & Cleaning
        log(f"Running Programmatic Formatting on {lead.business_name} snippets...", lead.domain)
        cleaned_snippets = []
        for s in raw_snippets:
            s = s.strip()
            # Programmatic filtering of junk
            if s.startswith("API_ERROR:") or (len(s) > 30 and not any(junk in s.lower() for junk in ["javascript", "download the app", "install", "latest version", "browser", "cookies", "redirect"])):
                cleaned_snippets.append(s)
                
        if not cleaned_snippets:
            lead.backstory_hooks = "<i>No relevant web reputation data found.</i>"
            snippet_text = "None"
        else:
            # Format nicely for the HTML DataTable using a scrolling div
            formatted_html = "<div style='max-height: 150px; overflow-y: auto; border: 1px solid #eee; padding: 5px;'><ul style='margin:0; padding-left:15px;'>"
            for s in cleaned_snippets:
                formatted_html += f"<li style='margin-bottom:5px; font-size: 0.9em;'>{s}</li>"
            formatted_html += "</ul></div>"
            lead.backstory_hooks = formatted_html
            snippet_text = "\n".join(cleaned_snippets)

        # 2. AI Culture Audit
        if not self.gemini_client:
            log("Gemini client missing. Skipping AI Audit.", "WARNING")
            return lead

        log(f"Running Gemini AI Culture Audit on {lead.business_name}...", lead.domain)
        
        prompt = f"""You are a highly analytical HR specialist and objective career advisor.
Analyze the following employer based on their job title and any web snippets found on Glassdoor/Reddit/Blind.

Employer: {lead.business_name}
Job Title: {lead.category}
Location: {lead.location}

Web Sentiment Snippets (if any):
{snippet_text}

Calculate an "Employer Quality Score" from 1 to 10 (Note: We output this as 'toxicity_score' for schema reasons, but 10 means EXCELLENT and 1 means TOXIC).
Be extremely strict and use the full range of scores. Do NOT default to 5.
1-2: Extremely Toxic (Widespread reports of harassment, wage theft, zero work-life balance, massive turnover).
3-4: Poor (Low pay, micromanagement, high stress, bad benefits, consistent negative reviews).
5: Truly Average (A mix of good and bad, typical corporate complaints, nothing special).
6-7: Good (Stable job, fair pay, decent management, minor complaints about bureaucracy).
8-9: Great (Highly praised culture, excellent benefits, strong leadership, low turnover).
10: Exceptional (Industry-leading compensation, utopian culture, remote work, transparent pay).

Return a raw JSON object with NO markdown formatting, NO backticks, and NO extra text.
The JSON must have these exact keys:
"toxicity_score": integer 1-10 using the rubric above.
"company_scale": string (Must be exactly one of: "Local", "Regional", "National", "Franchise", "Unknown") based on the employer's footprint.
"ai_analysis": string (2-3 sentences) giving a balanced summary of the culture, noting both pros and cons if present.
"""

        success = False
        retries = 0
        while not success and retries < self.max_retries:
            try:
                with GEMINI_LOCK:
                    now = time.time()
                    if now - LAST_API_CALL < 4.0: # Prevent 429s (15 RPM limits)
                        time.sleep(4.0 - (now - LAST_API_CALL))
                    LAST_API_CALL = time.time()

                    resp = self.gemini_client.models.generate_content(
                        model=self.model_name,
                        contents=prompt,
                        config=dict(
                            temperature=0.4,
                            response_mime_type="application/json"
                        )
                    )
                
                data = json.loads(resp.text)
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]

                # Map back to standard lead fields so SQLite and HTML export easily
                lead.html_score = data.get("toxicity_score", 0)
                lead.company_scale = data.get("company_scale", "Unknown")
                lead.gemini_flaws = data.get("ai_analysis", "No analysis provided.")
                
                log(f"Toxicity Score: {lead.html_score} | Evaluated {lead.business_name}", lead.domain)
                success = True

            except Exception as e:
                err_str = str(e).lower()
                if '429' in err_str or '503' in err_str or 'quota' in err_str or 'resource_exhausted' in err_str:
                    if retries >= 3 and self.model_name == 'gemini-3.5-flash-lite':
                        log(f"Daily quota likely exhausted on {self.model_name}. Failing over to gemini-3.1-flash-lite...", lead.domain)
                        self.model_name = 'gemini-3.1-flash-lite'
                        continue
                        
                    log(f"Gemini API busy/rate-limited. Waiting 15s... (Attempt {retries+1})", lead.domain)
                    time.sleep(15)
                    retries += 1
                else:
                    log(f"Job AI Audit error: {e}", lead.domain)
                    lead.html_score = 0
                    lead.gemini_flaws = f"AI Analysis failed: {e}"
                    break

        return lead

