# SPEC — 買い物リサーチツール（Phase 1: 楽天）

正本。実装後もこの文書を更新する（会話は揮発）。日付付きの経緯は WORKLOG / DECISIONS へ。
注意: `docs/` は GitHub Pages で公開される。認証情報・接続元IP・アフィリエイトID・個人の購入リストを書かない。

## 1. 目的

ChatGPT の通常チャットで「楽天で○○を条件付きで探して」「いつものトイレットペーパー、今どこが安い？」と頼むと、
裏で自作ツールが EC サイトの公式 API から商品を集め、比較し、購入候補と商品固有 URL を返す。
最終形は 楽天・Yahoo!ショッピング・Amazon・ヨドバシ の横断比較。購入操作はしない。

## 2. フェーズ

| Phase | 内容 | 状態 |
|---|---|---|
| 1 | 楽天検索エンジン・数量正規化・単価比較・定番品マスタ・MCP サーバー（ローカル） | 今回 |
| 2 | Yahoo!ショッピング Adapter | 未着手 |
| 3 | Amazon Adapter（Creators API の利用資格確認が先） | 未着手 |
| 4 | ヨドバシ（一般向け API 未確認。取得手段の調査が先） | 未着手 |
| 5 | 横断検索・購買支援の完成、ChatGPT 実接続 | 未着手 |

## 3. 構成

```
ChatGPT（MCP プラグイン）  /  CLI
        ↓
mcp_server.py / cli.py        … 外部インターフェース（薄く保つ）
        ↓
service.py                    … ツール単位の処理（検索・比較・定番品）
        ↓
orchestrator.py               … 複数キーワード・ページング・重複排除・統計・流量制限
        ↓
adapters/<mall>.py            … モール固有処理（Phase 1 は rakuten のみ）
        ↓
models.py（Product / Offer） → quantity.py（数量正規化） → pricing.py（単価・最安判定）
```

モール固有の知識は adapter の中だけに置く。Phase 2 以降は adapter を足すだけで済む形にする。

## 4. データモデル（不明は null。推測で埋めない）

Product: product_key, jan, maker, name, model_number, spec（dict）, spec_status（confirmed / extracted / unknown）

Offer: mall, shop_name, shop_code, mall_item_code, item_name, price（税込・円）,
shipping_included（true / false / null）, shipping_fee（円 / null。楽天の検索 API では常に null）,
shipping_status（included / separate / unknown）, availability（true / false / null）,
points_rate, review_average, review_count, coupon（null。Phase 1 は取得しない）,
item_url（商品固有 URL）, fetched_at（ISO8601・JST）, quantity（後述）

## 5. 楽天 Adapter

- エンドポイント: `https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701`
- 認証: クエリ `applicationId`、ヘッダー `accessKey`。`formatVersion=2`。
- 応答の商品配列は **`Items`（大文字）で返ることを 2026-11-04 の実通信で確認**。`items` / `Items` の両方を受け、どちらも無ければエラー。
- 送料: `postageFlag` 0=送料込み、1=送料別。実額は API から得られないので shipping_fee は null。
- 条件: keyword, NGKeyword（除外語）, minPrice/maxPrice, sort（standard / +itemPrice / -itemPrice / -reviewCount 等）, page, hits（1〜30）, availability。
- 商品固有 URL は `https://item.rakuten.co.jp/<shop>/<item>/` 形式であること。検索画面 URL を商品 URL として扱わない。形式に合わない URL は item_url_status=needs_review を付けて残す（捨てない・作らない）。
- エラー: 403 / 429 / timeout / ネットワーク / 不正 JSON を個別の種別で返す。429 はその検索全体を打ち切る（再試行ループしない）。
- 秘密情報: URL・ヘッダー・例外メッセージをログや戻り値に出さない。

## 6. 検索オーケストレーション

