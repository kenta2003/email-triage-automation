# Implementation Plan

- [x] 1. Foundation: プロジェクト基盤の構築

- [x] 1.1 環境確認・ディレクトリ構造・依存関係・秘匿情報管理の初期化
  - `python --version` でPython 3.10以上がインストールされていることを確認する（未インストールの場合はpython.orgからインストール）
  - `claude --version` でClaude Code CLIがPATHに存在することを確認する
  - `sources/`, `notifiers/`, `credentials/`, `tokens/`, `logs/` ディレクトリを作成する
  - `requirements.txt` に `google-api-python-client`, `google-auth-oauthlib`, `requests`, `python-dotenv` を記述する
  - `.gitignore` に `credentials/`, `tokens/`, `.env`, `logs/*.log` を追加する
  - `.env.example` に `SLACK_PRIMARY_REPLY_WEBHOOK`, `SLACK_PRIMARY_DIGEST_WEBHOOK`, `SLACK_SECONDARY_REPLY_WEBHOOK`, `SLACK_SECONDARY_DIGEST_WEBHOOK` の4変数をコメント付きで記述する
  - `pip install -r requirements.txt` が正常に完了し、必要パッケージがインストールされていることを確認
  - _Requirements: 6.1_

- [x] 1.2 Google Cloud OAuth認証情報のセットアップ（Primary・Secondary）
  - Google Cloud Consoleでプロジェクトを作成し、Gmail API を有効化する
  - OAuthクライアントID（デスクトップアプリ）を作成し、クレデンシャルJSONを `credentials/primary_credentials.json` としてダウンロードする
  - Secondaryアカウント用に同様の手順でクレデンシャルを `credentials/secondary_credentials.json` として取得する（または同一プロジェクトで2アカウントを管理する）
  - Slack管理画面（api.slack.com）でIncoming Webhookアプリを作成し、4チャンネル分のWebhook URLを取得して `.env` に記述する
  - `credentials/` に2本のJSONファイルが存在し、`.env` に4本のWebhook URLが設定されていることを確認
  - _Requirements: 1.1, 4.1, 4.4_

- [x] 1.3 アカウント設定モジュール（`config.py`）の実装
  - `AccountConfig` と `ClassificationRules` データクラスを定義する
  - Primaryアカウント設定を記述する（処理済みラベル名 `Claude-Processed-Primary`・分類ルール・Webhook URLキー・チャンネルマッピング）
  - Secondaryアカウント設定を記述する（分類ルールにお祈りメールを「見るべき」として明示的に含める）
  - `python-dotenv` で `.env` をロードし `os.getenv()` でWebhook URLを参照するロジックを実装する
  - `python -c "from config import ACCOUNTS; print([a.name for a in ACCOUNTS])"` で `['Primary', 'Secondary']` が表示されることを確認
  - _Requirements: 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 4.1, 4.4_

- [x] 2. Core: 独立コンポーネントの実装

- [x] 2.1 (P) GmailソースコンポーネントとOAuthトークン生成の実装
  - `sources/base.py` に `BaseSource` 抽象基底クラス（`fetch()` / `mark_processed()` メソッド）を定義する
  - `sources/gmail.py` に `GmailSource` クラスを実装する
  - Gmail APIで「`Claude-Processed-*` ラベルなし」のメールを検索・取得するロジックを実装する（前回処理ラベルのないメールが対象、ラベル未作成の初回は24時間以内を追加フィルタとして適用）
  - メール上限を50件に設定し、超過時は古いものから処理するロジックを実装する
  - 処理済みラベルを付与する `mark_processed()` を実装する
  - `credentials/primary_credentials.json` を使ってPrimaryOAuth認証フローを実行し `tokens/primary_token.json` を生成する
  - `credentials/secondary_credentials.json` を使ってSecondaryOAuth認証フローを実行し `tokens/secondary_token.json` を生成する
  - Gmail上に `Claude-Processed-Primary` / `Claude-Processed-Secondary` ラベルを手動または自動で作成する
  - `python -c "from sources.gmail import GmailSource; from config import ACCOUNTS; items = GmailSource(ACCOUNTS[0]).fetch(); print(len(items), 'emails fetched')"` でメール取得件数が表示されることを確認
  - _Depends: 1.2, 1.3_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 5.1, 5.2_
  - _Boundary: sources/gmail.py_

