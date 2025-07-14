

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
import time
import sys

def get_race_urls_for_year_selenium(year, race_name, driver):
    url = "https://race.netkeiba.com/top/schedule.html"
    driver.get(url)
    time.sleep(2)

    try:
        year_select_element = driver.find_element(By.NAME, "year")
        year_select = Select(year_select_element)
        year_select.select_by_value(str(year))
        display_button = driver.find_element(By.CSS_SELECTOR, "input[type='submit']")
        display_button.click()
        time.sleep(3)
    except Exception as e:
        print(f"Could not select year {year}: {e}")
        return []

    race_urls = []
    links = driver.find_elements(By.TAG_NAME, 'a')
    for link in links:
        if race_name in link.text:
            href = link.get_attribute('href')
            if href and '/race/result/' in href:
                race_urls.append(href)

    return list(set(race_urls))

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("使用法: python get_past_races.py <レース名>")
        sys.exit(1)

    race_name_to_find = sys.argv[1]
    output_file = f"/Users/akahoshihiroki/Documents/pytests/keiba_yosou/past_races_{race_name_to_find.replace(' ', '_')}.txt"

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    try:
        driver = webdriver.Chrome(options=chrome_options)
    except Exception as e:
        print(f"WebDriverの初期化エラー: {e}")
        sys.exit(1)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("")

    for year in range(2024, 2014, -1):
        print(f"{year}年のレースURLを検索中...")
        urls = get_race_urls_for_year_selenium(year, race_name_to_find, driver)
        with open(output_file, "a", encoding="utf-8") as f:
            for url in urls:
                f.write(f"- {url}\n")
        print(f"{year}年終了。 {len(urls)} 件のURLが見つかりました。")

    driver.quit()
    print(f"全てのレースURLを {output_file} に保存しました。")
