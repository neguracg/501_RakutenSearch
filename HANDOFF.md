# HANDOFF — 501_RakutenSearch（2026-11-05 時点）

## 状態
- Phase 1（楽天検索・数量の読み取り・単価比較・MCP・CLI）と Phase 1.5（公開Web と リモートMCP `{BASE}/mcp`）は実装済み。WP2（公開Web）・WP3（数量・比較のカテゴリ非依存化）・WP4（数量読み取りの強化 S1〜S11・W1〜W5）・WP5（数量の信頼度を「解釈の一致」で決める P0〜P4・X1〜X5）・WP6（数え語の直後の境界 P5〜P7）・WP7（P5 の捨てた数の検査の除外を3型の組に限定・コーパス383件・既知の限界 R1〜R3 を SPEC §7 に明記）も実装済み（WP5〜WP7 は verifier の再確認待ち）。**題名の読み取りの規則追加は WP7 で打ち止め**。E2E 80件（実題名）の測定が済み、WP8 で P0 違反（採らなかった候補の取りこぼし）を low に倒す修正と、楽天が HTTP 400 にする『1文字だけの語』の事前検査（keyword_term_too_short）を入れた（打ち止めは P0 違反を low に倒す修正に限って解除。商品の意味の扱いは腱さんの判断待ち）。**master へマージ・push 済み（e95dd04。worktree 撤去済み）**。WP7 は verifier 未レビュー。**2026-11-05 23:10 公開済み**: https://app.negura.website/kaimono/（VPS /opt/apps/kaimono・ホストポート 8014・Tunnel ingress 追加・実 API の比較 200 を確認）。GitHub リポジトリ名は 501_ShoppingSearch に変更済み（ローカルのフォルダ名は旧名のまま。改名キットは下記）。
- 試験: `.venv\Scripts\python -m pytest -q` が全件 green（2760 passed 以上。うちブラインド独立試験 = tests/test_blind_generic_quantity.py 416 件。tester が固定した物で、implementer は読まない・編集しない。実行は件数だけ `-q --tb=no`）。題名コーパス AC-Q1 = tests/test_title_corpus.py（407 件＝title_patterns 232・unseen1 71・unseen2 40・unseen3 40・unseen4 7〔E2E 実題名 T1〜T7〕・unseen5 17〔verifier 退行形 B1〜B6〕。高信頼の誤り 0（焼き鳥 1件は既知の限界 R2 で xfail）・単価不明 73件＝約 17.9%、2026-11-06 実測。383 件の部分は単価不明 67件＝17.5% のまま変わらず）。
- 正本: docs/SPEC.md（AC1〜AC12、公開Web は AC-W1〜W11）、指示書: plans/WP3〜WP8（最新は plans/WP8_e2e_p0_fixes.md）、経緯: docs/WORKLOG.md / DECISIONS.md / BUGLOG.md。
- 数量の高信頼は「全ての読み方が同じ総数を指す時だけ」（SPEC §7 P0）。誤読は『偽の最安』ではなく『単価不明』に倒す。数量の規則を足す前に P0〜P7 と矛盾しないか見る（足し算で誤り 16→50 件に悪化した経緯は BUGLOG A1・A1′・A2・A3・A4・A5）。数え語は直後の文字で個数かを決める（P5。語ごとの除外リストを足さない）。単価の丸め・整形は pricing.py が持つ。
- 道具は商品の意味を持たない（SPEC §7・§8）。持つのは「個数×内容量の読み取りと単位換算（quantity.py の UNITS / DISPLAY / COUNTERS 表）」と「含む語・除く語での絞り込み」だけ。仕様の違い（濃縮・層数・型番・色など）は判定せず、数量は商品名からの読み取りで誤ることがある旨とあわせて、caveats に常に2行出す。

## 次にやること（順番）
0. **WP8（E2E 80件の数量の誤読6件・半角1文字の語の HTTP 400）は master マージ済み・本番未反映**（051a634・verifier 3回で高信頼の新しい誤り0）。並走中の公開MCP全件化セッションと順番を合わせて VPS へ再デプロイ → 腱さんの ChatGPT で E2E 80件を再実施（実題名での単価不明率も測る）。商品の種類・仕様の扱いは消込表 #934 の回答待ち。
1. ChatGPT（Plus）からの実接続（消込表 #923。腱さん）。
2. 実題名での高信頼の誤り率の測定（公開アプリで10検索語程度。high の個数・総量を目視）と、WP7 の verifier レビュー。
3. フォルダ改名 501_RakutenSearch → 501_ShoppingSearch（消込表 #926。他セッションが止まっている時に）。キットは `C:\Claude\102_ClaudeUnyou\unyou\rename-501_ShoppingSearch\`。腱さんがアプリを完全終了 → `rename-folder.bat` → YES。その後 `POST-RENAME-TODO.md` を消し込む（GitHub 側は改名済み）。
4. Uptime Kuma に `http://kaimono:8000/kaimono/healthz` の監視を追加（ブラウザ操作・腱さん）。

## 待ち（腱さん・別セッション）
- 消込表 #923 / #926 / #927 の回答待ち（内容は消込表を正とする）。
- 再デプロイ: VPS 上の `/opt/apps/_tools/deploy_app.sh kaimono` を `nohup setsid` でデタッチ起動（README）。本番の `.env` に `RAKUTEN_APPLICATION_ID` / `RAKUTEN_ACCESS_KEY` が入っていないと `/healthz` が 503 になる。
- ChatGPT（Plus）から `https://app.negura.website/kaimono/mcp` への実接続は未検証（登録手順は README）。
- 実 API を使った WP3 後の通し確認（AC12 相当）は未実施。CLI は既定がモックなので `cli.py compare ... --live` を手動で 1 回行う。

## 注意
- リポジトリは public、docs/ は GitHub Pages で公開。認証情報・接続元IP・個人の購入リストを書かない（.env と data/ は管理外）。
- CLI と stdio MCP の既定はモック。実 API は CLI の `--live`、stdio MCP の `SHOPPING_LIVE=1` を明示した時だけ。公開Web は実 API が既定。
- 実装者の commit 帰属行は "Sonnet 5.5"（実際の実行モデル）。
