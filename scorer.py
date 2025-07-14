

import pandas as pd
import numpy as np
import re
from data_fetcher import get_horse_data, get_jockey_leading_data, get_horse_course_aptitude, get_jockey_course_aptitude, get_sire_course_aptitude, get_bms_course_aptitude
import time

# --- Scoring Constants ---
# Base scores for rank (reduced for finer granularity)
RANK_SCORES = {
    1: 800, # Further increased for 1st place
    2: 400,
    3: 200,
    4: 100,
    5: 60,
    6: 40,
}
DEFAULT_RANK_SCORE = 20

# Margin adjustment (smaller margin = higher bonus, reduced values)
# These are now interpreted as seconds or fractions of a second behind the winner.
# Smaller values mean closer to the winner, thus higher bonus.
MARGIN_TO_SECONDS = {
    "クビ": 0.05,  # Neck
    "アタマ": 0.02, # Head
    "ハナ": 0.01,  # Nose
    "1/2": 0.1,   # 1/2 length
    "3/4": 0.15,  # 3/4 length
    "1": 0.2,     # 1 length
    "1 1/4": 0.25,
    "1 1/2": 0.3,
    "1 3/4": 0.35,
    "2": 0.4,
    "2 1/2": 0.5,
    "3": 0.6,
    "3 1/2": 0.7,
    "4": 0.8,
    "5": 1.0,
    # Add more as needed, larger margins will get less bonus
}
MAX_MARGIN_BONUS = 500 # Increased max points for being very close to the winner

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
    1: 5000, 2: 3000, 3: 2000, 4: 1500, 5: 1000
}
DEFAULT_POPULARITY_SCORE = 500

# Parent horse score multiplier
PARENT_SCORE_MULTIPLIER = 3.0 # Further increased influence of parent scores

# Fairness (忖度) Logic Constants
MIN_RACES_FOR_FAIRNESS = 10 # Threshold for "fewer starts"
MIN_AVG_SCORE_FOR_FAIRNESS = 15 # Average score per race to be considered "good" (e.g., better than 5th place base score)
FAIRNESS_ADJUSTMENT_FACTOR = 0.5 # How much to adjust the score
RECENCY_DECAY_DAYS = 1095 # ~3 years for recency decay

# --- New Scoring Constants for additional factors ---
WAKUBAN_SCORES = { # Inner brackets are generally better
    1: 50, 2: 40, 3: 30, 4: 20, 5: 10, 6: -10, 7: -20, 8: -30
}
FUTAN_KG_BASE = 55.0 # Base weight for futan (jockey weight)
FUTAN_SCORE_MULTIPLIER = -20 # Points per kg over/under the base (increased impact)

WEIGHT_CHANGE_SCORE_MAP = { # Score based on change in horse weight from last race
    '大幅増': -100, # Large increase (more negative)
    '増': 30,    # Slight increase (more positive)
    '維持': 80,   # Maintained weight (more positive)
    '減': -30,     # Slight decrease (more negative)
    '大幅減': -100  # Large decrease (more negative)
}

TRAINER_SYOZOKU_SCORES = {
    "美浦": 15,
    "栗東": 15,
}
OWNER_CD_BONUS_MAP = {
    "226800": 20, # サンデーレーシング
    "486800": 20, # キャロットファーム
    "415800": 15, # 社台レースホース
    "393126": 15, # 社台ファーム
}

# --- New Scoring Constants for Odds and Corner ---
ODDS_SCORE_MULTIPLIER = 500 # Multiplier for odds-based score
CORNER_POSITION_BONUS = 20 # Bonus for being in a good position at corners

# --- New Scoring Constants for Haron Time and Chakusa ---
HARON_TIME_SCORE_MULTIPLIER = 100 # Multiplier for harontimel3 score (lower time is better)
CHAKUSA_SCORE_MULTIPLIER = 200 # Multiplier for chakusa score (smaller margin is better)

# --- Helper Functions ---

def parse_margin(margin_str):
    """Converts margin string to a numerical value (seconds) for scoring."""
    if pd.isna(margin_str):
        return 999.0 # Large value for unknown margin

    margin_str = str(margin_str).strip()

    # Direct mapping for common small margins
    if margin_str in MARGIN_TO_SECONDS:
        return MARGIN_TO_SECONDS[margin_str]

    # Handle numerical margins (e.g., "2 1/2", "3", "0.5")
    try:
        if " " in margin_str:
            parts = margin_str.split(" ")
            whole = float(parts[0])
            # Safely parse fraction without eval
            if '/' in parts[1]:
                num, den = map(int, parts[1].split('/'))
                fraction = num / den
            else:
                fraction = float(parts[1])
            return whole + fraction
        return float(margin_str)
    except ValueError:
        # If parsing fails, it's a large or unrecognised margin, assign a large value
        return 999.0

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

