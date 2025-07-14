import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
import datetime
from io import StringIO

# Base URL for horse data
BASE_URL = "https://db.netkeiba.com/horse/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36"
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
        time.sleep(1)

        soup = BeautifulSoup(response.content, "lxml")

        # --- Get Past Race Results ---
        race_results_df = None
        results_table = soup.find("table", class_="db_h_race_results")
        if results_table:
            race_results_df = pd.read_html(StringIO(str(results_table)))[0]
            # Rename columns for easier access
            race_results_df.rename(columns={'上り': 'agari_3f'}, inplace=True)

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

def get_horse_course_aptitude(horse_id):
    """Fetches course aptitude data for a given horse_id."""
    try:
        url = f"{BASE_URL}{horse_id}"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        time.sleep(1)
        soup = BeautifulSoup(response.content, "lxml")

        # Find the table containing course aptitude data
        # It's usually within a div with class 'db_prof_area' and then a table
        course_aptitude_table = None
        prof_area = soup.find("div", class_="db_prof_area")
        if prof_area:
            # Look for the specific table within this area that has course aptitude
            # This might be identified by a preceding h3 tag or a specific table structure
            # A common pattern is to find the table after an h3 with text 'コース別成績'
            for h3 in prof_area.find_all('h3'):
                if 'コース別成績' in h3.text:
                    course_aptitude_table = h3.find_next_sibling('table')
                    break

        if course_aptitude_table:
            df = pd.read_html(StringIO(str(course_aptitude_table)))[0]
            # Clean up column names if necessary (e.g., remove spaces)
            df.columns = [col.replace(' ', '') for col in df.columns]
            return df
    except Exception as e:
        print(f"Could not fetch horse course aptitude for {horse_id}: {e}")
    return pd.DataFrame()

def get_jockey_leading_data(year):
    """Fetches the jockey leading data for a specific year, handling pagination and caching."""
    current_year = datetime.date.today().year
    if year > current_year:
        year = current_year # Use current year's data for future races

    cache_file = f"/Users/akahoshihiroki/Documents/pytests/keiba_yosou/jockey_leading_{year}.csv"

    # Try to load from cache
    if os.path.exists(cache_file):
        try:
            print(f"Loading jockey leading data from cache: {cache_file}")
            return pd.read_csv(cache_file)
        except Exception as e:
            print(f"Error loading jockey data from cache {cache_file}: {e}. Fetching from web.")

    all_jockey_data = pd.DataFrame()
    page_num = 1
    while True:
        try:
            url = f"https://db.netkeiba.com/jockey/jockey_leading_jra.html?year={year}&page={page_num}"
            response = requests.get(url, headers=HEADERS)
            response.raise_for_status()
            time.sleep(1)
            soup = BeautifulSoup(response.content, "lxml")

            # Find the main table containing jockey data
            jockey_table = soup.find("table", class_="nk_tb_common race_table_01")
            if not jockey_table:
                break # No more tables, end pagination

            df = pd.read_html(StringIO(str(jockey_table)), header=None)[0]

            # Assuming the first row of the DataFrame is the header
            # and the actual data starts from the second row.
            df = pd.read_html(StringIO(str(jockey_table)), header=0)[0] # Let pandas handle header

            # Clean column names (remove spaces and other potential issues)
            # Convert MultiIndex to single level if it exists
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = ['_'.join(col).strip() for col in df.columns.values]
            df.columns = [col.replace(' ', '').strip() for col in df.columns]

            # Filter and rename relevant columns
            expected_cols_map = {
                '騎手': '騎手',
                '1着': '1着',
                '2着': '2着',
                '3着': '3着',
                '着外': '着外'
            }
            
            # Create a new DataFrame with only the expected columns, handling missing ones
            df_processed = pd.DataFrame()
            for expected_col_name, _ in expected_cols_map.items():
                found_col = None
                for actual_col_name in df.columns:
                    if expected_col_name in actual_col_name: # Use 'in' for partial matching
                        found_col = actual_col_name
                        break
                if found_col:
                    df_processed[expected_col_name] = df[found_col]
                else:
                    # If a critical column is missing, print a warning and skip this page
                    print(f"Warning: Critical column '{expected_col_name}' not found in jockey table for year {year}, page {page_num}. Actual columns: {df.columns.tolist()}")
                    df_processed = pd.DataFrame() # Clear df_processed to indicate failure for this page
                    break

            if not df_processed.empty:
                df_processed['1着'] = pd.to_numeric(df_processed['1着'], errors='coerce').fillna(0)
                df_processed['2着'] = pd.to_numeric(df_processed['2着'], errors='coerce').fillna(0)
                df_processed['3着'] = pd.to_numeric(df_processed['3着'], errors='coerce').fillna(0)
                df_processed['着外'] = pd.to_numeric(df_processed['着外'], errors='coerce').fillna(0)

                total_races_run = df_processed['1着'] + df_processed['2着'] + df_processed['3着'] + df_processed['着外']
                df_processed['win_rate'] = (df_processed['1着'] / total_races_run).fillna(0)
                df_processed['rentai_rate'] = ((df_processed['1着'] + df_processed['2着']) / total_races_run).fillna(0)

                df_final = df_processed[['騎手', 'win_rate', 'rentai_rate']]
                all_jockey_data = pd.concat([all_jockey_data, df_final], ignore_index=True)
            else:
                # If df_processed is empty due to missing critical columns, continue to next page
                pass # Warning already printed inside the loop

            # Check for next page
            pager = soup.find("div", class_="common_pager")
            # Check for a link to the next page number specifically
            next_page_link = pager.find('a', string=str(page_num + 1)) if pager else None
            if next_page_link:
                page_num += 1
            else:
                break # No next page link

        except requests.exceptions.RequestException as e:
            print(f"Could not fetch jockey leading data for {year}, page {page_num}: {e}")
            break
        except Exception as e:
            print(f"An unexpected error occurred while processing jockey leading data for {year}, page {page_num}: {e}")
            break
    
    # Save to cache
    if not all_jockey_data.empty:
        all_jockey_data.to_csv(cache_file, index=False)
        print(f"Jockey leading data saved to cache: {cache_file}")

    return all_jockey_data

