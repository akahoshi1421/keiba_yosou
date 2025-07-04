

import pandas as pd
import numpy as np
import re
from data_fetcher import get_horse_data
import time

# --- Scoring Constants ---
# Base scores for rank (reduced for finer granularity)
RANK_SCORES = {
    1: 10,
    2: 8,
    3: 6,
    4: 4,
    5: 2,
}
DEFAULT_RANK_SCORE = 1 # For ranks > 5 or unranked

# Margin adjustment (smaller margin = higher bonus, reduced values)
MARGIN_BONUS_MAP = {
    "クビ": 1.0, "アタマ": 0.8, "ハナ": 0.6,
    "1/2": 0.5, "3/4": 0.4, "1": 0.3, "1 1/4": 0.2, "1 1/2": 0.1,
}
DEFAULT_MARGIN_BONUS = 0 # For larger margins or unparsed

# Race condition similarity weights (used to distribute max bonus)
DISTANCE_SIMILARITY_WEIGHT = 0.3
TRACK_TYPE_SIMILARITY_WEIGHT = 0.4
WEATHER_SIMILARITY_WEIGHT = 0.3
MAX_SIMILARITY_BONUS_PER_FACTOR = 5 # Max bonus points for each similarity factor

# Track type scores (higher for better track conditions)
TRACK_TYPE_SCORES = {"良": 10, "稍重": 7, "重": 4, "不良": 1}
# Weather scores (higher for better weather conditions)
WEATHER_SCORES = {"晴": 10, "曇": 7, "雨": 4, "雪": 1}

# Popularity score (higher rank = higher score, significantly increased)
POPULARITY_SCORES = {
    1: 500, 2: 400, 3: 300, 4: 200, 5: 100
}
DEFAULT_POPULARITY_SCORE = 50 # For ranks > 5 or unranked

# Parent horse score multiplier
PARENT_SCORE_MULTIPLIER = 0.5

# Fairness (忖度) Logic Constants
MIN_RACES_FOR_FAIRNESS = 10 # Threshold for "fewer starts"
MIN_AVG_SCORE_FOR_FAIRNESS = 15 # Average score per race to be considered "good" (e.g., better than 5th place base score)
FAIRNESS_ADJUSTMENT_FACTOR = 0.5 # How much to adjust the score
RECENCY_DECAY_DAYS = 1095 # ~3 years for recency decay

# --- Helper Functions ---

def parse_margin(margin_str):
    """Converts margin string to a numerical value for scoring."""
    if pd.isna(margin_str):
        return 100 # Large value for unknown margin
    margin_str = str(margin_str).strip()
    if margin_str in MARGIN_BONUS_MAP:
        return MARGIN_BONUS_MAP[margin_str]
    try:
        # Handle numerical margins (e.g., "2 1/2", "3")
        if " " in margin_str:
            parts = margin_str.split(" ")
            whole = float(parts[0])
            fraction = eval(parts[1]) # e.g., "1/2" -> 0.5
            return whole + fraction
        return float(margin_str)
    except ValueError:
        return 100 # Default for unparsed or large margins

