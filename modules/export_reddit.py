import os
from datetime import datetime
from bs4 import BeautifulSoup
from core.models import Lead
from modules.base_module import BaseModule
from core.utils import _acquire_lock, _release_lock

class RedditExportModule(BaseModule):
    name: str = "RedditExportModule"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.out_dir = self.config.get("out_dir", "output")
        os.makedirs(self.out_dir, exist_ok=True)
        prefix = self.config.get("reddit_prefix", "jobs_reddit_")
        self.out_file = os.path.join(self.out_dir, f"{prefix}{datetime.now().strftime('%Y%m%d')}.md")

    def process(self, lead: Lead) -> Lead:
        if lead.is_disqualified:
            return lead

        lock_file = self.out_file + ".lock"
        _acquire_lock(lock_file)
        try:
            is_new = not os.path.isfile(self.out_file)

            queries = ", ".join(self.config.get("_queries", []))
            locations = ", ".join(self.config.get("_locations", []))

            lines = []
            if is_new:
                loc_display = locations if locations else (lead.location or "Local Area")
                kw_display = queries if queries else (lead.category or "Curated Searches")
                header = (
                    f"## 🎯 Curated Local Job Opportunities — {loc_display}\n\n"
                    f"**Location:** {loc_display}\n\n"
                    f"**Keywords / Focus:** {kw_display}\n\n"
                    f"**Generated:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
                    f"---\n\n"
                )
                lines.append(header)

            emp = lead.business_name or "Unknown Employer"
            title = lead.category or "Job Opportunity"
            loc = lead.location or "Tallahassee, FL"
            scale = lead.company_scale or "Unknown"
            score = lead.html_score
            culture = lead.gemini_flaws or "No culture analysis provided."
            apply_url = lead.website_url or "#"
            hooks_html = lead.backstory_hooks or ""

            # Extract clean snippet text and links from backstory_hooks HTML
            snippets = []
            if hooks_html and "<li" in hooks_html:
                try:
                    soup = BeautifulSoup(hooks_html, "html.parser")
                    for li in soup.find_all("li")[:3]: # Keep top 3 snippets for brevity
                        a = li.find("a")
                        href = a["href"] if (a and a.has_attr("href")) else ""
                        if a:
                            a.decompose()
                        text = li.get_text(strip=True)
                        if text:
                            if href:
                                snippets.append(f'* **Employee Review Quote:** "{text}" — [Source]({href})')
                            else:
                                snippets.append(f'* **Employee Review Quote:** "{text}"')
                except Exception:
                    pass

            item = (
                f"### 🏢 **{emp}** — *{title}*\n"
                f"* **Location:** {loc} ({scale})\n"
                f"* **Employer Quality / Toxicity Score:** {score}/10\n"
                f"* **Culture & Workplace Summary:** {culture}\n"
            )
            if snippets:
                for snip in snippets:
                    item += f"{snip}\n"
            item += f"* 🔗 **[Apply / View Posting Here]({apply_url})**\n\n---\n\n"

            lines.append(item)

            with open(self.out_file, "a" if not is_new else "w", encoding="utf-8") as f:
                f.write("".join(lines))

        finally:
            _release_lock(lock_file)

        return lead

