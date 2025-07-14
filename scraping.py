import requests
import json
import pandas as pd
from bs4 import BeautifulSoup
import re
import time
import os

def fetch_and_save_shutuba_data(race_id, retries=3, delay=5):
    """
    Fetches shutuba data from netkeiba.com race page and saves it to a CSV file.
    It extracts data directly from the HTML, looking for a specific script tag.
    Prioritizes loading from a local CSV if it already exists.

    Args:
        race_id (str): The ID of the race.
        retries (int): Number of retries for fetching data.
        delay (int): Delay in seconds between retries.

    Returns:
        str: The path to the saved CSV file, or None if an error occurred.
    """
    csv_path = f"/Users/akahoshihiroki/Documents/pytests/keiba_yosou/shutuba_{race_id}.csv"

    # Check if CSV already exists locally
    if os.path.exists(csv_path):
        print(f"出馬表データを {csv_path} から読み込みました (既存ファイル)。")
        return csv_path

    # If not, try to fetch from netkeiba.com
    for i in range(retries):
        try:
            url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
            response = requests.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36",
                "Referer": "https://race.netkeiba.com/"
            })
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "lxml")

            # Look for the script tag that contains the horse data
            script_tag = soup.find('script', text=re.compile(r'var HorseData = '))
            if not script_tag:
                print(f"Error: HorseData script tag not found for race_id {race_id}")
                return None

            json_str_match = re.search(r'var HorseData = (.*?);', script_tag.string)
            if not json_str_match:
                print(f"Error: HorseData JSON not found in script tag for race_id {race_id}")
                return None

            horse_data_json = json_str_match.group(1)
            horse_list = json.loads(horse_data_json)

            if horse_list:
                df = pd.DataFrame(horse_list)
                df.to_csv(csv_path, index=False, encoding='utf-8-sig')
                print(f"出馬表データを {csv_path} に保存しました。")
                return csv_path
            else:
                print(f"出馬表データが空でした for race_id {race_id}。")
                return None

        except requests.exceptions.RequestException as e:
            print(f"出馬表ページの取得中にエラーが発生しました for race_id {race_id}: {e}")
            if i < retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print(f"Max retries reached for race_id {race_id}.")
        except json.JSONDecodeError:
            print(f"出馬表データJSONの解析中にエラーが発生しました for race_id {race_id}.")
            return None
        except Exception as e:
            print(f"予期せぬエラーが発生しました for race_id {race_id}: {e}")
            return None
    return None

if __name__ == '__main__':
    # Example usage for testing
    test_race_id = "202410030211" # Example race ID (北九州記念)
    print(f"Fetching data for race ID: {test_race_id}")
    csv_file = fetch_and_save_shutuba_data(test_race_id)
    if csv_file:
        print(f"Data saved to: {csv_file}")
    else:
        print("Failed to fetch data.")