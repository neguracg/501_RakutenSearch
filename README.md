# 買い物リサーチツール / 501_RakutenSearch

個人の買い物を効率化する汎用の商品検索・比較ツール。特定の商品ジャンルに限定しない。
楽天市場の公式 API から商品を集め、商品名から個数と内容量（例: 洗剤 900g×6、水 2L×9本、電池 40本、パネル 100W×2）を読み取って単価を比べ、購入候補と商品固有 URL を返す。購入操作はしない。
道具は商品の意味を持たない: 持つのは「数量の読み取りと単位換算」と「語による絞り込み（含む語・除く語）」だけで、濃縮/通常・層数・色・型番などの仕様の違いは判定しない（呼び出し側の AI と利用者が判断する）。
仕様の正本は [docs/SPEC.md](docs/SPEC.md)。

## 現在の状態（Phase 1）

- 実装済み: 楽天検索 Adapter、複数キーワード検索（重複排除・流量制限）、数量正規化、単価・総額の比較、定番品マスタ、MCP サーバー（stdio）、CLI、公開Web（Phase 1.5）。
- 試験: モック・フィクスチャで自動試験（`pytest`）。**実 API を使った通し確認（AC12）は手動で別途行う**。pytest からは実 API を呼ばない。
- **ChatGPT からの実接続は未検証**（公開リモートMCP `{BASE}/mcp` は in-process 試験とローカル uvicorn で確認済み。ChatGPT への登録は下の手順で腱さんが行う）。
- **楽天ウェブサービス規約への対応**: 第10条(10)「特定の人のみがアクセスできる環境での使用」に適合させるため、楽天に登録するアプリは誰でも開ける公開Webアプリ（search / compare のみ・ログイン無し）とする。普段使い（ブラウザ・ChatGPT・Claude 等の AI）は公開アプリ（Web と `{BASE}/mcp`）に一本化し、ローカルの CLI・stdio MCP は運営者による開発・試験用（既定はモック）。定番品は利用者側（AI の記憶・指示やローカル）で持ち、サーバーには置かない。方針は [docs/SPEC.md](docs/SPEC.md) §11。公開アプリを装う方法は採らない。
- Phase 2 以降（Yahoo!ショッピング・Amazon・ヨドバシ、横断検索）は未着手。

## セットアップ

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

実 API を使う時だけ、リポジトリ直下の `.env`（git 管理外）に次の2つを書く。値はコミット・表示しない。

```
RAKUTEN_APPLICATION_ID=...
RAKUTEN_ACCESS_KEY=...
```

環境変数が優先、無ければ `.env`。モックだけなら認証情報は不要。

## 使い方（公開Web）

本番: https://app.negura.website/kaimono/ （ログイン無し・誰でも使える。search / compare のみで、定番品は出さない）。

ローカルで動かす（モック。実 API を呼ばない）:

```
set PYTHONPATH=src
set SHOPPING_MOCK=1
set BASE_PATH=/kaimono
.venv\Scripts\python -m uvicorn shopping.web:app --port 8000
```

`http://127.0.0.1:8000/kaimono/` を開く。`BASE_PATH` を空にすると `/` 直下で動く。実 API を使う時は `SHOPPING_MOCK` を外し、`.env` か環境変数に認証情報を置く（ブラウザには渡さない）。

- 流量保護（楽天 API のクォータを守る）: API 呼び出しはプロセス全体で 1 秒 1 回に直列化、同じ条件は最大 10 分キャッシュ、IP ごとに 20 回/分まで（超えると 429 の案内画面）。`RATE_LIMIT_PER_MIN` で回数を変えられる。
- 全ページのフッターに楽天のクレジット（Supported by Rakuten Developers）と運営者の責任表示を出す。結果から出るリンクは楽天の商品ページだけ。
- ヘルスチェック: `{BASE_PATH}/healthz`（API は呼ばない）。認証情報が無いと 503（`credentials=false`）で、本番での鍵の入れ忘れを unhealthy として検知する。モック運用（`SHOPPING_MOCK=1`）は鍵が要らないので 200。
- 入力検査: 検索語・含む語・除く語・楽天側の除外語はそれぞれ 1〜5 語、1 語は全角64文字（半角128文字。楽天の上限）まで。価格は 0〜10,000,000。`sort` は楽天公式の値、`basis` は単位表の値だけ。弾いた入力は楽天 API の枠も IP 別回数も消費しない。
- `GET {BASE_PATH}/mcp` は 405（stateless・JSON 応答のため SSE を開かない。`POST` だけ受ける）。

Docker（VPS 用）: `Dockerfile` と `docker-compose.prod.yml`（サービス `kaimono`、external network `internal`、ポート公開なし）。VPS 上の `.env`（git 管理外・600）に `BASE_PATH=/kaimono` `PUBLIC_BASE_URL=https://app.negura.website/kaimono/`（末尾スラッシュ付き） `APP_ENV=production` `RAKUTEN_APPLICATION_ID` `RAKUTEN_ACCESS_KEY` を置く（`.env.example` は秘密ファイル保護の設定で作れないため、キー名はここを正本とする）。起動・反映は VPS 上の `/opt/apps/_tools/deploy_app.sh kaimono` を `nohup setsid` でデタッチ起動する（直の `docker compose up` はフックが遮断）。イメージには `requirements.txt`（本番用）だけを入れる。試験用の `pytest` と `httpx` は `requirements-dev.txt`。

