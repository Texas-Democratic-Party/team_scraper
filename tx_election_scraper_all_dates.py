import argparse
import logging
import os
import pandas as pd
import time
from datetime import datetime, timedelta
from pathlib import Path

from pandas_gbq import to_gbq
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def init_driver(local_download_path):
    os.makedirs(local_download_path, exist_ok=True)
    logger.info("Initializing Chrome driver...")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--remote-debugging-port=9222")
    chrome_options.add_argument('--dns-prefetch-disable')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--enable-cdp-events')
    chrome_options.add_argument('--window-size=1920,1080')

    prefs = {
        "download.default_directory": str(Path(local_download_path).absolute()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)

    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": str(Path(local_download_path).absolute())
    })

    logger.info("Chrome driver initialized successfully")
    return driver


def load_page(driver, wait, base_url, election_name):
    """Navigate to the base URL and select the election — used at start and between iterations."""
    logger.info(f"Loading page and selecting election: {election_name}")
    driver.get(base_url)
    time.sleep(3)

    # Find election dropdown by formcontrolname
    election_dropdown = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "mat-select[formcontrolname='selectElection']"))
    )
    election_dropdown.click()
    time.sleep(1)

    option_xpath = f"//mat-option//span[contains(text(), '{election_name}')]"
    election_option = wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath)))
    election_option.click()
    logger.info(f"Election selected: {election_name}")
    time.sleep(1.5)


def get_available_dates(driver, wait):
    """Scrape all available date options from the date dropdown and return as a list, filtering out future dates."""
    logger.info("Reading available dates from dropdown...")

    date_dropdown = None
    try:
        date_dropdown = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "mat-select[formcontrolname='VotingByDate']"))
        )
    except TimeoutException:
        date_dropdown = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "mat-select[placeholder='Select Early Voting Date']"))
        )

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_dropdown)
    time.sleep(0.5)
    date_dropdown.click()
    time.sleep(1.5)

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.cdk-overlay-pane")))

    all_options = driver.find_elements(By.CSS_SELECTOR, "mat-option")

    # Collect all non-placeholder option texts
    dates = [
        opt.text.strip()
        for opt in all_options
        if opt.text.strip() and opt.text.strip().lower() != "select early voting date"
    ]

    # Filter out future dates (only include dates up to yesterday)
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    filtered_dates = []
    for date_str in dates:
        try:
            # Parse the date string (format: MM/DD/YYYY)
            date_obj = datetime.strptime(date_str, '%m/%d/%Y').date()
            if date_obj <= today:
                filtered_dates.append(date_str)
            else:
                logger.debug(f"Skipping future date: {date_str}")
        except ValueError:
            logger.warning(f"Could not parse date: {date_str}, skipping")
            continue

    logger.info(f"Found {len(dates)} total dates, {len(filtered_dates)} dates up to today ({today.strftime('%m/%d/%Y')})")
    logger.info(f"Dates to process: {filtered_dates}")

    # Close the dropdown without selecting anything by pressing Escape
    driver.find_element(By.TAG_NAME, "body").send_keys("\ue00c")
    time.sleep(0.5)

    return filtered_dates


def select_date(driver, wait, target_date):
    """Select a specific date from the date dropdown."""
    logger.info(f"Selecting date: {target_date}")

    date_dropdown = None
    try:
        date_dropdown = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "mat-select[formcontrolname='VotingByDate']"))
        )
    except TimeoutException:
        date_dropdown = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "mat-select[placeholder='Select Early Voting Date']"))
        )

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_dropdown)
    time.sleep(0.5)
    date_dropdown.click()
    time.sleep(1.5)

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.cdk-overlay-pane")))

    option_xpath = f"//mat-option//span[contains(text(), '{target_date}')]"
    date_option = wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath)))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_option)
    time.sleep(0.3)
    date_option.click()
    logger.info(f"Date selected: {target_date}")
    time.sleep(1.5)


def click_submit(driver, wait):
    """Click the Submit button."""
    logger.info("Clicking Submit button...")

    submit_button = None
    try:
        submit_button = wait.until(EC.element_to_be_clickable((By.ID, 'btnPlaceByCounty')))
    except TimeoutException:
        try:
            submit_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Submit')]"))
            )
        except TimeoutException:
            submit_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.mat-mdc-raised-button"))
            )

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submit_button)
    time.sleep(0.5)

    try:
        submit_button.click()
    except Exception:
        driver.execute_script("arguments[0].click();", submit_button)

    logger.info("Submit button clicked")
    time.sleep(3)