- [x] 2.2 (P) AI処理モジュール（`processor.py`）の実装
  - `SourceItem` / `ClassifiedItem` データクラスを定義する
  - `claude -p` をサブプロセス（`subprocess.run`、タイムアウト120秒）として呼び出し、複数メールを1リクエストでバッチ分類するロジックを実装する
  - 出力フォーマットをJSON形式で厳密に指定するプロンプトを実装する（`id`・`category`・`draft_reply`・`reasoning` フィールドを含む）
  - 「返信必要」以外のメールには `draft_reply=null` を指定し、実際の送信は行わないことをプロンプトに明示する
  - JSON出力のパース失敗時にリトライ（最大2回）し、それでも失敗した場合は全件「見るべき」として返すフォールバックを実装する
  - メール件数が50件を超える入力に対してエラーを返すバリデーションを実装する
  - `processor.py` を直接実行する簡易テストスクリプトでサンプルメール3件（返信必要・見るべき・スキップ各1件）を処理し、JSON出力がパースされ `ClassifiedItem` リストが返ることを確認
  - _Depends: 1.3_
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3_
  - _Boundary: processor.py_

- [x] 2.3 (P) Slack通知コンポーネント（`notifiers/slack.py`）の実装
  - `notifiers/base.py` に `BaseNotifier` 抽象基底クラス（`notify()` メソッド）を定義する
  - `notifiers/slack.py` に `SlackNotifier` クラスを実装する
  - 「返信必要」メールを1件ずつ個別フォーマット（送信者・件名・受信日時・返信下書き）で `reply_channel_webhook` に送信するロジックを実装する
  - 「見るべき」まとめ（送信者・件名・一行サマリー）・「スキップ」件名一覧・件数サマリーをダイジェストフォーマットで `digest_channel_webhook` に送信するロジックを実装する
  - 処理対象が0件のアカウントはSlack通知を送信しないロジックを実装する
  - `python -c "from notifiers.slack import SlackNotifier; from config import ACCOUNTS; SlackNotifier(ACCOUNTS[0])._post_webhook(ACCOUNTS[0].reply_channel_webhook, 'テスト通知')"` を実行し、`#学校-要対応` チャンネルにテストメッセージが届くことを確認
  - 同様に `#学校-ダイジェスト`・`#就活-要対応`・`#就活-ダイジェスト` の全4チャンネルへの送信を確認
  - _Depends: 1.2, 1.3_
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_
  - _Boundary: notifiers/slack.py_

- [x] 3. Integration: パイプライン統合

- [x] 3.1 オーケストレーター（`run.py`）の実装とパイプライン結合
  - `run.py` で全コンポーネントを順番に呼び出す（Primaryフェッチ→分類→ラベル付与→通知、Secondaryフェッチ→分類→ラベル付与→通知）パイプラインを実装する
  - アカウント単位のtry/exceptを実装し、片方で例外が発生しても他方の処理を継続するGraceful Degradationを実装する
  - `logging` モジュールで実行開始・終了時刻、アカウント別処理件数（返信必要・見るべき・スキップ各件数）、エラー内容を `logs/run.log` に追記しstdoutにも出力する
  - 起動時に `claude --version` でClaude Code CLIの存在確認を行い、未検出時はエラーログを出力して終了する
  - 将来の拡張のために `SOURCES` リストを `run.py` 内に定義し、新しいソースを追加する際は1行の追記のみで済む構造にする
  - `python run.py` を実行し、`logs/run.log` に処理ログが記録され4つのSlackチャンネルに通知が届くことを確認
  - _Depends: 2.1, 2.2, 2.3_
  - _Requirements: 1.1, 4.8, 4.9, 5.2, 6.2, 6.3, 6.4_

- [x] 4. Validation: 統合動作確認と定期実行設定

- [x] 4.1 統合動作確認（実メール・重複防止・障害耐性）
  - Primary・Secondaryの実際のGmailアカウントでメール取得・分類・Slack通知の全フローを確認する
  - `python run.py` を2回連続実行し、2回目は処理済みメールがスキップされてSlack通知が送信されないことを確認する（重複防止の確認）
  - Secondaryの `tokens/secondary_token.json` を退避してから実行し、SecondaryのGmailエラーが `logs/run.log` に記録されPrimaryは正常処理されることを確認する（Graceful Degradation）
  - `#学校-要対応`・`#学校-ダイジェスト`・`#就活-要対応`・`#就活-ダイジェスト` 全4チャンネルの通知フォーマット（個別・ダイジェスト・件数サマリー）が仕様通りであることを確認する
  - _Requirements: 1.2, 1.4, 5.1, 5.2, 6.2, 6.3_

- [x] 4.2 Windowsタスクスケジューラへの登録と定期実行確認
  - タスクスケジューラを開き（`taskschd.msc`）、新しいタスクを作成する
  - トリガーを「毎日」「繰り返し間隔: 6時間」「無期限」に設定する
  - 操作を「プログラムの開始」に設定し、プログラムを `python`、引数を `run.py`、作業フォルダをプロジェクトパスに設定する
  - 「条件」で「コンピューターをAC電源で使用している場合のみ」のチェックを外す（バッテリー駆動でも実行するため）
  - 「今すぐ実行」でタスクを手動起動し、`logs/run.log` に実行開始ログが追記されることを確認する
  - 次の定期実行時刻まで待機し、自動実行でSlack通知が届くことを確認する
  - _Requirements: 6.1, 6.4_
