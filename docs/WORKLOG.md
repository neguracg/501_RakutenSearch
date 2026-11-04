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
