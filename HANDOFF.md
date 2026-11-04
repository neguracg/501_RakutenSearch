# HANDOFF — 501_RakutenSearch（2026-11-05 01:05 時点）

## 状態
- Phase 1 MVP 実装・push 済み（版 7875dcc）。`.venv\Scripts\python -m pytest -q` → 308 passed（うちブラインド独立試験 96件 = tests/test_blind_quantity_pricing.py）。
- 実 API で 1 回動作確認済み: `.venv\Scripts\python cli.py compare "トイレットペーパー ダブル 12ロール"` → 30件取得・比較表示。
- 正本: docs/SPEC.md（AC1〜AC12）、指示書: plans/WP1_phase1_mvp.md、経緯: docs/WORKLOG.md / DECISIONS.md。

## 次にやること（優先順）
1. 実データで見えた不具合候補3点を直す（yokoten 適用・BUGLOG 1行）
   - 倍巻き・長さ不明の商品が通常品と同じ比較グループ（double|unknown）に混ざり、1ロール単価が不公平になる。
   - タイトルに「送料無料」とあっても postageFlag 由来で「送料別」と表示される。postageFlag の値の意味を公式仕様で再確認。
   - 商品 URL に `?rafcid=...` が付く。正規化するか判断。
2. tester が挙げた SPEC 未決点（tests/test_blind_quantity_pricing.py 冒頭の Q 一覧）を SPEC に反映。
3. verifier で全差分の初回レビュー（対象: 490c777..7875dcc）。
4. ChatGPT Plus から MCP サーバー（`python -m shopping.mcp_server`、stdio）へ接続する手順を調査し、腱さんの手作業を切り出す。接続は未検証。
5. 楽天規約 第10条(10)（特定の人のみがアクセスできる環境での使用）は未解決。実データの継続運用は判断待ち。

## 注意
- リポジトリは public、docs/ は GitHub Pages で公開。認証情報・接続元IP・個人の購入リストを書かない（.env と data/ は git 管理外）。
- 実装者の commit 帰属行は "Sonnet 5.5"（実際の実行モデル）。
