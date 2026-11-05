# BUGLOG

書式の正本: `~/.claude/skills/bug-review/references/buglog-rules.md`。1行の事実だけを書く（分析は週次レビュー）。

## 🔴 要対策

| 発覚 | 機構（次も起きること） | 回数 | 状態 |
|---|---|---|---|

## ログ

- 2026-11-05 | 倍巻き・長尺（2倍巻き等）の商品が、長さ不明の通常品と同じ比較グループ（double|unknown）に入り、1ロール単価が不公平に比べられた（実 API の通し確認 AC12 で発覚） | 原因: 倍巻き表記で length_m を None にするだけで、通常品の「長さ不明」と区別する情報（length_label）を持たず、group_key が (ply, length_m, unit) だけだった | WP2-2 同コミット | @jissou ヨコテン:済7件(group_key・_key_str・グループ生成・単位価格caveat・価格caveat・service辞書・cli表示。_spec_check と必要数量判定は不要=倍巻きは length_m None で仕様不明扱い/ロール数のみ判定) グローバル:不要(比較グループ鍵の仕様次元の話でこのアプリ固有) 解決:済(2026-11-05・tests/test_wp2_realdata.py::test_long_roll_not_in_same_group_as_plain_unknown_length)
- 2026-11-05 | タイトルに「送料無料」とあるのに「送料別」と表示された（実 API の通し確認で発覚） | 原因: 表示は楽天 postageFlag(1=送料別)由来で実装は公式仕様どおり(0=送料込み,1=送料別を公式で確認)。タイトルとフラグが食い違う候補を利用者に知らせていなかった | WP2-2 同コミット | @jissou ヨコテン:済1件(shipping_title_conflict を search/compare の両方に適用。他にタイトル文言とAPI項目を突き合わせる箇所は無く不要) グローバル:不要(楽天固有の表記の食い違い) 解決:済(2026-11-05・tests/test_wp2_realdata.py::test_title_free_shipping_does_not_override_flag_but_is_flagged)
- 2026-11-05 | 商品URLに ?rafcid=... が付くため正規化すべきか迷った(HANDOFF 由来) | 原因: 仕様として未記載。rafcid は楽天が API 経由の流入を数える値で改変しない方が規約上も安全。コード変更なし、SPEC §5 に「URL は API が返したまま使う」を明記 | WP2-2 同コミット | @youken ヨコテン:済0件(item_url を加工する箇所は adapter/service/cli のいずれにも無いことを grep で確認) グローバル:不要(アプリ固有の仕様) 解決:済(2026-11-05・tests/test_wp2_realdata.py::test_item_url_kept_as_returned_including_rafcid)
