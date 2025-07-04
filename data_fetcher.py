import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

# Base URL for horse data
BASE_URL = "https://db.netkeiba.com/horse/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
}

def get_horse_data(horse_id):
    """
    Fetches and parses the data for a given horse_id from netkeiba database.

    Args:
        horse_id (str): The ID of the horse.

    Returns:
        tuple: A tuple containing:
            - pd.DataFrame: Past race results of the horse. None if not found.
            - dict: A dictionary with parent horse IDs ('sire', 'mare'). None if not found.
    """
    try:
        url = f"{BASE_URL}{horse_id}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        # It's good practice to sleep between requests to avoid overwhelming the server.
        time.sleep(1)

        soup = BeautifulSoup(response.content, "lxml")

        # --- Get Past Race Results ---
        race_results_df = None
        results_table = soup.find("table", class_="db_h_race_results")
        if results_table:
            race_results_df = pd.read_html(str(results_table))[0]

        # --- Get Parent IDs ---
        parent_ids = {'sire': None, 'mare': None}
        blood_table = soup.find("table", class_="blood_table")
        if blood_table:
            # Find all <a> tags that link to horse pages within the blood_table
            horse_links = [link for link in blood_table.find_all('a') if link.get('href') and '/horse/' in link.get('href')]

            # Assuming the first link is the sire and the second is the mare
            if len(horse_links) >= 1:
                parent_ids['sire'] = horse_links[0].get('href').split('/')[-2]
            if len(horse_links) >= 2:
                parent_ids['mare'] = horse_links[1].get('href').split('/')[-2]

        return race_results_df, parent_ids

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for horse {horse_id}: {e}")
        return None, None
    except Exception as e:
        print(f"An error occurred while processing horse {horse_id}: {e}")
        return None, None

if __name__ == '__main__':
    # This is a test run to check if the fetcher works.
    # It uses a sample horse_id from your previous CSV.
    sample_horse_id = "2016104668" # カリボール
    print(f"--- Testing data_fetcher.py with horse_id: {sample_horse_id} ---")
    
    results, parents = get_horse_data(sample_horse_id)

    if results is not None:
        print("\n[Past Race Results Sample]")
        print(results.head().to_string())
    else:
        print("\nCould not fetch past race results.")

    if parents and (parents['sire'] or parents['mare']):
        print("\n[Parent IDs]")
        print(f"Sire (Father) ID: {parents['sire']}")
        print(f"Mare (Mother) ID: {parents['mare']}")
    else:
        print("\nCould not fetch parent IDs.")
