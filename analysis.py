import pandas as pd

# Set pandas display options to show all columns
pd.set_option('display.max_columns', None)

# Define file paths
results_csv_path = "/Users/akahoshihiroki/Documents/pytests/keiba_yosou/race_results.csv"
shutuba_csv_path = "/Users/akahoshihiroki/Documents/pytests/keiba_yosou/shutuba_202510020411.csv"

try:
    # Load the CSV files into pandas DataFrames
    df_results = pd.read_csv(results_csv_path)
    df_shutuba = pd.read_csv(shutuba_csv_path)

    print("--- 過去のレース結果 (race_results.csv) ---")
    print("\n[列名]")
    print(df_results.columns.tolist())
    print("\n[データサンプル]")
    print(df_results.head())
    print("\n" + "="*50 + "\n")

    print("--- 今回の出馬表 (shutuba_202510020411.csv) ---")
    print("\n[列名]")
    print(df_shutuba.columns.tolist())
    print("\n[データサンプル]")
    print(df_shutuba.head())

except FileNotFoundError as e:
    print(f"エラー: ファイルが見つかりません。 {e}")
except Exception as e:
    print(f"エラーが発生しました: {e}")
