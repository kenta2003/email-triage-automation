# email-triage-automation

複数の Gmail アカウントの受信メールを **Claude AI で自動分類**し、Slack に通知するパーソナル自動化システム。

> 「重要な連絡を見落とす」「返信タイミングを逃す」を防ぐために、自分用に設計・実装した。
> Windows タスクスケジューラで 6 時間ごとに無人実行。

---

## 🎯 解決した課題

複数の Gmail アカウントを行き来する運用では:

- 重要メールがメルマガに埋もれて見落としが発生する
- アカウントを開いて確認するコストがかかる
- 返信ドラフトを書き始めるまでに腰が重い

これを **「Slack を見るだけ」** に圧縮した。

## 🏗️ アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│  Windows Task Scheduler (every 6 hours)                     │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
        ┌────────────────────────────────────────┐
        │           run.py (Orchestrator)        │
        │   - Per-account graceful degradation   │
        │   - Structured logging                 │
        └──────┬──────────────┬──────────────────┘
               │              │
   ┌───────────▼──┐    ┌──────▼───────────┐
   │ sources/     │    │ processor.py     │
   │  gmail.py    │───▶│ - Batches up to  │
   │  - OAuth     │    │   50 emails      │
   │  - Label     │    │ - claude -p CLI  │
   │    dedup     │    │ - 3x retry +     │
   └──────────────┘    │   rule-based     │
                       │   fallback       │
                       └──────┬───────────┘
                              │
                       ┌──────▼───────────┐
                       │ notifiers/       │
                       │  slack.py        │
                       │  - 4 channels    │
                       │  - Reply drafts  │
                       └──────────────────┘
```

### 分類カテゴリ

| カテゴリ | 内容 | Slack 通知形式 |
|---------|------|---------------|
| 🔴 返信必要 | 個別の問い合わせ・期限付き案件 | 1 件ずつ個別通知（返信下書き付き） |
| 🟡 見るべき | 重要なお知らせ・FYI | ダイジェスト |
| ⚪ スキップ | メルマガ・自動通知 | 件名のみダイジェスト |

## ✨ 技術的な工夫

### 1. 追加 API コストゼロ
AI 分類部分を **Claude Code CLI (`claude -p`) のサブプロセス呼び出し**で実装。
Claude サブスクリプションさえあれば従量課金 API を一切使わずに済む。

### 2. Graceful Degradation
- アカウント単位の `try/except`：片方のアカウントが失敗しても他方は処理継続
- AI 分類失敗時：**キーワードベースのルール分類**にフォールバック（全件「見るべき」で埋めない）
- JSON パース失敗：最大 3 回リトライ → それでも失敗ならフォールバック

### 3. 拡張可能な設計
`BaseSource` / `BaseNotifier` の抽象基底クラスを定義。
将来 arXiv ソースや Discord 通知を追加する際、既存コードを変更せずに済む構造。

### 4. 重複処理の防止
Gmail のラベル機能（`Claude-Processed-*`）で処理済みメールを永続化。
2 回目以降の実行で同じメールが通知されない。

### 5. 仕様駆動開発
Kiro 方式の Spec-Driven Development（要件 → 設計 → タスク → 実装）で進めた。
仕様書は [`.kiro/specs/email-triage-automation/`](./.kiro/specs/email-triage-automation/) に格納。

## 📂 ディレクトリ構成

```
email-triage-automation/
├── run.py                     # オーケストレーター
├── config.py                  # アカウント・分類ルール設定
├── processor.py               # claude -p による AI 分類
├── sources/
│   ├── base.py                # 抽象基底クラス
│   └── gmail.py               # Gmail API クライアント
├── notifiers/
│   ├── base.py                # 抽象基底クラス
│   └── slack.py               # Slack Incoming Webhook
├── .kiro/specs/email-triage-automation/
│   ├── requirements.md        # EARS フォーマット要件定義
│   ├── design.md              # 技術設計
│   ├── tasks.md               # 実装タスク分解
│   └── spec.json              # 仕様メタデータ
├── credentials/               # OAuth クレデンシャル (git 管理外)
├── tokens/                    # OAuth トークン (git 管理外)
├── logs/                      # 実行ログ (git 管理外)
├── requirements.txt
├── .env.example
└── README.md
```

## 🛠️ セットアップ

### 前提
- Python 3.10+
- [Claude Code CLI](https://docs.claude.com/claude-code) インストール済み
- Gmail（OAuth 認証可能なアカウント）
- Slack ワークスペース（Incoming Webhook を作成可能）

### 手順

```bash
# 1. 依存関係インストール
pip install -r requirements.txt

# 2. 環境変数の設定
cp .env.example .env
# .env に Slack Webhook URL を 4 本記入

# 3. Google Cloud OAuth クライアント ID を作成し、
#    credentials/primary_credentials.json として配置
#    （複数アカウントなら secondary_credentials.json も）

# 4. 初回認証（ブラウザが開きトークンが tokens/ に保存される）
python run.py

# 5. Windows タスクスケジューラに 6 時間ごとの実行を登録
#    プログラム: python
#    引数:       run.py
#    開始場所:   <このフォルダの絶対パス>
```

## 🧰 技術スタック

| カテゴリ | 採用技術 | 選定理由 |
|----------|----------|----------|
| 言語 | Python 3.10+ | Gmail API SDK の充実、Windows との親和性 |
| AI | Claude Code CLI (`claude -p`) | サブスクリプション内で完結（API 課金不要） |
| メール | Gmail API v1 + OAuth 2.0 | 公式 SDK、ラベル機能で重複排除を完結 |
| 通知 | Slack Incoming Webhook | 認証フローが不要、4 チャンネル構成で文脈分離 |
| スケジューラ | Windows Task Scheduler | 追加ランタイム不要 |
| 設定 | `python-dotenv` + dataclass | 型付きの不変設定でテスタビリティ確保 |

## 🔒 セキュリティ

- OAuth クレデンシャル / トークン / `.env` は `.gitignore` で完全除外
- Slack Webhook URL は環境変数経由のみ
- 返信は**下書き生成のみ**（自動送信しない）

## 📄 ライセンス

MIT
