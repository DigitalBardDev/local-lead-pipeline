import os
import re
from core.models import Lead
from modules.base_module import BaseModule
from core.utils import log, translate_flaws
import owner_recon

class OwnerReconModule(BaseModule):
    name: str = "OwnerReconModule"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.out_dir = self.config.get("out_dir", "output")
        self.recon_dir = os.path.join(self.out_dir, "recon_reports")
        os.makedirs(self.recon_dir, exist_ok=True)
        self.score_threshold = self.config.get("score_threshold", 5)

    def process(self, lead: Lead) -> Lead:
        if lead.is_disqualified or not lead.website_url:
            return lead

        # We no longer skip Social Media. We want to generate a dossier to pitch them.

        if lead.html_score < self.score_threshold:
            log(f"Score ({lead.html_score}) below threshold ({self.score_threshold}). Skipping deep recon.", lead.domain)
            return lead

        log(f"Running deep OSINT & Sunbiz owner recon for {lead.business_name}...", lead.domain)
        try:
            recon_data = owner_recon.run_recon(
                business_name=lead.business_name,
                website_url=lead.website_url,
                phone_number=lead.phone,
                email=lead.email,
                all_html=lead.raw_html,
                location=lead.location,
                reviews=lead.reviews_texts
            )

            lead.owner_name = recon_data.get('owner_name', 'Unknown')
            lead.owner_source = recon_data.get('owner_source', 'Unlisted')
            lead.years_in_business = recon_data.get('years_in_business', 'Unknown')
            lead.alternate_contacts = recon_data.get('alternate_contacts', 'None')
            lead.backstory_hooks = recon_data.get('backstory_hooks', 'None')

            # Translate flaws for sales pitch
            flaws_list = [f.strip() for f in lead.audit_bullet_points.split(" | ") if f.strip()]
            translated_flaws = translate_flaws(flaws_list)

            pitch_angle = "Full Custom Site + Calculator + Internal Dashboard"
            if lead.builder_detected == "Social Media":
                pitch_angle = "Professional Custom Website to replace Facebook/Instagram dependency + SEO Foundation + Brand Credibility Building"
            elif lead.saas_detected != "None":
                pitch_angle = f"Front-End Price Calculator + Gatekeeper that hands off to {lead.saas_detected} OR replaces it"
            lead.recommended_tools = pitch_angle

            # Write Recon Dossier Markdown
            sanitized = re.sub(r'[^a-zA-Z0-9]', '_', lead.business_name)
            score_int = int(lead.html_score)
            recon_md_path = os.path.join(self.recon_dir, f"{score_int:02d}pts_{sanitized}.md")
            
            with open(recon_md_path, 'w', encoding='utf-8') as f:
                f.write(f"# Recon Dossier: {lead.business_name}\n\n")
                
                f.write("## 1. Owner & Contact Summary\n")
                f.write(f"- **Likely Owner:** {lead.owner_name} (Source: {lead.owner_source})\n")
                f.write(f"- **Direct Email:** {lead.email} ({lead.email_status})\n")
                f.write(f"- **Phone:** {lead.phone} (Discrepancy Alert: {lead.alternate_contacts})\n")
                f.write(f"- **Time in Business:** {lead.years_in_business}\n")
                f.write(f"- **Backstory & Policy Hooks:** {lead.backstory_hooks}\n")
                f.write(f"- **Existing SaaS Detected:** {lead.saas_detected}\n")
                f.write(f"- **Website Platform:** {lead.builder_detected}\n\n")
                
                f.write("## 2. Technical & Visual Metrics\n")
                f.write(f"- **Google Speed Score:** {lead.psi_performance}/100\n")
                f.write(f"- **Google SEO Score:** {lead.psi_seo}/100\n")
                f.write(f"- **Accessibility Score:** {lead.psi_accessibility}/100\n")
                f.write(f"- **Visual Design Score:** {lead.gemini_score}/10\n\n")

                f.write("## 3. Tech Stack Intel\n")
                f.write(f"{lead.audit_bullet_points}\n\n")

                f.write("## 4. Website Flaws & Plain-English Customer Impact\n")
                for t_flaw in translated_flaws:
                    f.write(f"- **{t_flaw[0]}**: {t_flaw[1]}\n")
                
                # Extract the AI suggested pitch from gemini_flaws if available
                flaw_parts = lead.gemini_flaws.split(" | SUGGESTED FIX: ")
                if len(flaw_parts) > 1:
                    gemini_identified_flaws = flaw_parts[0].strip()
                    ai_pitch = flaw_parts[1].strip()
                    f.write(f"- **Visual/AI Flaw**: {gemini_identified_flaws}\n")
                else:
                    if lead.gemini_flaws:
                        f.write(f"- **Visual/AI Flaw**: {lead.gemini_flaws}\n")
                    ai_pitch = "None provided."
                f.write("\n")

                f.write("## 5. Recommended Tool Pitch Angle\n")
                f.write(f"{pitch_angle}\n\n")
                
                f.write("## 6. AI Suggested Pitch\n")
                f.write(f"{ai_pitch}\n")

            lead.recon_report_path = recon_md_path
            log(f"Recon complete for {lead.business_name}. Owner: {lead.owner_name}", lead.domain)

        except Exception as e:
            log(f"Error during owner recon for {lead.domain}: {e}", lead.domain)

        return lead
