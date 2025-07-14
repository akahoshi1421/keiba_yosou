import pandas as pd
import itertools
import sys
import re
import requests
from bs4 import BeautifulSoup
from scorer import get_horse_total_score
from scraping import fetch_and_save_shutuba_data

# --- Configuration ---
# No specific configuration for number of recommendations as trifecta is removed.

def get_race_info_from_url(race_url):
    """
    Scrapes the race page to get race details.

    Args:
        race_url (str): The URL of the race page.

    Returns:
        dict: A dictionary containing race details, or None if an error occurred.
    """
    try:
        response = requests.get(race_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")

        # Extract race details from RaceData01
        race_details_element = soup.find('div', class_='RaceData01')
        if not race_details_element:
            print("RaceData01 element not found.")
            return None
        details_text = race_details_element.text.strip()

        distance_match = re.search(r'(芝|ダ)(\d+)m', details_text)
        if not distance_match:
            print("Could not extract distance from RaceData01.")
            return None
        track_type = distance_match.group(1) + str(distance_match.group(2))

        weather_match = re.search(r'天候:(\w+)', details_text)
        weather = weather_match.group(1) if weather_match else "良"

        # Search for the date in the entire page text, as its location can be inconsistent
        page_text = soup.get_text()
        date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', page_text)
        if date_match:
            year, month, day = date_match.groups()
            race_date_str = f"{year}-{month}-{day}"
            race_date = pd.to_datetime(race_date_str)
        else:
            print(f"Could not find date in the page's text.")
            return None

        return {
            "distance": track_type,
            "track_type": weather,  # Assuming track condition is same as weather for simplicity
            "weather": weather,
            "date": race_date
        }
    except Exception as e:
        print(f"レース情報の取得中にエラー: {e}")
        return None

def main(race_url, lap_times=None):
    print(f"--- Analyzing race: {race_url} ---")

    race_id_match = re.search(r'race_id=(\d+)', race_url)
    if not race_id_match:
        print("URLからrace_idが見つかりません。")
        return None, None

    race_id = race_id_match.group(1)
    shutuba_csv_path = fetch_and_save_shutuba_data(race_id)
    if not shutuba_csv_path:
        return None, None

    race_info = get_race_info_from_url(race_url)
    if not race_info:
        return None, None

    try:
        df_shutuba = pd.read_csv(shutuba_csv_path)
        horse_scores = []
        for index, row in df_shutuba.iterrows():
            horse_id = str(row['horse_id'])
            sire_id = pd.to_numeric(row['sire_id'], errors='coerce')
            bms_id = pd.to_numeric(row['bms_id'], errors='coerce')
            score = get_horse_total_score(
                horse_id, race_info["distance"], race_info["track_type"],
                race_info["weather"], row['yoso_ninki'], race_info["date"],
                row['jockey_name'], pd.to_numeric(row['jockey_cd'], errors='coerce'),
                sire_id if pd.notna(sire_id) else None,
                bms_id if pd.notna(bms_id) else None,
                row['futan'], row['weight'], row['weight_sa'], row['wakuban'],
                row['odds'], row['corner'], row['kyaku'], row['time'], row['pace'],
                row['harontimel3'], row['chakusa'], row['sex'], row['age'],
                row['blinker'], row['norikawari'], row['trainer_syozoku'], row['owner_cd'], lap_times
            )
            horse_scores.append({
                'umaban': row['umaban'],
                'horse_name': row['horse_name'],
                'score': score
            })

        sorted_horses = sorted(horse_scores, key=lambda x: x['score'], reverse=True)

        # --- Generate new recommendations based on LLM-add3.txt ---
        # Tansho (Win): Top 2 horses
        # Fukusho (Place): Top 2 horses
        # Wide (Quinella Place): 6 combinations from top 4 horses

        # Top 2 horses for Tansho and Fukusho
        top_2_horses = sorted_horses[:2]
        tansho_bets = [h['umaban'] for h in top_2_horses]
        fukusho_bets = [h['umaban'] for h in top_2_horses]

        # Top 4 horses for Wide combinations (yields C(4,2) = 6 combinations)
        top_4_horses = sorted_horses[:4]
        wide_combinations = list(itertools.combinations([h['umaban'] for h in top_4_horses], 2))
        wide_bets = [tuple(sorted(combo)) for combo in wide_combinations]

        recommended_bets = {
            "tansho": tansho_bets,
            "fukusho": fukusho_bets,
            "wide": wide_bets
        }

        return sorted_horses, recommended_bets

    except Exception as e:
        print(f"Prediction error: {e}")
        return None, None

if __name__ == '__main__':
    if len(sys.argv) > 1:
        race_url = sys.argv[1]
        predicted_horses, recommended_bets = main(race_url)
        if predicted_horses and recommended_bets:
            print("\n--- スコア上位馬 ---")
            for i, horse in enumerate(predicted_horses):
                print(f"{i+1}. 馬番: {horse['umaban']}, 馬名: {horse['horse_name']}, スコア: {horse['score']:.2f}")
            
            print("\n--- おすすめ単勝馬券 (2点) ---")
            if recommended_bets.get('tansho'):
                for umaban in recommended_bets['tansho']:
                    print(f"- {umaban}")

            print("\n--- おすすめ複勝馬券 (2点) ---")
            if recommended_bets.get('fukusho'):
                for umaban in recommended_bets['fukusho']:
                    print(f"- {umaban}")

            print("\n--- おすすめワイド馬券 (6点) ---")
            if recommended_bets.get('wide'):
                for i, combo in enumerate(recommended_bets['wide']):
                    print(f"{i+1}. {combo}")
    else:
        print("使用法: python main.py <レースページのURL>")