- 複数キーワードを順に検索し、itemCode で重複排除。どのキーワードで見つかったかは matched_keywords に残す。
- 流量: リクエスト間隔 1 秒以上。1 回の呼び出しの上限＝キーワード 5 個 × 3 ページ（設定で変更可、上限越えは拒否）。
- 統計: キーワードごとの hit 件数（API の count）・取得件数・エラー、全体の取得件数・重複除去件数・候補件数・取得日時・打ち切り理由。
- ChatGPT へは整形済みの必要項目だけ返す（生レスポンスを渡さない）。

## 7. 数量正規化（quantity.py）

商品名・説明から、比較の基準単位（例: ロール）あたりの数量を抽出する。

- 例: `12ロール×4袋` → 総 48 ロール、`12ロール×3パック` → 36、`12R×6` → 72。
- 付随仕様: シングル / ダブル、1 ロールの長さ（m）、倍巻き表記。
- 結果には confidence（high / low / none）と根拠文字列を持たせる。矛盾する表記が複数ある・読み取れない場合は総数を null にする。
- 単価計算に使うのは confidence=high のみ。

## 8. 価格比較（pricing.py）

区別して出す 4 種類:

1. 商品単価が最安（price）
2. 単位あたり価格が最安（price ÷ 総数。1 ロール単価、長さが取れれば 1m 単価）
3. 支払総額が最安（price + 送料。送料不明なら算出しない）
4. 必要数量を満たす最安（定番品マスタの希望数量以上を最少額で満たす候補）

規則:
- 送料が不明（shipping_status=unknown または separate で実額 null）の候補がある時、「総額最安」と断定しない。結果に caveats として理由を書く。
- シングル / ダブル・長さ・型番が違う商品は同じ比較グループに入れない（誤統合しない）。
- 単価は円・小数 2 桁で丸める（表示用）。比較は丸める前の値で行う。

## 9. 定番品マスタ（regulars.py）

- 置き場: `data/regulars.json`（git 管理外。個人の購入リストのため）。見本は `examples/regulars.sample.json`。
- 項目: id, name, maker, model_number, jan, required_spec（例: {"ply": "double", "length_m": 30}）, unit（例: ロール）, desired_quantity, keywords, known_urls, notes。
- 価格・在庫は保存しない。検索のたびに取り直す。

## 10. MCP サーバー（mcp_server.py）

- stdio の MCP サーバー。ツール: `search_products` / `compare_offers` / `find_regular_item`。
- 環境変数 `SHOPPING_MOCK=1` でフィクスチャを返す（API を呼ばない）。
- ChatGPT（Plus）からの実接続は未検証。接続手順と検証は別課題。

## 11. 規約（未解決）

楽天ウェブサービス規約 第10条（10）「特定の人のみがアクセスできる環境での使用」は原則禁止。個人専用運用が許されるかは未確定。
公開アプリと偽装する方法は採らない。他社商品との併記は出典明示で可（楽天 FAQ）。価格・在庫のキャッシュは 24 時間以内。
開発とモック試験は進め、実データの継続運用は規約の確認後とする。

## 12. 受入条件（Phase 1）

| # | 条件 |
|---|---|
| AC1 | 複数キーワードから候補を取得できる |
| AC2 | 同じ itemCode が重複しない（matched_keywords に両方残る） |
| AC3 | 同一商品の入り数違いを同じグループで認識する |
| AC4 | 12ロール×3/×4/×6 を 36/48/72 と算出する |
| AC5 | 1 ロール単価で正しく順位付けする |
| AC6 | シングル/ダブル・長さ違いを誤統合しない |
| AC7 | 送料不明時は総額最安と断定しない |
| AC8 | 商品固有 URL が欠落しない（形式不一致は needs_review で残る） |
| AC9 | 403 / 429 / timeout で安全に止まり、種別が分かる |
| AC10 | 認証情報がログ・戻り値・例外に出ない |
| AC11 | MCP クライアントからモック検索結果を取得できる |
| AC12 | 実 API で 1 キーワード検索が通る（CLI・手動 1 回。pytest には入れない） |