def calculate_race_condition_similarity(race_distance, race_track_type, race_weather, 
                                        target_distance, target_track_type, target_weather):
    """Calculates an additive similarity bonus based on race conditions."""
    similarity_bonus = 0

    # Distance similarity bonus
    if not pd.isna(race_distance) and not pd.isna(target_distance):
        try:
            race_dist_val = int(re.search(r'\d+', str(race_distance)).group())
            target_dist_val = int(re.search(r'\d+', str(target_distance)).group())
            dist_diff = abs(race_dist_val - target_dist_val)
            # Max bonus if distance is the same, linearly decreases with difference
            similarity_bonus += max(0, (1 - dist_diff / 1000)) * MAX_SIMILARITY_BONUS_PER_FACTOR * DISTANCE_SIMILARITY_WEIGHT
        except (AttributeError, ValueError):
            pass # Cannot parse distance, no bonus

    # Track type similarity bonus
    if not pd.isna(race_track_type) and not pd.isna(target_track_type):
        race_tt_score = TRACK_TYPE_SCORES.get(str(race_track_type).strip(), 0)
        target_tt_score = TRACK_TYPE_SCORES.get(str(target_track_type).strip(), 0)
        # Higher bonus if scores are close
        similarity_bonus += (1 - abs(race_tt_score - target_tt_score) / 10) * MAX_SIMILARITY_BONUS_PER_FACTOR * TRACK_TYPE_SIMILARITY_WEIGHT

    # Weather similarity bonus
    if not pd.isna(race_weather) and not pd.isna(target_weather):
        race_w_score = WEATHER_SCORES.get(str(race_weather).strip(), 0)
        target_w_score = WEATHER_SCORES.get(str(target_weather).strip(), 0)
        # Higher bonus if scores are close
        similarity_bonus += (1 - abs(race_w_score - target_w_score) / 10) * MAX_SIMILARITY_BONUS_PER_FACTOR * WEATHER_SIMILARITY_WEIGHT

    return similarity_bonus

# --- Main Scoring Functions ---

def calculate_past_performance_score(race_results_df, target_distance, target_track_type, target_weather, current_race_date):
    """Calculates a score based on a horse's past race results, considering recency."""
    total_score = 0
    num_races_evaluated = 0
    total_score_recent_6_months = 0

    if race_results_df is None or race_results_df.empty:
        return total_score, num_races_evaluated, total_score_recent_6_months

    # Convert '日付' column to datetime objects
    race_results_df['日付'] = pd.to_datetime(race_results_df['日付'], errors='coerce')

    # Define the cutoff date for recent races (6 months before current_race_date)
    six_months_ago = current_race_date - pd.DateOffset(months=6)

    for index, row in race_results_df.iterrows():
        race_date = row.get('日付')
        if pd.isna(race_date):
            continue

        rank = row.get('着 順')
        margin = row.get('着差')
        race_distance = row.get('距離')
        race_track_type = row.get('馬 場')
        race_weather = row.get('天 気')

        # Base score from rank
        if pd.isna(rank):
            rank_score = DEFAULT_RANK_SCORE
        else:
            try:
                rank = int(rank)
                rank_score = RANK_SCORES.get(rank, DEFAULT_RANK_SCORE)
            except ValueError:
                rank_score = DEFAULT_RANK_SCORE

        # Adjust score based on margin (smaller margin = higher score)
        parsed_margin = parse_margin(margin)
        margin_adjustment = max(0, 100 - parsed_margin) / 100 # Scale it down to be small

        race_base_score = rank_score + margin_adjustment

        # Calculate recency factor
        days_since_race = (current_race_date - race_date).days
        recency_factor = max(0.1, 1 - (days_since_race / RECENCY_DECAY_DAYS)) # Min factor 0.1

        # Apply recency factor
        race_score_with_recency = race_base_score * recency_factor

        # Add similarity bonus
        similarity_bonus = calculate_race_condition_similarity(
            race_distance, race_track_type, race_weather,
            target_distance, target_track_type, target_weather
        )
        
        final_race_score = race_score_with_recency + similarity_bonus
        total_score += final_race_score
        num_races_evaluated += 1

        if race_date >= six_months_ago:
            total_score_recent_6_months += final_race_score

    return total_score, num_races_evaluated, total_score_recent_6_months

def calculate_popularity_score(popularity_rank):
    """Calculates a score based on the horse's popularity rank."""
    if pd.isna(popularity_rank):
        return DEFAULT_POPULARITY_SCORE
    try:
        popularity_rank = int(popularity_rank)
        # For ranks beyond 5, we can linearly decrease the score or use a default
        if popularity_rank > 5:
            # Example: For rank 6, score is 90, rank 7 is 80, etc.
            return max(0, DEFAULT_POPULARITY_SCORE - (popularity_rank - 5) * 10)
        return POPULARITY_SCORES.get(popularity_rank, DEFAULT_POPULARITY_SCORE)
    except ValueError:
        return DEFAULT_POPULARITY_SCORE

