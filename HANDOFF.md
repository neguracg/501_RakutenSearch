# HANDOFF — 501_RakutenSearch（2026-11-05 時点）

## 状態
- Phase 1（楽天検索・数量の読み取り・単価比較・MCP・CLI）と Phase 1.5（公開Web と リモートMCP `{BASE}/mcp`）は実装済み。WP2（公開Web）・WP3（数量・比較のカテゴリ非依存化）・WP4（数量読み取りの強化 S1〜S11・W1〜W5）・WP5（数量の信頼度を「解釈の一致」で決める P0〜P4・X1〜X5）・WP6（数え語の直後の境界 P5〜P7）・WP7（P5 の捨てた数の検査の除外を3型の組に限定・コーパス383件・既知の限界 R1〜R3 を SPEC §7 に明記）も実装済み（WP5〜WP7 は verifier の再確認待ち）。**題名の読み取りの規則追加は WP7 で打ち止め**。次は実 API の実題名で高信頼の誤り率を測ってから決める。ブランチ `worktree-public-web` 上で、**本体（master）へのマージと VPS へのデプロイは待ち**。push も未実施。
- 試験: `.venv\Scripts\python -m pytest -q` が全件 green（2492 passed 以上。うちブラインド独立試験 = tests/test_blind_generic_quantity.py 416 件。tester が固定した物で、implementer は読まない・編集しない。実行は件数だけ `-q --tb=no`）。題名コーパス AC-Q1 = tests/test_title_corpus.py（383 件＝title_patterns 232・unseen1 71・unseen2 40・unseen3 40。高信頼の誤り 0（焼き鳥 1件は既知の限界 R2 で xfail）・単価不明 67件＝約 17.5%、2026-11-05 実測）。
- 正本: docs/SPEC.md（AC1〜AC12、公開Web は AC-W1〜W11）、指示書: plans/WP3〜WP7（最新は plans/WP7_close_quantity.md）、経緯: docs/WORKLOG.md / DECISIONS.md / BUGLOG.md。
- 数量の高信頼は「全ての読み方が同じ総数を指す時だけ」（SPEC §7 P0）。誤読は『偽の最安』ではなく『単価不明』に倒す。数量の規則を足す前に P0〜P7 と矛盾しないか見る（足し算で誤り 16→50 件に悪化した経緯は BUGLOG A1・A1′・A2・A3）。数え語は直後の文字で個数かを決める（P5。語ごとの除外リストを足さない）。単価の丸め・整形は pricing.py が持つ。
- 道具は商品の意味を持たない（SPEC §7・§8）。持つのは「個数×内容量の読み取りと単位換算（quantity.py の UNITS / DISPLAY / COUNTERS 表）」と「含む語・除く語での絞り込み」だけ。仕様の違い（濃縮・層数・型番・色など）は判定せず、数量は商品名からの読み取りで誤ることがある旨とあわせて、caveats に常に2行出す。

## 待ち（腱さん・別セッション）
- 消込表 #921 / #923 の回答待ち（内容は消込表を正とする）。
- 本体への取り込みとデプロイ: worktree の試験が green のままマージ → VPS 上の `/opt/apps/_tools/deploy_app.sh kaimono` を `nohup setsid` でデタッチ起動（README）。本番の `.env` に `RAKUTEN_APPLICATION_ID` / `RAKUTEN_ACCESS_KEY` が入っていないと `/healthz` が 503 になる。
- ChatGPT（Plus）から `https://app.negura.website/kaimono/mcp` への実接続は未検証（登録手順は README）。
- 実 API を使った WP3 後の通し確認（AC12 相当）は未実施。CLI は既定がモックなので `cli.py compare ... --live` を手動で 1 回行う。

## 注意
- リポジトリは public、docs/ は GitHub Pages で公開。認証情報・接続元IP・個人の購入リストを書かない（.env と data/ は管理外）。
- CLI と stdio MCP の既定はモック。実 API は CLI の `--live`、stdio MCP の `SHOPPING_LIVE=1` を明示した時だけ。公開Web は実 API が既定。
- 実装者の commit 帰属行は "Sonnet 5.5"（実際の実行モデル）。