def download_csv(driver, wait, csv_dl_dir, date_label):
    """Click 'Generate Statewide Report' button and wait for the file, then return the file path."""
    logger.info("Looking for 'Generate Statewide Report' button...")

    report_button = None
    try:
        # Strategy 1: Find by the mdc-button__label text
        report_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//span[@class='mdc-button__label' and contains(text(), 'Generate Statewide Report')]"))
        )
    except TimeoutException:
        # Strategy 2: Find any button containing the text
        try:
            report_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Generate Statewide Report')]"))
            )
        except TimeoutException:
            # Strategy 3: Find by button with mdc-button class containing the text
            report_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'mdc-button')]//span[contains(text(), 'Generate Statewide Report')]"))
            )

    existing_csvs = {f for f in os.listdir(csv_dl_dir) if f.endswith('.csv')}
    logger.info(f"'Generate Statewide Report' button found, clicking for date: {date_label}")
    
    # Scroll into view and click
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", report_button)
    time.sleep(0.5)
    
    try:
        report_button.click()
    except Exception:
        # Try JavaScript click if regular click fails
        driver.execute_script("arguments[0].click();", report_button)

    max_wait = 60
    for _ in range(max_wait):
        current_csvs = {f for f in os.listdir(csv_dl_dir) if f.endswith('.csv')}
        new_files = current_csvs - existing_csvs
        if new_files:
            newest = max(
                [os.path.join(csv_dl_dir, f) for f in new_files],
                key=os.path.getctime
            )
            logger.info(f"Download complete: {os.path.basename(newest)}")
            return newest
        time.sleep(1)

    raise TimeoutException(f"CSV did not download within {max_wait} seconds for date: {date_label}")


