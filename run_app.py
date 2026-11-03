import sys
import multiprocessing

def ensure_playwright_installed():
    import subprocess
    import os
    # Check if we already installed it by looking for a marker file or just let playwright manage it
    # Calling install safely ignores if already installed
    try:
        if not getattr(sys, 'frozen', False):
            print("Checking browser dependencies...")
            subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        else:
            # When frozen as an .exe, PyInstaller + Playwright requires specific environment hooks.
            # We assume the end-user has the browsers bundled or available.
            pass
    except Exception as e:
        print(f"Error installing playwright: {e}")

def main():
    multiprocessing.freeze_support()
    
    # If the user (or our GUI) passed arguments, route to the CLI engine
    if len(sys.argv) > 1 and sys.argv[1] == "--recipe":
        from main import main as cli_main
        cli_main()
    else:
        # Otherwise, boot up the visual Dashboard
        ensure_playwright_installed()
        from gui.app import LeadHunterApp
        app = LeadHunterApp()
        app.mainloop()

if __name__ == "__main__":
    main()
