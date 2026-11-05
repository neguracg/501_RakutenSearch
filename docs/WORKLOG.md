# WORKLOG


## 2026-11-04
- 初期コミットの全4ファイルを確認。静的説明ページを追加。
- 汎用の買い物ツールとしてREADMEと方針を記載。
- 公開・接続試験の結果は確認後に追記する。

- リポジトリをpublic化し、master /docs のGitHub Pages公開を設定。
- GitHub APIでPages built、公開処理successを確認。公開ページの本文とデスクトップ表示をブラウザーで確認。
- 公開URLを楽天登録フォームへ入力。IP欄はユーザーが入力済み。画像認証・規約同意送信・ID発行・API接続試験は未実施。
- HTML解析とgit diff --check成功。モバイル表示は未確認。

- 2026-11-05 WP1-1: 土台（requirements/pyproject/conftest/config/models/adapters.base）を追加 / pytest 5 passed
- 2026-11-05 WP1-2: RakutenAdapter（Items/items両対応・403/429/timeout/invalid_json・URL形式検査・秘密非漏洩）とフィクスチャ追加 / pytest 49 passed
- 2026-11-05 WP1-3: orchestrator（複数語・itemCode重複排除・429打ち切り・上限超えValueError・間隔sleep）追加 / pytest 74 passed
- 2026-11-05 WP1-4: quantity（表記揺れ/ply/長さ/矛盾→low）とpricing（グループ分け・単位価格・総額・送料不明caveat）を追加 / pytest 152 passed（自作確認。判定は別途ブラインド試験）
- 2026-11-05 WP1-5: regulars・examples/regulars.sample.json・MockAdapter(mock_data.json)・service（search/compare/find_regular）を追加 / pytest 195 passed
- 2026-11-05 WP1-6: mcp_server（MCPServer・3ツール・stdio）とin-process/stdio子プロセスのMCPクライアント試験を追加(AC11) / pytest 202 passed
- 2026-11-05 WP1-7: cli.py（search/compare/regular・--mock/--json）とREADME更新（本体未実装表記を削除、起動方法・MOCK・規約未解決・ChatGPT未接続を記載） / pytest 211 passed
- 2026-11-05 WP1-4b: 自己変異で生き残った単価のconfidence検査に試験を追加 / pytest 212 passed
- 2026-11-05 判定: ブラインド独立試験（quantity/pricing 96件）を tests/test_blind_quantity_pricing.py に固定し全件 green。全体 308 passed。
- 2026-11-05 AC12: 実 API で `cli.py compare "トイレットペーパー ダブル 12ロール"` を1回実行し取得30件（API件数4589）。動作は成立。実データで見えた要改善3点（倍巻き・長さ不明が同じ比較グループに混ざる／タイトル「送料無料」でも postageFlag 由来で送料別と出る／商品URLに rafcid 付き）は次セッションで対応。
- 2026-11-05 WP2-1: SPEC §2/§3/§11/§12(AC-W1〜W8)・DECISIONS・README を公開Web方針へ更新（文書のみ） / pytest 308 passed
- 2026-11-05 WP2-2: 倍巻き/長尺をlength_labelで別グループ化・送料タイトル食い違いの注意表示・URLはAPI返却のまま(SPEC §5/§7/§8)・BUGLOG3行 / pytest 333 passed(ブラインド96件green)
- 2026-11-05 WP2-3: 公開Web(web.py/web_view.py/guard.py=直列化1秒・10分キャッシュ・IP別20回/分の共通層)・Dockerfile/compose/.dockerignore・requirements追加(docker未実行, .env.example は権限で作成不可) / pytest 373 passed
- 2026-11-05 WP2-4: docs/index.html に公開URL・クレジット・運営者表示、README に Web 起動方法/本番URL/Docker / pytest 373 passed
- 2026-11-05 WP2-5: 公開リモートMCP {BASE}/mcp(stateless・JSON・2ツール・credit必須・guard共有)・credit.py・SPEC §10/§11/AC-W9・README(ChatGPT登録手順)・指示書更新 / pytest 384 passed
- 2026-11-05 WP3-0: 汎用化に伴い旧ブラインド(TP専用)を退役、汎用ブラインド test_blind_generic_quantity.py を固定 / 130件
- 2026-11-05 WP3-0b: 汎用ブラインドを確定契約(Q0〜Q17)に合わせて更新(結果の形・スロット名・ラベルを確定名へ、Q5/Q7/Q10/Q15/Q16 追加) / 150件
- 2026-11-05 WP3-1: SPEC §7・§8・§10・§12 を汎用化（確定契約Q0〜Q17を同文面で採録）、quantity.py を換算表(UNITS/DISPLAY/COUNTERS)ベースで作り直し、QuantityInfo/Offer(unit_price)を新項目へ / pytest tests/test_quantity.py 83 passed（pricing 以降は WP3-2/3 で復旧するため全体は途中赤。ブラインド 103/150＝数量系は全緑、残り47は価格比較）
- 2026-11-05 WP3-2: pricing.py を basis(自動/個/別名正規化)・include/exclude_terms・単価不明グループ・常設caveat・cheapest_for_quantity で作り直し、旧TP前提の試験を削除/置換 / pytest tests/test_pricing.py 40 passed（ブラインド 150/150。service以降は WP3-3 で復旧するため全体は途中赤）
- 2026-11-05 WP3-3: service/MCP/CLI/Web/regulars/mock_data/README/docs を新インターフェース(include_terms・exclude_terms・basis・cheapest_for_quantity)へ、required_spec・unit・ply系を廃止、coreにply/倍巻き/length_label/ロール既定なし(COUNTERS表とプロンプト例のみ)、DECISIONSの個人例も一般例へ / pytest 480 passed（ブラインド 150/150）
- 2026-11-05 WP3-4: verifier 初回レビュー指摘 B1〜B5・C3〜C9 を修正（公開入力検査を guard.Gate.admit→inputs.validate に一本化、isascii+isdecimal、CLI/stdio MCP 既定モック、GET /mcp 405、healthz 503、requirements 分離と httpx2 直接 import 廃止、HANDOFF/SPEC AC-W1〜W11/README 更新）、BUGLOG 6行 / pytest 598 passed（ブラインド 150/150）。uvicorn 実起動(SHOPPING_MOCK=1・BASE_PATH=/kaimono)で Web 比較4カテゴリ200・/mcp compare_offers・GET /mcp 405・healthz 200 を確認し停止
