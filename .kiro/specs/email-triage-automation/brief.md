# Brief: email-triage-automation

## Problem
受信メールへの対応漏れや確認漏れが発生しやすく、重要なメールと不要なメールが混在しているため、優先度の判断に時間がかかっている。

## Current State
手動でGmailを確認し、返信・対応の判断を自分で行っている。自動分類・通知の仕組みはない。

## Desired Outcome
6時間ごとに自動でメールを取得・分類し、Slackに通知が届く状態。返信が必要なメールには下書きが添付され、すべてのメールを把握できる。

## Approach
Claude Code CLI（`claude -p`）をWindowsタスクスケジューラで6時間ごとに実行。Gmail MCPでメール取得、Claude本体がAI分類・下書き生成、Slack MCPで通知を送信。追加APIコストなし。

## Scope
- **In**:
  - Gmail MCPによる未処理メールの取得
  - Claudeによる3分類（返信必要・見るべき・スキップ）
  - 返信必要メールへの返信下書き自動生成
  - Slackへの通知（2チャンネル構成）
  - 処理済みメールの重複回避（Gmailラベルで管理）
  - Windowsタスクスケジューラへの登録手順
- **Out**:
  - 実際の返信送信（下書き止まり）
  - モバイル対応
  - 複数Gmailアカウント対応

## 分類ルール
| 分類 | 条件 |
|------|------|
| 返信必要 | 問い合わせ・依頼・確認要求・期限付き案件 |
| 見るべき | 社内共有・FYI・契約書・重要通知 |
| スキップ | 営業メール・メルマガ・自動通知（ただし件名一覧は通知） |

## Slack通知構成
- `#要対応-メール`: 返信必要メール（1件ずつ、下書き付き）
- `#メール-ダイジェスト`: 見るべき要約 + スキップ件名リスト

## Boundary Candidates
- メール取得・ラベル付け（Gmail MCP）
- AI判断・下書き生成（Claude本体）
- Slack通知フォーマット・送信（Slack MCP）
- スケジューラ設定（Windowsタスクスケジューラ）

## Out of Boundary
- 返信の自動送信
- カレンダー連携（別途検討）
- 他メールサービス対応

## Upstream / Downstream
- **Upstream**: Gmail MCP（認証済み）、Slack MCP（認証済み）、Claude Code CLI
- **Downstream**: 将来的なカレンダー自動登録・タスク管理連携

## Constraints
- Claude Code サブスクリプション以外の費用ゼロ
- Windows 11 環境
- `claude -p` の非インタラクティブ実行でMCPツールが利用可能であること
