# 指示書 WP2 — 公開Webアプリ化（楽天規約 第10条(10) 適合）＋実データ不具合3点

正本の仕様: `docs/SPEC.md`。この WP で SPEC §2・§11・§12 を同じコミットで更新する（変更分類 B）。
判断の出典: 消込表 #920（2026-11-05 腱さん「Bにしよう」）＝**誰でも開ける公開Webアプリ（VPS・ログイン無し）**。

## 環境

- 作業場所: `C:\Claude\501_RakutenSearch\.claude\worktrees\public-web`（ブランチ `worktree-public-web`）。本体ディレクトリには書かない。
- Python: 本体の `C:\Claude\501_RakutenSearch\.venv\Scripts\python`（worktree に .venv は無い）。追加パッケージは同じ venv へ入れる。
- 参考実装（同じ社内の型）: `C:\Claude\73_AnoReci`（FastAPI・BASE_PATH・Dockerfile・docker-compose.prod.yml）。読むだけ。
- VPS 要件の正本: `~/.claude/skills/vps-deploy/references/app-requirements.md`（§2 BASE_PATH・§3 healthz・§4 Dockerfile・§5 compose・§6 .env.example）。
- repo は public。`docs/` は GitHub Pages で公開。認証情報・IP・個人の購入リストを書かない。

## 着手前5問（kaishu-policy）

1. 変えるもの: 公開Web画面を新設、SPEC §11 の規約方針、quantity/pricing の比較グループ、送料表示。
2. 壊しうる呼び出し側: `service.compare_offers` を使う MCP・CLI・試験（ブラインド96件含む）。
3. 触らないもの: MCP ツールの名前・引数、CLI のサブコマンド、regulars（公開Webでは使わない）。
4. データ: DB 無し。価格・在庫は保存しない（Web のメモリキャッシュは最大10分）。
5. 試験: 既存 308件が全部 green のまま＋新規試験。ブラインド試験の期待値を変えたくなったら**変えずに報告**する。

## 作業単位（順番どおり。作業単位ごとに commit＋WORKLOG 1行）

### WP2-1 方針の文書反映（コード無し）

- SPEC §11 を「規約（運用方針）」に書き換える。中身:
  - 楽天に登録するアプリ＝**誰でも開ける公開Webアプリ** `https://app.negura.website/kaimono/`。ログイン・Cloudflare Access・IP制限を掛けない。
  - CLI・MCP サーバーは同じ登録アプリの**運用者用ツール**（同じアプリIDで運用者がテスト・調査に使う）という解釈。
  - 公開アプリと偽装する方法（2人限定なのに公開と称する等）は採らない。
  - 規約から来る画面の義務（下の AC-W に列挙）。
- SPEC §2 フェーズ表に「Phase 1.5 公開Web（search/compare のみ）」を足す。定番品(regulars)は公開Webに出さない。
- SPEC §12 に AC-W1〜W8（下記）を追加。
- DECISIONS.md に 2026-11-05 の決定を追記（#920）。README の「規約の確認が未解決」と「公開ページからAPIを呼び出さない」を新方針に書き換え（サーバー側がAPIを呼ぶ。ブラウザにキーを渡さない）。

### WP2-2 実データ不具合3点（HANDOFF 由来。BUGLOG 1行ずつ・ヨコテン表）

`docs/BUGLOG.md` が無ければ作る（書式は `~/.claude/skills/bug-review/references/buglog-rules.md`）。

1. **倍巻き・長さ不明が通常品と同じ比較グループに混ざる**: 倍巻き（「2倍巻き」「1.5倍」「3倍長持ち」等）を検出し、長さ不明の商品と長さが分かる商品・倍巻き商品を**同じグループで比べない**。グループ鍵に長さ区分を入れる等。SPEC §7・§8 を同じコミットで更新。
2. **タイトル「送料無料」でも「送料別」と出る**: 楽天公式の `postageFlag` の意味（0/1 のどちらが送料込みか）を公式ドキュメント（webservice.rakuten.co.jp の IchibaItem/Search の出力項目）で確認し、実装と照合する。実装が正しく、タイトルとフラグが食い違うだけなら、フラグを正とし、食い違いを caveat に出す（タイトルの文字で送料を決めない）。
3. **商品URLの `?rafcid=...`**: 外さない（楽天がAPI経由の流入を数えるための値で、規約上も改変しない方が安全）。SPEC §5 に「URL は API が返したまま使う」と1行書く。コード変更は無し。

