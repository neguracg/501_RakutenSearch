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