def calculate_sex_age_score(sex, age):
    """Calculates a score based on the horse's sex and age."""
    score = 0
    if sex == '牡': # Male
        score += 10
    elif sex == '牝': # Female
        score += 5
    elif sex == 'セ': # Gelding
        score += 0

    try:
        age = int(age)
        if age == 3:
            score += 20 # 3-year-olds often have potential
        elif age == 4:
            score += 15
        elif age == 5:
            score += 10
        elif age >= 6:
            score -= 5 # Older horses might be less competitive
    except (ValueError, TypeError):
        pass # Ignore if age is not a valid number
    return score

# --- Main Scoring Functions ---

def calculate_past_performance_score(race_results_df, target_distance, target_track_type, target_weather, current_race_date):
    """Calculates a score based on a horse's past race results, considering recency and finishing speed."""
    total_score = 0
    num_races_evaluated = 0
    total_score_recent_6_months = 0
    total_agari_3f_score = 0

    if race_results_df is None or race_results_df.empty:
        return total_score, num_races_evaluated, total_score_recent_6_months, total_agari_3f_score

    race_results_df['日付'] = pd.to_datetime(race_results_df['日付'], errors='coerce')
    race_results_df['agari_3f'] = pd.to_numeric(race_results_df['agari_3f'], errors='coerce')

    six_months_ago = current_race_date - pd.DateOffset(months=6)

    for index, row in race_results_df.iterrows():
        rank = row.get('着 順')
        margin = row.get('着差') # This is margin to the winner for non-winners, or 0 for winner
        race_distance = row.get('距離')
        race_track_type = row.get('馬 場')
        race_weather = row.get('天 気')
        agari_3f = row.get('agari_3f')

        if pd.isna(rank):
            rank_score = DEFAULT_RANK_SCORE
        else:
            try:
                rank = int(rank)
                rank_score = RANK_SCORES.get(rank, DEFAULT_RANK_SCORE)
            except ValueError:
                rank_score = DEFAULT_RANK_SCORE

        # Calculate margin bonus: smaller margin (closer to winner) means higher bonus
        margin_bonus = 0
        if pd.notna(margin) and rank != 1: # Only apply margin bonus if not 1st place
            parsed_margin_seconds = parse_margin(margin)
            # Inverse relationship: smaller seconds -> higher bonus
            # Example: 0.01s (ハナ) -> MAX_MARGIN_BONUS
            # 1.0s (5馬身) -> 0 bonus
            if parsed_margin_seconds <= 0.5: # For very close finishes
                margin_bonus = MAX_MARGIN_BONUS * (1 - (parsed_margin_seconds / 0.5))
            elif parsed_margin_seconds <= 1.0: # For close finishes
                margin_bonus = (MAX_MARGIN_BONUS / 2) * (1 - ((parsed_margin_seconds - 0.5) / 0.5))
            # For margins > 1.0s, bonus quickly diminishes or becomes 0

        race_base_score = rank_score + margin_bonus

        # Agari 3F (finishing speed) score
        agari_score = 0
        if pd.notna(agari_3f) and agari_3f > 0:
            # Higher score for faster times (lower agari_3f value)
            agari_score = max(0, 50 - agari_3f) * 30 # Increased impact
        
        # Recency factor
        race_date = row.get('日付')
        if pd.isna(race_date):
            continue
        days_since_race = (current_race_date - race_date).days
        recency_factor = max(0.1, 1 - (days_since_race / RECENCY_DECAY_DAYS))

        # Apply recency to all parts of the score
        race_score_with_recency = (race_base_score + agari_score) * recency_factor

        # Similarity bonus
        similarity_bonus = calculate_race_condition_similarity(
            race_distance, race_track_type, race_weather,
            target_distance, target_track_type, target_weather
        )
        
        final_race_score = race_score_with_recency + similarity_bonus
        total_score += final_race_score
        num_races_evaluated += 1
        total_agari_3f_score += agari_score * recency_factor # Keep track of the 3f score part

        if pd.to_datetime(race_date) >= six_months_ago:
            total_score_recent_6_months += final_race_score

    return total_score, num_races_evaluated, total_score_recent_6_months, total_agari_3f_score

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

