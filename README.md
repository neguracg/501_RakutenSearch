# 買い物リサーチツール / 501_RakutenSearch

個人の買い物を効率化する汎用の商品検索・比較ツール。特定の商品ジャンルに限定しない。
楽天市場の公式 API から商品を集め、入り数を読み取って単価を比べ、購入候補と商品固有 URL を返す。購入操作はしない。
仕様の正本は [docs/SPEC.md](docs/SPEC.md)。

## 現在の状態（Phase 1）

- 実装済み: 楽天検索 Adapter、複数キーワード検索（重複排除・流量制限）、数量正規化、単価・総額の比較、定番品マスタ、MCP サーバー（stdio）、CLI。
- 試験: モック・フィクスチャで自動試験（`pytest`）。**実 API を使った通し確認（AC12）は手動で別途行う**。pytest からは実 API を呼ばない。
- **ChatGPT からの実接続は未検証**（MCP サーバーはローカルの stdio で動くところまで。接続手順の確立は別課題）。
- **楽天ウェブサービス規約への対応**: 第10条(10)「特定の人のみがアクセスできる環境での使用」に適合させるため、楽天に登録するアプリは誰でも開ける公開Webアプリ（search / compare のみ・ログイン無し）とする。CLI と MCP サーバーは同じ登録アプリの運営者用ツール。方針は [docs/SPEC.md](docs/SPEC.md) §11。公開アプリを装う方法は採らない。
- Phase 2 以降（Yahoo!ショッピング・Amazon・ヨドバシ、横断検索）は未着手。

## セットアップ

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

実 API を使う時だけ、リポジトリ直下の `.env`（git 管理外）に次の2つを書く。値はコミット・表示しない。

```
RAKUTEN_APPLICATION_ID=...
RAKUTEN_ACCESS_KEY=...
```

環境変数が優先、無ければ `.env`。モックだけなら認証情報は不要。

## 使い方（CLI）

```
.venv\Scripts\python cli.py search "トイレットペーパー ダブル 30m" "トイレットペーパー 12ロール" --mock
.venv\Scripts\python cli.py compare "トイレットペーパー ダブル 30m" --ply double --length-m 30 --desired-quantity 48 --mock
.venv\Scripts\python cli.py regular tp-double-30m --regulars examples\regulars.sample.json --mock
```

- `--mock` を付ける（または環境変数 `SHOPPING_MOCK=1`）と、架空データ（`src/shopping/mock_data.json`）を返し、API を呼ばない。付けないと実 API を呼ぶ。
- `--json` で整形済み JSON。キーワードは 1 回 5 個まで、ページは語ごとに 3 ページまで、リクエスト間隔は 1 秒以上。
- 比較は「商品価格」「単位価格」「支払総額」「必要数量を満たす最安」を分けて出す。送料が不明な候補があると支払総額の最安は断定せず、理由を表示する。シングル/ダブル・長さの違う商品は別の束にする。

## 使い方（MCP サーバー）

ツールは `search_products` / `compare_offers` / `find_regular_item` の3つ。stdio で起動する。

```
set PYTHONPATH=src
set SHOPPING_MOCK=1
.venv\Scripts\python -m shopping.mcp_server
```

MCP クライアント側の設定例（コマンドと環境変数の指定。クライアントごとに書式は異なる）:

```
command: <このリポジトリ>\.venv\Scripts\python.exe
args:    -m shopping.mcp_server
env:     PYTHONPATH=<このリポジトリ>\src, SHOPPING_MOCK=1   （実 API を使う時は SHOPPING_MOCK を外す）
```

## 定番品マスタ

`data/regulars.json`（git 管理外。個人の購入リストのため）に置く。見本は `examples/regulars.sample.json`。価格・在庫は保存せず、検索のたびに取り直す。置き場は環境変数 `SHOPPING_REGULARS_PATH` でも指定できる。

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
