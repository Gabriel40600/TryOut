import time
import csv
import json
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Configuration
SEARCH_URL = "https://www.metrocuadrado.com/apartamento-apartaestudio-casa/venta/nuevo/bogota?search=form"
MAX_PAGES = 3
OUTPUT_FILE = "metrocuadrado_properties.csv"
HEADLESS = True
DEBUG_DIR = "debug_screenshots"

# Create debug directory if it doesn't exist
if not os.path.exists(DEBUG_DIR):
    os.makedirs(DEBUG_DIR)


def init_driver():
    """Initialize Chrome WebDriver with verified options"""
    chrome_options = Options()
    if HEADLESS:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")
    # Ignore certificate errors to avoid privacy error page in restricted
    # environments
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--allow-running-insecure-content")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

    # Anti-detection options
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Remove navigator.webdriver flag
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    return driver


def take_screenshot(driver, name):
    """Take screenshot and save to debug directory"""
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"{DEBUG_DIR}/{name}_{timestamp}.png"
    driver.save_screenshot(filename)
    print(f"Saved screenshot: {filename}")
    return filename


def scrape_property_page(driver, url):
    """Scrape data from a single property page"""
    print(f"Scraping property: {url}")
    driver.get(url)

    try:
        # Wait for the page to load
        try:
            WebDriverWait(driver, 15).until(
                EC.visibility_of_element_located((By.XPATH, "//h1[@data-testid='title-listing-detail']"))
            )
        except TimeoutException:
            # Try alternative loading indicator
            WebDriverWait(driver, 15).until(
                EC.visibility_of_element_located((By.XPATH, "//div[@class='listing-detail']"))
            )

        # Extract JSON data from script tag
        script_element = driver.find_element(By.XPATH, "//script[@id='__NEXT_DATA__']")
        json_data = json.loads(script_element.get_attribute('textContent'))

        # Extract listing data
        page_props = json_data.get('props', {}).get('pageProps', {})
        listing = page_props.get('listing', {})

        if not listing:
            print("  - No listing data found in JSON")
            take_screenshot(driver, "no_listing_data")
            return None

        # Extract key details
        location = listing.get('location', {})
        broker = listing.get('broker', {})
        images = [img.get('url', '') for img in listing.get('images', []) if img.get('url')]

        # Compile property data
        return {
            "url": url,
            "title": listing.get('title', ''),
            "price": listing.get('price', {}).get('value', ''),
            "currency": listing.get('price', {}).get('currency', 'COP'),
            "location": location.get('formattedAddress', ''),
            "neighborhood": location.get('neighborhood', {}).get('name', ''),
            "city": location.get('city', {}).get('name', ''),
            "property_type": listing.get('propertyType', ''),
            "area": listing.get('area', ''),
            "rooms": listing.get('rooms', ''),
            "bathrooms": listing.get('bathrooms', ''),
            "parking": listing.get('parking', ''),
            "stratum": listing.get('stratum', ''),
            "status": listing.get('status', ''),
            "description": listing.get('description', '')[:500].replace('\n', ' ') + "...",
            "features": ", ".join(listing.get('features', [])),
            "broker": broker.get('name', ''),
            "broker_phone": broker.get('phone', ''),
            "images": "; ".join(images),
            "virtual_tour": listing.get('virtualTourUrl', ''),
            "property_id": listing.get('id', ''),
            "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    except Exception as e:
        print(f"  - Error scraping property: {str(e)}")
        take_screenshot(driver, "property_error")
        return None


def scrape_search_results(driver):
    """Scrape property listings using multiple detection methods"""
    print(f"Navigating to search page: {SEARCH_URL}")
    driver.get(SEARCH_URL)
    time.sleep(3)  # Initial sleep to let page load

    # Save initial page screenshot
    take_screenshot(driver, "initial_page")

    # Accept cookies if present
    try:
        accept_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Aceptar todo')]"))
        )
        accept_button.click()
        print("Accepted cookies")
        time.sleep(1)
        take_screenshot(driver, "after_cookies")
    except:
        print("No cookie dialog found")

    properties = []
    page = 1

    while page <= MAX_PAGES:
        try:
            print(f"\n{'=' * 50}")
            print(f"Processing page {page}/{MAX_PAGES}")
            print(f"{'=' * 50}")

            # Scroll to load all content
            print("Scrolling to load content...")
            for _ in range(2):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            take_screenshot(driver, f"after_scroll_page_{page}")

            # Try multiple methods to find property cards
            cards = []
            print("Attempting to locate property cards...")

            # Method 1: data-testid attribute
            try:
                cards = driver.find_elements(By.CSS_SELECTOR, "div[data-testid='m2-card-listings-container']")
                print(f"Found {len(cards)} listings using data-testid method")
            except NoSuchElementException:
                print("No listings found using data-testid method")

            # Method 2: Class-based selector if first method failed
            if not cards:
                try:
                    cards = driver.find_elements(By.CSS_SELECTOR, "div.m2-card-listing")
                    print(f"Found {len(cards)} listings using class-based method")
                except NoSuchElementException:
                    print("No listings found using class-based method")

            # Method 3: Generic card detection
            if not cards:
                try:
                    cards = driver.find_elements(By.CSS_SELECTOR, "div[class*='card']")
                    print(f"Found {len(cards)} listings using generic card method")
                except NoSuchElementException:
                    print("No listings found using generic card method")

            # If still no cards, show page source for debugging
            if not cards:
                print("No property cards found on the page")
                page_source = driver.page_source
                with open(f"{DEBUG_DIR}/page_{page}_source.html", "w", encoding="utf-8") as f:
                    f.write(page_source)
                print(f"Saved page source to {DEBUG_DIR}/page_{page}_source.html")
                take_screenshot(driver, f"no_cards_page_{page}")
                break

            # Extract URLs from cards
            links = []
            for card in cards:
                try:
                    # Try to find link inside card
                    try:
                        link = card.find_element(By.TAG_NAME, "a")
                    except NoSuchElementException:
                        # Look for any link inside the card
                        link = card.find_element(By.CSS_SELECTOR, "a")

                    href = link.get_attribute('href')
                    if href and ("/inmueble/" in href or "/proyecto/" in href):
                        links.append(href)
                except Exception as e:
                    print(f"  - Error extracting link: {str(e)}")
                    continue

            # Remove duplicates
            links = list(set(links))
            print(f"Found {len(links)} unique listing URLs")

            if not links:
                print("No valid links found - stopping")
                take_screenshot(driver, "no_valid_links")
                break

            # Scrape each property
            for i, url in enumerate(links, 1):
                print(f"\nProcessing property {i}/{len(links)}: {url[:70]}...")
                property_data = scrape_property_page(driver, url)
                if property_data:
                    properties.append(property_data)
                time.sleep(2)  # Pause between requests

            # Go to next page
            if page < MAX_PAGES:
                print("Attempting to navigate to next page...")
                try:
                    # Try multiple ways to find next button
                    try:
                        next_button = driver.find_element(By.XPATH, "//a[@aria-label='Siguiente página']")
                    except:
                        try:
                            next_button = driver.find_element(By.XPATH, "//a[contains(@class, 'm2-pagination__next')]")
                        except:
                            next_button = driver.find_element(By.XPATH, "//a[contains(text(), 'Siguiente')]")

                    if next_button:
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        driver.execute_script("arguments[0].click();", next_button)

                        # Wait for new page to load
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.XPATH,
                                                            "//div[contains(@class, 'm2-card-listing') or @data-testid='m2-card-listings-container']"))
                        )
                        time.sleep(3)
                        page += 1
                        take_screenshot(driver, f"after_navigation_page_{page}")
                    else:
                        print("Next page button not found - stopping pagination")
                        break
                except Exception as e:
                    print(f"Error navigating to next page: {str(e)}")
                    take_screenshot(driver, "next_page_error")
                    break
            else:
                break

        except Exception as e:
            print(f"Error processing page {page}: {str(e)}")
            take_screenshot(driver, f"page_{page}_error")
            break

    return properties


def main():
    print("Starting MetroCuadrado scraper with enhanced debugging...")
    driver = init_driver()

    try:
        # Scrape properties
        results = scrape_search_results(driver)

        if results:
            # Save to CSV
            with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)
            print(f"\nSuccess! Saved {len(results)} properties to {OUTPUT_FILE}")
        else:
            print("No data scraped")

    except Exception as e:
        print(f"Main error: {str(e)}")
        take_screenshot(driver, "main_error")
    finally:
        driver.quit()
        print("Browser closed")


if __name__ == "__main__":
    main()