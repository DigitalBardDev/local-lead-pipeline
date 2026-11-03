import os
import json
from datetime import datetime
from core.models import Lead
from modules.base_module import BaseModule
from core.utils import _acquire_lock, _release_lock

class HtmlExportModule(BaseModule):
    name: str = "HtmlExportModule"

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.out_dir = self.config.get("out_dir", "output")
        os.makedirs(self.out_dir, exist_ok=True)
        html_prefix = self.config.get("html_prefix", "leads_")
        self.out_file = os.path.join(self.out_dir, f"{html_prefix}{datetime.now().strftime('%Y%m%d')}.html")
        self.format = self.config.get("html_format", "table")

    def process(self, lead: Lead) -> Lead:
        if lead.is_disqualified:
            return lead

        display_mapping = self.config.get("display_mapping", {})
        if display_mapping:
            keys = list(display_mapping.keys())
        else:
            keys = [
                'html_score', 'business_name', 'category', 'website_url', 'email', 'email_status',
                'phone', 'review_count_rating', 'builder_detected', 'saas_detected',
                'audit_bullet_points', 'recommended_tools', 'screenshot_path', 'owner_name',
                'owner_source', 'years_in_business', 'alternate_contacts', 'backstory_hooks',
                'recon_report_path', 'psi_performance', 'psi_accessibility', 'psi_best_practices',
                'psi_seo', 'psi_lcp', 'psi_fcp', 'gemini_score', 'gemini_flaws'
            ]

        lock_file = self.out_file + ".lock"
        _acquire_lock(lock_file)
        try:
            if not os.path.isfile(self.out_file):
                with open(self.out_file, 'w', encoding='utf-8') as f:
                    if self.format == "dossier":
                        queries = ", ".join(self.config.get("_queries", []))
                        locations = ", ".join(self.config.get("_locations", []))
                        limit = self.config.get("max_leads", "∞")
                        if limit == 0 or limit == "0":
                            limit = "∞"
                        harvester = self.config.get("harvester_type", "google_maps")
                        
                        f.write(f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Lead Dossiers</title>
<style>
    body {{ font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f0f2f5; margin: 0; padding: 20px; color: #1c1e21; }}
    .dossier-page {{ background-color: white; max-width: 900px; margin: 0 auto 40px auto; padding: 40px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); page-break-after: always; }}
    .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #005A9C; padding-bottom: 15px; margin-bottom: 25px; }}
    .score-badge {{ background-color: #005A9C; color: white; padding: 10px 20px; border-radius: 20px; font-weight: bold; font-size: 1.2em; }}
    h1 {{ margin: 0; color: #005A9C; font-size: 2.2em; }}
    .subtitle {{ color: #65676B; font-size: 1.1em; margin-top: 5px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 25px; }}
    .box {{ background: #f8f9fa; border: 1px solid #e4e6eb; border-radius: 8px; padding: 15px; }}
    .box h3 {{ margin-top: 0; margin-bottom: 15px; color: #333; font-size: 1.1em; border-bottom: 1px solid #ccc; padding-bottom: 5px; }}
    .data-row {{ display: flex; margin-bottom: 8px; }}
    .data-label {{ font-weight: 600; width: 140px; color: #555; }}
    .data-val {{ flex: 1; }}
    .full-width {{ grid-column: 1 / -1; }}
    .summary-text {{ line-height: 1.6; font-size: 1.05em; }}
    .success {{ color: #28a745; font-weight: bold; }}
    .warning {{ color: #ffc107; font-weight: bold; }}
    .danger {{ color: #dc3545; font-weight: bold; }}
    a {{ color: #005A9C; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .run-params {{ background-color: #e9ecef; padding: 15px 20px; border-radius: 8px; margin: 0 auto 30px auto; max-width: 900px; text-align: center; color: #495057; font-size: 1.05em; border: 1px solid #dee2e6; }}
    @media print {{ body {{ background-color: white; padding: 0; }} .dossier-page {{ box-shadow: none; margin: 0; padding: 20px; border-radius: 0; }} .run-params {{ display: none; }} }}
</style>
<script>
function updateCount() {{
    const count = document.querySelectorAll('.dossier-page').length;
    const countSpan = document.getElementById('lead-count');
    if (countSpan) countSpan.textContent = count;
}}
function sortLeads() {{
    const container = document.getElementById('dossier-container');
    const sortVal = document.getElementById('sort-select').value;
    const pages = Array.from(container.querySelectorAll('.dossier-page'));
    
    pages.sort((a, b) => {{
        if (sortVal === 'score_desc' || sortVal === 'score_asc') {{
            const scoreA = parseFloat(a.getAttribute('data-score')) || 0;
            const scoreB = parseFloat(b.getAttribute('data-score')) || 0;
            return sortVal === 'score_desc' ? scoreB - scoreA : scoreA - scoreB;
        }} else {{
            const nameA = a.getAttribute('data-name').toLowerCase();
            const nameB = b.getAttribute('data-name').toLowerCase();
            return nameA.localeCompare(nameB);
        }}
    }});
    
    pages.forEach(p => container.appendChild(p));
}}
document.addEventListener("DOMContentLoaded", () => {{
    updateCount();
}});
async function deleteRecord(btn, reconPath) {{
    if (confirm("Remove this report? The markdown file will also be deleted, but it will remain marked as 'seen' in the database so it won't be re-scraped.")) {{
        btn.closest('.dossier-page').remove();
        updateCount();
        
        if (reconPath && reconPath !== 'None') {{
            try {{
                let url = "http://localhost:8080/delete_dossier";
                if (window.location.protocol === 'http:' && window.location.port) {{
                    url = '/delete_dossier';
                }}
                await fetch(url, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ recon_path: reconPath }})
                }});
            }} catch (e) {{
                console.error("Failed to delete markdown file. Is report_viewer.py running?", e);
            }}
        }}
    }}
}}
</script>
</head>
<body>
    <div class="run-params">
        <strong>Run Parameters</strong><br>
        Keywords: <i>{queries}</i> &nbsp;|&nbsp; Locations: <i>{locations}</i> &nbsp;|&nbsp; Harvester: <i>{harvester}</i> &nbsp;|&nbsp; Limit: <i>{limit}</i>
        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #dee2e6; display: flex; justify-content: space-between; align-items: center;">
            <div style="font-weight: bold;">Displaying: <span id="lead-count">0</span> Leads</div>
            <div>
                <label for="sort-select" style="font-weight: 600; margin-right: 5px;">Sort by:</label>
                <select id="sort-select" onchange="sortLeads()" style="padding: 5px; border-radius: 4px; border: 1px solid #ccc;">
                    <option value="score_desc">Score (Highest First)</option>
                    <option value="score_asc">Score (Lowest First)</option>
                    <option value="name_asc">Business Name (A-Z)</option>
                </select>
            </div>
        </div>
    </div>
    <div id="dossier-container">
    </div>
</body>
</html>""")
                    else:
                        f.write("<!DOCTYPE html>\n<html>\n<head>\n<title>Lead Hunter Report</title>\n")
                        f.write('''<link rel="stylesheet" type="text/css" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>
<style>
body { font-family: sans-serif; padding: 20px; }
table { width: 100%; }
th { background-color: #f2f2f2; text-transform: capitalize; }
td { vertical-align: top; }
</style>''')
                        queries = ", ".join(self.config.get("_queries", []))
                        locations = ", ".join(self.config.get("_locations", []))
                        job_type = self.config.get("job_type", "N/A")
                        radius = self.config.get("radius_miles", "N/A")
                        limit = self.config.get("max_leads", "No Limit")
                        harvester = self.config.get("harvester_type", "google_maps")
                        
                        job_type_str = f" | Job Type: {job_type}" if job_type != "N/A" else ""
                        radius_str = f" | Radius: {radius}" if radius != "N/A" else ""

                        meta_html = f'''
                        <div style="background:#f9f9f9; padding:15px; border:1px solid #ddd; margin-bottom:20px; border-radius:5px;">
                            <b>Parameters Used:</b><br/>
                            Queries: {queries} | Locations: {locations} | Limit: {limit}<br/>
                            Harvester: {harvester}{job_type_str}{radius_str}
                            <div style="margin-top:12px;">
                                <button onclick="copyRedditMarkdown()" style="background-color:#ff4500; color:white; border:none; padding:8px 16px; border-radius:5px; font-weight:bold; cursor:pointer; font-size:0.95em;">📋 Copy Visible Rows for Reddit</button>
                                <span id="copyRedditMsg" style="margin-left:12px; font-weight:bold; color:#28a745;"></span>
                            </div>
                        </div>
                        '''
                        f.write(f"</head>\n<body>\n<h2>Lead Report</h2>\n{meta_html}\n<table id=\"leadsTable\" class=\"display\">\n")
                        
                        headers_html = ""
                        for k in keys:
                            display_name = display_mapping.get(k, k.replace('_', ' ').title())
                            headers_html += f"<th>{display_name}</th>"
                        
                        f.write(f"<thead><tr>{headers_html}</tr></thead>\n<tbody>\n")
                        f.write('''</tbody>\n</table>
<script>
$(document).ready(function() { 
    $("#leadsTable").DataTable({"order": [[0, "desc"]], "pageLength": 50}); 
});

function copyRedditMarkdown() {
    var table = $("#leadsTable").DataTable();
    var rows = table.rows({ search: "applied" }).nodes();
    if (!rows.length) {
        alert("No visible rows to copy.");
        return;
    }
    var md = "## 🎯 Curated Local Job Opportunities\\n\\n";
    var html = "<h2>🎯 Curated Local Job Opportunities</h2><hr>";

    $(rows).each(function() {
        var tds = $(this).find("td");
        if (tds.length >= 8) {
            var emp = $(tds[0]).text().trim();
            var title = $(tds[1]).text().trim();
            var loc = $(tds[2]).text().trim();
            var scale = $(tds[3]).text().trim();
            var score = $(tds[4]).text().trim();
            var culture = $(tds[5]).text().trim();
            var applyUrl = $(tds[7]).find("a").attr("href") || "";

            // Plain Markdown
            md += "### 🏢 **" + emp + "** — *" + title + "*\\n";
            md += "* **Location:** " + loc + " (" + scale + ")\\n";
            md += "* **Employer Quality / Toxicity Score:** " + score + "/10\\n";
            md += "* **Culture & Workplace Summary:** " + culture + "\\n";
            if (applyUrl) {
                md += "* 🔗 **[Apply / View Posting Here](" + applyUrl + ")**\\n";
            }
            md += "\\n---\\n\\n";

            // Rich HTML
            html += "<h3>🏢 <b>" + emp + "</b> — <i>" + title + "</i></h3>";
            html += "<ul>";
            html += "<li><b>Location:</b> " + loc + " (" + scale + ")</li>";
            html += "<li><b>Employer Quality / Toxicity Score:</b> " + score + "/10</li>";
            html += "<li><b>Culture & Workplace Summary:</b> " + culture + "</li>";
            if (applyUrl) {
                html += "<li>🔗 <a href=\\"" + applyUrl + "\\"><b>Apply / View Posting Here</b></a></li>";
            }
            html += "</ul><hr>";
        }
    });

    if (navigator.clipboard && window.ClipboardItem) {
        var blobHtml = new Blob([html], { type: "text/html" });
        var blobText = new Blob([md], { type: "text/plain" });
        var item = new ClipboardItem({ "text/html": blobHtml, "text/plain": blobText });
        navigator.clipboard.write([item]).then(function() {
            $("#copyRedditMsg").text("Copied " + rows.length + " jobs to clipboard (ready for Reddit)!").fadeIn().delay(3500).fadeOut();
        }).catch(function() {
            navigator.clipboard.writeText(md).then(function() {
                $("#copyRedditMsg").text("Copied " + rows.length + " jobs to clipboard!").fadeIn().delay(3500).fadeOut();
            });
        });
    } else {
        navigator.clipboard.writeText(md).then(function() {
            $("#copyRedditMsg").text("Copied " + rows.length + " jobs to clipboard!").fadeIn().delay(3500).fadeOut();
        });
    }
}
</script>
</body>\n</html>''')

            with open(self.out_file, 'r', encoding='utf-8') as f:
                content = f.read()

            data_dict = lead.to_supabase_dict()

            # Format Phone
            phone_val = str(data_dict.get('phone', 'N/A'))
            phone_display = phone_val
            if phone_val and phone_val != 'None':
                digits = "".join(filter(str.isdigit, str(phone_val)))
                if len(digits) >= 10:
                    prefix = digits[-10:-7]
                    if prefix in ['800', '888', '877', '866', '855', '844', '833']:
                        phone_display = f"{phone_val}<br><span style='color:#d9a400; font-size: 0.8em;'>&#9888; Toll-Free</span>"
                    elif prefix in ['850', '448', '229']:
                        phone_display = f"{phone_val}<br><span style='color:green; font-size: 0.8em;'>&#10004; Local (TLH/SWGA)</span>"
                    else:
                        phone_display = f"{phone_val}<br><span style='color:gray; font-size: 0.8em;'>&#10068; Out of Area ({prefix})</span>"

            email_val = str(data_dict.get('email', 'N/A'))
            email_status = str(data_dict.get('email_status', 'None'))
            email_display = f"{email_val} ({email_status})" if email_status != 'None' else email_val

            if self.format == "dossier":
                bname = data_dict.get('business_name', 'Unknown Business')
                score = data_dict.get('html_score', '0')
                category = data_dict.get('category', '').title()
                loc = data_dict.get('location', '')
                website = data_dict.get('website_url', '#')
                reviews = data_dict.get('review_count_rating', 'N/A')
                scale = data_dict.get('company_scale', 'N/A')
                years = data_dict.get('years_in_business', 'N/A')
                owner = data_dict.get('owner_name', 'Unknown')
                owner_src = data_dict.get('owner_source', '')
                ad_spend = data_dict.get('wtxl_ad_spend', 'None')
                ad_spend_html = f'<div class="data-row"><div class="data-label">Competitor Ads:</div><div class="data-val">{ad_spend}</div></div>' if ad_spend and ad_spend != 'None' else ''
                hooks = data_dict.get('backstory_hooks', 'None')
                summary = data_dict.get('wtxl_market_summary', 'No summary available.')
                tech = data_dict.get('audit_bullet_points', 'N/A')
                platform = data_dict.get('builder_detected', 'N/A')
                saas = data_dict.get('saas_detected', 'N/A')
                flaws = data_dict.get('gemini_flaws', 'None')
                design_score = data_dict.get('gemini_score', 'N/A')
                
                psi_perf = data_dict.get('psi_performance', 'N/A')
                psi_seo = data_dict.get('psi_seo', 'N/A')
                psi_acc = data_dict.get('psi_accessibility', 'N/A')
                
                if owner != "Unknown" and owner_src:
                    owner = f"{owner} ({owner_src})"
                    
                flaw_parts = flaws.split(" | SUGGESTED FIX: ")
                if len(flaw_parts) > 1:
                    flaw_html = f"<b>Identified Flaws:</b> {flaw_parts[0]}<br><br><b style='color:#005A9C;'>Suggested Pitch:</b> <i>{flaw_parts[1]}</i>"
                else:
                    flaw_html = f"<b>Identified Flaws:</b> {flaws}"
                    
                tech_html = f"<br><br><b>Tech Stack Intel:</b> {tech}" if tech and tech != "N/A" and tech.strip() else ""
                
                # WTXL / Media Sales sections: AI Market Summary + Backstory Hooks (Reddit/News/Community)
                has_summary = bool(summary) and summary != 'No summary available.'
                has_hooks = bool(hooks) and hooks != 'None'
                wtxl_html = ""
                if has_summary:
                    wtxl_html += f"""        <div class="box full-width">
            <h3>AI Market Summary & Targeting</h3>
            <div class="summary-text">{summary}</div>
        </div>"""
                if has_summary and has_hooks:
                    wtxl_html += f"""
        
        <div class="box full-width">
            <h3>Backstory Hooks & Raw Intel</h3>
            <div class="summary-text">{hooks}</div>
        </div>"""
                
                recon_path_escaped = str(data_dict.get('recon_report_path', 'None')).replace('\\', '\\\\').replace('"', '&quot;')
                bname_escaped = bname.replace('"', '&quot;')
                dossier_html = f"""
<div class="dossier-page" data-name="{bname_escaped}" data-score="{score}">
    <div class="header">
        <div>
            <h1>{bname}</h1>
            <div class="subtitle">{category} &bull; {loc}</div>
        </div>
        <div style="display: flex; flex-direction: column; align-items: flex-end;">
            <div class="score-badge">{'Lead Quality Score (0-100)' if ad_spend and ad_spend != 'None' else 'Technical Vulnerability Score'}: {score}</div>
            <button onclick="deleteRecord(this, '{recon_path_escaped}')" style="margin-top: 10px; padding: 5px 12px; cursor: pointer; background: #dc3545; color: white; border: none; border-radius: 5px; font-weight: bold; font-size: 0.9em;">&#10006; Remove from Report</button>
        </div>
    </div>
    
    <div class="grid">
        <div class="box">
            <h3>Contact Intel</h3>
            <div class="data-row"><div class="data-label">Phone:</div><div class="data-val">{phone_display}</div></div>
            <div class="data-row"><div class="data-label">Email:</div><div class="data-val">{email_display}</div></div>
            <div class="data-row"><div class="data-label">Website:</div><div class="data-val"><a href="{website}" target="_blank">Visit Site</a></div></div>
            <div class="data-row"><div class="data-label">Decision Maker:</div><div class="data-val"><b>{owner}</b></div></div>
        </div>
        
        <div class="box">
            <h3>Business Profile</h3>
            <div class="data-row"><div class="data-label">Years in Biz:</div><div class="data-val">{years}</div></div>
            <div class="data-row"><div class="data-label">Google Reviews:</div><div class="data-val">{reviews}</div></div>
            <div class="data-row"><div class="data-label">Market Scale:</div><div class="data-val">{scale}</div></div>
            {ad_spend_html}
        </div>
        
{wtxl_html}
        
        <div class="box">
            <h3>Digital Sales Triggers</h3>
            <div class="data-row"><div class="data-label">Website Platform:</div><div class="data-val">{platform}</div></div>
            <div class="data-row"><div class="data-label">SaaS Investments:</div><div class="data-val">{saas}</div></div>
            <div class="data-row"><div class="data-label">Visual Design:</div><div class="data-val">{design_score}/10</div></div>
            <div class="data-row"><div class="data-label">Google Speed:</div><div class="data-val">{psi_perf}/100</div></div>
            <div class="data-row"><div class="data-label">Google SEO:</div><div class="data-val">{psi_seo}/100</div></div>
            <div class="data-row"><div class="data-label">Accessibility:</div><div class="data-val">{psi_acc}/100</div></div>
        </div>
        
        <div class="box">
            <h3>Technical Vulnerabilities & Upsell</h3>
            <div class="summary-text" style="font-size: 0.95em; line-height: 1.5;">
                {flaw_html}
                {tech_html}
            </div>
        </div>
    </div>
</div>"""
                content = content.replace('</div>\n</body>\n</html>', dossier_html + '\n</div>\n</body>\n</html>')
            else:
                row = "<tr>"
                for k in keys:
                    val = str(data_dict.get(k, 'None'))
                    if k == 'website_url' and val != 'None':
                        row += f"<td><a href='{val}' target='_blank'>Link</a></td>"
                    elif k == 'screenshot_path' and val and val != 'None':
                        rel_path = os.path.relpath(val, self.out_dir).replace('\\', '/')
                        row += f"<td><a href='{rel_path}' target='_blank'>View Screenshot</a></td>"
                    elif k == 'recon_report_path' and val and val != 'None':
                        rel_path = os.path.relpath(val, self.out_dir).replace('\\', '/')
                        row += f"<td><a href='{rel_path}' target='_blank'>View Dossier</a></td>"
                    elif k == 'phone':
                        row += f"<td>{phone_display}</td>"
                    elif k == 'email':
                        row += f"<td>{email_display}</td>"
                    else:
                        row += f"<td>{val}</td>"
                row += "</tr>\n"
                content = content.replace("</tbody>", f"{row}</tbody>")

            with open(self.out_file, 'w', encoding='utf-8') as f:
                f.write(content)
        finally:
            _release_lock(lock_file)

        return lead
