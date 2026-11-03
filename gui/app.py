import customtkinter as ctk
import sqlite3
import json
import threading
import sys
import os
from pathlib import Path
from tkinter import messagebox

# We'll need to run main pipeline stuff, but right now we can simulate it or run main.py via subprocess/threads
# For now, let's just lay out the GUI.

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class LeadHunterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Local Lead Hunter 2.0")
        self.geometry("900x850")
        
        # Tabview
        self.tabview = ctk.CTkTabview(self, width=850, height=800)
        self.tabview.pack(padx=20, pady=20, fill="both", expand=True)
        
        self.tab_dashboard = self.tabview.add("Dashboard")
        self.tab_results = self.tabview.add("Results Viewer")
        self.tab_settings = self.tabview.add("Settings")
        
        self.build_dashboard()
        self.build_results_viewer()
        self.build_settings()
        
        # Trigger default state
        self._on_template_change(self.template_var.get())
        
    def build_dashboard(self):
        # Template selection
        self.lbl_template = ctk.CTkLabel(self.tab_dashboard, text="Select Template:", font=ctk.CTkFont(weight="bold"))
        self.lbl_template.grid(row=0, column=0, padx=20, pady=10, sticky="w")
        
        # Dynamically discover all YAML recipes in the recipes/ directory
        import os
        from pathlib import Path
        recipe_files = []
        recipes_dir = Path(__file__).parent.parent / "recipes"
        if recipes_dir.exists():
            recipe_files = [f.name for f in recipes_dir.glob("*.yaml")]
            
        if not recipe_files:
            recipe_files = ["web_design.yaml", "b2b_saas.yaml"] # Fallback
            
        self.template_var = ctk.StringVar(value=recipe_files[0])
        self.template_menu = ctk.CTkOptionMenu(self.tab_dashboard, variable=self.template_var,
                                               values=recipe_files, command=self._on_template_change)
        self.template_menu.grid(row=0, column=1, padx=20, pady=10, sticky="we")
        
        # Keywords
        self.lbl_keywords = ctk.CTkLabel(self.tab_dashboard, text="Keywords* (comma separated):", font=ctk.CTkFont(weight="bold"))
        self.lbl_keywords.grid(row=1, column=0, padx=20, pady=10, sticky="w")
        self.entry_keywords = ctk.CTkEntry(self.tab_dashboard, placeholder_text="e.g. plumber, lawn care")
        self.entry_keywords.grid(row=1, column=1, padx=20, pady=10, sticky="we")
        
        # Exclude Companies
        self.lbl_exclude = ctk.CTkLabel(self.tab_dashboard, text="Exclude Companies:", font=ctk.CTkFont(weight="bold"))
        self.lbl_exclude.grid(row=2, column=0, padx=20, pady=10, sticky="w")
        self.entry_exclude = ctk.CTkEntry(self.tab_dashboard, placeholder_text="Company names work best, do not use keywords (comma separated)")
        self.entry_exclude.grid(row=2, column=1, padx=20, pady=10, sticky="we")
        
        # Locations
        self.lbl_locations = ctk.CTkLabel(self.tab_dashboard, text="Locations* (comma separated):", font=ctk.CTkFont(weight="bold"))
        self.lbl_locations.grid(row=3, column=0, padx=20, pady=10, sticky="w")
        self.entry_locations = ctk.CTkEntry(self.tab_dashboard, placeholder_text="e.g. Tallahassee FL, Atlanta GA")
        self.entry_locations.grid(row=3, column=1, padx=20, pady=10, sticky="we")

        # Limit
        self.lbl_limit = ctk.CTkLabel(self.tab_dashboard, text="Limit (Max leads per query):", font=ctk.CTkFont(weight="bold"))
        self.lbl_limit.grid(row=4, column=0, padx=20, pady=10, sticky="w")
        self.entry_limit = ctk.CTkEntry(self.tab_dashboard, placeholder_text="e.g. 5 (Leave blank for no limit)")
        self.entry_limit.grid(row=4, column=1, padx=20, pady=10, sticky="we")
        
        # Dynamic Job Hunter Frame (Hidden by default)
        self.job_frame = ctk.CTkFrame(self.tab_dashboard)
        
        self.lbl_job_source = ctk.CTkLabel(self.job_frame, text="Job Source:", font=ctk.CTkFont(weight="bold"))
        self.lbl_job_source.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.var_job_source = ctk.StringVar(value="LinkedIn")
        self.opt_job_source = ctk.CTkOptionMenu(self.job_frame, variable=self.var_job_source, values=["LinkedIn", "Indeed", "Both"])
        self.opt_job_source.grid(row=0, column=1, padx=10, pady=5, sticky="we")
        
        self.lbl_job_type = ctk.CTkLabel(self.job_frame, text="Job Type:", font=ctk.CTkFont(weight="bold"))
        self.lbl_job_type.grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.var_job_type = ctk.StringVar(value="ANY")
        self.opt_job_type = ctk.CTkOptionMenu(self.job_frame, variable=self.var_job_type, values=["ANY", "FULLTIME", "PARTTIME", "CONTRACT", "INTERNSHIP"])
        self.opt_job_type.grid(row=1, column=1, padx=10, pady=5, sticky="we")
        
        self.lbl_radius = ctk.CTkLabel(self.job_frame, text="Radius (Miles):", font=ctk.CTkFont(weight="bold"))
        self.lbl_radius.grid(row=2, column=0, padx=10, pady=5, sticky="w")
        self.var_radius = ctk.StringVar(value="25")
        self.opt_radius = ctk.CTkOptionMenu(self.job_frame, variable=self.var_radius, values=["0", "5", "10", "25", "50", "100"])
        self.opt_radius.grid(row=2, column=1, padx=10, pady=5, sticky="we")
        
        # We grid it below if the template matches
        
        # Start button
        self.btn_start = ctk.CTkButton(self.tab_dashboard, text="Start Hunting", command=self.start_hunting, fg_color="green", hover_color="darkgreen")
        self.btn_start.grid(row=5, column=0, columnspan=2, padx=20, pady=20, sticky="we")
        
        # Progress Bar
        self.progressbar = ctk.CTkProgressBar(self.tab_dashboard, mode="indeterminate")
        self.progressbar.grid(row=6, column=0, columnspan=2, padx=20, pady=10, sticky="we")
        self.progressbar.set(0)
        
        # Log console
        self.log_console = ctk.CTkTextbox(self.tab_dashboard, height=350, state="disabled")
        self.log_console.grid(row=7, column=0, columnspan=2, padx=20, pady=10, sticky="we")
        
        self.tab_dashboard.grid_columnconfigure(1, weight=1)
        self.tab_dashboard.grid_rowconfigure(7, weight=1)

    def _on_template_change(self, choice):
        # Toggle dynamic Job Hunter UI
        if "job" in choice.lower():
            self.lbl_exclude.grid(row=2, column=0, padx=20, pady=10, sticky="w")
            self.entry_exclude.grid(row=2, column=1, padx=20, pady=10, sticky="we")
            self.job_frame.grid(row=5, column=0, columnspan=2, padx=20, pady=10, sticky="we")
            self.btn_start.grid(row=6, column=0, columnspan=2, padx=20, pady=20, sticky="we")
            self.progressbar.grid(row=7, column=0, columnspan=2, padx=20, pady=10, sticky="we")
            self.log_console.grid(row=8, column=0, columnspan=2, padx=20, pady=10, sticky="we")
            self.tab_dashboard.grid_rowconfigure(7, weight=0)
            self.tab_dashboard.grid_rowconfigure(8, weight=1)
        else:
            self.lbl_exclude.grid_forget()
            self.entry_exclude.grid_forget()
            self.job_frame.grid_forget()
            self.btn_start.grid(row=5, column=0, columnspan=2, padx=20, pady=20, sticky="we")
            self.progressbar.grid(row=6, column=0, columnspan=2, padx=20, pady=10, sticky="we")
            self.log_console.grid(row=7, column=0, columnspan=2, padx=20, pady=10, sticky="we")
            self.tab_dashboard.grid_rowconfigure(8, weight=0)
            self.tab_dashboard.grid_rowconfigure(7, weight=1)

        # Refresh the Results Viewer when the template changes
        self.load_data()

    def build_results_viewer(self):
        self.btn_refresh = ctk.CTkButton(self.tab_results, text="Refresh Data", command=self.load_data)
        self.btn_refresh.pack(padx=20, pady=10)
        
        self.results_frame = ctk.CTkScrollableFrame(self.tab_results, width=800, height=400)
        self.results_frame.pack(padx=20, pady=10, fill="both", expand=True)

    def build_settings(self):
        # Gemini API Key
        self.lbl_gemini = ctk.CTkLabel(self.tab_settings, text="Gemini API Key:", font=ctk.CTkFont(weight="bold"))
        self.lbl_gemini.grid(row=0, column=0, padx=20, pady=20, sticky="w")
        
        self.entry_gemini = ctk.CTkEntry(self.tab_settings, width=400, show="*")
        self.entry_gemini.grid(row=0, column=1, padx=20, pady=20, sticky="w")
        
        # PSI API Key
        self.lbl_psi = ctk.CTkLabel(self.tab_settings, text="PageSpeed Insights API Key:", font=ctk.CTkFont(weight="bold"))
        self.lbl_psi.grid(row=1, column=0, padx=20, pady=20, sticky="w")
        
        self.entry_psi = ctk.CTkEntry(self.tab_settings, width=400, show="*")
        self.entry_psi.grid(row=1, column=1, padx=20, pady=20, sticky="w")
        
        self.btn_save_settings = ctk.CTkButton(self.tab_settings, text="Save Settings", command=self.save_settings)
        self.btn_save_settings.grid(row=2, column=0, columnspan=2, padx=20, pady=40)
        
        # Load existing settings if they exist
        self.load_settings()

    def log(self, message):
        self.log_console.configure(state="normal")
        self.log_console.insert("end", message + "\n")
        self.log_console.see("end")
        self.log_console.configure(state="disabled")

    def start_hunting(self):
        template = self.template_var.get()
        keywords = self.entry_keywords.get()
        locations = self.entry_locations.get()
        limit = self.entry_limit.get()
        
        job_type = self.var_job_type.get() if "job" in template.lower() else None
        radius = self.var_radius.get() if "job" in template.lower() else None
        job_source = self.var_job_source.get().lower() if "job" in template.lower() else None
        exclude_companies = self.entry_exclude.get() if "job" in template.lower() else ""
        
        if not keywords or not locations:
            messagebox.showerror("Error", "Please enter keywords and locations.")
            return
            
        self.btn_start.configure(state="disabled", text="Hunting...")
        self.progressbar.start()
        self.log(f"Starting pipeline with template: {template}")
        self.log(f"Keywords: {keywords}")
        self.log(f"Locations: {locations}")
        if limit:
            self.log(f"Limit: {limit}")
        if exclude_companies:
            self.log(f"Excluding: {exclude_companies}")
        
        # Run in background thread to avoid freezing UI
        threading.Thread(target=self.run_pipeline_thread, args=(template, keywords, locations, limit, job_type, radius, job_source, exclude_companies), daemon=True).start()

    def run_pipeline_thread(self, template, keywords, locations, limit, job_type, radius, job_source, exclude_companies):
        import subprocess
        from pathlib import Path
        
        # Ensure the template points to the recipes directory
        if not template.startswith("recipes/") and not template.startswith("recipes\\"):
            template = str(Path("recipes") / template)
            
        cmd = [
            sys.executable, "main.py" if not getattr(sys, 'frozen', False) else "",
            "--recipe", template,
            "--queries", keywords,
            "--locations", locations
        ]
        
        # Clean empty element if frozen
        if getattr(sys, 'frozen', False):
            cmd.remove("")
            
        if limit:
            cmd.extend(["--limit", limit])
            
        if job_type:
            cmd.extend(["--config", f"job_type={job_type}"])
        if radius:
            cmd.extend(["--config", f"radius_miles={radius}"])
        if job_source:
            # Map the UI "both", "linkedin", "indeed" to the harvester config
            if job_source == "linkedin":
                cmd.extend(["--config", "harvester_type=google_jobs"])
            elif job_source == "indeed":
                cmd.extend(["--config", "harvester_type=indeed_jobs"])
            elif job_source == "both":
                cmd.extend(["--config", "harvester_type=both"])
                
        if exclude_companies:
            cmd.extend(["--config", f"exclude_companies={exclude_companies}"])
        
        import os
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(Path(__file__).parent.parent), env=env)
        
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                # We must update GUI from main thread
                self.after(0, self.log, line.strip())
            
        process.wait()
        
        self.after(0, self.finish_hunting)

    def finish_hunting(self):
        self.progressbar.stop()
        self.btn_start.configure(state="normal", text="Start Hunting")
        self.log("Hunting completed!")
        self.load_data()

    def show_text_popup(self, title, full_text):
        popup = ctk.CTkToplevel(self)
        popup.title(title)
        popup.geometry("600x400")
        popup.attributes('-topmost', True)
        
        textbox = ctk.CTkTextbox(popup, wrap="word", font=ctk.CTkFont(size=13))
        textbox.pack(fill="both", expand=True, padx=20, pady=20)
        textbox.insert("0.0", full_text)
        textbox.configure(state="disabled")

    def load_data(self):
        # Clear existing widgets
        for widget in self.results_frame.winfo_children():
            widget.destroy()
            
        # Dynamically determine the database name based on the selected recipe
        import yaml
        from pathlib import Path
        db_filename = "leads_database.db"
        display_mapping = {}
        try:
            selected_yaml = self.template_var.get()
            yaml_path = Path("recipes") / selected_yaml
            if yaml_path.exists():
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    recipe_data = yaml.safe_load(f)
                    config = recipe_data.get("config", {})
                    display_mapping = config.get("display_mapping", {})
                    db_filename = config.get("sqlite_filename", "leads_database.db")
        except Exception as e:
            print(f"Error loading yaml: {e}")

        db_path = Path(__file__).parent.parent / "output" / db_filename
        if not db_path.exists():
            lbl = ctk.CTkLabel(self.results_frame, text="No leads found. Run a hunt first!")
            lbl.pack(pady=20)
            return
            
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT 
                    json_extract(audit_results_json, '$.category'), 
                    name, 
                    json_extract(audit_results_json, '$.company_scale'),
                    website, 
                    phone, 
                    score,
                    json_extract(audit_results_json, '$.email'),
                    json_extract(audit_results_json, '$.owner_name'),
                    json_extract(audit_results_json, '$.is_mobile_responsive')
                FROM leads 
                ORDER BY score DESC 
                LIMIT 100
            ''')
            rows = cursor.fetchall()
            
            # Use the display_mapping parsed earlier to construct headers
            default_headers = ["Category", "Name", "Scale", "Website", "Phone", "Score", "Email", "Owner", "Responsive"]
            sql_keys = ["category", "business_name", "company_scale", "website_url", "phone", "html_score", "email", "owner_name", "is_mobile_responsive"]
            
            # Determine which columns to actually display
            display_indices = []
            headers = []
            for i, default_name in enumerate(default_headers):
                db_key = sql_keys[i]
                if display_mapping:
                    if db_key == "category" or db_key in display_mapping:
                        display_indices.append(i)
                        headers.append(display_mapping.get(db_key, default_name))
                else:
                    display_indices.append(i)
                    headers.append(default_name)

            for col, text in enumerate(headers):
                lbl = ctk.CTkLabel(self.results_frame, text=text, font=ctk.CTkFont(weight="bold"))
                lbl.grid(row=0, column=col, padx=10, pady=5, sticky="w")
                
            for row_idx, row in enumerate(rows, start=1):
                col_offset = 0
                for col_idx, value in enumerate(row):
                    if col_idx not in display_indices:
                        continue
                        
                    # Retrieve the underlying DB key for this column
                    db_key = sql_keys[col_idx]
                    
                    # Format boolean responsive
                    if db_key == "is_mobile_responsive":
                        val_str = "Yes" if value == 1 or str(value).lower() == "true" else "No" if value is not None else "N/A"
                    else:
                        val_str = str(value) if value is not None else "N/A"
                        
                    if db_key == "website_url" and value and str(value).startswith("http"):
                        # Make URLs a clickable link labeled 'Apply'
                        lbl = ctk.CTkLabel(self.results_frame, text="Apply", text_color="blue", cursor="hand2")
                        lbl.bind("<Button-1>", lambda e, url=str(value): __import__('webbrowser').open(url))
                    else:
                        is_truncated = len(val_str) > 50
                        display_text = val_str[:50] + "..." if is_truncated else val_str
                        
                        if is_truncated:
                            # Highlight it slightly so they know it's clickable, or just use hand2 cursor
                            lbl = ctk.CTkLabel(self.results_frame, text=display_text, cursor="hand2")
                            lbl.bind("<Button-1>", lambda e, full_text=val_str, title=headers[col_offset]: self.show_text_popup(title, full_text))
                        else:
                            lbl = ctk.CTkLabel(self.results_frame, text=display_text)
                    
                    lbl.grid(row=row_idx, column=col_offset, padx=10, pady=5, sticky="w")
                    col_offset += 1
        except Exception as e:
            lbl = ctk.CTkLabel(self.results_frame, text=f"Error loading db: {e}")
            lbl.pack(pady=20)
        finally:
            conn.close()

    def load_settings(self):
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8-sig") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip()
                        self.entry_gemini.insert(0, val)
                        os.environ["GEMINI_API_KEY"] = val
                    elif line.startswith("PSI_API_KEY="):
                        val = line.split("=", 1)[1].strip()
                        self.entry_psi.insert(0, val)
                        os.environ["PSI_API_KEY"] = val

    def save_settings(self):
        env_file = Path(__file__).parent.parent / ".env"
        lines = []
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
                
        gemini_key = self.entry_gemini.get()
        psi_key = self.entry_psi.get()
        
        new_lines = []
        found_gemini = False
        found_psi = False
        
        for line in lines:
            if line.startswith("GEMINI_API_KEY="):
                new_lines.append(f"GEMINI_API_KEY={gemini_key}\n")
                found_gemini = True
            elif line.startswith("PSI_API_KEY="):
                new_lines.append(f"PSI_API_KEY={psi_key}\n")
                found_psi = True
            else:
                new_lines.append(line)
                
        if not found_gemini:
            new_lines.append(f"GEMINI_API_KEY={gemini_key}\n")
        if not found_psi:
            new_lines.append(f"PSI_API_KEY={psi_key}\n")
            
        with open(env_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
        # Also set in current process env
        os.environ["GEMINI_API_KEY"] = gemini_key
        os.environ["PSI_API_KEY"] = psi_key
        
        messagebox.showinfo("Success", "Settings saved successfully!")

if __name__ == "__main__":
    app = LeadHunterApp()
    app.mainloop()
