# 指示書 WP1 — Phase 1 MVP（楽天検索エンジン＋MCP）

正本の仕様: `docs/SPEC.md`（受入条件 AC1〜AC12）。この指示書は「どう作るか」と公開インターフェースを固定する。

## 環境

- 作業場所: `C:\Claude\501_RakutenSearch`（public リポジトリ。`docs/` は GitHub Pages で公開される）
- Python: `.venv\Scripts\python`（3.12。`mcp` 2.3.0 と `pytest` 導入済み）。`requirements.txt` に `mcp==2.3.0` と `pytest` を固定して書く。
- 標準ライブラリ優先。HTTP は urllib（既存 `preflight.py` の作法: リダイレクト禁止・URL/ヘッダー/例外本文を出さない）を流用する。FastAPI・DB・UI は作らない。
- `.env` は読むだけ（`RAKUTEN_APPLICATION_ID` / `RAKUTEN_ACCESS_KEY`）。中身を表示・ログ出力・コミットしない。python-dotenv は使わず自前の小さなローダー。

## レイアウト（固定）

```
src/shopping/__init__.py
src/shopping/config.py        … .env / 環境変数の読み込み。repr で秘密を伏せる
src/shopping/models.py        … Offer / Product / QuantityInfo / SearchStats 等の dataclass
src/shopping/adapters/__init__.py
src/shopping/adapters/base.py … MarketplaceAdapter（Protocol/ABC）, AdapterError(kind)
src/shopping/adapters/rakuten.py
src/shopping/orchestrator.py
src/shopping/quantity.py
src/shopping/pricing.py
src/shopping/regulars.py
src/shopping/service.py       … search_products / compare_offers / find_regular_item（MCP と CLI の共通処理）
src/shopping/mcp_server.py
cli.py                        … 薄いラッパー（argparse）
tests/fixtures/*.json         … 楽天応答の形を模した架空データ（実商品データを入れない）
tests/test_*.py
examples/regulars.sample.json
```

`pyproject.toml` か `tests/conftest.py` で `src` を import パスに通し、`.venv\Scripts\python -m pytest` で全部通ること。

## 公開インターフェース（固定。名前・型を変えない）

### models.py

```python
@dataclass
class QuantityInfo:
    unit: str                    # 比較の基準単位（例 "ロール"）
    per_pack: int | None         # 1袋あたり
    pack_count: int | None       # 袋数（単品なら 1）
    total: int | None            # 総数。confidence != "high" なら None
    ply: str | None              # "single" / "double" / None
    length_m: float | None       # 1単位あたりの長さ(m)
    confidence: str              # "high" / "low" / "none"
    evidence: str                # 根拠にした文字列（無ければ ""）

@dataclass
class Offer:
    mall: str
    mall_item_code: str
    item_name: str
    price: int | None
    item_url: str
    item_url_status: str         # "ok" / "needs_review"
    shop_name: str | None = None
    shop_code: str | None = None
    shipping_status: str = "unknown"      # "included" / "separate" / "unknown"
    shipping_fee: int | None = None
    availability: bool | None = None
    points_rate: int | None = None
    review_average: float | None = None
    review_count: int | None = None
    jan: str | None = None
    model_number: str | None = None
    caption: str | None = None
    fetched_at: str | None = None         # ISO8601 JST
    matched_keywords: list[str] = field(default_factory=list)
    quantity: QuantityInfo | None = None
```

### quantity.py

```python
def parse_quantity(text: str, unit: str = "ロール") -> QuantityInfo
```
- 表記揺れ: `12ロール×4袋` / `12ロール x 4パック` / `12R×6` / `12ロール入×3` / `（12ロール）×4セット` / 全角数字・全角× を扱う。単品 `12ロール` のみなら pack_count=1, total=12。
- ply: `ダブル`/`2枚重ね` → "double"、`シングル`/`1枚` → "single"。
- length_m: `30m` / `27.5m` / `25メートル`。`2倍巻き` 等で長さが確定できない場合は length_m=None。
- 総数の候補が 2 つ以上で食い違う（例: タイトルに 48ロール と 72ロール）→ total=None, confidence="low"。
- 何も読めない → confidence="none"。

### pricing.py