def calculate_odds_score(odds):
    """Calculates a score based on the horse's odds."""
    if pd.isna(odds) or odds <= 0:
        return 0
    try:
        # Lower odds mean higher score (e.g., 1.0 odds -> 100 points, 10.0 odds -> 10 points)
        return ODDS_SCORE_MULTIPLIER / float(odds)
    except ValueError:
        return 0

def calculate_corner_score(corner_str):
    """Calculates a score based on the horse's position at corners."""
    if pd.isna(corner_str):
        return 0
    try:
        # Corner string is like "4-4-5-4", take the average of the first two positions
        positions = [int(p) for p in str(corner_str).split('-') if p.isdigit()]
        if len(positions) >= 2:
            avg_position = (positions[0] + positions[1]) / 2
            # Lower average position means higher bonus
            return max(0, (10 - avg_position)) * CORNER_POSITION_BONUS # Example: avg 1 -> 9*20=180, avg 10 -> 0
        return 0
    except ValueError:
        return 0

def get_horse_total_score(horse_id, target_distance, target_track_type, target_weather, 
                          current_popularity_rank, current_race_date, 
                          jockey_name, jockey_id, sire_id, bms_id, 
                          futan, weight, weight_sa, wakuban, odds, corner, 
                          kyaku, time_str, pace,
                          is_parent=False):
    """
    Calculates the total score for a horse, including its own performance, parent's performance, and jockey's skill.
    """
    total_score = 0
    
    # Fetch horse data
    race_results_df, parent_ids = get_horse_data(horse_id)
    
    # Calculate past performance score
    past_performance_score, num_races, total_score_recent, _ = calculate_past_performance_score(
        race_results_df, target_distance, target_track_type, target_weather, current_race_date
    )
    total_score += past_performance_score

    # --- NEW: Add scores for additional factors ---
    if not is_parent:
        # Wakuban (Gate number) score
        total_score += WAKUBAN_SCORES.get(wakuban, 0)

        # Futan (Jockey weight) score
        try:
            futan_kg = float(futan)
            total_score += (FUTAN_KG_BASE - futan_kg) * FUTAN_SCORE_MULTIPLIER
        except (ValueError, TypeError):
            pass # Ignore if futan is not a valid number

        # Weight change score
        if not pd.isna(weight_sa):
            weight_sa_str = str(weight_sa) # Convert to string to safely use 'in' operator
            if '増' in weight_sa_str and len(weight_sa_str) > 1: # 大幅増
                total_score += WEIGHT_CHANGE_SCORE_MAP['大幅増']
            elif '増' in weight_sa_str:
                total_score += WEIGHT_CHANGE_SCORE_MAP['増']
            elif '減' in weight_sa_str and len(weight_sa_str) > 1: # 大幅減
                total_score += WEIGHT_CHANGE_SCORE_MAP['大幅減']
            elif '減' in weight_sa_str:
                total_score += WEIGHT_CHANGE_SCORE_MAP['減']
            else: # 維持
                total_score += WEIGHT_CHANGE_SCORE_MAP['維持']

        # Odds score
        total_score += calculate_odds_score(odds)

        # Corner position score
        total_score += calculate_corner_score(corner)

        # Kyaku (Running style) score
        total_score += calculate_kyaku_score(kyaku, target_distance)

        # Time score
        total_score += calculate_time_score(time_str, target_distance)

        # Pace score
        total_score += calculate_pace_score(pace, kyaku, target_distance)

    # Fairness (忖度) Logic
    if not is_parent and num_races > 0 and num_races < MIN_RACES_FOR_FAIRNESS:
        avg_score_recent = total_score_recent / (num_races if num_races > 0 else 1)
        if avg_score_recent > MIN_AVG_SCORE_FOR_FAIRNESS:
            potential_score_increase = (MIN_RACES_FOR_FAIRNESS - num_races) * avg_score_recent * FAIRNESS_ADJUSTMENT_FACTOR
            total_score += potential_score_increase

    # Calculate popularity score
    if not is_parent:
        popularity_score = calculate_popularity_score(current_popularity_rank)
        total_score += popularity_score

    # Add jockey score
    if not is_parent and jockey_name:
        jockey_df = get_jockey_leading_data(current_race_date.year)
        if not jockey_df.empty:
            jockey_stats = jockey_df[jockey_df['騎手'] == jockey_name]
            if not jockey_stats.empty:
                win_rate = jockey_stats.iloc[0]['win_rate']
                rentai_rate = jockey_stats.iloc[0]['rentai_rate']
                jockey_score = (win_rate * 1000) + (rentai_rate * 200) # Increased win rate weighting
                total_score += jockey_score

    # Add horse course aptitude score
    if not is_parent:
        horse_aptitude_df = get_horse_course_aptitude(horse_id)
        if not horse_aptitude_df.empty:
            # Filter for relevant course conditions
            # Assuming 'コース' column contains combined info like '東京 芝 1600m'
            # And '勝率' and '連対率' are available
            course_aptitude_score = 0
            for index, row in horse_aptitude_df.iterrows():
                course_info = row.get('コース', '')
                win_rate = pd.to_numeric(row.get('勝率', 0), errors='coerce')
                rentai_rate = pd.to_numeric(row.get('連対率', 0), errors='coerce')

                # Check for matching distance and track type
                if str(target_distance) in course_info and target_track_type in course_info:
                    course_aptitude_score += (win_rate * 150) + (rentai_rate * 25) # Increased win rate weighting
            total_score += course_aptitude_score

    # Add jockey course aptitude score
    if not is_parent and jockey_id:
        jockey_aptitude_df = get_jockey_course_aptitude(jockey_id)
        if not jockey_aptitude_df.empty:
            jockey_course_aptitude_score = 0
            for index, row in jockey_aptitude_df.iterrows():
                course_info = row.get('コース', '')
                win_rate = pd.to_numeric(row.get('勝率', 0), errors='coerce')
                rentai_rate = pd.to_numeric(row.get('連対率', 0), errors='coerce')

                if str(target_distance) in course_info and target_track_type in course_info:
                    jockey_course_aptitude_score += (win_rate * 150) + (rentai_rate * 25) # Increased win rate weighting
            total_score += jockey_course_aptitude_score

    # Add parent horse scores
    if not is_parent and parent_ids:
        if parent_ids['sire']:
            sire_score = get_horse_total_score(
                parent_ids['sire'], target_distance, target_track_type, target_weather, 
                None, current_race_date, None, None, None, None, 
                None, None, None, None, None, None, None, None, None,
                is_parent=True
            )
            total_score += sire_score * PARENT_SCORE_MULTIPLIER
            time.sleep(0.5)

        if parent_ids['mare']:
            mare_score = get_horse_total_score(
                parent_ids['mare'], target_distance, target_track_type, target_weather, 
                None, current_race_date, None, None, None, None, 
                None, None, None, None, None, None, None, None, None,
                is_parent=True
            )
            total_score += mare_score * PARENT_SCORE_MULTIPLIER
            time.sleep(0.5)

    # Add sire course aptitude score
    if not is_parent and sire_id:
        sire_aptitude_df = get_sire_course_aptitude(sire_id)
        if not sire_aptitude_df.empty:
            sire_course_aptitude_score = 0
            for index, row in sire_aptitude_df.iterrows():
                course_info = row.get('コース', '')
                win_rate = pd.to_numeric(row.get('勝率', 0), errors='coerce')
                rentai_rate = pd.to_numeric(row.get('連対率', 0), errors='coerce')

                if str(target_distance) in course_info and target_track_type in course_info:
                    sire_course_aptitude_score += (win_rate * 75) + (rentai_rate * 12.5) # Increased win rate weighting
            total_score += sire_course_aptitude_score

    # Add bms course aptitude score
    if not is_parent and bms_id:
        bms_aptitude_df = get_bms_course_aptitude(bms_id)
        if not bms_aptitude_df.empty:
            bms_course_aptitude_score = 0
            for index, row in bms_aptitude_df.iterrows():
                course_info = row.get('コース', '')
                win_rate = pd.to_numeric(row.get('勝率', 0), errors='coerce')
                rentai_rate = pd.to_numeric(row.get('連対率', 0), errors='coerce')

                if str(target_distance) in course_info and target_track_type in course_info:
                    sire_course_aptitude_score += (win_rate * 175) + (rentai_rate * 37.5) # Further increased win rate weighting
            total_score += bms_course_aptitude_score

    # Trainer affiliation score
    if not is_parent and not pd.isna(trainer_syozoku):
        total_score += TRAINER_SYOZOKU_SCORES.get(trainer_syozoku, 0)

    # Owner code bonus
    if not is_parent and not pd.isna(owner_cd) and str(owner_cd) in OWNER_CD_BONUS_MAP:
        total_score += OWNER_CD_BONUS_MAP[str(owner_cd)]

    return total_score