def get_jockey_course_aptitude(jockey_id):
    """Fetches course aptitude data for a given jockey_id."""
    try:
        url = f"https://db.netkeiba.com/jockey/{jockey_id}/"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        time.sleep(1)
        soup = BeautifulSoup(response.content, "lxml")

        course_aptitude_table = None
        # Jockey course aptitude is usually in a table after an h3 with text 'コース別成績'
        for h3 in soup.find_all('h3'):
            if 'コース別成績' in h3.text:
                course_aptitude_table = h3.find_next_sibling('table')
                break

        if course_aptitude_table:
            df = pd.read_html(StringIO(str(course_aptitude_table)))[0]
            df.columns = [col.replace(' ', '') for col in df.columns]
            return df
    except Exception as e:
        print(f"Could not fetch jockey course aptitude for {jockey_id}: {e}")
    return pd.DataFrame()

def get_sire_course_aptitude(sire_id):
    """Fetches course aptitude data for a given sire_id."""
    try:
        url = f"https://db.netkeiba.com/horse/sire/{sire_id}/"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        time.sleep(1)
        soup = BeautifulSoup(response.content, "lxml")

        course_aptitude_table = None
        for h3 in soup.find_all('h3'):
            if 'コース別成績' in h3.text:
                course_aptitude_table = h3.find_next_sibling('table')
                break

        if course_aptitude_table:
            df = pd.read_html(StringIO(str(course_aptitude_table)))[0]
            df.columns = [col.replace(' ', '') for col in df.columns]
            return df
    except Exception as e:
        print(f"Could not fetch sire course aptitude for {sire_id}: {e}")
    return pd.DataFrame()

def get_bms_course_aptitude(bms_id):
    """Fetches course aptitude data for a given bms_id."""
    try:
        url = f"https://db.netkeiba.com/horse/bms/{bms_id}/"
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        time.sleep(1)
        soup = BeautifulSoup(response.content, "lxml")

        course_aptitude_table = None
        for h3 in soup.find_all('h3'):
            if 'コース別成績' in h3.text:
                course_aptitude_table = h3.find_next_sibling('table')
                break

        if course_aptitude_table:
            df = pd.read_html(StringIO(str(course_aptitude_table)))[0]
            df.columns = [col.replace(' ', '') for col in df.columns]
            return df
    except Exception as e:
        print(f"Could not fetch bms course aptitude for {bms_id}: {e}")
    return pd.DataFrame()