# HANDOFF — 501_RakutenSearch（2026-11-05 時点）

## 状態
- Phase 1（楽天検索・数量の読み取り・単価比較・MCP・CLI）と Phase 1.5（公開Web と リモートMCP `{BASE}/mcp`）は実装済み。WP2（公開Web）・WP3（数量・比較のカテゴリ非依存化）も実装済み。ブランチ `worktree-public-web` 上で、**本体（master）へのマージと VPS へのデプロイは待ち**。push も未実施。
- 試験: `.venv\Scripts\python -m pytest -q` が全件 green（うちブラインド独立試験 = tests/test_blind_generic_quantity.py 150 件。tester が固定した物で、implementer は読まない・編集しない）。
- 正本: docs/SPEC.md（AC1〜AC12、公開Web は AC-W1〜W11）、指示書: plans/WP3_generic_quantity.md、経緯: docs/WORKLOG.md / DECISIONS.md / BUGLOG.md。
- 道具は商品の意味を持たない（SPEC §7・§8）。持つのは「個数×内容量の読み取りと単位換算（quantity.py の UNITS / DISPLAY / COUNTERS 表）」と「含む語・除く語での絞り込み」だけ。仕様の違い（濃縮・層数・型番・色など）は判定せず、caveats に常に1行出す。

## 待ち（腱さん・別セッション）
- 消込表 #921 / #923 の回答待ち（内容は消込表を正とする）。
- 本体への取り込みとデプロイ: worktree の試験が green のままマージ → VPS 上の `/opt/apps/_tools/deploy_app.sh kaimono` を `nohup setsid` でデタッチ起動（README）。本番の `.env` に `RAKUTEN_APPLICATION_ID` / `RAKUTEN_ACCESS_KEY` が入っていないと `/healthz` が 503 になる。
- ChatGPT（Plus）から `https://app.negura.website/kaimono/mcp` への実接続は未検証（登録手順は README）。
- 実 API を使った WP3 後の通し確認（AC12 相当）は未実施。CLI は既定がモックなので `cli.py compare ... --live` を手動で 1 回行う。

## 注意
- リポジトリは public、docs/ は GitHub Pages で公開。認証情報・接続元IP・個人の購入リストを書かない（.env と data/ は管理外）。
- CLI と stdio MCP の既定はモック。実 API は CLI の `--live`、stdio MCP の `SHOPPING_LIVE=1` を明示した時だけ。公開Web は実 API が既定。
- 実装者の commit 帰属行は "Sonnet 5.5"（実際の実行モデル）。