def scrape_all_dates(election_name, csv_dl_dir, base_url, primary_party=None):
    """
    Main scraping function. Iterates through all available dates for an election,
    downloads the CSV for each, and returns a single concatenated DataFrame.
    
    Args:
        election_name: Name of the election to scrape
        csv_dl_dir: Directory for temporary CSV downloads
        base_url: Base URL of the election website
        primary_party: Optional party designation (e.g., 'D' or 'R') to add as ballot_party column
    """
    logger.info("=" * 70)
    logger.info(f"Starting full scrape for election: {election_name}")
    if primary_party:
        logger.info(f"Primary party: {primary_party}")
    logger.info("=" * 70)

    # Clear download directory
    for f in os.listdir(csv_dl_dir):
        fpath = os.path.join(csv_dl_dir, f)
        if os.path.isfile(fpath):
            os.remove(fpath)

    driver = init_driver(local_download_path=csv_dl_dir)
    wait = WebDriverWait(driver, 20)

    try:
        # Step 1: Load page, select election, and read the available dates
        load_page(driver, wait, base_url, election_name)
        available_dates = get_available_dates(driver, wait)

        if not available_dates:
            raise Exception("No dates found in the date dropdown (or all dates are in the future).")

        # Step 2: Iterate through each date
        all_dfs = []
        for i, date in enumerate(available_dates, start=1):
            logger.info(f"--- Processing date {i}/{len(available_dates)}: {date} ---")

            try:
                # Return to base page and re-select election on every iteration
                # to get back to a clean state with the date dropdown available
                load_page(driver, wait, base_url, election_name)
                select_date(driver, wait, date)
                click_submit(driver, wait)
                csv_path = download_csv(driver, wait, csv_dl_dir, date)

                df = pd.read_csv(csv_path)
                
                # Rename id_voter to sos_id
                if 'id_voter' in df.columns:
                    df.rename(columns={'id_voter': 'sos_id'}, inplace=True)
                    logger.debug("Renamed column 'id_voter' to 'sos_id'")
                
                # Add report_date column
                df['report_date'] = date
                
                # Add ballot_party column if primary_party is specified
                if primary_party:
                    df['ballot_party'] = primary_party
                    logger.debug(f"Added column 'ballot_party' with value '{primary_party}'")
                
                all_dfs.append(df)
                logger.info(f"Appended {len(df)} rows for date: {date}")

                # Remove the downloaded file to keep the folder clean
                os.remove(csv_path)

            except Exception as e:
                logger.error(f"Failed to process date {date}: {str(e)}")
                try:
                    driver.save_screenshot(f"error_{date.replace('/', '-')}.png")
                except:
                    pass
                # Continue to the next date rather than aborting the whole run
                continue

        if not all_dfs:
            raise Exception("No data was successfully downloaded for any date.")

        final_df = pd.concat(all_dfs, axis=0, ignore_index=True)
        logger.info("=" * 70)
        logger.info(f"Scraping complete. Total rows: {len(final_df)}, Dates: {len(all_dfs)}/{len(available_dates)}")
        logger.info("=" * 70)
        return final_df

    finally:
        driver.quit()
        logger.debug("Browser closed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Texas Election Early Voting Scraper — All Dates",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('--election', type=str, default='2026 SPECIAL RUNOFF ELECTION CONGRESSIONAL DISTRICT 18')
    parser.add_argument('--output-dir', type=str, default='downloaded_files')
    parser.add_argument('--output-csv', type=str, default='all_dates_ev_turnout.csv',
                        help="Filename for the final concatenated CSV output")
    parser.add_argument('--log-level', type=str, default='INFO',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'])
    parser.add_argument('--primary', type=str, default=None,
                        help="Primary ballot party (e.g., 'D' or 'R'). If provided, adds 'ballot_party' column to dataframe")
    parser.add_argument('--upload-to-gbq', action='store_true',
                        help="Upload results to Google BigQuery")
    parser.add_argument('--gbq-project-id', type=str, default='demstxsp',
                        help="Google BigQuery project ID")
    parser.add_argument('--gbq-dataset', type=str, default='evav_processing_2026',
                        help="Google BigQuery dataset name")
    parser.add_argument('--gbq-table', type=str, default=None,
                        help="Google BigQuery table name (auto-generated from election if not specified)")
    args = parser.parse_args()

    logger.setLevel(getattr(logging, args.log_level))

    BASE_URL = "https://goelect.txelections.civixapps.com/ivis-evr-ui/evr"

    os.makedirs(args.output_dir, exist_ok=True)

    final_df = scrape_all_dates(
        election_name=args.election,
        csv_dl_dir=args.output_dir,
        base_url=BASE_URL,
        primary_party=args.primary
    )

    output_path = os.path.join(args.output_dir, args.output_csv)
    final_df.to_csv(output_path, index=False)
    logger.info(f"Final dataset saved to: {output_path}")

    print("\n" + "=" * 70)
    print(f"Shape: {final_df.shape[0]} rows × {final_df.shape[1]} columns")
    print(f"Dates collected: {final_df['report_date'].nunique()}")
    print(f"\nFirst few rows:\n{final_df.head().to_string()}")
    print("=" * 70)

    # Upload to BigQuery if requested
    if args.upload_to_gbq:
        logger.info("\n" + "=" * 70)
        logger.info("Uploading to Google BigQuery...")
        
        # Auto-generate table name from election if not specified
        if args.gbq_table is None:
            # Convert election name to valid table name
            # Example: "2026 MARCH 3 PRIMARY ELECTION" -> "20260303_primary_election"
            table_name = args.election.lower()
            table_name = table_name.replace(" ", "_")
            # Remove invalid characters for BigQuery table names
            table_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in table_name)
            args.gbq_table = table_name
        
        full_table_name = f"{args.gbq_dataset}.{args.gbq_table}"
        logger.info(f"Target table: {args.gbq_project_id}.{full_table_name}")
        logger.info(f"Preview of data being uploaded:\n{final_df.head()}")
        
        try:
            to_gbq(
                final_df,
                full_table_name,
                project_id=args.gbq_project_id,
                if_exists='replace'
            )
            logger.info(f"Successfully uploaded {len(final_df)} rows to BigQuery!")
            logger.info("=" * 70)
        except Exception as e:
            logger.error(f"Failed to upload to BigQuery: {str(e)}")
            logger.error("Data has been saved locally to CSV")
            logger.error("=" * 70)
