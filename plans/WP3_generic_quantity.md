# 指示書 WP3 — 数量・比較の汎用化（カテゴリ固有知識を core から外す）

出典: 2026-11-05 腱さん指摘「汎用ツールなのに倍巻き・トイペの話ばかり。汎用な作りじゃないと意味ない」。
SPEC §1 の目的（再掲）: 「楽天で○○を条件付きで探して」を **どんな商品でも** 扱う汎用の買い物リサーチツール。

## 設計の原則（この WP の骨格）

- **道具は商品の意味を持たない。** 持つのは「数量の読み取り（個数×内容量）と単位換算」と「語による絞り込み」だけ。
  濃縮/通常・層数・色・型番などの**仕様の違いは道具では判定しない**。商品の意味を判断するのは呼び出し側の AI（と利用者）。
- カテゴリ固有の知識（シングル/ダブル・倍巻き・ロール既定など）は core から削除する。プロファイルとしても残さない。
- 例・説明文・見本は**3カテゴリ以上**で書く（例: 洗濯洗剤 詰め替え 900g×6、単3電池 40本、ソーラーパネル 100W×2、ミネラルウォーター 2L×9本、トイレットペーパー 12ロール×4）。特定カテゴリの例だけにしない。

## SPEC §7・§8 の差し替え（この文面を SPEC に入れる。tester はこれだけを見て試験を作る）

### §7 数量の読み取り（quantity.py）

商品名から **個数** と **1個あたりの内容量** を読み取る。

- 個数: 「N<数え語>×M<数え語>」「N<数え語>入り×M」「N<数え語>」等。数え語は表（データ）で持つ:
  個・本・枚・袋・箱・パック・缶・ロール・セット・組・足・着・台・錠・包・粒・ケース・玉・束・巻・食・回分 等（`R` は「ロール」の略として個数扱い）。
  総数 = 1袋あたり × 袋数。数え語が2段（例「12ロール×4パック」）なら掛け算、単独なら単体。数字だけの「×6」は直前の個数に掛ける。
- 内容量: 数値＋計量単位。**換算表（データ）**で基準単位に直す:
  | 次元 | 基準単位 | 換算 |
  |---|---|---|
  | volume | ml | ml/mL=1, L/ℓ/リットル=1000, cc=1 |
  | mass | g | g=1, kg=1000, mg=0.001 |
  | length | m | m/メートル=1, cm=0.01, mm=0.001, km=1000 |
  | power | W | W/ワット=1, kW=1000 |
  | charge | mAh | mAh=1, Ah=1000 |
  | energy | Wh | Wh=1, kWh=1000 |
  換算表に足すだけで単位を増やせる形にする（if 分岐で単位ごとに書かない）。
- 結果（QuantityInfo を作り直す）: `count_total`（総個数）・`count_unit`（数え語。無ければ "個"）・`content_amount`（1個あたり内容量・基準単位）・`content_dimension`（volume/mass/…/None）・`content_unit`（基準単位名）・`measure_total`（count_total × content_amount）・`confidence`（high/low/none）・`evidence`（根拠文字列）。
- 「ポイント10倍」「最大50%OFF」「送料無料」「1000円ポッキリ」等の販促・価格表記は数量にしない。「24ロール分」「〜相当」「〜あたり」は換算の説明なので数えない。
- 矛盾する表記（同じ次元で値が違う内容量・総数が食い違う個数表記）が複数あれば confidence=low とし、総数・内容量を null。読めなければ none。単価計算に使うのは high のみ。

### §8 価格比較（pricing.py）

- **比較の基準（basis）**: 呼び出し側が `basis` を指定できる（"個" または 換算表の基準単位 "ml"/"g"/"m"/"W"/"mAh"/"Wh"、または L・kg 等の別名＝基準単位に正規化）。
  未指定なら自動: 候補の過半（high のもの）が同じ内容量の次元を持てばその次元の基準単位、そうでなければ "個"。
