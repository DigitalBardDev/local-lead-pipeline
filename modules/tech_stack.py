import re
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

from core.models import Lead
from modules.base_module import BaseModule
from core.utils import (
    log, get_domain, extract_emails, verify_email,
    MARKETPLACES, FRANCHISES, SAAS_DOMAINS
)

class TechStackModule(BaseModule):
    name: str = "TechStackModule"

    def process(self, lead: Lead) -> Lead:
        url = lead.website_url
        if not url:
            lead.is_disqualified = True
            lead.disqualification_reason = "No URL provided"
            return lead

        if not url.startswith('http://') and not url.startswith('https://'):
            url = 'https://' + url
            lead.website_url = url

        domain = get_domain(url)
        lead.domain = domain
        log(f"Analyzing tech stack for {url}", domain)

        # 1. Social Media Bypass
        social_sites = ['facebook.com', 'instagram.com', 'twitter.com', 'x.com', 'linkedin.com', 'youtube.com', 'pinterest.com', 'tiktok.com']
        if any(s in domain for s in social_sites):
            log(f"Social Media link detected ({domain}). Bypassing crawl.", domain)
            lead.builder_detected = "Social Media"
            lead.saas_detected = "Social Media"
            lead.audit_bullet_points = "No Official Website (Using Social Media)"
            lead.recommended_tools = "Full Website Build"
            lead.html_score = 0.0
            lead.gemini_score = 0
            lead.gemini_flaws = "No Website"
            return lead

        # 2. Franchise Filter
        if any(f in domain for f in FRANCHISES):
            lead.is_disqualified = True
            lead.disqualification_reason = "Known franchise or national chain"
            log(f"Skipping {domain}: Known franchise/chain", domain)
            return lead

        score = 0.0
        flaws = []

        # 3. Marketplace Check (Angi, Thumbtack, LawnStarter, etc.)
        if any(m in domain for m in MARKETPLACES):
            score += 10.0
            flaws.append("DANGER: Paying for Shared Leads on Marketplace")

        # 4. Free Subdomain Check
        free_subdomains = ['.wixsite.com', '.weebly.com', 'sites.google.com', '.vercel.app', '.wordpress.com', '.blogspot.com', '.square.site']
        if any(fs in domain for fs in free_subdomains):
            score += 5.0
            flaws.append("No Custom Domain (Free Subdomain)")

        all_html = ""
        with sync_playwright() as playwright:
            desktop = playwright.devices['Desktop Chrome']
            iphone = playwright.devices['iPhone 14']
            
            browser = playwright.chromium.launch(headless=True)
            dt_context = browser.new_context(**desktop, ignore_https_errors=True)
            mb_context = browser.new_context(**iphone, ignore_https_errors=True)
            Stealth().apply_stealth_sync(dt_context)
            Stealth().apply_stealth_sync(mb_context)
            
            dt_page = dt_context.new_page()
            mb_page = mb_context.new_page()

            try:
                response = dt_page.goto(url, timeout=15000)
                dt_page.wait_for_load_state('domcontentloaded', timeout=5000)
                html = dt_page.content()
                all_html += html
            except Exception as e:
                log(f"Could not load {url} (Site down or timeout): {e}", domain)
                browser.close()
                lead.is_disqualified = True
                lead.disqualification_reason = f"Site down or unreachable: {e}"
                return lead

            # SaaS Detection
            saas_detected = "None"
            for saas in SAAS_DOMAINS:
                if saas in html:
                    if 'jobber' in saas: saas_detected = 'Jobber'
                    elif 'housecallpro' in saas: saas_detected = 'Housecall Pro'
                    elif 'servicetitan' in saas: saas_detected = 'ServiceTitan'
                    elif 'vagaro' in saas: saas_detected = 'Vagaro'
                    elif 'mindbody' in saas: saas_detected = 'Mindbody'
                    elif 'acuity' in saas: saas_detected = 'Acuity'
                    elif 'squarespace' in saas: saas_detected = 'Squarespace'
                    elif 'squareup' in saas: saas_detected = 'Square'
                    elif 'calendly' in saas: saas_detected = 'Calendly'
                    elif 'tekmetric' in saas: saas_detected = 'Tekmetric'
                    elif 'shop-ware' in saas: saas_detected = 'Shop-Ware'
                    elif 'savvy' in saas: saas_detected = 'Savvy'
                    else: saas_detected = saas
                    break
            lead.saas_detected = saas_detected

            # Discover subpages
            soup = BeautifulSoup(html, 'html.parser')
            subpage_links = []
            for a in soup.find_all('a', href=True):
                href = a.get('href')
                if not href: continue
                full_url = urljoin(url, href).split('#')[0]
                parsed_href = urlparse(full_url)
                href_domain = parsed_href.netloc.lower()
                if href_domain.startswith('www.'): href_domain = href_domain[4:]
                if href_domain == domain and full_url not in subpage_links and full_url != url:
                    if not any(full_url.lower().endswith(ext) for ext in ['.xml', '.pdf', '.jpg', '.png', '.gif', '.webp', '.svg', '.mp4', '.zip', '.doc', '.docx']):
                        subpage_links.append(full_url)

            # SSL Check
            final_url = response.url if response else url
            if not final_url.startswith('https'):
                score += 3.0
                flaws.append("Missing SSL")

            # Favicon
            has_favicon = False
            for link in soup.find_all('link', rel=True):
                rel_attrs = [r.lower() for r in link['rel']] if isinstance(link['rel'], list) else [link['rel'].lower()]
                if 'icon' in rel_attrs or 'shortcut icon' in rel_attrs:
                    has_favicon = True
                    break
            if not has_favicon:
                score += 1.0
                flaws.append("Missing or Default Favicon")

            if not soup.find('h1'):
                score += 2.0
                flaws.append("Missing H1 Tag")

            meta_desc = soup.find('meta', attrs={'name': lambda n: n and n.lower() == 'description'})
            if not meta_desc or not meta_desc.get('content', '').strip():
                score += 1.0
                flaws.append("Missing Meta Description")

            # Cluttered Image Gallery
            carousel_classes = ['slick', 'swiper', 'carousel', 'glide']
            cluttered_gallery_found = False
            for container in soup.find_all(['div', 'section', 'ul']):
                if len(container.find_all('img')) >= 10:
                    has_child_with_10_imgs = False
                    for child in container.find_all(['div', 'section', 'ul']):
                        if len(child.find_all('img')) >= 10:
                            has_child_with_10_imgs = True
                            break
                    if not has_child_with_10_imgs:
                        is_carousel = False
                        curr = container
                        for _ in range(3):
                            if curr and curr.get('class'):
                                classes = ' '.join(curr.get('class', [])).lower() if isinstance(curr.get('class'), list) else str(curr.get('class', '')).lower()
                                if any(c in classes for c in carousel_classes):
                                    is_carousel = True
                                    break
                            if curr: curr = curr.parent
                        if not is_carousel:
                            cluttered_gallery_found = True
                            break
            if cluttered_gallery_found:
                score += 3.0
                flaws.append("Cluttered Image Gallery (Needs Slider)")

            # Crawl subpages for quote form, PDF traps, a11y, etc.
            pages_to_crawl = [url] + subpage_links[:5]
            fake_quote_found = False
            pdf_trap_found = False
            missing_nav_found = False

            for page_url in pages_to_crawl:
                try:
                    if page_url != url:
                        dt_page.goto(page_url, timeout=8000)
                        p_html = dt_page.content()
                        all_html += p_html
                    else:
                        p_html = html
                    p_soup = BeautifulSoup(p_html, 'html.parser')

                    if page_url != url:
                        nav_links = p_soup.select('header a, nav a')
                        if len(nav_links) < 2 and not missing_nav_found:
                            score += 2.0
                            flaws.append("Missing Navigation Bar on Subpages")
                            missing_nav_found = True

                    if not fake_quote_found and re.search(r'(Get a Quote|Free Estimate|Request an Estimate|Book Online)', p_html, re.I):
                        if "<select" not in p_html and "checkbox" not in p_html and "radio" not in p_html:
                            score += 3.0
                            flaws.append("Fake/Basic Quote Form")
                            fake_quote_found = True

                    if not pdf_trap_found:
                        for a in p_soup.find_all('a', href=True):
                            href = a['href'].lower()
                            atext = a.text.lower()
                            if ('.pdf' in href or 'drive.google.com' in href or 'dropbox.com' in href):
                                if any(k in href or k in atext for k in ['price', 'pricing', 'rates', 'packages', 'services', 'menu', 'estimate', 'quote', 'order', 'intake', 'booking', 'form']):
                                    if not any(k in href or k in atext for k in ['privacy', 'terms', 'warranty', 'application', 'w9', 'brochure']):
                                        score += 3.0
                                        flaws.append(f"PDF Trap for Pricing/Services ({atext[:30]})")
                                        pdf_trap_found = True
                                        break
                except Exception:
                    pass

            # Mobile layout check
            try:
                mb_page.goto(url, timeout=10000)
                scroll_width = mb_page.evaluate("document.documentElement.scrollWidth")
                inner_width = mb_page.evaluate("window.innerWidth")
                if scroll_width > inner_width + 20:
                    score += 3.0
                    flaws.append("Broken Mobile Layout (Overflow)")
            except Exception:
                pass

            browser.close()

        # Template Prompts
        template_prompts = ["Welcome to Business", "This is a paragraph", "I'm a paragraph", "Click here to edit", "Add a description", "Coming Soon", "Lorem ipsum"]
        for tp in template_prompts:
            if tp.lower() in all_html.lower():
                score += 3.0
                flaws.append(f"Template text found: {tp}")
                break

        # Builder & Agency detection
        detected_builder = "Unknown"
        builders = ['wix.com', 'godaddy', 'weebly', 'homestead', 'vistaprint', 'squarespace']
        for b in builders:
            if b in all_html.lower():
                score += 2.0
                flaws.append(f"DIY Builder: {b}")
                detected_builder = b
                break
                
        if detected_builder == "Unknown":
            agency_match = re.search(r'(?i)(?:powered by|website by|designed by)\s+([a-zA-Z0-9\s\&]+(?:agency|media|technologies|marketing|web|design|llc|inc))', all_html)
            if agency_match:
                detected_builder = f"Agency: {agency_match.group(1).strip()}"
            else:
                simple_match = re.search(r'(?i)(?:powered by|website by|designed by)\s+([A-Z][a-zA-Z0-9\s\&]{2,20})', all_html)
                if simple_match:
                    found_agency = simple_match.group(1).strip()
                    blacklist = ["Slider Revolution", "WordPress", "Shopify", "Wix", "Squarespace", "Weebly", "GoDaddy"]
                    if not any(b.lower() in found_agency.lower() for b in blacklist):
                        detected_builder = f"Agency: {found_agency}"
        
        lead.builder_detected = detected_builder

        if detected_builder == "Unknown":
            if "wp-content" in all_html.lower() or "wordpress" in all_html.lower():
                detected_builder = "WordPress"
            elif re.search(r'(?i)(website by|site by|designed by|created by|developed by|powered by|proudly built by)[\s\w<>\.\-]+agency', all_html):
                detected_builder = "Agency / Custom"
            elif re.search(r'(?i)(website by|site by|designed by|created by|developed by)\s+<a\s', all_html):
                detected_builder = "Agency / Custom"
        lead.builder_detected = detected_builder

        # Outdated Copyright
        match = re.search(r'(?:©|Copyright)\s*(200\d|201\d|202[0-5])', all_html)
        if match:
            score += 2.0
            flaws.append(f"Outdated Copyright: {match.group(1)}")

        # Cloned slugs
        if re.search(r'/(services-1|about-1|contact-1|blank-1|copy-of-)', all_html):
            score += 2.0
            flaws.append("Cloned/Default URL Slugs")

        # Emails & verification
        emails = extract_emails(all_html)
        if emails:
            lead.email = emails[0]
            lead.email_status = verify_email(lead.email)
        else:
            lead.email = ""
            lead.email_status = "NONE_FOUND"

        lead.html_score = score
        lead.audit_bullet_points = " | ".join(flaws)
        lead.raw_html = all_html
        return lead
