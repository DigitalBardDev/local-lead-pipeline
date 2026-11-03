# Local Lead Generator 2.0 (`lead-hunter`)

**Local Lead Generator 2.0** is an automated, completely modular desktop application and CLI tool for discovering, auditing, and grading business leads or job opportunities. The architecture relies on an engine of interchangeable "Plugins" (Modules) governed by customizable **YAML Recipes**.

With the new V2 architecture, you can instantly pivot the tool from a **B2B Web Design Lead Scraper** to an **AI Job Hunter** simply by swapping the active YAML template in the GUI.


### Important System Files
* **`owner_recon.pyc`**: This is a REQUIRED, compiled proprietary file sitting in the root directory. It contains the Sunbiz/OSINT scraper logic that powers the `owner_recon` module. DO NOT DELETE THIS FILE, or the owner discovery module will crash.

### Temporary AI Files
If the AI Assistant needs to create temporary script files or scratchpads to perform tasks, they will always be prefixed with `goose_` (e.g., `goose_patch_html.py`). This naming convention ensures you always know which files are temporary artifacts and can be safely deleted, keeping your root directory perfectly clean.

---


## 1. Installation & Setup

1. **Create and activate a virtual environment (recommended):**
   ```bash
   python -m venv venv
   
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers:**
   ```bash
   playwright install chromium
   ```

4. **Environment Variables:**
   The GUI handles this automatically! On boot, it reads from the `.env` file in the root directory. If the file doesn't exist, you can enter your API keys directly into the **Settings** tab in the GUI and it will save them for you.
   * `GEMINI_API_KEY`: Required for AI Visual Audits and Job Toxicity Grading (Supports Gemini 3.5 & 3.1 Flash-Lite)
   * `PSI_API_KEY`: Required for Google PageSpeed Insights

---

## 2. Launching the GUI (Desktop App)

The easiest way to run LLG 2.0 is via the CustomTkinter Desktop Application:

```bash
python gui/app.py
```
*(Or use the CLI: `python main.py --gui`)*

### GUI Features:
* **Template Dropdown:** Instantly swap between pipelines (e.g. `web_design.yaml` vs `job_hunter.yaml`).
* **Dynamic Results Viewer:** The data grid automatically isolates your databases so Job Hunt results never mix with Web Design leads. It even dynamically renames the columns based on your active template (e.g., swapping "Phone" for "Salary").
* **Settings Manager:** Securely injects API keys on boot without hardcoding.

---

## 3. Architecture & Modularity

The engine operates on a strict Pipeline approach. It executes the Harvester, and then streams each lead through a sequence of `BaseModule` plugins defined in your YAML.

### Included Modules
* **Harvesters:** `harvester_maps` (Google Maps Leads), `job_harvester` (LinkedIn Job Postings)
* **Auditing:** `tech_stack` (Wappalyzer & HTML parsing), `pagespeed` (Google PSI)
* **AI Vision:** `visual_audit` (Automated screenshots graded by Gemini)
* **Reconnaissance:** `owner_recon` (Sunbiz & OSINT), `company_recon` (Reddit & Glassdoor scraping)
* **AI Text:** `job_ai_audit` (Grading employer toxicity based on snippets)
* **Exporters:** `export_sqlite`, `export_html`, `export_supabase`

### Built-in Smart Failover
The AI modules contain intelligent rate-limit tracking. If the `gemini-3.5-flash-lite` model hits the 15 RPM cap, the system automatically pauses for 15s. If it hits a hard Daily Quota wall (4 failures in a row), it automatically pivots to the cheaper `gemini-3.1-flash-lite` model mid-run so your batch completes.

### Data Deduplication & Shielding
Before any lead hits the ThreadPool, the engine globally deduplicates it against the current session. Additionally, to avoid HIPAA and medical privacy concerns, any scraped business containing "Hospital", "Clinic", or "Medical" in the name is silently skipped.

---

## 4. YAML Recipe Guide

YAML files define the exact structure, display names, and storage paths for your hunt. Here is an example of `recipes/job_hunter.yaml`:

```yaml
name: "AI Job Hunter & Employer Recon"
description: "Aggregates job postings, performs Google Dorking for Glassdoor/Reddit sentiment, and uses AI to grade employer toxicity and growth potential."

# Define exactly which modules run and in what order
pipeline:
  - company_recon
  - job_ai_audit
  - export_sqlite
  - export_html

config:
  harvester_type: "google_jobs" # Or default maps harvester
  
  # Data Isolation
  sqlite_filename: "jobs_database.db" # (Defaults to leads_database.db)
  html_prefix: "jobs_"                # (Defaults to leads_)
  
  # Dynamic UI Header Renaming
  display_mapping:
    business_name: "Employer"
    category: "Job Title"
    phone: "Salary"
    website_url: "Apply Link"
    html_score: "Toxicity Score"
    gemini_flaws: "AI Analysis"

queries:
  - "marketing manager"

locations:
  - "Tampa, FL"
```

Because of `sqlite_filename` and `html_prefix`, the Job Hunter output is securely separated from the `leads_database.db` used by the Web Design tool. If a YAML file does NOT specify these values (like `web_design.yaml`), the system gracefully defaults to the standard configurations, ensuring 100% backward compatibility with all legacy recipes.

---

## 5. Pipeline Recipe Profiles (Why we use different modules)

The power of LLG 2.0 is that the core engine is identical for every run, but the **YAML pipeline definition** determines what logic executes. Different prospecting goals require entirely different modules.

### B2B Pipelines (The `owner_recon` focus)
B2B pipelines target *businesses* as clients. Their primary OSINT goal is to bypass gatekeepers by finding the actual business owner's name. They all rely heavily on **`owner_recon`**, which scrapes state corporate registries (like Florida Sunbiz) to extract the registered agent/owner.

* **`web_design.yaml`**: The heaviest, most comprehensive pipeline. It runs `tech_stack`, `pagespeed`, `visual_audit` (Gemini AI screenshot analysis), and `owner_recon`. It's designed to find businesses with ugly, slow websites so you can pitch them a rebuild, armed with the owner's name and a custom AI critique of their current site.
* **`seo_audit.yaml`**: A faster variant of Web Design. It completely skips the heavy `visual_audit` (no screenshots, no AI API costs) and focuses purely on `pagespeed` and `tech_stack` to pitch SEO and performance optimization services to the owner.
* **`b2b_saas.yaml`**: Skips all visual and performance audits. Focuses exclusively on `tech_stack` to detect what software a business is currently using (e.g., Shopify, WordPress, Mindbody), combined with `owner_recon` so a B2B SaaS vendor can pitch competitor migrations directly to the decision-maker.
* **`tv_ad_sales.yaml`**: Extremely lightweight. Uses a custom config (`min_reviews: 100`) to filter out startups and only targets established, high-budget businesses. It skips audits entirely and just uses `owner_recon` to find who to pitch a $10k/mo TV ad buy to.

### B2C / Career Pipelines (The `company_recon` focus)
Career pipelines target *employers* on behalf of a job seeker. You don't care who the registered agent is; you care if the company culture is toxic. Therefore, they drop `owner_recon` entirely.

* **`job_hunter.yaml`**: Instead of scraping Sunbiz, this recipe runs **`company_recon`**, which uses Google Dorking via Serper to scrape Glassdoor and local Reddit threads (`site:reddit.com OR site:glassdoor.com`) using specific employee-centric phrases ("I work at", "my boss", "salary"). It then passes those snippets to **`job_ai_audit`** where Gemini reads the raw employee complaints and assigns a 1-10 "Toxicity Score" and determines the company scale (Local vs Franchise).