ブラインド試験（tests/test_blind_quantity_pricing.py）が 1 の変更で落ちる場合は、試験を直さず、どの試験がどう落ちたかを報告に書いて WP2-2 の 1 だけ止める（他は進める）。

### WP2-3 公開Webアプリ（FastAPI）

- 依存: `fastapi` `uvicorn[standard]` `jinja2` をバージョン固定で requirements.txt へ（mcp と衝突しない版）。試験用に `httpx`。
- `src/shopping/web.py`（`app = create_app()`）。`BASE_PATH` 環境変数（既定 `""`、本番 `/kaimono`）を全ルート・href・form action・静的ファイルに通す。
- 画面（スマホ前提・1カラム・外部CSS/JS/CDN 無し・inline CSS）:
  - `GET {BASE}/` 検索フォーム。キーワード欄（改行またはカンマで 1〜5語）、モード（一覧 / 比較）、除外語、価格下限・上限。
  - `GET {BASE}/search?q=...` → `service.search_products`、`GET {BASE}/compare?q=...` → `service.compare_offers`。結果は表/カード。caveats と notes を必ず表示（「最安」と断定しない文言は service の結果に従う）。
  - pages=1・hits=30 に固定（利用者に変えさせない）。
- `GET {BASE}/healthz` → 200 `{"ok": true, "credentials": true/false}`（API は呼ばない。秘密の値は出さない）。
- **クォータ保護（必須）**:
  - プロセス全体で楽天 API への呼び出しを**1秒1回に直列化**（threading.Lock＋最終呼び出し時刻）。adapter 呼び出しの手前に置く。
  - 同じ検索条件の結果をメモリに最大10分キャッシュ（件数上限あり。24時間を超えない）。
  - IP 別の回数制限（例 20回/分）。超えたら 429 と「少し待って」画面。IP は `CF-Connecting-IP` ヘッダー → なければ client.host。
  - AdapterError(429/timeout等) は「楽天側が混雑」等の画面にする（例外本文・URL・キーを出さない）。
- **規約の表示（AC-W）**: 全ページのフッターに
  - クレジット: `<a href="https://developers.rakuten.com/" target="_blank">Supported by Rakuten Developers</a>`（https://webservice.rakuten.co.jp/guide/credit のテキスト版。改変しない。実ページを開いて文字列を照合すること）
  - 運営者表示: 「このサイトは個人開発者 negura が作成・運営しており、内容の責任は運営者にあります。楽天グループとは関係ありません。」（リンク無し）
  - 「価格・在庫は検索時点のもの。購入前に楽天市場の商品ページで確認してください。」
- 結果画面からのリンクは**楽天の商品URLだけ**（`target="_blank" rel="noopener"`）。GitHub・他サイトへのリンクを置かない（クレジットのリンクは除く）。
- Cookie・ログイン・アクセス解析・個人情報の保存は無し。
- **Docker**: `Dockerfile`（python:3.12-slim・非root uid1000・HEALTHCHECK が `${BASE_PATH}/healthz` を叩く・`uvicorn shopping.web:app`・PYTHONPATH=src）、`docker-compose.prod.yml`（サービス `kaimono` 1つ・`restart: unless-stopped`・`env_file: .env`・external network `internal`・ポート公開は書かない）、`.env.example`（`BASE_PATH` `PUBLIC_BASE_URL` `APP_ENV` `RAKUTEN_APPLICATION_ID` `RAKUTEN_ACCESS_KEY` のキー名だけ）、`.dockerignore`（.env・data・.venv・tests は入れてよい）。
- Docker がこの PC で使えるなら `docker build` を1回通す。使えなければ「未実行」と報告。
- 試験（tests/test_web.py・SHOPPING_MOCK=1 か fake adapter で API を呼ばない）:
  - BASE_PATH="" と "/kaimono" の両方で トップ・search・compare・healthz が 200、全 href/action が BASE_PATH 始まり。
  - フッターにクレジット文字列・運営者表示が全ページにある。
  - 結果の外部リンクが item.rakuten.co.jp（とクレジットの developers.rakuten.com）以外に無い。
  - IP 別回数制限で 429。キャッシュで2回目は adapter を呼ばない。直列化で2回の呼び出し間隔が1秒以上（時計は差し替え可能に作る）。
  - 応答本文にアクセスキー・アプリID の値が出ない。
