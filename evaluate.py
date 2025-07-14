import sys
import re
import pandas as pd
import requests
from bs4 import BeautifulSoup
from io import StringIO
from main import main as run_prediction

PAST_RACES_FILE = "/Users/akahoshihiroki/Documents/pytests/keiba_yosou/pastRace.txt"

def get_actual_payouts(result_url):
    """Fetches the payout information by iterating through each row of the payout tables."""
    try:
        response = requests.get(result_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")
        
        payouts = {'tansho': [], 'fukusho': [], 'wide': []}
        all_rows = soup.select('.Payout_Detail_Table tr')

        for row in all_rows:
            header_tag = row.find('th')
            result_cell = row.find('td', class_='Result')

            if not header_tag or not result_cell:
                continue

            header = header_tag.text.strip()
            
            try:
                numbers = [int(s.text) for s in result_cell.find_all('span') if s.text.strip().isdigit()]
            except (ValueError, TypeError):
                continue

            if '単勝' in header and numbers:
                payouts['tansho'] = numbers
            elif '複勝' in header and numbers:
                payouts['fukusho'] = numbers
            elif 'ワイド' in header and numbers:
                if len(numbers) % 2 == 0:
                    payouts['wide'] = [tuple(sorted(numbers[i:i+2])) for i in range(0, len(numbers), 2)]

        return payouts
    except Exception as e:
        print(f"Could not fetch or parse payout results from {result_url}: {e}")
        raise

def get_race_lap_times(result_url):
    """Fetches lap times from the race result page."""
    try:
        response = requests.get(result_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml")

        lap_time_p = soup.find('p', class_='Race_LapTime')
        if lap_time_p:
            lap_times_str = lap_time_p.get_text(strip=True)
            lap_times = [float(lt) for lt in lap_times_str.split('-')]
            return lap_times

        return None
    except Exception as e:
        print(f"Could not fetch or parse lap times from {result_url}: {e}")
        return None

def evaluate_races(num_races_to_evaluate=None, specific_urls=None):
    """Runs predictions on past races and evaluates based on the new criteria."""
    if specific_urls:
        race_urls = specific_urls
    else:
        try:
            with open(PAST_RACES_FILE, 'r') as f:
                race_urls = [line.strip().lstrip('-').strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"エラー: {PAST_RACES_FILE} が見つかりません。")
            return 0
        if num_races_to_evaluate:
            race_urls = race_urls[:num_races_to_evaluate]

    total_races = 0
    total_tansho_hits = 0
    total_fukusho_hits = 0
    total_wide_hits = 0
    
    for result_url in race_urls:
        if not result_url:
            continue
        
        shutuba_url = result_url.replace('result.html', 'shutuba.html')
        race_id_match = re.search(r'race_id=(\d+)', shutuba_url)
        if not race_id_match:
            print(f"URLからrace_idを抽出できませんでした: {shutuba_url}")
            continue
        race_id = race_id_match.group(1)

        print(f"\n--- レース評価中: {race_id} ---")
        
        try:
            total_races += 1

            lap_times = get_race_lap_times(result_url)
            predicted_horses, recommended_bets = run_prediction(shutuba_url, lap_times)
            if not predicted_horses or not recommended_bets:
                print("このレースの予測に失敗しました。")
                continue

            actual_payouts = get_actual_payouts(result_url)
            if not actual_payouts:
                print("このレースの実際の結果を取得できませんでした。")
                continue

            print(f"  - 実際の単勝: {actual_payouts.get('tansho', [])}")
            print(f"  - 実際の複勝: {actual_payouts.get('fukusho', [])}")
            print(f"  - 実際のワイド: {actual_payouts.get('wide', [])}")
            print(f"  - 推奨単勝: {recommended_bets.get('tansho', [])}")
            print(f"  - 推奨複勝: {recommended_bets.get('fukusho', [])}")
            print(f"  - 推奨ワイド: {recommended_bets.get('wide', [])}")

            tansho_hits_in_race = 0
            for bet in recommended_bets.get('tansho', []):
                if bet in actual_payouts.get('tansho', []):
                    tansho_hits_in_race += 1
                    print(f"[的中] 単勝! 賭け: {bet}, 実際: {actual_payouts['tansho']}")
            total_tansho_hits += tansho_hits_in_race

            fukusho_hits_in_race = 0
            for bet in recommended_bets.get('fukusho', []):
                if bet in actual_payouts.get('fukusho', []):
                    fukusho_hits_in_race += 1
                    print(f"[的中] 複勝! 賭け: {bet}, 実際: {actual_payouts['fukusho']}")
            total_fukusho_hits += fukusho_hits_in_race

            wide_hits_in_race = 0
            for bet in recommended_bets.get('wide', []):
                if tuple(sorted(bet)) in actual_payouts.get('wide', []):
                    wide_hits_in_race += 1
                    print(f"[的中] ワイド! 賭け: {bet}, 実際: {actual_payouts['wide']}")
            total_wide_hits += wide_hits_in_race
            
            print(f"レース {race_id} 結果: 単勝的中: {tansho_hits_in_race}, 複勝的中: {fukusho_hits_in_race}, ワイド的中: {wide_hits_in_race}")
        except Exception as e:
            print(f"レース {race_id} の評価中に回復不能なエラーが発生しました: {e}")
            print("評価を停止します。")
            return 0

    print("\n--- 評価完了 ---")
    if total_races > 0:
        wide_win_rate = (total_wide_hits / (total_races * 3)) * 100
        
        print(f"評価レース数: {total_races}")
        print(f"単勝的中数: {total_tansho_hits}")
        print(f"複勝的中数: {total_fukusho_hits}")
        print(f"ワイド的中数: {total_wide_hits}")
        print(f"ワイド的中率: {wide_win_rate:.2f}%")

        return wide_win_rate
    else:
        print("評価されたレースはありませんでした。")
        return 0

if __name__ == '__main__':
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        print(f"--- 単一レースチェックを実行中: {test_url} ---")
        evaluate_races(specific_urls=[test_url])
    else:
        print("全レース評価の実行方法: python evaluate.py")
        print("単一レースチェックの実行方法: python evaluate.py <レース結果のURL>")
        print("\n--- 仮検証 (最初の80レース) ---")
        provisional_win_rate = evaluate_races(num_races_to_evaluate=80)
        if provisional_win_rate >= 30:
            print("\n仮検証の勝率が30%以上です。全レースで本格評価を行います。")
            evaluate_races()
        else:
            print(f"\n仮検証の的中率が {provisional_win_rate:.2f}% であり、30%未満です。アルゴリズムを見直してください。\nまだ使われていないカラムを活用するか、URLを読み込む方法を検討してください。")
