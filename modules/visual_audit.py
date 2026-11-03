import os
import re
import json
import time
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from PIL import Image, ImageDraw, ImageFont
from google.genai import types

from core.models import Lead
from modules.base_module import BaseModule
from core.utils import log, get_gemini_client, enforce_image_limits, GEMINI_LOCK

class VisualAuditModule(BaseModule):
    name: str = "VisualAuditModule"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.out_dir = self.config.get("out_dir", "output")
        self.screenshots_dir = os.path.join(self.out_dir, "screenshots")
        os.makedirs(self.screenshots_dir, exist_ok=True)
        os.makedirs("tmp", exist_ok=True)
        self.gemini_client = get_gemini_client()
        self.model_name = self.config.get("gemini_model", "gemini-3.5-flash-lite")

    def process(self, lead: Lead) -> Lead:
        if lead.is_disqualified or not lead.website_url:
            return lead

        if lead.builder_detected == "Social Media":
            lead.gemini_score = 0
            lead.gemini_flaws = "No Official Website (Using Social Media)"
            lead.is_mobile_responsive = False
            lead.has_baked_in_text = False
            return lead

        domain = lead.domain
        dt_path = os.path.join("tmp", f"{domain}_dt_0.png")
        mb_path = os.path.join("tmp", f"{domain}_mb_0.png")

        # Fallback check for www. prefix in tmp
        if not (os.path.exists(dt_path) and os.path.exists(mb_path)):
            netloc = urlparse(lead.website_url).netloc.lower()
            if os.path.exists(os.path.join("tmp", f"{netloc}_dt_0.png")) and os.path.exists(os.path.join("tmp", f"{netloc}_mb_0.png")):
                dt_path = os.path.join("tmp", f"{netloc}_dt_0.png")
                mb_path = os.path.join("tmp", f"{netloc}_mb_0.png")

        # Capture screenshots if not already present
        if not (os.path.exists(dt_path) and os.path.exists(mb_path)):
            log(f"Capturing desktop & mobile screenshots for {domain}...", domain)

            try:
                with sync_playwright() as playwright:
                    desktop = playwright.devices['Desktop Chrome']
                    iphone = playwright.devices['iPhone 14']

                    browser = playwright.chromium.launch(headless=True)
                    dt_ctx = browser.new_context(**desktop, ignore_https_errors=True)
                    mb_ctx = browser.new_context(**iphone, ignore_https_errors=True)
                    Stealth().apply_stealth_sync(dt_ctx)
                    Stealth().apply_stealth_sync(mb_ctx)

                    dt_page = dt_ctx.new_page()
                    mb_page = mb_ctx.new_page()

                    dt_page.goto(lead.website_url, timeout=15000)
                    try:
                        dt_page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    dt_page.screenshot(path=dt_path, full_page=True, timeout=15000)

                    mb_page.goto(lead.website_url, timeout=15000)
                    try:
                        mb_page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    mb_page.screenshot(path=mb_path, full_page=True, timeout=15000)

                    browser.close()
            except Exception as e:
                log(f"Screenshot capture failed for {domain}: {e}", domain)

        # Enforce pixel dimension limits for Gemini
        if os.path.exists(dt_path):
            enforce_image_limits(dt_path, max_height=8000)
            lead.dt_screenshot_path = dt_path

            # Save dedicated full-page desktop screenshot in output/screenshots
            sanitized = re.sub(r'[^a-zA-Z0-9]', '_', lead.business_name if lead.business_name and lead.business_name != "Manual Target" else domain)
            full_dt_dest = os.path.join(self.screenshots_dir, f"{sanitized}_desktop_fullpage.png")
            try:
                import shutil
                shutil.copyfile(dt_path, full_dt_dest)
                log(f"Saved full-page desktop screenshot to: {full_dt_dest}", domain)
            except Exception as e:
                log(f"Could not copy desktop screenshot: {e}", domain)
        if os.path.exists(mb_path):
            enforce_image_limits(mb_path, max_height=8000)
            lead.mb_screenshot_path = mb_path

        # Generate Visual Audit Composite Card (Optional)
        if self.config.get("save_cards", False) and os.path.exists(dt_path) and os.path.exists(mb_path):
            lead.screenshot_path = self._create_visual_audit_card(
                lead, dt_path, mb_path
            )


        # Gemini Multimodal Vision AI Analysis
        if self.gemini_client and os.path.exists(dt_path) and os.path.exists(mb_path):
            log(f"Running Gemini Vision AI on {domain}...", domain)
            self._analyze_with_gemini(lead, dt_path, mb_path)

        # Storage Optimization: Clean up raw full-page temporary files once card & AI are done
        if self.config.get("cleanup_temp_images", True):
            for p in [dt_path, mb_path]:
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass

        return lead


    def _analyze_with_gemini(self, lead: Lead, dt_path: str, mb_path: str):
        tech_flaws = lead.audit_bullet_points if lead.audit_bullet_points else "None found"
        builder = lead.builder_detected if lead.builder_detected else "Unknown"

        prompt = self.config.get("visual_audit_prompt", f"""You are an expert, objective web design auditor and conversion rate optimization (CRO) specialist. Analyze these desktop and mobile screenshots of a local business website.

We have programmatically scanned the site's code and found the following:
- Detected Platform: {builder}
- Code-level Flaws: {tech_flaws}

Please perform a visual confidence check: do these code-level flaws negatively impact the user experience visually, or are there hidden visual flaws the scraper missed?

Use this detailed rubric for the design score (1-10):
1-2: Non-functional or severely broken. Completely unreadable, layout overlaps, or missing CSS.
3-4: Very outdated or cheap. Unprofessional branding, poor contrast, text difficult to read, or lacks clear structure.
5-6: Functional but generic. Standard template, lacks modern polish, missing strong calls-to-action (CTAs), or basic visual hierarchy issues.
7-8: Good modern design. Clean layout, readable typography, clear CTAs, but may lack a high-end custom feel or have minor mobile issues.
9-10: Exceptional. High-end, custom design, strong branding, perfect mobile responsiveness, and highly optimized for conversions.

Return a raw JSON object with NO markdown formatting, NO backticks, and NO extra text.
The JSON must have these exact keys:
"gemini_score": integer 1-10 using the rubric above.
"gemini_flaws": string listing 1 to 3 specific, actionable visual design or UX flaws (e.g., "Primary CTA button blends into background", "Hero text lacks contrast"). Note if the code-level flaws are visibly harmful.
"suggestion": string giving the single best, most impactful actionable suggestion to improve the design or conversion rate.
"is_mobile_responsive": boolean true/false indicating if the mobile layout is properly responsive without horizontal scrolling or broken elements.
"has_baked_in_text": boolean true/false indicating if large readable text is baked into images instead of being HTML text.""")
        
        sys_instr = self.config.get("visual_audit_sys", "You are an objective web design auditor. Evaluate the site fairly using the 1-10 scale. Focus on usability, modern design standards, and actionable conversion rate improvements.")

        with open(dt_path, "rb") as f: dt_bytes = f.read()
        with open(mb_path, "rb") as f: mb_bytes = f.read()

        success = False
        retries = 0
        while not success and retries < 5:
            try:
                with GEMINI_LOCK:
                    time.sleep(4.5)  # Enforce 15 RPM safety window
                    resp = self.gemini_client.models.generate_content(
                        model=self.model_name,
                        contents=[
                            types.Part.from_bytes(data=dt_bytes, mime_type='image/png'),
                            types.Part.from_bytes(data=mb_bytes, mime_type='image/png'),
                            prompt
                        ],
                        config=types.GenerateContentConfig(
                            system_instruction=sys_instr,
                            temperature=0.7,
                            response_mime_type="application/json"
                        )
                    )
                data = json.loads(resp.text)
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]
                if not isinstance(data, dict):
                    data = {}

                lead.gemini_score = data.get("gemini_score", 0)
                flaws = data.get("gemini_flaws", "")
                suggestion = data.get("suggestion", "")
                if suggestion:
                    lead.gemini_flaws = f"{flaws} | SUGGESTED FIX: {suggestion}"
                else:
                    lead.gemini_flaws = flaws
                lead.is_mobile_responsive = data.get("is_mobile_responsive", False)
                lead.has_baked_in_text = data.get("has_baked_in_text", False)
                log(f"Gemini Score: {lead.gemini_score} | Responsive: {lead.is_mobile_responsive}", lead.domain)
                success = True
            except Exception as e:
                err_str = str(e).lower()
                
                if '429' in err_str or '503' in err_str or 'quota' in err_str or 'unavailable' in err_str or 'resource_exhausted' in err_str:
                    # If we've retried 3 times (45+ seconds), it's a daily limit, not a minute limit. Failover!
                    if retries >= 3 and self.model_name == 'gemini-3.5-flash-lite':
                        log(f"Daily quota likely exhausted on {self.model_name}. Failing over to gemini-3.1-flash-lite...", lead.domain)
                        self.model_name = 'gemini-3.1-flash-lite'
                        continue
                        
                    log(f"Gemini API busy/rate-limited. Waiting 15s... (Attempt {retries+1})", lead.domain)
                    time.sleep(15)
                    retries += 1
                else:
                    log(f"Gemini Error on {lead.domain}: {e}", lead.domain)
                    lead.gemini_score = 0
                    lead.gemini_flaws = f"Error: {str(e)[:50]}"
                    success = True


    def _create_visual_audit_card(self, lead: Lead, dt_path: str, mb_path: str) -> str:
        try:
            try:
                font = ImageFont.truetype("arial.ttf", 30)
                font_small = ImageFont.truetype("arial.ttf", 20)
            except IOError:
                font = ImageFont.load_default()
                font_small = ImageFont.load_default()

            score_int = int(lead.html_score)
            line1 = f"[{score_int} PTS] {lead.business_name} | Owner: {lead.owner_name} | Email: {lead.email} [{lead.email_status}] | SaaS: {lead.saas_detected}"
            line2 = f"Flaws: {lead.audit_bullet_points}"

            Image.MAX_IMAGE_PIXELS = None
            dt_w = 1280
            mb_w = 450
            MAX_CROP_HEIGHT = 8000

            dt_img = Image.open(dt_path)
            scale = dt_w / dt_img.width
            crop_h = int(MAX_CROP_HEIGHT / scale)
            if dt_img.height * scale > MAX_CROP_HEIGHT:
                dt_img = dt_img.crop((0, 0, dt_img.width, crop_h))
            dt_img = dt_img.resize((dt_w, int(dt_img.height * scale)), Image.Resampling.LANCZOS)

            mb_img = Image.open(mb_path)
            scale_mb = mb_w / mb_img.width
            if mb_img.height * scale_mb > MAX_CROP_HEIGHT:
                mb_crop_h = int(MAX_CROP_HEIGHT / scale_mb)
                mb_img = mb_img.crop((0, 0, mb_img.width, mb_crop_h))
            mb_img = mb_img.resize((mb_w, int(mb_img.height * scale_mb)), Image.Resampling.LANCZOS)

            row_h = max(dt_img.height, mb_img.height)
            canvas_h = max(600, row_h + 200)

            canvas = Image.new('RGB', (1790, canvas_h), color='#1e1e1e')
            draw = ImageDraw.Draw(canvas)

            draw.text((20, 20), line1, font=font, fill=(255, 255, 255))
            draw.text((20, 70), line2[:150] + ("..." if len(line2) > 150 else ""), font=font_small, fill=(200, 200, 200))

            canvas.paste(dt_img, (20, 150))
            canvas.paste(mb_img, (20 + dt_w + 20, 150))

            sanitized = re.sub(r'[^a-zA-Z0-9]', '_', lead.business_name)
            out_path = os.path.join(self.screenshots_dir, f"{score_int:02d}pts_{sanitized}.jpg")
            canvas.save(out_path, "JPEG", quality=75, optimize=True)
            return out_path
        except Exception as e:
            log(f"Failed to create visual audit card for {lead.domain}: {e}", lead.domain)
            return ""