# --- New Scoring Constants for Kyaku, Time, Pace ---
KYAKU_SCORE_MAP = {
    "逃げ": {"芝1200": 30, "芝1600": 20, "芝2000": 10, "ダ1200": 25, "ダ1800": 15}, # Example values
    "先行": {"芝1200": 25, "芝1600": 30, "芝2000": 20, "ダ1200": 20, "ダ1800": 25},
    "差し": {"芝1200": 10, "芝1600": 20, "芝2000": 30, "ダ1200": 15, "ダ1800": 20},
    "追込": {"芝1200": 5, "芝1600": 10, "芝2000": 25, "ダ1200": 10, "ダ1800": 15},
}
TIME_SCORE_MULTIPLIER = 50 # Multiplier for time-based score (lower time is better)
PACE_SCORE_MAP = {
    "S": {"逃げ": 40, "先行": 20, "差し": -20, "追込": -40}, # Slow pace favors front runners (more distinct)
    "M": {"逃げ": 20, "先行": 40, "差し": 20, "追込": 0}, # Middle pace is balanced (more distinct)
    "H": {"逃げ": -40, "先行": -20, "差し": 40, "追込": 60}, # High pace favors closers (more distinct)
}

# --- Main Scoring Functions ---

def calculate_kyaku_score(kyaku, target_distance):
    """Calculates a score based on the horse's running style (kyaku) and race distance."""
    if pd.isna(kyaku) or pd.isna(target_distance):
        return 0
    
    distance_category = None
    if "芝" in target_distance:
        if "1200" in target_distance: distance_category = "芝1200"
        elif "1600" in target_distance: distance_category = "芝1600"
        elif "2000" in target_distance: distance_category = "芝2000"
    elif "ダ" in target_distance:
        if "1200" in target_distance: distance_category = "ダ1200"
        elif "1800" in target_distance: distance_category = "ダ1800"

    if distance_category and kyaku in KYAKU_SCORE_MAP:
        return KYAKU_SCORE_MAP[kyaku].get(distance_category, 0)
    return 0