- 実起動確認: `BASE_PATH=/kaimono SHOPPING_MOCK=1` で uvicorn を起動し、curl で `/kaimono/`・`/kaimono/compare?q=...`・`/kaimono/healthz` が 200。**確認後に必ずサーバーを停止**。

### WP2-4 説明ページとREADME

- `docs/index.html` に「使ってみる: https://app.negura.website/kaimono/」のリンクと、クレジット表示を足す（「開発中」の文言を実態に合わせる）。
- README に Web の起動方法（ローカル）と本番URL、Docker の説明。

### WP2-5 リモートMCP（ChatGPT のチャットから呼ぶ本命の入口。2026-11-05 追加）

SPEC §1 の目的は「ChatGPT の通常チャットから呼ぶ」。ChatGPT（Web/アプリ）は localhost の stdio MCP に繋げないため、
公開アプリに **Streamable HTTP の MCP エンドポイント `{BASE}/mcp`** を同居させる（ChatGPT の開発者モード→コネクタ作成で URL を登録、認証は「なし」）。

- `mcp_server.build_server()` の同じツール定義を流用し、**公開面では `search_products` と `compare_offers` の2つだけ**を出す（`find_regular_item` は出さない＝AC-W8）。stdio の `python -m shopping.mcp_server` はローカル用に3ツールのまま残す。
- mcp 2.3.0 の Streamable HTTP（ASGI アプリ）を FastAPI に `{BASE}/mcp` でマウント。stateless・JSON 応答で動く設定を優先（Cloudflare Tunnel 越しで SSE の長時間接続に頼らない）。
- MCP 経由の呼び出しも Web と**同じ流量保護**（1秒1回の直列化・10分キャッシュ・IP別回数制限）を通す。保護は service の手前の共通層に置き、Web と MCP の二重実装にしない。
- 応答にキー・アプリIDを出さない。ツール説明文（INSTRUCTIONS）の「個人用」を「公開の買い物リサーチツール」に直し、caveats を伝える指示は残す。
- **規約の義務を優先（腱さん指示）**: 公開MCP のツール結果に `credit: "Supported by Rakuten Developers"`・`credit_url: "https://developers.rakuten.com/"`・`operator: "個人開発者 negura が運営（楽天グループとは無関係）"`・`web: PUBLIC_BASE_URL` を必ず含め（エラー結果にも）、INSTRUCTIONS に「回答の末尾にクレジット（Supported by Rakuten Developers）を添えること」と書く。試験で tools/call の結果に credit が入ることを確認。
- 試験: in-process の MCP クライアント（streamable http）で `{BASE}/mcp` に initialize → tools/list（2件だけ・find_regular_item が無い）→ compare_offers 呼び出しが通る。BASE_PATH 有り/無しの両方。
- 実起動確認: uvicorn（SHOPPING_MOCK=1・BASE_PATH=/kaimono）で `/kaimono/mcp` に initialize と tools/list が通ることを MCP クライアントで確認し、停止する。
- README に ChatGPT への登録手順（設定→アプリとコネクタ→詳細設定→開発者モード ON→作成→URL `https://app.negura.website/kaimono/mcp`・認証なし）を書く。画面名は変わりうるので「2026-11 時点」と添える。

## 受入条件（SPEC §12 へ転記する）

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
| AC-W9 | `{BASE}/mcp`（Streamable HTTP・認証なし）で MCP の initialize・tools/list・compare_offers が通り、公開するツールは search_products と compare_offers の2つだけ。流量保護は Web と共通 |

## 報告に含めるもの

各作業単位の commit ハッシュ／pytest 件数／ブラインド試験の結果／docker build の実行有無／uvicorn 実起動の結果／残リスク1〜3行。
