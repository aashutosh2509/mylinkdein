import os
import json
import time
import random
import threading
from datetime import datetime
from playwright.sync_api import sync_playwright

# Path to database and browser data
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.json")
USER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linkedin_user_data")

class AutomationState:
    def __init__(self):
        self.is_running = False
        self.logs = []
        self.current_action = "Idle"
        self.progress_percent = 0
        self.stop_requested = False
        self._lock = threading.Lock()
        
    def start_running(self):
        with self._lock:
            if self.is_running:
                return False
            self.is_running = True
            self.stop_requested = False
            return True

    def stop_running(self):
        with self._lock:
            self.is_running = False
            
    def add_log(self, text, type="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {"time": timestamp, "message": text, "type": type}
        with self._lock:
            self.logs.append(log_entry)
            # Keep last 200 logs
            if len(self.logs) > 200:
                self.logs.pop(0)
        print(f"[{timestamp}] [{type.upper()}] {text}")

    def update_status(self, action=None, progress=None):
        with self._lock:
            if action is not None:
                self.current_action = action
            if progress is not None:
                self.progress_percent = progress

    def get_state(self):
        with self._lock:
            return {
                "is_running": self.is_running,
                "current_action": self.current_action,
                "progress_percent": self.progress_percent,
                "logs": self.logs
            }

state = AutomationState()

def load_db():
    if not os.path.exists(DB_PATH):
        return []
    try:
        with open(DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        state.add_log(f"Error loading database: {str(e)}", "error")
        return []

def save_db(data):
    try:
        with open(DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        state.add_log(f"Error saving database: {str(e)}", "error")

def resolve_template(template, contact):
    """
    Replaces tags like {FirstName}, {LastName}, {Company} with values from the contact dictionary.
    """
    if not template:
        return ""
    
    # Try to extract first name if it is a single 'name' field
    full_name = contact.get("name", "")
    first_name = contact.get("first_name", "")
    last_name = contact.get("last_name", "")
    
    if not first_name and full_name:
        parts = full_name.split()
        first_name = parts[0] if parts else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

    replacements = {
        "{FirstName}": first_name or full_name or "there",
        "{LastName}": last_name or "",
        "{FullName}": full_name or "there",
        "{Company}": contact.get("company", "") or "your company",
        "{Title}": contact.get("title", "") or "your role"
    }
    
    resolved = template
    for tag, value in replacements.items():
        resolved = resolved.replace(tag, value)
    return resolved

# Persistent browser launcher
def launch_browser(headed=True):
    """
    Launches browser with persistent user data context so session persists.
    """
    state.add_log("Launching persistent browser...", "info")
    playwright = sync_playwright().start()
    
    # Ensure user data dir exists
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=not headed,
        viewport={"width": 1280, "height": 800},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox"
        ]
    )
    
    # Set default timeouts
    context.set_default_timeout(20000)
    return playwright, context

def check_login_status(page):
    """
    Checks if user is logged into LinkedIn. If not, directs them to login.
    """
    try:
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        time.sleep(3)
        
        # Check if we are redirected to login page or guest page
        if "login" in page.url or "signup" in page.url or page.locator("a:has-text('Sign in')").is_visible():
            try:
                screenshot_dir = r"C:\Users\lenovo\.gemini\antigravity\brain\eeb3f292-7445-4086-bb03-812d2a3c527c"
                os.makedirs(screenshot_dir, exist_ok=True)
                page.screenshot(path=os.path.join(screenshot_dir, "debug_login_status.png"))
                public_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
                page.screenshot(path=os.path.join(public_dir, "debug_login_status.png"))
            except Exception:
                pass
            return False
        return True
    except Exception:
        return False

def open_linkedin_for_login():
    """
    Utility to open LinkedIn in headed browser for user to log in manually.
    """
    if not state.start_running():
        state.add_log("System is currently busy (another automation or browser task is active).", "warning")
        return
        
    def run():
        state.update_status(action="Opening login window...")
        playwright = None
        context = None
        try:
            playwright, context = launch_browser(headed=True)
            page = context.new_page()
            state.add_log("Opening LinkedIn login page. Please log in manually if needed...", "info")
            page.goto("https://www.linkedin.com/login")
            
            # Wait until user is on feed page or closes browser
            logged_in = False
            for _ in range(600): # Wait up to 10 minutes
                if state.stop_requested:
                    break
                try:
                    # Detect login once and log success
                    if not logged_in and ("feed" in page.url or page.locator(".global-nav").is_visible()):
                        state.add_log("Successfully detected LinkedIn login session! You can close this window now or keep it open.", "success")
                        logged_in = True
                    
                    # Keep checking if the page is still open. 
                    # If the user closes the browser, accessing page.url will throw an exception and exit the loop.
                    _check = page.url
                except Exception:
                    # Browser might have been closed by user
                    state.add_log("Browser window was closed by the user.", "info")
                    break
                time.sleep(1)
                
            if not logged_in:
                state.add_log("Login session setup complete or cancelled.", "info")
        except Exception as e:
            state.add_log(f"Error during manual login setup: {str(e)}", "error")
        finally:
            state.stop_running()
            state.update_status(action="Idle")
            if context:
                try: context.close() 
                except: pass
            if playwright:
                try: playwright.stop()
                except: pass

    threading.Thread(target=run, daemon=True).start()

# Sync acceptance logic
def sync_acceptance_task():
    """
    Goes to LinkedIn Sent Invitations and synchronizes statuses in DB.
    """
    if not state.start_running():
        state.add_log("System is currently busy (another automation or browser task is active).", "warning")
        return
        
    def run():
        state.update_status(action="Checking sent requests...", progress=10)
        state.add_log("Starting Acceptance Synchronization...", "info")
        
        playwright = None
        context = None
        try:
            playwright, context = launch_browser(headed=True)
            page = context.new_page()
            
            if not check_login_status(page):
                state.add_log("Not logged in to LinkedIn! Please click 'Launch Browser / Login' first.", "error")
                return
                
            state.add_log("Logged in. Navigating to Sent Invitations page...", "info")
            page.goto("https://www.linkedin.com/mynetwork/invitation-manager/sent/")
            time.sleep(5)
            
            # Scroll down a bit to load more items if necessary
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)
                
            # Scrape pending invitations URLs using class-independent semantic locator
            pending_usernames = set()
            links = page.locator("a").all()
            
            for link in links:
                try:
                    href = link.get_attribute("href")
                    if href and "/in/" in href:
                        # Extract username from URL
                        url_clean = href.split("?")[0].rstrip("/")
                        username = url_clean.split("/in/")[-1].strip()
                        if username:
                            pending_usernames.add(username)
                except Exception:
                    continue
                    
            state.add_log(f"Scraped {len(pending_usernames)} unique pending usernames from invitations list.", "info")
            
            # Load DB and compare
            db_data = load_db()
            updated_count = 0
            
            for contact in db_data:
                status = contact.get("status", "Not Started")
                url = contact.get("profile_url", "").strip()
                
                # Extract username from contact profile URL
                url_clean = url.split("?")[0].rstrip("/")
                contact_username = url_clean.split("/in/")[-1].strip() if "/in/" in url_clean else ""
                
                if contact_username and contact_username in pending_usernames:
                    # Auto-discovery: If they are pending on LinkedIn, update database status to Pending
                    if status != "Pending":
                        contact["status"] = "Pending"
                        contact["date_sent"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        state.add_log(f"Status Updated: {contact.get('name', 'Unknown')} is Pending on LinkedIn (Auto-discovered).", "info")
                        updated_count += 1
                else:
                    # No longer in the pending list on LinkedIn.
                    # If they were previously Pending or Sent, it means they accepted!
                    if status in ["Sent", "Pending"]:
                        contact["status"] = "Connected"
                        contact["date_accepted"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        state.add_log(f"Status Updated: {contact.get('name', 'Unknown')} is now Connected!", "success")
                        updated_count += 1
            
            if updated_count > 0:
                save_db(db_data)
                state.add_log(f"Acceptance Sync Complete! {updated_count} contact statuses updated to 'Connected'.", "success")
            else:
                state.add_log("Acceptance Sync Complete! No status changes detected.", "info")
                
        except Exception as e:
            state.add_log(f"Error during Acceptance Sync: {str(e)}", "error")
        finally:
            state.stop_running()
            state.update_status(action="Idle", progress=100)
            if context:
                try: context.close()
                except: pass
            if playwright:
                try: playwright.stop()
                except: pass
                
    threading.Thread(target=run, daemon=True).start()

# Connection Request automation worker
def run_automation_worker(note_template, send_with_note, delay_min, delay_max, daily_limit, start_index=None, end_index=None):
    """
    Main loop that goes through profiles and sends requests.
    """
    if not state.start_running():
        state.add_log("System is currently busy (another automation or browser task is active).", "warning")
        return
        
    def run():
        state.update_status(action="Starting connection worker...", progress=0)
        state.add_log("Starting LinkedIn Connection Automation...", "info")
        
        playwright = None
        context = None
        
        try:
            # 1. Load contacts and add original index tracking
            db_data = load_db()
            for original_idx, contact in enumerate(db_data, start=1):
                contact["_original_idx"] = original_idx
                
            # Filter by index range if provided
            if start_index is not None or end_index is not None:
                s_idx = start_index if start_index is not None else 1
                e_idx = end_index if end_index is not None else len(db_data)
                
                # Bounds check
                s_idx = max(1, s_idx)
                e_idx = min(len(db_data), e_idx)
                
                if s_idx <= e_idx:
                    state.add_log(f"Range filter active: targeting profiles from Sr. No. {s_idx} to {e_idx}.", "info")
                    db_data_slice = db_data[s_idx - 1 : e_idx]
                else:
                    state.add_log(f"Invalid range {s_idx} to {e_idx}. Processing full list.", "warning")
                    db_data_slice = db_data
            else:
                db_data_slice = db_data
                
            pending_contacts = [c for c in db_data_slice if c.get("status", "Not Started") == "Not Started"]
            
            if not pending_contacts:
                state.add_log("No profiles found with 'Not Started' status in the specified range.", "warning")
                return
                
            state.add_log(f"Found {len(pending_contacts)} profiles to process.", "info")
            
            # 2. Launch browser
            playwright, context = launch_browser(headed=True)
            page = context.new_page()
            
            # 3. Check login
            if not check_login_status(page):
                state.add_log("Not logged in to LinkedIn! Please click 'Launch Browser / Login' first.", "error")
                return
                
            state.add_log("Login session validated. Starting request sequences...", "success")
            
            sent_today_count = 0
            total_to_process = len(pending_contacts)
            
            for idx, contact in enumerate(pending_contacts):
                # Check for stop triggers
                if state.stop_requested:
                    state.add_log("Automation paused/stopped by user.", "warning")
                    break
                    
                # Check daily limits
                if sent_today_count >= daily_limit:
                    state.add_log(f"Daily limit of {daily_limit} reached! Stopping automation to protect your account.", "warning")
                    break
                
                # Check if browser page or context has been closed
                is_browser_closed = False
                try:
                    if page.is_closed():
                        is_browser_closed = True
                except Exception:
                    is_browser_closed = True
                    
                if is_browser_closed:
                    state.add_log("Browser page was closed or lost. Pausing automation sequence...", "warning")
                    break
                
                # Update progress
                progress = int((idx / total_to_process) * 100)
                state.update_status(action=f"Processing {contact.get('name', 'Contact')}", progress=progress)
                
                profile_url = contact.get("profile_url", "").strip()
                if not profile_url:
                    contact["status"] = "Failed"
                    contact["logs"] = "Empty profile URL"
                    continue
                
                orig_idx = contact.get("_original_idx", idx + 1)
                state.add_log(f"[{idx+1}/{total_to_process}] Navigating to profile: {contact.get('name', 'Unknown')} (Sr. No. {orig_idx})...", "info")
                try:
                    # 1. Normalize profile URL to www.linkedin.com to avoid country subdomain redirects (e.g., in.linkedin.com)
                    normalized_url = profile_url
                    if "linkedin.com" in profile_url:
                        # Replace specific subdomains (like in., uk., ca., etc.) with www.
                        parts = profile_url.split("linkedin.com")
                        scheme_part = parts[0]
                        path_part = parts[1]
                        if scheme_part.endswith("."):
                            # It has a subdomain, e.g. https://in.
                            scheme_part = scheme_part.split("://")[0] + "://www."
                        normalized_url = f"{scheme_part}linkedin.com{path_part}"

                    # Navigate to profile with self-healing retries for SPA interruption issues
                    max_nav_retries = 2
                    nav_success = False
                    for nav_attempt in range(max_nav_retries):
                        try:
                            page.goto(normalized_url, wait_until="domcontentloaded", timeout=30000)
                            nav_success = True
                            break
                        except Exception as nav_err:
                            err_str = str(nav_err).lower()
                            # Self-healing: check if target profile username is actually loaded despite the error
                            target_username = profile_url.split("/in/")[-1].split("/")[0].split('?')[0].rstrip('/')
                            current_url = page.url.split('?')[0].rstrip('/')
                            if target_username in current_url:
                                state.add_log(f"Navigation returned an error, but target profile '{target_username}' is active on page. Proceeding...", "warning")
                                nav_success = True
                                break
                                
                            if nav_attempt < max_nav_retries - 1 and ("interrupted" in err_str or "abort" in err_str or "navigation" in err_str):
                                state.add_log(f"Navigation was interrupted/failed. Retrying in 3 seconds (Attempt {nav_attempt+2}/{max_nav_retries})...", "warning")
                                time.sleep(3)
                                try: page.goto("about:blank")
                                except: pass
                                time.sleep(1)
                            else:
                                if target_username in page.url:
                                    nav_success = True
                                    break
                                raise nav_err
                    # Wait for profile page to render and name heading (h1 or h2) to appear
                    try:
                        state.add_log("Waiting for profile layout to render...", "info")
                        # Look for h1 or h2 inside main section to represent the profile name
                        page.locator("main section h1, main section h2").first.wait_for(state="visible", timeout=12000)
                        profile_name_text = page.locator("main section h1, main section h2").first.text_content() or ""
                        state.add_log(f"Profile loaded: {profile_name_text.strip()}", "info")
                    except Exception as wait_err:
                        state.add_log(f"Profile layout heading did not appear within 12 seconds: {str(wait_err)}. Capturing debug screenshot...", "warning")
                        try:
                            screenshot_dir = r"C:\Users\lenovo\.gemini\antigravity\brain\eeb3f292-7445-4086-bb03-812d2a3c527c"
                            os.makedirs(screenshot_dir, exist_ok=True)
                            page.screenshot(path=os.path.join(screenshot_dir, "debug_failure.png"))
                            public_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
                            page.screenshot(path=os.path.join(public_dir, "debug_failure.png"))
                            state.add_log("Saved debug screenshot to debug_failure.png", "info")
                        except Exception as ss_err:
                            state.add_log(f"Failed to capture debug screenshot: {str(ss_err)}", "warning")

                    time.sleep(random.uniform(3, 5))
                    
                    # Scroll down a bit to simulate human reading
                    page.evaluate("window.scrollTo(0, 300)")
                    time.sleep(1.5)
                    
                    # 4. Automate connection request
                    # Check if already connected or invitation already sent
                    # Let's check profile buttons
                    
                    # Case A: Scoped check to determine if already connected
                    is_first_degree = False
                    is_second_or_third_degree = False
                    
                    # Non-class-based Semantic HTML XPaths (highly resilient to hashed layouts!)
                    # Anchor directly to the parent section of the profile name heading
                    HEADER_ANCHOR = "xpath=(//main//section[1]//h1 | //main//section[1]//h2)[1]/ancestor::section[1]"
                    
                    # 1. Look for specific degree badges inside the main layout
                    degree_selectors = [
                        f"{HEADER_ANCHOR}//*[contains(@class, 'dist-value')]",
                        f"{HEADER_ANCHOR}//*[text()='1st' or text()='2nd' or text()='3rd' or contains(text(), '1st') or contains(text(), '2nd') or contains(text(), '3rd')]",
                        "main.scaffold-layout__main span.dist-value",
                        "main.scaffold-layout__main [class*='dist-value']",
                        ".pv-text-details__leftpanel span.dist-value",
                        ".pv-member-badge span.dist-value"
                    ]
                    
                    for sel in degree_selectors:
                        try:
                            badge = page.locator(sel).first
                            if badge.is_visible():
                                degree_text = (badge.text_content() or "").strip()
                                if "1st" in degree_text:
                                    is_first_degree = True
                                    break
                                elif "2nd" in degree_text or "3rd" in degree_text:
                                    is_second_or_third_degree = True
                                    break
                        except Exception:
                            continue
                            
                    # Deduce if already connected:
                    # - If explicitly 1st degree: YES.
                    # - If explicitly 2nd/3rd degree: NO (never skip).
                    # - If degree is not detected: we will NOT skip. We only assume connected if we have solid proof to prevent false positive skips.
                    already_connected = False
                    if is_first_degree:
                        already_connected = True
                        
                    if already_connected:
                        contact["status"] = "Connected"
                        contact["date_accepted"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        state.add_log(f"Already connected with {contact.get('name', 'this user')} (1st degree). Marked as Connected.", "success")
                        db_data = load_db()
                        for d in db_data:
                            if d["profile_url"] == profile_url:
                                d["status"] = "Connected"
                                d["date_accepted"] = contact["date_accepted"]
                        save_db(db_data)
                        continue
                        
                    # Case B: Scoped check to determine if invitation is already pending
                    pending_selectors = [
                        f"{HEADER_ANCHOR}//button[contains(., 'Pending') or contains(., 'Sent')]",
                        f"{HEADER_ANCHOR}//*[text()='Pending' or text()='Sent']",
                        "main [class*='top-card'] button:has-text('Pending')",
                        "main [class*='top-card'] button:has-text('Sent')"
                    ]
                    
                    pending_button = page.locator(pending_selectors[0]).first
                    for sel in pending_selectors:
                        try:
                            btn = page.locator(sel).first
                            if btn.is_visible():
                                pending_button = btn
                                break
                        except Exception:
                            continue
                            
                    if pending_button and pending_button.is_visible():
                        contact["status"] = "Pending"
                        state.add_log(f"Request is already pending for {contact.get('name', 'this user')}.", "info")
                        db_data = load_db()
                        for d in db_data:
                            if d["profile_url"] == profile_url:
                                d["status"] = "Pending"
                        save_db(db_data)
                        continue
                        
                    # Prioritize direct 'Connect' button first, then fall back to 'More' dropdown
                    clicked_connect = False
                    
                    # Strategy 1: Look for direct 'Connect' button on the profile header first (if available, click directly without opening 'More')
                    state.add_log("Primary strategy: Searching for direct 'Connect' button on the profile header...", "info")
                    connect_button = None
                    direct_connect_selectors = [
                        f"{HEADER_ANCHOR}//button[contains(., 'Connect')]",
                        f"{HEADER_ANCHOR}//p[text()='Connect']",
                        f"{HEADER_ANCHOR}//span[text()='Connect']",
                        f"{HEADER_ANCHOR}//*[text()='Connect']",
                        f"{HEADER_ANCHOR}//*[contains(text(), 'Connect')]",
                        f"{HEADER_ANCHOR}//*[@aria-label[contains(., 'Connect') or contains(., 'connect')]]",
                        "main [class*='top-card'] button:has-text('Connect')",
                        "main [class*='top-card'] p:text-is('Connect')",
                        "main [class*='top-card'] span:text-is('Connect')",
                        "main [class*='top-card'] p:has-text('Connect')",
                        "main [class*='top-card'] span:has-text('Connect')",
                        "main [class*='top-card'] [aria-label*='connect']",
                        "main [class*='top-card'] [aria-label*='Connect']"
                    ]
                    
                    # Wait dynamically up to 4 seconds for at least one direct connect option to appear
                    try:
                        page.locator(", ".join([s for s in direct_connect_selectors if not s.startswith("xpath=")])).first.wait_for(state="visible", timeout=2000)
                    except Exception:
                        pass

                    for selector in direct_connect_selectors:
                        try:
                            btn = page.locator(selector).first
                            if btn.is_visible() and btn.is_enabled():
                                connect_button = btn
                                break
                        except Exception:
                            continue
                            
                    if connect_button:
                        state.add_log("Found direct 'Connect' button on header. Clicking...", "info")
                        connect_button.click(force=True)
                        clicked_connect = True
                    else:
                        state.add_log("Direct 'Connect' button not visible or disabled on header.", "info")
                        
                    # Strategy 2 (Fallback): If direct 'Connect' button was not available, look in the 'More' dropdown menu
                    if not clicked_connect:
                        state.add_log("Fallback strategy: Clicking 'More...' dropdown to locate 'Connect' option...", "info")
                        more_button = None
                        more_selectors = [
                            f"{HEADER_ANCHOR}//button[contains(., 'More')]",
                            f"{HEADER_ANCHOR}//*[text()='More']",
                            f"{HEADER_ANCHOR}//*[contains(text(), 'More')]",
                            "main [class*='top-card'] button:has-text('More')",
                            "main [class*='top-card'] button[aria-label*='More actions']",
                            "main [class*='top-card'] button[aria-label*='more actions']",
                            "main [class*='top-card'] button[aria-label^='More']",
                            "main [class*='top-card'] span:text-is('More')",
                            "main [class*='top-card'] span:has-text('More')"
                        ]
                        # Wait dynamically up to 2 seconds for at least one 'More' option to appear
                        try:
                            page.locator(", ".join([s for s in more_selectors if not s.startswith("xpath=")])).first.wait_for(state="visible", timeout=1500)
                        except Exception:
                            pass

                        for selector in more_selectors:
                            try:
                                btn = page.locator(selector).first
                                if btn.is_visible() and btn.is_enabled():
                                    more_button = btn
                                    break
                            except Exception:
                                continue
                        
                        if more_button:
                            more_button.click(force=True)
                            time.sleep(random.uniform(1.5, 2.5))
                            
                            # Look for Connect/Invite option in the dropdown menu
                            dropdown_connect = None
                            dropdown_connect_selectors = [
                                # Non-class-based Semantic HTML XPaths (highly resilient to hashed layouts!)
                                "xpath=//*[@role='menuitem']//*[text()='Connect']",
                                "xpath=//*[@role='menuitem']//*[text()='Invite']",
                                "xpath=//*[@role='menu']//*[text()='Connect']",
                                "xpath=//*[@role='menu']//*[text()='Invite']",
                                "xpath=//*[text()='Connect']",
                                "xpath=//*[text()='Invite']",

                                # Prioritize exact paragraph/span matches inside menuitems or globally within active menu
                                "[role='menuitem'] p:text-is('Connect')",
                                "[role='menuitem'] span:text-is('Connect')",
                                "p:text-is('Connect')",
                                "span:text-is('Connect')",
                                "div[role='button']:has-text('Connect')",
                                "div[role='button']:has-text('Invite')",
                                "li:has-text('Connect')",
                                "li:has-text('Invite')",
                                "span:has-text('Connect')",
                                "span:has-text('Invite')",
                                "p:has-text('Connect')",
                                "[role='menuitem'] :has-text('Connect')",
                                "[role='menuitem'] :has-text('Invite')",
                                "[role='menuitem']:has-text('Connect')",
                                "[role='menuitem']:has-text('Invite')",
                                "[aria-label*='connect']",
                                "[aria-label*='Invite']",
                                "[aria-label*='invite']"
                            ]
                            # Wait dynamically up to 2 seconds for at least one dropdown option to appear
                            try:
                                page.locator(", ".join([s for s in dropdown_connect_selectors if not s.startswith("xpath=")])).first.wait_for(state="visible", timeout=1500)
                            except Exception:
                                pass

                            for selector in dropdown_connect_selectors:
                                try:
                                    btn = page.locator(selector).first
                                    if btn.is_visible():
                                        dropdown_connect = btn
                                        break
                                except Exception:
                                    continue
                                    
                            if dropdown_connect:
                                state.add_log("Found 'Connect' in the 'More' dropdown menu. Clicking...", "info")
                                dropdown_connect.click(force=True)
                                clicked_connect = True
                            else:
                                state.add_log("Could not find 'Connect' in the 'More' dropdown menu. Closing dropdown...", "warning")
                                try:
                                    page.keyboard.press("Escape")
                                    time.sleep(1.0)
                                except Exception:
                                    pass
                        else:
                            state.add_log("'More' button not visible or not enabled either.", "warning")
                            
                    if not clicked_connect:
                        state.add_log(f"Skipping {contact.get('name', 'Contact')}: Connect action not available. Capturing debug screenshot...", "warning")
                        try:
                            screenshot_dir = r"C:\Users\lenovo\.gemini\antigravity\brain\eeb3f292-7445-4086-bb03-812d2a3c527c"
                            os.makedirs(screenshot_dir, exist_ok=True)
                            page.screenshot(path=os.path.join(screenshot_dir, "debug_connect_missing.png"))
                            public_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
                            page.screenshot(path=os.path.join(public_dir, "debug_connect_missing.png"))
                        except Exception:
                            pass
                        contact["status"] = "Failed"
                        contact["logs"] = "Connect button not found or disabled"
                        db_data = load_db()
                        for d in db_data:
                            if d["profile_url"] == profile_url:
                                d["status"] = "Failed"
                                d["logs"] = "Connect button not found or disabled"
                        save_db(db_data)
                        continue
                        
                    # 5. Handle modals after clicking Connect
                    # Locate the active modal container - strictly scoped to .artdeco-modal
                    modal = page.locator(".artdeco-modal").first
                    
                    # Wait dynamically up to 5 seconds for a modal to become visible
                    modal_appeared = False
                    try:
                        state.add_log("Waiting dynamically for connection modal to load...", "info")
                        modal.wait_for(state="visible", timeout=5000)
                        modal_appeared = True
                        state.add_log("LinkedIn modal detected.", "info")
                    except Exception:
                        state.add_log("No modal appeared within 5 seconds. Checking direct-send success...", "info")
                    
                    # A. Handle "How do you know this person?" modal if it is active
                    if modal_appeared and modal.is_visible() and ("How do you know" in (modal.text_content() or "")):
                        state.add_log("LinkedIn asked 'How do you know this person?'. Selecting professional relationship...", "info")
                        
                        # Preferred options to bypass email verification (e.g. Colleague, Classmate)
                        know_options = [
                            "button:has-text('Colleague')", "label:has-text('Colleague')",
                            "button:has-text('Classmate')", "label:has-text('Classmate')",
                            "button:has-text('We worked together')", "label:has-text('We worked together')",
                            "button:has-text('Other')", "label:has-text('Other')", "[aria-label*='Other']"
                        ]
                        
                        clicked_option = False
                        for opt_selector in know_options:
                            opt = modal.locator(opt_selector).first
                            if opt.is_visible():
                                opt.click(force=True)
                                clicked_option = True
                                try:
                                    opt_text = opt.text_content() or "Relationship option"
                                    state.add_log(f"Selected: {opt_text.strip()}", "info")
                                except:
                                    pass
                                break
                        
                        if not clicked_option:
                            state.add_log("Could not find standard relationship options in modal.", "warning")
                        
                        time.sleep(1.5)
                        
                        # Click the Connect/Next button inside this modal
                        sub_connect = modal.locator("button:has-text('Connect'), button:has-text('Next'), button:has-text('Send')").first
                        if sub_connect.is_visible() and sub_connect.is_enabled():
                            state.add_log("Clicking Next/Connect inside relationship modal...", "info")
                            sub_connect.click(force=True)
                            # Wait a bit for the modal transition
                            time.sleep(2.5)
                        else:
                            state.add_log("Next/Connect button is not active in relationship modal.", "warning")
                    
                    # B. Check if modal is still open (or if a new modal opened)
                    modal = page.locator(".artdeco-modal").first
                    
                    # Short transition check
                    if modal_appeared:
                        time.sleep(1.5)
                    
                    if not modal.is_visible():
                        state.add_log("No modal is visible. The connection request was successfully sent directly!", "success")
                    else:
                        # Modal is still open. Let's see what is inside it.
                        
                        # B1. Check for email input field (indicating LinkedIn anti-spam email requirement)
                        email_input = modal.locator("input[type='email'], input[name='email'], #email").first
                        if email_input.is_visible():
                            state.add_log("LinkedIn is requiring email address verification to connect. Skipping this contact.", "warning")
                            # Dismiss the modal to let automation proceed to the next profile
                            close_btn = modal.locator("button[aria-label*='Dismiss'], button[aria-label*='Close'], button:has-text('Close')").first
                            if close_btn.is_visible():
                                close_btn.click(force=True)
                            else:
                                page.keyboard.press("Escape")
                            time.sleep(1.5)
                            raise Exception("LinkedIn email verification required")
                            
                        # B2. Check for "Add a note" button
                        add_note_btn = modal.locator("button:has-text('Add a note'), button[aria-label*='Add a note']").first
                        
                        note_sent_successfully = False
                        
                        if send_with_note and add_note_btn.is_visible() and add_note_btn.is_enabled():
                            try:
                                state.add_log("Clicking 'Add a note'...", "info")
                                add_note_btn.click(force=True)
                                time.sleep(1.5)
                                
                                # Find note textarea strictly scoped inside this modal
                                textarea = modal.locator("textarea, #custom-message").first
                                try:
                                    textarea.wait_for(state="visible", timeout=3000)
                                except Exception:
                                    pass
                                    
                                if textarea.is_visible():
                                    # Personalize message template
                                    note_text = resolve_template(note_template, contact)
                                    # Truncate if exceeds LinkedIn limit (300 chars)
                                    if len(note_text) > 300:
                                        note_text = note_text[:297] + "..."
                                    state.add_log(f"Typing personalized note ({len(note_text)} chars)...", "info")
                                    
                                    # Human-like typing
                                    textarea.focus()
                                    for char in note_text:
                                        page.keyboard.write(char)
                                        time.sleep(random.uniform(0.01, 0.05))
                                        
                                    time.sleep(1.5)
                                    
                                    # Find and click Send strictly inside the modal
                                    send_btn = modal.locator("button:has-text('Send'), button[aria-label*='Send now']").first
                                    try:
                                        send_btn.wait_for(state="visible", timeout=2000)
                                    except Exception:
                                        pass
                                        
                                    if send_btn.is_visible() and send_btn.is_enabled():
                                        send_btn.click(force=True)
                                        state.add_log("Personalized connection request sent!", "success")
                                        note_sent_successfully = True
                                    else:
                                        raise Exception("Send button disabled/not found")
                                else:
                                    raise Exception("Textarea not found")
                            except Exception as note_err:
                                state.add_log(f"Note-sending failed: {str(note_err)}. Trying self-healing fallback to Send without a note...", "warning")
                                # Try clicking Cancel or Back to return to previous modal view if available
                                try:
                                    cancel_btn = modal.locator("button:has-text('Cancel'), button:has-text('Back'), button[aria-label*='Cancel'], button[aria-label*='Back']").first
                                    if cancel_btn.is_visible() and cancel_btn.is_enabled():
                                        cancel_btn.click(force=True)
                                        time.sleep(1.5)
                                except Exception:
                                    pass
                                
                        if not note_sent_successfully:
                            # Send without note
                            send_without_note_btn = modal.locator("button:has-text('Send without a note'), button[aria-label*='Send without a note']").first
                            if send_without_note_btn.is_visible() and send_without_note_btn.is_enabled():
                                send_without_note_btn.click(force=True)
                                state.add_log("Connection request sent (without note)!", "success")
                            else:
                                # Try general Send/Connect button strictly inside modal
                                send_general = modal.locator("button:has-text('Send'), button[aria-label*='Send now'], button:has-text('Connect')").first
                                if send_general.is_visible() and send_general.is_enabled():
                                    send_general.click(force=True)
                                    state.add_log("Connection request sent!", "success")
                                else:
                                    state.add_log("Could not send request: send buttons not found or disabled in modal.", "error")
                                    raise Exception("Send button not found in modal")
                                
                    # 6. Success: Update Database status to Pending
                    sent_today_count += 1
                    contact["status"] = "Pending"
                    contact["date_sent"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    db_data = load_db()
                    for d in db_data:
                        if d["profile_url"] == profile_url:
                            d["status"] = "Pending"
                            d["date_sent"] = contact["date_sent"]
                    save_db(db_data)
                    
                    # 7. Sleep random human-like delay
                    if idx < total_to_process - 1:
                        sleep_time = random.randint(delay_min, delay_max)
                        state.add_log(f"Sleeping for {sleep_time} seconds to simulate human activity...", "info")
                        for s in range(sleep_time):
                            if state.stop_requested:
                                break
                            time.sleep(1)
                            
                except Exception as ex:
                    state.add_log(f"Exception during request for {contact.get('name', 'Contact')}: {str(ex)}", "error")
                    
                    # Check if browser was closed or crashed during the operation
                    is_browser_closed = False
                    try:
                        if page.is_closed():
                            is_browser_closed = True
                    except Exception:
                        is_browser_closed = True
                        
                    if is_browser_closed:
                        state.add_log("Browser window was closed or crashed. Halting automation without marking remaining contacts as failed.", "warning")
                        break
                        
                    contact["status"] = "Failed"
                    contact["logs"] = str(ex)
                    
                    db_data = load_db()
                    for d in db_data:
                        if d["profile_url"] == profile_url:
                            d["status"] = "Failed"
                            d["logs"] = str(ex)
                    save_db(db_data)
                    
            state.add_log(f"Automation execution run finished. Requests sent during this run: {sent_today_count}", "success")
            
        except Exception as e:
            state.add_log(f"Critical error in automation loop: {str(e)}", "error")
        finally:
            state.stop_running()
            state.update_status(action="Idle", progress=100)
            if context:
                try: context.close()
                except: pass
            if playwright:
                try: playwright.stop()
                except: pass

    threading.Thread(target=run, daemon=True).start()