def calculate_time_score(time_str, target_distance):
    """Calculates a score based on the horse's past race time."""
    if pd.isna(time_str) or pd.isna(target_distance):
        return 0
    try:
        # Convert time string (e.g., "1:33.4") to seconds
        minutes, seconds = map(float, time_str.split(':'))
        total_seconds = minutes * 60 + seconds

        # This is a very simplified approach. Ideally, you'd compare to average times for the distance.
        # For now, assume faster times are better and give a bonus.
        # Example: 1:30.0 (90s) vs 1:35.0 (95s). Faster time gets more points.
        # A simple inverse relationship for now.
        if total_seconds > 0:
            return TIME_SCORE_MULTIPLIER / total_seconds * 100 # Scale to make it meaningful
        return 0
    except (ValueError, AttributeError):
        return 0

def calculate_pace_score(pace, kyaku, target_distance):
    """Calculates a score based on race pace and horse's running style."""
    if pd.isna(kyaku) or pd.isna(target_distance) or pd.isna(pace):
        return 0
    
    if pace in PACE_SCORE_MAP and kyaku in PACE_SCORE_MAP[pace]:
        return PACE_SCORE_MAP[pace][kyaku]
    return 0

def determine_race_pace(lap_times, target_distance):
    """Determines the overall pace of the race (S: Slow, M: Medium, H: High) based on lap times.
    This is a simplified heuristic and may need refinement.
    """
    if not lap_times or len(lap_times) < 2:
        return None # Cannot determine pace without enough lap times

    # Calculate average lap time
    avg_lap_time = sum(lap_times) / len(lap_times)

    # Heuristic for pace determination (these thresholds are examples and need tuning)
    # Adjust thresholds based on distance and track type for better accuracy
    if "1200" in target_distance:
        if avg_lap_time < 11.5: # Very fast for 1200m
            return 'H'
        elif avg_lap_time < 12.0:
            return 'M'
        else:
            return 'S'
    elif "1600" in target_distance:
        if avg_lap_time < 12.0:
            return 'H'
        elif avg_lap_time < 12.5:
            return 'M'
        else:
            return 'S'
    elif "1800" in target_distance:
        if avg_lap_time < 12.5:
            return 'H'
        elif avg_lap_time < 13.0:
            return 'M'
        else:
            return 'S'
    elif "2000" in target_distance:
        if avg_lap_time < 13.0:
            return 'H'
        elif avg_lap_time < 13.5:
            return 'M'
        else:
            return 'S'
    # Add more distance categories as needed
    return 'M' # Default to Medium if distance not covered

