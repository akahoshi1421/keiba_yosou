const 過去のレースのURL一覧: string[] = ファイルを読み込む("pastRace.txt");

type 動作確認をした結果に起こったエラー = {
  エラーが起きたか: boolean;
  エラー内容: string;
};

function 動作確認および修正をする(): void {
  while (true) {
    const エラー: 動作確認をした結果に起こったエラー = 動作確認をする(
      過去のレースのURL一覧[0]
    );
    if (!エラー.エラーが起きたか) break;

    修正をする(エラー.エラー内容);
  }
}

function 評価アルゴリズムを見直し修正をする(): void {
  const 見直すためにLLMが読む参考資料: string[] = [
    "advice1.md",
    "advice2.md",
    "スコアリングアルゴリズムにて加算される数字を見直す",
    "shutuba_XXXXXX.csv(shutuba_202403010511.csv等)に記載されているまだ使われていないカラムを活用する",
  ];
  const 修正内容: string =
    評価アルゴリズムを見直す(見直すためにLLMが読む参考資料);
  console.log("評価アルゴリズムを見直しました:", 修正内容);

  見直した評価アルゴリズムを元に修正をする(修正内容);

  const ファイルデータ: string[] = ファイルを読み込む("teian.txt");
  const GEMINIMDのファイルデータ: string[] = ファイルを読み込む("GEMINI.md");

  ファイルデータ.push(修正内容);
  ファイルに書き込む("teian.txt", ファイルデータ);

  GEMINIMDのファイルデータ.push(修正内容);
  ファイルに書き込む("GEMINI.md", ファイルデータ);
}

function プログラムの評価をする(レース数: number): boolean {
  const パーセント勝率: number = シミレーションをする(
    過去のレースのURL一覧.slice(0, レース数)
  );

  if (パーセント勝率 >= 30) return true;

  評価アルゴリズムを見直し修正をする();
  動作確認および修正をする();

  return false;
}

const 設定 = {
  言語: "ja",
  基本設定: "修正をする際は人間の判断を仰がず、勝手に判断して修正をすること",
};

new GeminiCLI(設定);

while (true) {
  const 仮評価でワイド馬券勝率30パーセント以上か = プログラムの評価をする(80);
  if (!仮評価でワイド馬券勝率30パーセント以上か) continue;

  console.log("仮評価の勝率が30パーセント以上です。本評価に進みます。");

  const 本評価でワイド馬券勝率30パーセント以上か = プログラムの評価をする(138);
  if (本評価でワイド馬券勝率30パーセント以上か) {
    console.log(
      "本評価の勝率が30パーセント以上です。プログラムは成功しました。"
    );
    break;
  }
}
