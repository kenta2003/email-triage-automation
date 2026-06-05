# Research & Design Decisions

---
**Purpose**: 技術調査の知見と設計判断の根拠を記録する。

---

## Summary
- **Feature**: `email-triage-automation`
- **Discovery Scope**: Complex Integration（新規自動化システム）
- **Key Findings**:
  - `claude -p` 非インタラクティブモードは claude.ai MCP（Gmail/Slack）に接続不可（設計上の制限、修正予定なし）
  - Gmail MCP は複数アカウント非対応、Google Workspace OAuthの永続化も非対応
  - 代替: Python（Gmail API + Slack Webhook）+ `claude -p`（AI処理のみ）で費用ゼロを維持可能
  - ユーザーが将来的に論文監視等の拡張を希望 → モジュラー構造（案B）で設計

## Research Log

### `claude -p` と claude.ai MCP の互換性
- **Context**: `claude -p` でGmail/Slack MCPを使った自動化を検討
- **Sources Consulted**:
  - GitHub Issue #37805: [BUG] claude -p non-interactive mode does not connect to claude.ai MCP servers
  - Claude Code CLI リファレンス
- **Findings**:
  - `-p` モードでは `cloudMcp` が強制的に空（`Promise.resolve({ clients: [], tools: [], commands: [] })`）になる
  - Anthropicが意図的な設計として Closed as not planned
  - ローカル stdio MCP（`--mcp-config` 指定）は利用可能
- **Implications**: Gmail/Slack の統合には claude.ai MCPではなく直接APIを使う必要がある

### Gmail MCP の制約
- **Sources**: GitHub Issue #27567（複数アカウント）, #35092（OAuth永続化）
- **Findings**:
  - 公式 Google Workspace MCP: 単一アカウントのみ
  - Google Workspace OAuthトークン: セッション間で永続化されない（既知バグ、未解決）
  - 利用可能ツール: `search_threads`, `get_thread`, `label_message`, `create_draft` 等10個
- **Implications**: Python + google-api-python-client でGmail APIを直接呼び出す方が安定

### Slack MCP の制約
- **Findings**:
  - `slack_send_message` は `channel_id`（チャンネル名不可）が必須
  - claude.ai MCPなのでclaude -p では利用不可
- **Implications**: Slack Incoming Webhook または Slack SDK を使う

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations |
|--------|-------------|-----------|---------------------|
| A: claude -p + MCP | claude -p でGmail/Slack MCPを直接操作 | シンプル | 非インタラクティブモードで動作不可（致命的） |
| B: Python monolith | 1ファイルのPythonスクリプト | すぐ書ける | 拡張時に複雑化、論文監視追加が困難 |
| C: Python modular + claude -p | sources/notifiers分離、AI処理はclaudeに委譲 | 拡張性高、費用ゼロ維持 | 初期設計がやや複雑 |

**選択: C（Python Modular + claude -p）**

## Design Decisions

### Decision: モジュラー構造（案B）の採用
- **Context**: ユーザーが論文監視など将来の拡張を明示的に希望
- **Alternatives Considered**:
  1. シンプル単一スクリプト — すぐ動くが拡張時に全書き直し
  2. モジュラー構造 — 初期コストはやや高いが拡張が容易
- **Selected Approach**: `BaseSource` / `BaseNotifier` の抽象基底クラスを定義し、Gmail・Slackはその実装として分離
- **Rationale**: ユーザーが論文監視等の追加を明示的に希望しており、拡張を見越した設計が適切
- **Trade-offs**: 初期ファイル数が増えるが、新しいSourceを追加する際に既存コードを変更不要
- **Follow-up**: 論文監視（arXiv等）は別スペックとして後から追加

### Decision: AI処理を `claude -p` サブプロセスに委譲
- **Context**: 追加費用ゼロの制約、かつ高精度な自然言語分類が必要
- **Selected Approach**: `subprocess.run(['claude', '-p', prompt])` でClaudeを呼び出し、テキスト出力をパース
- **Rationale**: Claude Codeサブスクリプションで賄える。別途Claude APIキーや費用が不要
- **Trade-offs**: subprocessオーバーヘッドあり（1メール約数秒）。メール件数が多い場合は処理時間が長くなる
- **Follow-up**: 1回の`claude -p`呼び出しで複数メールをバッチ処理することで最適化可能

### Decision: 処理済み状態管理をGmailラベルで行う
- **Context**: 重複処理防止のための状態管理が必要
- **Selected Approach**: Gmailラベル `Claude-Processed-Primary` / `Claude-Processed-Secondary` を付与
- **Rationale**: 外部DBやファイル不要。Gmail自体が状態を保持するため信頼性が高い
- **Trade-offs**: ラベルがGmail UIに表示されるが機能上は問題なし

### Decision: Slack通知にIncoming Webhookを使用
- **Context**: Slack MCPが非インタラクティブモードで使えない
- **Selected Approach**: Slack Incoming Webhook URL（チャンネルごとに1つ）を使用
- **Rationale**: 設定が簡単（URL1本）、費用ゼロ、追加ライブラリ不要（requests のみ）
- **Trade-offs**: チャンネルIDではなくWebhook URLで管理。URLが漏洩するとスパム送信リスクあり（.envで管理）

## Risks & Mitigations
- `claude -p` の出力フォーマットが安定しない → 出力フォーマットをプロンプトで厳密に指定（JSON形式）
- Gmail OAuth初回設定が複雑 → セットアップ手順書をタスクに含める
- Slack Webhook URLの漏洩 → `.env` ファイルで管理し `.gitignore` に追加
- Google Workspace（学校メール）のOAuth更新頻度 → refresh_tokenを保存し自動更新、失敗時はログ通知

## References
- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference)
- [GitHub Issue #37805 - claude -p と claude.ai MCP](https://github.com/anthropics/claude-code/issues/37805)
- [Google Gmail API Python Quickstart](https://developers.google.com/gmail/api/quickstart/python)
- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)