```python
@dataclass
class ComparisonGroup:
    key: str                          # 比較可能な束の識別子（ply・length_m・unit で作る）
    ply: str | None
    length_m: float | None
    offers: list[Offer]               # 単位価格の安い順（算出不能は末尾）

@dataclass
class Comparison:
    groups: list[ComparisonGroup]
    cheapest_price: Offer | None          # 商品価格が最安
    cheapest_unit_price: Offer | None     # 単位価格が最安（confidence high のみ対象）
    cheapest_total: Offer | None          # 支払総額が最安。送料不明が1件でも候補にあれば None
    cheapest_meeting_quantity: Offer | None  # desired_quantity 以上を最少額で満たす
    caveats: list[str]                    # 断定できない理由（日本語）

def unit_price(offer: Offer) -> float | None       # price / quantity.total。high 以外は None
def total_price(offer: Offer) -> int | None        # included→price、separate かつ fee あり→price+fee、他は None
def compare(offers: list[Offer], required_spec: dict | None = None,
            desired_quantity: int | None = None) -> Comparison
```
- required_spec（例 `{"ply": "double", "length_m": 30}`）に合わない offer は比較から除外し、caveats に件数を書く。
- 最安判定は「最も候補数の多いグループ」ではなく、required_spec 指定時はその仕様のグループ、未指定時は全グループ横断で行うが **ply か length_m が違う offer 同士を単位価格で比べた結果は caveats に「仕様違いを含む」と明記**する。

### adapters/rakuten.py

```python
class RakutenAdapter(MarketplaceAdapter):
    def __init__(self, app_id: str, access_key: str, opener=None, clock=None): ...
    def search(self, keyword: str, *, page: int = 1, hits: int = 30, ng_keyword: str | None = None,
               min_price: int | None = None, max_price: int | None = None,
               sort: str = "standard", availability: int = 1) -> tuple[list[Offer], int]   # (offers, api_count)
```
- `items` / `Items` 両対応。formatVersion=2 の平らな item dict。postageFlag→shipping_status。
- AdapterError(kind) の kind: `http_403` / `http_429` / `http_<code>` / `timeout` / `network_error` / `invalid_json` / `unexpected_response` / `missing_credentials`。str(exc) に URL・キーを含めない。

### orchestrator.py

```python
def search_many(adapter, keywords: list[str], *, max_pages: int = 1, hits: int = 30,
                limits: Limits = Limits(), sleep=time.sleep, **filters) -> tuple[list[Offer], SearchStats]
```
- Limits の既定: max_keywords=5, max_pages=3, min_interval_sec=1.0。超えたら ValueError（黙って切らない）。
- itemCode で重複排除、matched_keywords に追記。429 で残り全部を打ち切り stats.stopped_reason="rate_limited"。他エラーはそのキーワードだけ記録して続行。
- SearchStats: per_keyword（keyword, api_count, received, error）, total_received, duplicates_removed, unique_offers, fetched_at, stopped_reason。

### service.py / mcp_server.py / cli.py

- service: `search_products(keywords, filters…) -> dict`、`compare_offers(keywords, required_spec, desired_quantity, filters…) -> dict`、`find_regular_item(regular_id) -> dict`。戻り値は JSON 化可能な dict（offer は必要項目だけ。caption は 200 字で切る）。
- 依存注入: service は adapter を引数で受け取れる。`SHOPPING_MOCK=1` のときは `tests/fixtures` 由来ではなく `src/shopping/mock_data.json`（架空データ）を返す MockAdapter を使う。
- mcp_server: mcp 2.3.0 の実際の API を `.venv` 内のパッケージで確認してから書く（記憶で書かない）。stdio。ツール 3 つ。各ツールの説明文は ChatGPT が使い分けられるよう日本語で具体的に。
- cli: `python cli.py search "kw1" "kw2" [--min-price] [--max-price] [--ng] [--pages] [--mock] [--json]`、`python cli.py compare ...`、`python cli.py regular <id>`。表示に URL は出してよい（商品固有 URL）が、キー・IP は出さない。

## 作業単位とコミット（この順で。単位ごとに commit し WORKLOG に1行）

1. 土台: requirements / conftest / config / models / adapters.base
2. RakutenAdapter ＋ テスト（フィクスチャ・403/429/timeout/invalid_json/URL 形式/秘密非漏洩）
3. orchestrator ＋ テスト（複数語・重複排除・429 打ち切り・上限超え ValueError・sleep 間隔）
4. quantity ＋ pricing（自前の単体テストも書いてよいが、別途ブラインド試験で判定する）
5. regulars ＋ examples ＋ service
6. mcp_server ＋ in-process クライアントでの呼び出し試験（AC11）
7. cli ＋ README 更新（「本体未実装」を消し、起動方法・MOCK・規約未解決・ChatGPT 未接続を書く）

author は `neguracg <neguracg@users.noreply.github.com>`。コミット末尾に `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。push はしない（オーケストレータが行う）。`git add -A` は使わず、対象ファイルを名指しで add する。

## やらないこと

- 実 API を pytest から呼ぶこと（AC12 はオーケストレータが手動で1回）
- `.env` の中身を読んで表示・ログ・テスト期待値に使うこと
- `docs/index.html` の変更、VPS・Cloudflare・GitHub 設定の変更、push
- 実在の商品データ・店舗名をフィクスチャに入れること（架空の名前を使う）
