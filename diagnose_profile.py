import os
import time
from playwright.sync_api import sync_playwright

USER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linkedin_user_data")

def main():
    print("Launching persistent browser for DOM diagnostic...")
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
        
        # 1. Dump all headings
        print("\n--- HEADINGS ---")
        for tag in ["h1", "h2", "h3", "h4"]:
            elements = page.locator(tag).all()
            print(f"Found {len(elements)} <{tag}> elements:")
            for idx, el in enumerate(elements):
                try:
                    text = el.text_content() or ""
                    visible = el.is_visible()
                    print(f"  [{idx+1}] Visible: {visible} | Text: {text.strip()[:100]}")
                except Exception as e:
                    print(f"  [{idx+1}] Error: {str(e)}")
                    
        # 2. Dump all button-like elements with text or aria-labels
        print("\n--- BUTTONS ---")
        buttons = page.locator("button, a[role='button'], div[role='button']").all()
        print(f"Found {len(buttons)} button elements:")
        for idx, btn in enumerate(buttons):
            try:
                text = btn.text_content() or ""
                text_clean = " ".join(text.split())
                label = btn.get_attribute("aria-label") or ""
                visible = btn.is_visible()
                if visible and (text_clean or label):
                    print(f"  [{idx+1}] Text: '{text_clean}' | Aria-label: '{label}'")
            except Exception as e:
                pass
                
        # 3. Check for specific text content
        print("\n--- SEARCH FOR CONNECT/MORE TEXT ---")
        for search_word in ["Connect", "More", "Message"]:
            locators = page.locator(f"//button[contains(., '{search_word}')] | //*[text()='{search_word}'] | //*[contains(text(), '{search_word}')]").all()
            print(f"Searching for '{search_word}' returned {len(locators)} matches:")
            for idx, loc in enumerate(locators):
                try:
                    if loc.is_visible():
                        tag_name = loc.evaluate("el => el.tagName")
                        text_clean = " ".join((loc.text_content() or "").split())
                        print(f"  [{idx+1}] Tag: <{tag_name}> | Text: '{text_clean[:100]}'")
                except Exception:
                    pass
                    
        context.close()

if __name__ == "__main__":
    main()
