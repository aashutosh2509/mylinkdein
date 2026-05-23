import os
import time
from playwright.sync_api import sync_playwright

USER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linkedin_user_data")

def main():
    print("Launching persistent browser to verify anchor selectors...")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=True,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        page = context.new_page()
        
        profile_url = "https://www.linkedin.com/in/dr-ramkisan-pawar-7a8470b9"
        print(f"Navigating to: {profile_url}")
        page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)
        
        # Test anchors
        HEADER_ANCHOR = "xpath=(//main//section[1]//h1 | //main//section[1]//h2)[1]/ancestor::section[1]"
        print(f"\nHEADER_ANCHOR base path: {HEADER_ANCHOR}")
        
        try:
            anchor_el = page.locator(HEADER_ANCHOR).first
            print(f"Anchor visible: {anchor_el.is_visible()}")
            if anchor_el.is_visible():
                print(f"Anchor outerHTML tag and classes: {anchor_el.evaluate('el => el.tagName')} | class='{anchor_el.evaluate('el => el.className')}'")
        except Exception as e:
            print(f"ERROR matching anchor: {str(e)}")

        print("\n--- ANCHORED SELECTORS TEST ---")
        tests = {
            "Profile Name": "xpath=(//main//section[1]//h1 | //main//section[1]//h2)[1]",
            "More Button": f"{HEADER_ANCHOR}//button[contains(., 'More')]",
            "Follow Button": f"{HEADER_ANCHOR}//button[contains(., 'Follow')]",
            "Message Button": f"{HEADER_ANCHOR}//button[contains(., 'Message')]",
            "Connect Text/Span": f"{HEADER_ANCHOR}//*[text()='Connect']",
            "Degree Badge (Text)": f"{HEADER_ANCHOR}//*[text()='1st' or text()='2nd' or text()='3rd' or contains(text(), '1st') or contains(text(), '2nd') or contains(text(), '3rd')]"
        }
        
        for name, sel in tests.items():
            try:
                loc = page.locator(sel).first
                if loc.is_visible():
                    print(f"PASS: {name} found | Text: '{loc.text_content().strip()}'")
                else:
                    print(f"FAIL: {name} is NOT visible using '{sel}'")
            except Exception as e:
                print(f"ERROR on {name} using '{sel}': {str(e)}")
                
        context.close()

if __name__ == "__main__":
    main()