# --- Main Scoring Functions ---

def get_horse_total_score(horse_id, target_distance, target_track_type, target_weather, 
                          current_popularity_rank, current_race_date, 
                          jockey_name, jockey_id, sire_id, bms_id, 
                          futan, weight, weight_sa, wakuban, odds, corner, 
                          kyaku, time_str, pace,
                          harontimel3, chakusa, sex, age, blinker, norikawari, trainer_syozoku, owner_cd, lap_times, is_parent=False):
    """
    Calculates the total score for a horse, including its own performance, parent's performance, and jockey's skill.
    """
    total_score = 0
    
    # Fetch horse data
    race_results_df, parent_ids = get_horse_data(horse_id)
    
    # Calculate past performance score
    past_performance_score, num_races, total_score_recent, _ = calculate_past_performance_score(
        race_results_df, target_distance, target_track_type, target_weather, current_race_date
    )
    total_score += past_performance_score

    # --- NEW: Add scores for additional factors ---
    if not is_parent:
        # Wakuban (Gate number) score
        total_score += WAKUBAN_SCORES.get(wakuban, 0)

        # Futan (Jockey weight) score
        try:
            futan_kg = float(futan)
            total_score += (FUTAN_KG_BASE - futan_kg) * FUTAN_SCORE_MULTIPLIER
        except (ValueError, TypeError):
            pass # Ignore if futan is not a valid number

        # Weight change score
        if not pd.isna(weight_sa):
            weight_sa_str = str(weight_sa) # Convert to string to safely use 'in' operator
            if '増' in weight_sa_str and len(weight_sa_str) > 1: # 大幅増
                total_score += WEIGHT_CHANGE_SCORE_MAP['大幅増']
            elif '増' in weight_sa_str:
                total_score += WEIGHT_CHANGE_SCORE_MAP['増']
            elif '減' in weight_sa_str and len(weight_sa_str) > 1: # 大幅減
                total_score += WEIGHT_CHANGE_SCORE_MAP['大幅減']
            elif '減' in weight_sa_str:
                total_score += WEIGHT_CHANGE_SCORE_MAP['減']
            else: # 維持
                total_score += WEIGHT_CHANGE_SCORE_MAP['維持']

        # Odds score
        total_score += calculate_odds_score(odds)

        # Corner position score
        total_score += calculate_corner_score(corner)

        # Kyaku (Running style) score
        total_score += calculate_kyaku_score(kyaku, target_distance)

        # Time score
        total_score += calculate_time_score(time_str, target_distance)

        # Pace score
        total_score += calculate_pace_score(lap_times, kyaku, target_distance)

        # Sex and Age score
        total_score += calculate_sex_age_score(sex, age)

        # Blinker score
        if not pd.isna(blinker) and blinker == 1:
            total_score += 10 # Small bonus for blinker

        # Norikawari (Jockey change) score
        if not pd.isna(norikawari) and norikawari == 1:
            total_score -= 5 # Small penalty for jockey change

        # Trainer affiliation score
        if not pd.isna(trainer_syozoku):
            total_score += TRAINER_SYOZOKU_SCORES.get(trainer_syozoku, 0)

        # Owner code bonus
        if not pd.isna(owner_cd) and str(owner_cd) in OWNER_CD_BONUS_MAP:
            total_score += OWNER_CD_BONUS_MAP[str(owner_cd)]

    # Fairness (忖度) Logic
    if not is_parent and num_races > 0 and num_races < MIN_RACES_FOR_FAIRNESS:
        avg_score_recent = total_score_recent / (num_races if num_races > 0 else 1)
        if avg_score_recent > MIN_AVG_SCORE_FOR_FAIRNESS:
            potential_score_increase = (MIN_RACES_FOR_FAIRNESS - num_races) * avg_score_recent * FAIRNESS_ADJUSTMENT_FACTOR
            total_score += potential_score_increase

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
        score = get_horse_total_score(horse_id, target_distance, target_track_type, target_weather, 
                                      yoso_ninki, current_race_date, 
                                      None, None, None, None, # Jockey, Jockey ID, Sire, BMS are not available in this simplified example
                                      None, None, None, None, # Futan, Weight, Weight_sa, Wakuban are not available in this simplified example
                                      None, None, None, None, None, # Odds, Corner, Kyaku, Time, Pace are not available in this simplified example
                                      is_parent=False # Explicitly set is_parent for clarity
                                     )
        print(f"Total Score for {horse_name}: {score:.2f}")