## ChatGPT のチャットから使う（リモートMCP）

公開Web と同じサーバーに MCP エンドポイントがある: `https://app.negura.website/kaimono/mcp`（Streamable HTTP・認証なし）。ツールは `search_products` と `compare_offers` の 2 つだけ（定番品は出さない）。流量保護は Web と共通で、結果にはクレジット（Supported by Rakuten Developers）が必ず入る。

ChatGPT への登録手順（2026-11 時点。画面名は変わりうる）:

1. 設定 → アプリとコネクタ → 詳細設定 → 開発者モードを ON
2. 作成（コネクタを追加）
3. URL に `https://app.negura.website/kaimono/mcp` を入力、認証は「なし」にして作成
4. チャットで「楽天で洗濯洗剤の詰め替えを探して。100gあたりの最安を比べて」「単3電池を1本あたりで比べて」「ミネラルウォーター2Lを100mlあたりで」のように頼む（含む語・除く語・比べる単位は AI が指定する）

Claude・Codex など他の MCP クライアントも同じ URL を登録すればよい。ローカル確認: 上の uvicorn を起動し `http://127.0.0.1:8000/kaimono/mcp` を登録する。

## 使い方（CLI）

```
.venv\Scripts\python cli.py search "洗濯洗剤 詰め替え" "単3電池" --mock
.venv\Scripts\python cli.py compare "洗濯洗剤 詰め替え" --include 詰め替え --exclude 本体 --basis g --desired-quantity 5000 --mock
.venv\Scripts\python cli.py compare "単3電池" --basis 個 --mock
.venv\Scripts\python cli.py compare "ミネラルウォーター" --include 2L --basis ml --mock
.venv\Scripts\python cli.py regular detergent-refill --regulars examples\regulars.sample.json --mock
```

- **既定は架空データ**（`src/shopping/mock_data.json`。洗剤・電池・水・ソーラーパネル・トイレットペーパーの架空商品）で、API を呼ばない。実 API を呼ぶのは `--live`（または環境変数 `SHOPPING_LIVE=1`）を明示した時だけ（運営者の開発・試験用。SPEC §11）。`--mock` は互換のため残してある。
- `--json` で整形済み JSON。キーワードは 1 回 5 個まで、ページは語ごとに 3 ページまで、リクエスト間隔は 1 秒以上。
- 比較は「商品価格」「単位価格」「支払総額」「必要数量を満たす最安」を分けて出す。送料が不明な候補があると支払総額の最安は断定せず、理由を表示する。単価は `--basis`（個・ml・g・m・W・mAh・Wh。L・kg などの別名も可。省略で自動）あたりで出し、その量を読み取れない候補は「単価不明」として最安判定から外す。`--include` は商品名に全部含む語、`--exclude` は含んだら外す語。仕様の違い（濃縮・層数・型番・色など）は判定しないので、結果の商品名で確認する。

## 使い方（MCP サーバー）

ツールは `search_products` / `compare_offers` / `find_regular_item` の3つ。stdio で起動する。

```
set PYTHONPATH=src
rem 既定はモック（API を呼ばない）。実 API は set SHOPPING_LIVE=1 を明示した時だけ
.venv\Scripts\python -m shopping.mcp_server
```

MCP クライアント側の設定例（コマンドと環境変数の指定。クライアントごとに書式は異なる）:

```
command: <このリポジトリ>\.venv\Scripts\python.exe
args:    -m shopping.mcp_server
env:     PYTHONPATH=<このリポジトリ>\src   （既定はモック。実 API を使う時だけ SHOPPING_LIVE=1 を足す）
```

## 定番品マスタ

`data/regulars.json`（git 管理外。個人の購入リストのため）に置く。見本は `examples/regulars.sample.json`（洗剤・電池・水の3カテゴリ）。項目は `include_terms` / `exclude_terms` / `basis` / `desired_quantity` / `keywords` など（`required_spec` と `unit` は廃止）。価格・在庫は保存せず、検索のたびに取り直す。置き場は環境変数 `SHOPPING_REGULARS_PATH` でも指定できる。

## 試験

```
.venv\Scripts\python -m pytest -q
```

## 説明ページ

GitHub Pagesで master ブランチの /docs を公開。
公開URL（2026-11-04にブラウザー表示確認済み）: https://neguracg.github.io/501_RakutenSearch/
静的ページのソース: docs/index.html

## 秘密情報

APIキー・アプリID・接続元IP・商品データ・個人情報をコミットしない。
楽天 API を呼ぶのはサーバー側だけで、アクセスキー・アプリIDをブラウザ（公開ページの HTML・JS）へ渡さない。`docs/`（静的説明ページ）から API は呼ばない。`docs/` は公開されるため認証情報や個人の購入リストを書かない。
`preflight.py` / `check_connection.py` は接続確認用の単発プローブ（商品データや認証情報を出力しない）。
