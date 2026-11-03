from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class Lead(BaseModel):
    # Basic Maps / Identification
    business_name: str = ""
    website_url: str = ""
    category: str = "Unknown"
    location: str = ""
    phone: str = ""
    rating: float = 0.0
    review_count: str = "Unknown"
    domain: str = ""

    # Contact & Outreach
    email: str = ""
    email_status: str = "NONE_FOUND"
    
    # Audit Scores & Tech Stack
    html_score: float = 0.0
    company_scale: str = "Unknown"  # Local, Regional, National, Franchise
    audit_bullet_points: str = ""
    builder_detected: str = "Unknown"
    saas_detected: str = "None"
    recommended_tools: str = "Full Website Build"
    
    # Performance & Speed (PSI)
    psi_performance: str = ""
    psi_accessibility: str = ""
    psi_best_practices: str = ""
    psi_seo: str = ""
    psi_lcp: str = ""
    psi_fcp: str = ""

    # Visual & AI Analysis (Gemini)
    screenshot_path: Optional[str] = None
    dt_screenshot_path: Optional[str] = None
    mb_screenshot_path: Optional[str] = None
    gemini_score: Optional[int] = None
    gemini_flaws: str = ""
    is_mobile_responsive: bool = False
    has_baked_in_text: bool = False

    # Owner / Intelligence (OSINT & Sunbiz)
    owner_name: str = "Unknown"
    owner_source: str = "Unlisted"
    years_in_business: str = "Unknown"
    alternate_contacts: str = "None"
    backstory_hooks: str = "None"
    recon_report_path: Optional[str] = None

    # Pipeline State Tracking
    is_disqualified: bool = False
    disqualification_reason: str = ""
    raw_html: str = Field(default="", exclude=True)
    raw_soup_text: str = Field(default="", exclude=True)
    reviews_texts: List[str] = Field(default_factory=list, exclude=True)

    # WTXL specific fields
    wtxl_market_summary: str = ""
    wtxl_ad_spend: str = ""

    def to_supabase_dict(self) -> Dict[str, Any]:
        """Formats the lead for direct Supabase lead_table upsert."""
        return {
            "html_score": float(self.html_score) if str(self.html_score).replace('.', '', 1).isdigit() else 0.0,
            "business_name": self.business_name,
            "category": self.category,
            "website_url": self.website_url,
            "location": self.location,
            "email": self.email,
            "email_status": self.email_status,
            "phone": self.phone,
            "company_scale": self.company_scale,
            "review_count_rating": f"{self.rating} stars ({self.review_count} reviews)",
            "builder_detected": self.builder_detected,
            "saas_detected": self.saas_detected,
            "audit_bullet_points": self.audit_bullet_points,
            "recommended_tools": self.recommended_tools,
            "screenshot_path": self.screenshot_path,
            "owner_name": self.owner_name,
            "owner_source": self.owner_source,
            "years_in_business": self.years_in_business,
            "alternate_contacts": self.alternate_contacts,
            "backstory_hooks": self.backstory_hooks,
            "recon_report_path": self.recon_report_path,
            "psi_performance": self.psi_performance,
            "psi_accessibility": self.psi_accessibility,
            "psi_best_practices": self.psi_best_practices,
            "psi_seo": self.psi_seo,
            "psi_lcp": self.psi_lcp,
            "psi_fcp": self.psi_fcp,
            "gemini_score": self.gemini_score,
            "gemini_flaws": self.gemini_flaws,
            "is_mobile_responsive": self.is_mobile_responsive,
            "has_baked_in_text": self.has_baked_in_text,
            "wtxl_market_summary": self.wtxl_market_summary,
            "wtxl_ad_spend": self.wtxl_ad_spend
        }
