# 指示書: 公開MCPを「既定で全件取得」にする（2026-11-06・b09cf13 の再修正）

作業場所: worktree `C:\Claude\501_RakutenSearch\.claude\worktrees\mcp-allpages`（ブランチ worktree-mcp-allpages）。本体には書かない。git stash 禁止。
変更分類: B（SPEC 同コミット更新）。

## 最重要の原則（今回の失敗の再発防止）
- **出典の無い上限を新設しない・残さない。** 上限・既定件数を置く／残す時は、コメントに出典（楽天API仕様・実測値）を1行書く。書けない数字は消す。
- 腱さんの目的: プラグインは「人間が楽天で検索結果を見るのと同じもの＝ヒットした全件」を ChatGPT に渡すデータ層。件数の節約はしない。
- 実在する制約は2つだけ: ①楽天 IchibaItem Search の仕様 page≤100・hits≤30（1語最大3000件）②1秒1回（GuardedAdapter が直列化済み）。

## やること
1. pages の意味を変える: 省略（None）＝**全件**（`page*hits >= api_count` で止まる既存ループを、楽天の天井 100 ページまで回す）。整数指定は 1〜100 でその枚数まで。
   - `inputs.MAX_PAGES=3`・`MAX_FETCHES=9` と「語数×ページ数」検査を撤去。pages の検査は「None か 1〜100 の int」。100 は楽天仕様が出典とコメントに書く。
   - `orchestrator.Limits.max_pages=3` も楽天天井 100 に（出典コメント）。`search_many` は max_pages=None を全件として扱えるように。
   - 運営者用 stdio MCP・CLI・service の pages 既定も同じく None＝全件（CLI `--pages` 省略＝全件）。Web（web.py PAGES=1）は画面表示なので変えない。
2. `truncated` の意味: 「ヒットが残っているのに、楽天の100ページ天井 または 明示 pages で止めた時だけ true」。説明文も直す。
3. 返却件数の切り詰めを撤去（同じ「黙って切る」型）:
   - search_products の max_results: 既定 None=全件は維持。CLI `--max-results` 既定を None（全件）に。
   - compare_offers の `GROUP_OFFERS_MAX=10`（service._comparison_to_dict のグループ・不明候補の切り詰め）: **MCP（公開・stdio）と CLI では切らない**。Web 画面の表示だけは従来の10件のままにする（引数で切替。Web の出力は不変）。
4. 回数制限の weight: 明示 pages はその値、None は 1（取得前に枚数が分からないため。楽天側は直列化で守られる）。weight の丸め実装は維持。
5. 観測値: 結果の stats に `elapsed_sec`（取得にかかった秒・小数1桁）を足す。次に上限を置くかはこの実測で決める（今回は置かない）。
6. ツール説明文・SPEC.md（241・260行付近、§の pages 記述すべて）を新仕様に更新。「pages 省略＝全件（楽天の上限100ページ=3000件/語まで）」。
7. 試験: b09cf13 で入れた「pages=4 は invalid」「語数×ページ数9」系の試験を新仕様に書き換え。追加: pages 省略で api_count=144 → 5ページ取得して144件全部返る／pages 省略で api_count=5000 → 100ページで止まり truncated=true／pages=101・0 は invalid_request／compare_offers が MCP ではグループ10件で切らず Web では10件／CLI 既定が全件。
8. **数値上限の全数棚卸し表**を報告に付ける（src/shopping と cli.py の全ての数値上限・既定件数を grep で列挙し、出典あり／実測／根拠なし に分類。根拠なしで残すものは理由）。楽天由来（hits 30・1秒・128バイト・page100・キャッシュ24h以内）にはコメントに出典を1行足す。
9. pytest 全件 GREEN（本体の .venv の python を使ってよい）。docs/WORKLOG.md に1行。コミット（author neguracg <neguracg@users.noreply.github.com>、末尾 `Co-Authored-By:` は実行モデル名）。push・デプロイはしない。

## 報告
変更ファイル・pytest 結果・棚卸し表・迷った点。
