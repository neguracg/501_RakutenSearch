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
| 1.5 | 公開Web とリモートMCP `{BASE}/mcp`（search / compare のみ。楽天規約 第10条(10) 適合のため。定番品 regulars は出さない） | 今回 |
| 2 | Yahoo!ショッピング Adapter | 未着手 |
| 3 | Amazon Adapter（Creators API の利用資格確認が先） | 未着手 |
| 4 | ヨドバシ（一般向け API 未確認。取得手段の調査が先） | 未着手 |
| 5 | 横断検索・購買支援の完成、ChatGPT 実接続 | 未着手 |

## 3. 構成

```
ChatGPT（MCP プラグイン）  /  CLI  /  公開Web（web.py）
        ↓
mcp_server.py / cli.py / web.py … 外部インターフェース（薄く保つ）。web.py は検索 API の流量保護（直列化・キャッシュ・IP別回数制限）と規約の表示を持つ
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
- 送料: `postageFlag` 0=送料込み、1=送料別（楽天公式 IchibaItem Search の出力項目で 2026-11-05 に確認）。実額は API から得られないので shipping_fee は null。フラグを正とし、タイトルの「送料無料」「送料別」等の文字で送料を決めない。タイトルとフラグが食い違う候補は注意（notes / caveats と各候補の shipping_title_conflict）に出す。
- 条件: keyword, NGKeyword（除外語）, minPrice/maxPrice, sort（standard / +itemPrice / -itemPrice / -reviewCount 等）, page, hits（1〜30）, availability。
- 商品 URL は API が返したまま使う（`?rafcid=...` 等のクエリは楽天が API 経由の流入を数える値なので外さない・改変しない）。商品固有 URL は `https://item.rakuten.co.jp/<shop>/<item>/` 形式であること。検索画面 URL を商品 URL として扱わない。形式に合わない URL は item_url_status=needs_review を付けて残す（捨てない・作らない）。
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
- 付随仕様: シングル / ダブル、1 ロールの長さ（m）、倍巻き・長尺表記（length_label: `x2` `x1.5` `multi`=倍率不明 `long`=ロング/長尺。「ポイント10倍」等の販促表記は倍巻きとしない）。倍巻き・長尺の実長は確定させず length_m は null。
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
- シングル / ダブル・長さ・型番が違う商品は同じ比較グループに入れない（誤統合しない）。グループ鍵は ply・length_m・unit に加え、倍巻き・長尺の length_label（表記が無ければ付けない）。長さ不明の通常品と倍巻き・長尺品、倍率の違う倍巻き同士は別グループ。
- 全体の「単位価格が最安」は、通常表記の候補があるなら倍巻き・長尺品を判定から外し、外した件数を caveats に書く（倍巻きだけの時は倍巻きどうしで順位付けする）。
- 単価は円・小数 2 桁で丸める（表示用）。比較は丸める前の値で行う。

## 9. 定番品マスタ（regulars.py）

- 置き場: `data/regulars.json`（git 管理外。個人の購入リストのため）。見本は `examples/regulars.sample.json`。
- 項目: id, name, maker, model_number, jan, required_spec（例: {"ply": "double", "length_m": 30}）, unit（例: ロール）, desired_quantity, keywords, known_urls, notes。
- 価格・在庫は保存しない。検索のたびに取り直す。

## 10. MCP サーバー（mcp_server.py）

- stdio の MCP サーバー。ツール: `search_products` / `compare_offers` / `find_regular_item`。
- 環境変数 `SHOPPING_MOCK=1` でフィクスチャを返す（API を呼ばない）。
- 公開リモートMCP: `{BASE}/mcp`（Streamable HTTP・stateless・JSON 応答・認証なし）。ツールは `search_products` と `compare_offers` の 2 つだけ（`find_regular_item` は出さない）。流量保護（直列化・キャッシュ・IP別回数制限）は Web と共通（guard.py）。pages は 1 に固定。
- ChatGPT（Plus）からの実接続は未検証（登録手順は README）。

## 11. 規約（運用方針）

楽天ウェブサービス規約 第10条（10）「特定の人のみがアクセスできる環境での使用」は原則禁止。この規約に適合させるため、次の方針で運用する（判断の出典: 消込表 #920）。

- 楽天に登録するアプリは **誰でも開ける公開Webアプリ** `https://app.negura.website/kaimono/`。ログイン・Cloudflare Access・IP制限を掛けない。
- 普段使い（ChatGPT・Claude・Codex 等の AI から呼ぶ・ブラウザで使う）は公開アプリ（Web と `{BASE}/mcp`）経由に一本化する。
- ローカルの CLI・stdio MCP で実 API を呼ぶのは運営者による開発・試験に限る（既定はモック）。同じ登録アプリの運営者用ツールという位置づけ。
- 定番品は利用者側（AI の記憶・指示やローカル）で持ち、サーバーには置かない。
- 公開アプリと偽装する方法（2人限定なのに公開と称する等）は採らない。
- 公開面（Web と `{BASE}/mcp`）は search / compare のみ。定番品（regulars。個人の購入リスト）は出さない。
- 公開MCP の結果には `credit` `credit_url` `operator` `web` を必ず含め（エラー結果にも）、INSTRUCTIONS で回答末尾へクレジットを添えるよう指示する。
- 楽天のアクセスキー・アプリIDはサーバー側だけが持つ。ブラウザへの応答に一切含めない。
- 規約から来る画面の義務は AC-W1〜W8（§12）に列挙する。全ページのフッターに、楽天のクレジット（公式テキスト版・無改変）・運営者の責任表示・価格在庫の注意を出す。
- 結果画面から出す外部リンクは楽天の商品URLだけ（クレジットのリンクを除く）。
- 他社商品との併記は出典明示で可（楽天 FAQ）。価格・在庫のキャッシュは 24 時間以内。公開Webのメモリキャッシュは最大 10 分。
- 公開面の流量保護（Web と MCP は共通の guard 層を通す）: 楽天 API 呼び出しはプロセス全体で 1 秒 1 回に直列化、同条件は最大 10 分キャッシュ、IP 別に回数制限（既定 20 回/分）。pages=1・hits=30 固定。
- Cookie・ログイン・アクセス解析・個人情報の保存は無し。

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

### Phase 1.5 公開Web

| # | 条件 |
|---|---|
| AC-W1 | ログイン無しで誰でも `{BASE}/` から検索・比較できる（アクセス制限を掛けない） |
| AC-W2 | 楽天のアクセスキー・アプリIDがブラウザへの応答に一切含まれない |
| AC-W3 | 全ページに楽天のクレジット表示（公式テキスト版・無改変）と運営者の責任表示がある |
| AC-W4 | API を使う画面からの外部リンクは楽天の商品URL（とクレジット）だけ |
| AC-W5 | 楽天 API 呼び出しはプロセス全体で1秒1回以下、同条件はメモリで最大10分キャッシュ（24時間以内） |
| AC-W6 | IP 別回数制限を超えると 429 で待つよう案内し、楽天の 429/timeout は混雑画面になる |
| AC-W7 | BASE_PATH 有り/無しの両方で全ルート・リンクが通る。`{BASE}/healthz` が 200 |
| AC-W8 | 定番品（個人の購入リスト）を公開Webに出さない。Cookie・個人情報を保存しない |
| AC-W9 | `{BASE}/mcp`（Streamable HTTP・認証なし）で MCP の initialize・tools/list・compare_offers が通り、公開するツールは search_products と compare_offers の2つだけ。結果に credit を含み、流量保護は Web と共通 |
