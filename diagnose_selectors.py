import os
import time
from playwright.sync_api import sync_playwright

USER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linkedin_user_data")

def main():
    print("Launching persistent browser for selector diagnostic...")
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
        
        # Test out various selectors for finding the name, the direct connect button, and the "More" button.
        print("\n--- NAME SELECTOR TEST ---")
        name_selectors = [
            "h1",
            "h2",
            "//main//section[1]//h2",
            "//main//section[1]//h1",
            "//main//section[contains(@class, 'profile-card')]//h2",
            "//main//section[contains(@class, 'profile-card')]//h1",
            ".pv-text-details__leftpanel h1",
            ".pv-text-details__leftpanel h2",
        ]
        for sel in name_selectors:
            try:
                if sel.startswith("//"):
                    loc = page.locator(f"xpath={sel}").first
                else:
                    loc = page.locator(sel).first
                if loc.is_visible():
                    print(f"PASS: Name selector '{sel}' matches visible element. Text: '{loc.text_content().strip()}'")
                else:
                    print(f"FAIL: Name selector '{sel}' is not visible.")
            except Exception as e:
                print(f"ERROR: Name selector '{sel}' raised error: {str(e)}")

        print("\n--- FIRST SECTION TEST ---")
        try:
            sec = page.locator("main section").first
            print(f"main section (first) is_visible: {sec.is_visible()}")
            print(f"main section (first) outerHTML preview: {sec.evaluate('el => el.outerHTML.substring(0, 300)')}...")
        except Exception as e:
            print(f"ERROR: main section first failed: {str(e)}")

        print("\n--- MORE BUTTON SELECTOR TEST ---")
        more_selectors = [
            "//main//section[1]//button[contains(., 'More')]",
            "//main//section[1]//button[contains(., 'actions')]",
            "//main//section[1]//*[text()='More']",
            "//main//section[contains(@class, 'profile-card')]//button[contains(., 'More')]",
            "//main//section[1]//button[contains(., 'More') or contains(., 'actions')]",
            "button:has-text('More')",
            "main button:has-text('More')",
            "main section button:has-text('More')",
        ]
        for sel in more_selectors:
            try:
                if sel.startswith("//"):
                    loc = page.locator(f"xpath={sel}").first
                else:
                    loc = page.locator(sel).first
                if loc.is_visible():
                    print(f"PASS: More selector '{sel}' matches visible element. Text: '{loc.text_content().strip()}'")
                else:
                    print(f"FAIL: More selector '{sel}' is not visible.")
            except Exception as e:
                print(f"ERROR: More selector '{sel}' raised error: {str(e)}")

        context.close()

if __name__ == "__main__":
    main()