- 単位価格 = 価格 ÷（basis が "個" なら count_total、内容量の次元なら measure_total）。表示用に「100ml あたり」「100g あたり」「1m あたり」「1個あたり」「1W あたり」等の表示単位を付ける（表示換算は表で持つ）。
- グループは **basis の次元が同じもの** だけ。basis の量が読めない候補は「単価不明」グループに入れ、単位価格の最安判定から外す（件数を caveats）。サイズ違い・入り数違いはグループを分けない（単価で比べるため）。
- 語の絞り込み: `include_terms`（全部を商品名に含むものだけ残す）・`exclude_terms`（どれかを含むものは外す。既存の ng_keyword とは別に商品名で判定）。外した件数を notes に出す。
- 区別して出す4種類は維持: 商品単価最安／単位価格最安／支払総額最安（送料不明なら断定しない）／必要数量を満たす最安（`desired_quantity` は basis の単位で解釈）。
- **caveats に常に1行**:「仕様の違い（濃縮・層数・型番・色など）は判定していません。商品名で確認してください。」
- 単価は丸める前の値で比較し、表示は小数2桁。

### インターフェース（service・MCP・CLI・Web）

- `compare_offers(keywords, include_terms=None, exclude_terms=None, desired_quantity=None, basis=None, ng_keyword, min_price, max_price, sort, pages)`。`required_spec` と `unit="ロール"` 既定は**廃止**（MCP は未公開なので互換不要）。
- 結果の各候補に `quantity`（上の新項目）と `unit_price`・`unit_price_label`（例「100gあたり」）。グループは `basis`・`dimension`。
- MCP の INSTRUCTIONS・ツール説明を汎用の文に書き直す。「include_terms に仕様（例: 『詰め替え』『ダブル』『単3』）を入れる」「仕様差の判定は AI 側の責任」を明記。例は3カテゴリ以上。
- Web の比較フォームに「含む語」「除く語」「比べる単位（自動/個/ml/g/m/W…）」を足す。
- CLI の `--unit` は `--basis` に、`--include`/`--exclude` を追加。
- 定番品（regulars.py・ローカル専用）: `required_spec` を `include_terms`/`exclude_terms`/`basis` に置換。`examples/regulars.sample.json` は3カテゴリの見本にする。

## 試験

- **ブラインド**: tester が上の §7・§8 だけから独立試験を `tests/test_blind_generic_quantity.py` に固定する（implementer は読まない・編集しない）。
- 旧ブラインド `tests/test_blind_quantity_pricing.py`（トイレットペーパー専用の ply/倍巻き前提）は、仕様が廃止されるため **tester が退役**させる（`git rm`＋WORKLOG に理由1行）。implementer は触らない。
- implementer は自作試験を汎用に書き直す（ply/length_label/倍巻き前提の試験は削除し、3カテゴリ以上の試験に置き換える）。

## 実装の順序（implementer。作業単位ごとに commit＋WORKLOG 1行）

1. WP3-1 SPEC §7・§8・§10・§12（AC3〜AC6 等の TP 前提の文言を汎用に）を差し替え、quantity.py を換算表ベースで作り直す。
2. WP3-2 pricing.py（basis・グループ・include/exclude・caveat）。
3. WP3-3 service・MCP・CLI・Web・regulars・README・docs/index.html を新インターフェースへ。TP 固有の語（ply・倍巻き・ロール既定）が core（src/shopping 配下の quantity/pricing/service/mcp_server/web*）に残っていないことを grep で確認して報告。
4. 全試験＋ブラインド新旧の扱いを報告。uvicorn 実起動（SHOPPING_MOCK=1・BASE_PATH=/kaimono）で 洗剤/電池 系のモック比較が 200 で出ること・/mcp の compare_offers が通ることを確認し、停止。モックデータ（mock_data.json）にも3カテゴリ以上の架空商品を入れる。
