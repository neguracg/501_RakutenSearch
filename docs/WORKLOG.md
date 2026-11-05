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
- 2026-11-05 WP4-0: 数量読み取り強化(S1〜S11)のブラインドを追記(既存150件は不変) / 209件
- 2026-11-05 WP4-0b: W1〜W5 確定(×無し2段・count_unit正規名・小数点境界・l/L/ℓ casefold)をブラインドに固定、弱い形を確定形へ / 220件
- 2026-11-05 WP4-1: SPEC §7・§8 に S1〜S11・W1〜W5 を追記し、quantity.py(回分・言い直し・総量併記・数え語P/pc/ダース等・2段・桁数・未知数え語low・表整合)と pricing.py(語の数字境界・basis次元・filter_by_terms)を修正、inputs(UTF-8 128バイト・check_basis/check_desired_quantity 一本化)/service/rakuten も連動 / pytest 740 passed（ブラインド 220/220）
- 2026-11-05 WP4-2: B4 公開入口4×入力項目の未固定セルを試験で固定(tests/test_wp4_cells.py。MCP compare の ng_keyword・価格、basis・desired_quantity の回数無消費×MCP/Web、service 省略既定モック)、C19 GET /mcp 405 に締切、basis/desired_quantity の検査を inputs に一本化 / pytest 932 passed, 31 skipped(入口に無い項目のセル)（ブラインド 220/220。自己変異 17件中17件で赤）
- 2026-11-05 WP4-3: S8〜S10 の Web・CLI・MCP・README・SPEC(一覧でも含む/除く語、basis は一覧で不使用の表示、全角42文字の文言、指数表記なし・小さな単価の桁増し)、BUGLOG A1(!重)・B1・B2・B3 / pytest 932 passed（ブラインド 220/220）
- 2026-11-05 WP5-0: 一致原則(P0〜P4)の母集団をブラインドに追記(既存220件は不変) / 392件
- 2026-11-05 WP5-0b: X1〜X5 確定(P精密化・別語言い直し・低信頼化・入数直後)をブラインドに固定、矛盾した追記分を修正 / 413件
- 2026-11-05 WP5-0c: X1訂正を固定(単独NPはlow、ヶ・点単独はhigh維持。「ティッシュ 12P」→12 を low に変更) / 416件
- 2026-11-05 WP5-1: quantity.py に一致原則(P0〜P4・X1〜X5・S3精密化・数え語コ/ケ/膳・倒れ ×N の low)を実装、題名コーパス AC-Q1 を tests/test_title_corpus.py で固定 / pytest 1600 passed（ブラインド 416/416・コーパス 誤り0/不明22・OK210）
- 2026-11-05 WP5-2: SPEC §7 に P0〜P4・X1〜X5・S/W の整理・AC-Q1 を追記、BUGLOG A1 追記と A1′・A2(!重) / pytest 1600 passed（ブラインド 416/416・コーパス 誤り0/不明22）
- 2026-11-05 WP5-3: B(S5 比べた次元 unit_price_dimension・content_amounts を結果に)・C1(単価の桁数を quantity.unit_price_digits に一本化)・C3(regulars の desired_quantity を inputs 検査へ)・C2(HANDOFF 同期)・SPEC 追記 / pytest 1612 passed（ブラインド 416/416・コーパス 誤り0/不明22）
- 2026-11-05 WP6-1: quantity.py に P5(数え語の直後の境界を1関数に・個別除外リスト撤去)・P6(連結位置で捨てる時は low・連結P/計量値直後Pは上限99を掛けない)・P7(量・個数に空白で続くカタカナ未知語は low)、単価の丸めを pricing.py へ移管、AC-Q1 を343件へ、SPEC §7 に P5〜P7 / pytest 1780 passed（ブラインド 416/416・コーパス343 誤り0/不明44）
- 2026-11-05 WP6-2: BUGLOG A3(恒久化: P5 ホワイトリスト化)・HANDOFF 同期・plans/WP5_fixexp_quantity.diff 先頭2行(ローカルパス)削除・tests/corpus/run_set.py の import を title_patterns へ / pytest 1780 passed（ブラインド 416/416・コーパス343 誤り0/不明44）
- 2026-11-05 WP6-3: _P_NOT_COUNT(還元等の除外リスト)を撤去し P5 に一本化・SPEC X1 の P の文面を P5/P6 に整合・試験追加 / pytest 1785 passed（ブラインド 416/416・コーパス343 誤り0/不明44）
- 2026-11-05 WP6-4: P5 で捨てた数字＋数え語が採用した総数と食い違う時は low（12個送料無料・6本まとめ買い・6本ダブル。月/購入/還元等の既知の非個数は対象外）、SPEC P5 に追記 / pytest 1794 passed（ブラインド 416/416・コーパス343 誤り0/不明55）
- 2026-11-05 WP7-1: A(P5 の捨てた数の検査の除外を SPEC 例示の3型の組＝ヶ/ケ＋月・点＋購入/以上/まで/で・P＋還元等だけに限定。6個で1000円・30本ポイント10倍は検査)・「6個以上」「6個まで」の数も検査・数え語表×9語の表試験・B1・コーパス383件(unseen3 追加・焼き鳥は R2 で xfail)・SPEC P5 補足 / pytest 2491 passed（ブラインド 416/416・コーパス383 誤り0(xfail1)/不明67）
- 2026-11-05 WP7-2: SPEC §7 に「既知の限界」(R1 空白を挟む販促語・R2 未知の数え語・R3 英字の数え語+英字・C3 末尾の1ケース/1箱)、結果の caveats の常設文に「数量は商品名からの読み取りで、誤ることがあります。購入前に商品ページで確認」を追加(pricing.QUANTITY_CAVEAT) / pytest 2492 passed（ブラインド 416/416・コーパス383 誤り0(xfail1)/不明67）
- 2026-11-05 WP7-3: BUGLOG(要対策表の回数 5回・A1′/A2 に恒久化と commit 75d224f・A4 を追加)・HANDOFF 同期(コーパス383・単価不明 17.5% 実測・WP7 打ち止め) / pytest 2492 passed（ブラインド 416/416・コーパス383 誤り0(xfail1)/不明67）
- 2026-11-05 WP7-4: 表試験に「まで」を追加・BUGLOG A4 のヨコテン件数を実数(2件)に・SPEC AC6 の caveats 行数を整合 / pytest 2564 passed（ブラインド 416/416・コーパス383 誤り0(xfail1)/不明67）
- 2026-11-05 VPS配置: negura-tools-01 の /opt/apps/kaimono に 6a41135 を配置（ホストポート127.0.0.1:8014・外部未公開＝Tunnel ingress 未追加）。ローカル.envの読取が拒否されたため RAKUTEN_* は空 → healthz 503(想定内)・コンテナ unhealthy。/kaimono/ 200・POST /kaimono/mcp initialize 200・GET /kaimono/mcp 405 を内部で確認。鍵投入後は deploy_app.sh kaimono --env-only で反映
- 2026-11-05 公開: Tunnel ingress（app.negura.website ^/kaimono → 127.0.0.1:8014、config.yml は .bak-20261105-kaimono に退避）を追加し cloudflared 再起動。外部から healthz 200・トップ 200（クレジット表示あり）・GET /mcp 405・POST /mcp initialize 200、隣接アプリ akky/anoreci の healthz 200 を確認。VPS 内で実 API の比較 200（22件）。docs/index.html を公開中に戻した
- 2026-11-06 公開MCPで pages を効かせる(変更分類B): invoke の pages=1 固定と _PUBLIC_PAGES_NOTE を撤去、inputs.validate に pages(1〜3)・語数×pages≤9、Gate.admit は pages 回分を回数制限へ(RateLimiter.hit に weight)、search_products の max_results 既定を None(全件)に、KeywordStat に pages_fetched/truncated を追加、SPEC 241・260 行更新、ツール説明文更新。Web は不変 / pytest 2608 passed（+44。自己変異 2/2 で赤）
- 2026-11-06 本番反映: b09cf13 を deploy_app.sh kaimono で反映（STATE=OK）。本番 /kaimono/mcp search_products「ソーラーパネル 500W」pages=3 → api_count144・received90・pages_fetched3・truncated=true、pages=4 → invalid_request を実測
