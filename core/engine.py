import os
import concurrent.futures
from typing import List, Dict, Any, Type

from core.models import Lead
from core.utils import log
from modules.base_module import BaseModule
from modules.harvester_maps import MapsHarvester
from modules.job_harvester import JobHarvester
from modules.tech_stack import TechStackModule
from modules.pagespeed import PageSpeedModule
from modules.visual_audit import VisualAuditModule
from modules.owner_recon import OwnerReconModule
from modules.company_recon import CompanyReconModule
from modules.job_ai_audit import JobAiAuditModule
from modules.wtxl_recon import WTXLReconModule
from modules.export_supabase import SupabaseExportModule
from modules.export_html import HtmlExportModule
from modules.export_sqlite import ExportSQLite
from modules.export_reddit import RedditExportModule

MODULE_REGISTRY: Dict[str, Type[BaseModule]] = {
    "tech_stack": TechStackModule,
    "pagespeed": PageSpeedModule,
    "visual_audit": VisualAuditModule,
    "owner_recon": OwnerReconModule,
    "company_recon": CompanyReconModule,
    "job_ai_audit": JobAiAuditModule,
    "wtxl_recon": WTXLReconModule,
    "export_supabase": SupabaseExportModule,
    "export_html": HtmlExportModule,
    "export_sqlite": ExportSQLite,
    "export_reddit": RedditExportModule,
}

class PipelineEngine:
    def __init__(self, recipe: Dict[str, Any]):
        self.recipe = recipe
        self.config = recipe.get("config", {})
        self.max_workers = self.config.get("max_workers", 3)
        self.active_modules: List[BaseModule] = []
        self._load_modules()

    def _load_modules(self):
        pipeline_names = self.recipe.get("pipeline", [
            "tech_stack", "pagespeed", "visual_audit", "owner_recon", "export_supabase", "export_html"
        ])
        for name in pipeline_names:
            if name in MODULE_REGISTRY:
                module_cls = MODULE_REGISTRY[name]
                instance = module_cls(config=self.config)
                self.active_modules.append(instance)
                log(f"Loaded module: {instance.name}")
            else:
                log(f"Warning: Module '{name}' not found in registry.")

    def process_lead(self, lead: Lead) -> Lead:
        """Runs a single lead through the entire conveyor belt of loaded modules."""
        for module in self.active_modules:
            if lead.is_disqualified and not module.name.startswith("Export"):
                break
            try:
                lead = module.process(lead)
            except Exception as e:
                log(f"Module '{module.name}' error on {lead.domain or lead.website_url}: {e}", lead.domain or "PIPELINE")
        return lead

    def run_url(self, url: str, business_name: str = "Manual Target", phone: str = "", location: str = "") -> Lead:
        """Runs the pipeline on a single specific URL."""
        lead = Lead(website_url=url, business_name=business_name, phone=phone, location=location)
        log(f"Running manual pipeline on: {url} ({business_name})")
        return self.process_lead(lead)

    def run(self):
        """Runs the full pipeline across all configured queries and locations."""
        queries = self.recipe.get("queries", self.config.get("queries", []))
        locations = self.recipe.get("locations", self.config.get("locations", []))

        # Inject into config so export modules can render them in headers
        self.config["_queries"] = queries
        self.config["_locations"] = locations

        if not queries or not locations:
            log("No queries or locations defined in recipe. Exiting.")
            return

        harvester_type = self.config.get("harvester_type", "google_maps")
        harvesters = []
        if harvester_type == "google_jobs":
            from modules.job_harvester import JobHarvester
            harvesters.append(JobHarvester(config=self.config))
        elif harvester_type == "indeed_jobs":
            from modules.indeed_harvester import IndeedHarvester
            harvesters.append(IndeedHarvester(config=self.config))
        elif harvester_type == "both":
            from modules.job_harvester import JobHarvester
            from modules.indeed_harvester import IndeedHarvester
            harvesters.append(JobHarvester(config=self.config))
            harvesters.append(IndeedHarvester(config=self.config))
        else:
            harvesters.append(MapsHarvester(config=self.config))

        # Free Geocoding & Location Standardization via OpenStreetMap (Nominatim)
        import requests
        import time
        standardized_locations = []
        for loc in locations:
            try:
                # Sleep to respect Nominatim's 1-request-per-second policy
                time.sleep(1.1)
                headers = {'User-Agent': 'LocalLeadGenerator/2.0 (contact@example.com)'}
                resp = requests.get(f"https://nominatim.openstreetmap.org/search?q={loc}&format=json&addressdetails=1&limit=1", headers=headers, timeout=5)
                if resp.status_code == 200 and resp.json():
                    data = resp.json()[0]
                    address = data.get('address', {})
                    city = address.get('city') or address.get('town') or address.get('village') or address.get('county')
                    state = address.get('state')
                    if city and state:
                        clean_loc = f"{city}, {state}"
                        if clean_loc.lower() != loc.lower():
                            log(f"Auto-Corrected Location: '{loc}' -> '{clean_loc}'", "SYSTEM")
                        standardized_locations.append(clean_loc)
                    else:
                        standardized_locations.append(data.get('display_name', loc).split(',')[0])
                else:
                    standardized_locations.append(loc)
            except Exception as e:
                log(f"Geocoding skipped for '{loc}': {e}", "SYSTEM")
                standardized_locations.append(loc)
        
        locations = standardized_locations

        seen_domains = set()

        for query in queries:
            for location in locations:
                log(f"Starting harvest for query='{query}' in location='{location}'")
                
                raw_leads = []
                for harvester in harvesters:
                    raw_leads.extend(harvester.harvest(query=query, location=location))
                
                # Filter out duplicates across queries and skip medical/HIPAA risks
                unique_leads = []
                
                exclude_str = str(self.config.get("exclude_companies", "")).lower()
                exclude_list = [x.strip() for x in exclude_str.split(",") if x.strip()]
                
                for lead in raw_leads:
                    bname = lead.business_name.lower()
                    
                    # User-defined exclusion list
                    if any(ex in bname for ex in exclude_list):
                        log(f"Skipping {lead.business_name} (User Exclude List)", "PIPELINE")
                        continue
                        
                    # Skip Medical, Hospital, and Clinic to avoid HIPAA
                    if "hospital" in bname or "medical" in bname or "clinic" in bname:
                        log(f"Skipping {lead.business_name} (Medical/HIPAA filter)", "PIPELINE")
                        continue
                        
                    domain_key = lead.domain or lead.website_url or lead.business_name
                    if domain_key not in seen_domains:
                        seen_domains.add(domain_key)
                        unique_leads.append(lead)

                raw_leads = unique_leads
                log(f"Harvester returned {len(raw_leads)} unique, non-medical leads.")

                if not raw_leads:
                    log(f"WARNING: No leads found for '{query}' in '{location}'. Check your search terms or radius.", "WARNING")
                    continue

                with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {executor.submit(self.process_lead, lead): lead for lead in raw_leads}
                    for future in concurrent.futures.as_completed(futures):
                        orig_lead = futures[future]
                        try:
                            res = future.result(timeout=600)
                            if not res.is_disqualified:
                                log(f"Successfully processed: {res.business_name} (Score: {res.html_score})", res.domain)
                        except concurrent.futures.TimeoutError:
                            log(f"Timeout (600s) processing {orig_lead.website_url}", orig_lead.domain)
                        except Exception as e:
                            log(f"Pipeline error on {orig_lead.website_url}: {e}", orig_lead.domain)
