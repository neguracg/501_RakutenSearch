# 指示書: 既定3ページ＋全量件数＋範囲指定で何件でも（2026-11-06・d1affb3 の上に積む）

作業場所: worktree `C:\Claude\501_RakutenSearch\.claude\worktrees\mcp-allpages`（ブランチ worktree-mcp-allpages。d1affb3 の上）。本体には書かない。git stash 禁止。変更分類 B（SPEC 同コミット更新）。

## 腱さんの決定（2026-11-06 01:22・#931）
- 既定は語ごとに 3 ページ（90 件）を渡し、**全量が何件か（楽天のヒット数）を必ず伝える**。
- リクエストがあれば（例「4 ページ目から 10 ページ分」）**何件でも渡す**。

## 原則（前回の失敗の再発防止）
- 出典の無い上限を新設しない。残してよい天井は楽天仕様（page ≤ 100・hits ≤ 30）と、下記の Cloudflare 打ち切り（出典: Cloudflare の既定プロキシ読み取りタイムアウト 100 秒＝524）だけ。どちらもコメントに出典1行。

## やること
1. パラメータ: search_products / compare_offers（公開・stdio）と CLI に `start_page`（既定 1）を追加。`pages` の既定を **3** に（d1affb3 の None=全件を置き換え）。取得範囲は start_page〜start_page+pages-1。
   - 検査: start_page は 1〜100 の int、pages は 1〜100 の int、かつ start_page+pages-1 ≤ 100（楽天の天井。超えたら invalid_request で「楽天は 100 ページ目までしか返さない」と伝える）。語数×ページ数の上限は置かない。
   - ヒットが尽きたら早く止める既存挙動は維持（page*hits >= api_count）。
2. 全量と続きの表示: stats.per_keyword に `api_count`（全量）に加えて `start_page`・`pages_fetched`・`last_page`（取得した最後のページ）・`next_page`（続きがあれば次のページ番号、無ければ null。楽天の 100 ページ天井を超える場合も null）・`remaining`（api_count のうち 100 ページ天井以内で未取得の件数の目安）を返す。`truncated` は「next_page がある」と同義に整理してよい。
3. 時間の安全網: 1 回の呼び出しの取得が **80 秒**（Cloudflare 100 秒打ち切りに応答生成の余裕 20 秒）を超えそうなら、そこで止めて取れた分を返し、next_page と notes「時間の上限で途中まで。続きは start_page=N で」を付ける（全損させない）。実時間は orchestrator に clock を注入して試験で固定。
4. ツール説明文: 「既定は語ごと 3 ページ（90 件）。全量は stats.per_keyword.api_count。続きが欲しい時は start_page=next_page で呼ぶ。pages を増やせば一度に多く取れる（1 ページ約 1 秒）。楽天は 100 ページ目（3000 件）まで」。利用者に全量と取得範囲を伝えるよう INSTRUCTIONS にも1文。
5. 回数制限の weight は pages（明示値または既定 3）。
6. compare_offers も同じ取得処理（グループで切らないのは d1affb3 のまま）。Web は従来どおり 1 ページ・不変。
7. SPEC.md・README（CLI）を更新。試験: 既定で 3 ページ・api_count 144 → 90 件 + next_page=4／start_page=4,pages=2 で page 4,5 を取得し 144 件目まで（54 件）／start_page=99,pages=3 は invalid／80 秒で打ち切って next_page が付く／compare_offers・CLI でも start_page が効く。d1affb3 の「省略で全件」試験は新仕様へ書き換え。
8. pytest 全件 GREEN、WORKLOG 1行、コミット（author neguracg <neguracg@users.noreply.github.com>）。push・デプロイはしない。

## 報告
変更ファイル・pytest 結果・迷った点。
