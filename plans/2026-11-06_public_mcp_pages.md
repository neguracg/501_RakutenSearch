# 指示書: 公開MCPで pages を効かせる（2026-11-06）

作業場所: worktree `C:\Claude\501_RakutenSearch\.claude\worktrees\mcp-pages`（ブランチ worktree-mcp-pages）。本体には書かない。
変更分類: B（仕様変更。SPEC を同じコミットで更新）。

## 背景
ChatGPT から公開 `{BASE}/mcp` の search_products に `pages=3, max_results=100` を渡しても 30 件しか返らない。
原因は意図した暫定仕様: `src/shopping/mcp_server.py` の invoke が公開面で `pages=1` に固定し `_PUBLIC_PAGES_NOTE` を付けている（SPEC.md 241行・260行「pages=1 固定」）。
腱さんの判断: プラグインは「人間が楽天で検索結果を見るのと同じものを渡す」データ層。件数を取れることが目的なので固定を外す。

## やること
1. `mcp_server.py` invoke: 公開面でも `pages=pages` を渡す。`_PUBLIC_PAGES_NOTE` と付与処理を削除。
2. 入力検査: `inputs.validate` に `pages` を追加（int 1〜3、範囲外・非整数は InvalidInput）。search_products / compare_offers の `check=dict(...)` に pages を渡す。さらに `len(keywords) × pages ≤ 9` を超えたら InvalidInput（メッセージ例「検索語の数×ページ数は9まで」）。理由: API は1秒1回直列なので1呼び出し最大約9秒に抑える。
3. 流量の公平性: Gate.admit の回数制限は1回の呼び出しを pages 回分として数える（RateLimiter.hit を pages 回、または重み付き）。Web は pages=1 なので挙動不変。
4. max_results（隠れた2本目の上限）: search_products の `max_results` 既定を None にし、None なら全件（keywords×pages×30 が上限）を返す。明示指定時は従来どおり切り詰め＋notes。service.search_products の既定も合わせる（CLI/stdio の呼び出し側を壊さないこと。grep で呼び出し元を全列挙）。compare_offers 側に同種の切り詰めが無いか確認し、あれば同様に。
5. 取得ページ数の可視化: 結果に語ごとの取得状況（api_count＝楽天ヒット数・received＝取得件数・取得ページ数・上限で打ち切ったか）が既に出ているか確認。無ければ per_keyword に `pages_fetched` と `truncated`（api_count > received かつ要求ページを取り切った）を足す。
6. ツール説明文の pages の記述（1〜3・1ページ30件・検索語数×ページ数は9まで）を更新。
7. SPEC.md 241・260行を新仕様に更新（Web は pages=1 のまま、と書き分ける）。web.py は触らない。
8. 試験: tests/test_mcp_http.py:254 付近の「pages 固定」を検証している試験を新仕様に書き換え。追加: 公開面で pages=3 → adapter に page=1,2,3 が渡り最大90件返る／pages=4・pages=0 → invalid_request（API 呼び出し0回）／keywords 4語×pages 3 → invalid_request／回数制限が pages 分減る／max_results 省略時に30件で切れない。
9. 全試験 `pytest` GREEN を確認。docs/WORKLOG.md に1行追記。コミットは意味の単位で（author neguracg <neguracg@users.noreply.github.com>、末尾に `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`）。push・デプロイはしない（オーケストレータが行う）。

## 報告
変更ファイル一覧・試験件数・呼び出し元の列挙結果・迷った点。
