
import requests
import json
import pandas as pd

# The race ID for the target race
race_id = "202510020411"

# This API endpoint and parameters are based on the JavaScript found in the page source
api_url = "https://race.netkeiba.com/race_api/"
params = {
    'class': 'AplRaceHorse',
    'race_id': race_id,
    'method': 'get',
    'compress': 0,
    'output': 'jsonp', # The API seems to return JSON even with this setting
    'input': 'UTF-8'
}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36",
    "Referer": "https://race.netkeiba.com/"
}

try:
    response = requests.get(api_url, params=params, headers=headers)
    response.raise_for_status() # Raise an exception for bad status codes

    # The response is JSON, sometimes wrapped in parentheses. Let's handle that.
    json_text = response.text
    if json_text.startswith('(') and json_text.endswith(')'):
        json_text = json_text[1:-1]

    data = json.loads(json_text)

    # The actual horse list is nested under a dynamic key
    data_key = f"nkrace_horse::{race_id}"

    if data.get('status') == 'OK' and data.get('data') and data_key in data['data']:
        horse_list = data['data'][data_key]

        if horse_list:
            # Convert the list of dictionaries to a DataFrame
            df = pd.DataFrame.from_dict(horse_list)
            print("APIから出馬表データを取得しました。")
            print(df.to_string())

            # Save the DataFrame to a CSV file
            csv_path = f"/Users/akahoshihiroki/Documents/pytests/keiba_yosou/shutuba_{race_id}.csv"
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"出馬表データを {csv_path} に保存しました。")
        else:
            print("APIからの応答に出馬表データが含まれていませんでした（リストが空です）。")
            print("レースが未来の日付のため、まだ出馬表が公開されていない可能性があります。")
    else:
        print("APIからの応答に予期したデータ構造が見つかりませんでした。")
        print("Response Data:", data)

except requests.exceptions.RequestException as e:
    print(f"APIへのリクエスト中にエラーが発生しました: {e}")
except json.JSONDecodeError:
    print("APIからの応答をJSONとして解析できませんでした。")
    print(f"Response Text: {response.text[:300]}...")
