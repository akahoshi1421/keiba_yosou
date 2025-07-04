import pandas as pd
import itertools
from scorer import get_horse_total_score

# --- Configuration ---
SHUTUBA_CSV_PATH = "/Users/akahoshihiroki/Documents/pytests/keiba_yosou/shutuba_202510020411.csv"

# Target race conditions for 北九州記念 (Kokura, Turf 1200m)
# These should ideally be dynamically extracted from the race page if it changes.
TARGET_DISTANCE = "芝1200"
TARGET_TRACK_TYPE = "良" # Assuming a typical good track for prediction
TARGET_WEATHER = "晴" # Assuming a typical clear weather for prediction
CURRENT_RACE_DATE = pd.to_datetime("2025-07-06") # Date of the target race (北九州記念)

NUM_RECOMMENDATIONS = 10 # Number of trifecta combinations to recommend

def main():
    print("--- 競馬予想プログラムを開始します ---")

    try:
        # 1. Load the shutuba DataFrame
        df_shutuba = pd.read_csv(SHUTUBA_CSV_PATH)
        print(f"出馬表データを {SHUTUBA_CSV_PATH} から読み込みました。")

        # Prepare a list to store horse scores
        horse_scores = []

        # 2. Calculate score for each horse
        print("各出走馬のスコアを計算中... (時間がかかる場合があります)")
        for index, row in df_shutuba.iterrows():
            horse_id = str(row['horse_id'])
            horse_name = row['horse_name']
            umaban = row['umaban']
            yoso_ninki = row['yoso_ninki'] # Use yoso_ninki for initial popularity

            print(f"  - {horse_name} (馬番: {umaban}, ID: {horse_id}) のスコアを計算中...")
            score = get_horse_total_score(
                horse_id, TARGET_DISTANCE, TARGET_TRACK_TYPE, TARGET_WEATHER, yoso_ninki, CURRENT_RACE_DATE
            )
            horse_scores.append({
                'umaban': umaban,
                'horse_name': horse_name,
                'score': score,
                'popularity_rank': yoso_ninki
            })
            print(f"    スコア: {score:.2f}")

        # Sort horses by score in descending order
        sorted_horses = sorted(horse_scores, key=lambda x: x['score'], reverse=True)
        
        print("\n--- スコア上位馬 --- ")
        for i, horse in enumerate(sorted_horses):
            print(f"{i+1}. 馬番: {horse['umaban']}, 馬名: {horse['horse_name']}, スコア: {horse['score']:.2f}, {horse['popularity_rank']}番人気")

        # 3. Generate trifecta (三連複) recommendations
        # Pick top N horses for combinations. Let's start with top 6-8 for reasonable combinations.
        # The number of horses to consider for combinations can be adjusted.
        horses_for_combinations = sorted_horses[:8] # Consider top 8 horses
        
        recommended_combinations = []
        for combo in itertools.combinations(horses_for_combinations, 3):
            # Sort the combination by umaban for consistent output
            sorted_combo = sorted(combo, key=lambda x: x['umaban'])
            recommended_combinations.append(tuple(h['umaban'] for h in sorted_combo))

        # Limit to NUM_RECOMMENDATIONS
        recommended_combinations = recommended_combinations[:NUM_RECOMMENDATIONS]

        print(f"\n--- おすすめ三連複馬券 ({NUM_RECOMMENDATIONS}点) --- ")
        for i, combo in enumerate(recommended_combinations):
            print(f"{i+1}. {combo}")

    except FileNotFoundError:
        print(f"エラー: 出馬表ファイルが見つかりません。パスを確認してください: {SHUTUBA_CSV_PATH}")
    except Exception as e:
        print(f"予期せぬエラーが発生しました: {e}")

if __name__ == '__main__':
    main()