def get_horse_total_score(horse_id, target_distance, target_track_type, target_weather, current_popularity_rank, current_race_date, is_parent=False):
    """
    Calculates the total score for a horse, including its own performance and parent's performance.
    """
    total_score = 0
    
    # Fetch horse data
    race_results_df, parent_ids = get_horse_data(horse_id)
    
    # Calculate past performance score
    past_performance_score, num_races, total_score_recent = calculate_past_performance_score(
        race_results_df, target_distance, target_track_type, target_weather, current_race_date
    )
    total_score += past_performance_score

    # Fairness (忖度) Logic
    if not is_parent and num_races > 0 and num_races < MIN_RACES_FOR_FAIRNESS:
        avg_score_recent = total_score_recent / (num_races if num_races > 0 else 1)
        if avg_score_recent > MIN_AVG_SCORE_FOR_FAIRNESS:
            # Calculate potential score if they had more races
            potential_score_increase = (MIN_RACES_FOR_FAIRNESS - num_races) * avg_score_recent * FAIRNESS_ADJUSTMENT_FACTOR
            total_score += potential_score_increase
            print(f"  [忖度適用] 馬ID {horse_id} (出走数: {num_races}) に公平性ボーナス {potential_score_increase:.2f} を加算しました.")


    # Calculate popularity score (only for the main horse, not parents)
    if not is_parent:
        popularity_score = calculate_popularity_score(current_popularity_rank)
        total_score += popularity_score

    # Add parent horse scores (only one level deep)
    if not is_parent and parent_ids:
        if parent_ids['sire']:
            sire_score = get_horse_total_score(
                parent_ids['sire'], target_distance, target_track_type, target_weather, None, current_race_date, is_parent=True
            )
            total_score += sire_score * PARENT_SCORE_MULTIPLIER
            time.sleep(0.5) # Be kind to the server

        if parent_ids['mare']:
            mare_score = get_horse_total_score(
                parent_ids['mare'], target_distance, target_track_type, target_weather, None, current_race_date, is_parent=True
            )
            total_score += mare_score * PARENT_SCORE_MULTIPLIER
            time.sleep(0.5) # Be kind to the server

    return total_score

if __name__ == '__main__':
    # Example Usage (using data from your shutuba_202510020411.csv)
    # This is a simplified example as we don't have actual target race conditions yet.
    # You would get these from the main race data.
    
    # Sample target race conditions (adjust as needed for the actual race)
    target_distance = "芝1200"
    target_track_type = "良"
    target_weather = "晴"
    current_race_date = pd.to_datetime("2025-07-06") # Example date

    # Sample horse data from shutuba_202510020411.csv
    # Replace with actual horse_id and yoso_ninki from your shutuba DataFrame
    sample_horse_data = [
        {"horse_id": "2019100604", "horse_name": "ヤマニンアンフィル", "yoso_ninki": 13}, # Sample 1
        {"horse_id": "2016104668", "horse_name": "カリボール", "yoso_ninki": 16}, # Sample 2
        {"horse_id": "2020102764", "horse_name": "モズメイメイ", "yoso_ninki": 3}, # Sample 3
    ]

    print("--- Calculating Scores for Sample Horses ---")
    for horse in sample_horse_data:
        horse_id = horse["horse_id"]
        horse_name = horse["horse_name"]
        yoso_ninki = horse["yoso_ninki"]
        
        print(f"\nCalculating score for {horse_name} (ID: {horse_id}, Popularity: {yoso_ninki})...")
        score = get_horse_total_score(horse_id, target_distance, target_track_type, target_weather, yoso_ninki, current_race_date)
        print(f"Total Score for {horse_name}: {score:.2f}")
