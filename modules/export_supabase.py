from core.models import Lead
from modules.base_module import BaseModule
from core.utils import log, get_supabase_client, mark_seen

class SupabaseExportModule(BaseModule):
    name: str = "SupabaseExportModule"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.supabase = get_supabase_client()
        self.db_file = self.config.get("db_file", "seen_leads.json")

    def process(self, lead: Lead) -> Lead:
        domain = lead.domain
        
        # 1. Update local cache
        if lead.is_disqualified:
            mark_seen(self.db_file, domain, 0, lead.disqualification_reason or "DISQUALIFIED")
            return lead

        status = "QUALIFIED" if lead.html_score >= self.config.get("score_threshold", 5) else "LOW_SCORE"
        mark_seen(self.db_file, domain, lead.html_score, status)

        # 2. Upsert to Supabase
        if not self.supabase:
            log("Supabase client not configured. Skipping cloud export.", domain)
            return lead

        try:
            data = lead.to_supabase_dict()
            self.supabase.table("lead_table").upsert(data, on_conflict="website_url").execute()
            log(f"Upserted {lead.business_name} ({lead.website_url}) to Supabase.", domain)
        except Exception as e:
            log(f"Supabase upsert failed for {domain}: {e}", domain)

        return lead
