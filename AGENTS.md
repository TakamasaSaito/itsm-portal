# ITSMポータル — Codex 実装指示書

## プロジェクト概要

ServiceNow ITSM（IT Service Management）の主要機能を再現するWebアプリ。
SPMポータル（apm-portal）と同じ技術スタック・UIデザインで、別リポジトリとして独立作成する。
目的：社内プレゼン・経営層向けデモ。

---

## 技術スタック

| 項目 | 内容 |
|------|------|
| バックエンド | FastAPI + SQLite |
| フロントエンド | 単一HTML（index.html） |
| 認証 | JWT（SPMポータルのauth.pyを流用） |
| デプロイ | Railway（GitHubへのpushで自動デプロイ） |
| 外部ライブラリ | Chart.js（CDN） |
| 開発環境 | WSL/Ubuntu |

### リポジトリ情報

| 項目 | 内容 |
|------|------|
| リポジトリ | TakamasaSaito/itsm-portal |
| 参照元 | TakamasaSaito/apm-portal（設計・コード流用元） |

### Codex起動コマンド

```bash
cd ~/itsm-portal && git pull && Codex --dangerously-skip-permissions
```

---

## フェーズ1（最初に実装する）

### 1. インシデント管理（最優先）

- チケット一覧（10件/ページ、ページネーションは最初から実装）
- チケット詳細（3タブ：Notes / Related Records / Resolution Information）
- 新規作成フォーム
- 担当者割り当て・グループ変更
- 解決・クローズ操作
- ワークノート（コメント投稿・履歴表示）
- ステージバー表示：New → Assigned → In Progress → Resolved → Closed

### 2. ITSMダッシュボード

- KPIカード：オープン件数 / 重大件数 / 未解決問題数 / 本日のサービス要求数
- 優先度別棒グラフ（Chart.js）
- 週次トレンド折れ線グラフ（Chart.js）

### フェーズ2（後回し・今は触らない）

- 問題管理（PRB）
- 変更管理（CHG）
- サービス要求（SRTASK）

---

## DBテーブル設計

### チケットID形式

| 種別 | 形式 | 例 |
|------|------|----|
| インシデント | INC0001001 | INC0001001 |
| 問題 | PRB0001001 | PRB0001001 |
| 変更 | CHG0001001 | CHG0001001 |
| サービス要求 | SRTASK0001001 | SRTASK0001001 |

### フェーズ1で作成するテーブル

```sql
-- 部署（10件）
CREATE TABLE department (
  department_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL,
  code            TEXT NOT NULL
);

-- サービスカタログ（窓口）（8〜10件）
-- 例：コミュニケーション基盤、人事システム、経理システム、情報セキュリティ 等
CREATE TABLE service_catalog (
  catalog_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL,     -- 例: 情報セキュリティ
  description     TEXT,
  icon            TEXT,              -- 例: 🔐（表示用）
  is_active       INTEGER DEFAULT 1
);

-- 担当グループ（8〜10件）
-- サービスカタログと1対1で対応させる（1窓口=1グループ）
CREATE TABLE assignment_group (
  group_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL,     -- 例: 情報セキュリティチーム
  catalog_id      INTEGER REFERENCES service_catalog(catalog_id),
  description     TEXT
);

-- グループメンバー（グループ ↔ ユーザーの多対多）
CREATE TABLE group_member (
  group_id        INTEGER REFERENCES assignment_group(group_id),
  user_id         INTEGER REFERENCES user(user_id),
  role            TEXT DEFAULT 'member',  -- member / leader
  PRIMARY KEY (group_id, user_id)
);

-- ユーザー（20件）
CREATE TABLE user (
  user_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  username        TEXT UNIQUE NOT NULL,
  password_hash   TEXT NOT NULL,
  full_name       TEXT NOT NULL,
  email           TEXT,
  role            TEXT DEFAULT 'user',  -- admin / user
  department_id   INTEGER REFERENCES department(department_id)
);

-- インシデント（30件のサンプルデータ）
CREATE TABLE incident (
  incident_id         TEXT PRIMARY KEY,           -- INC0001001形式
  short_description   TEXT NOT NULL,              -- 件名（一覧表示用）
  description         TEXT,                       -- 詳細説明
  service_catalog_id  INTEGER REFERENCES service_catalog(catalog_id),  -- ★どの窓口への問い合わせか
  category            TEXT,                       -- inquiry/software/hardware/network/security
  subcategory         TEXT,                       -- カテゴリ内サブ分類
  channel             TEXT DEFAULT 'portal',      -- portal/email/phone/walk-in
  priority            TEXT,                       -- 自動計算：1-critical/2-high/3-moderate/4-low/5-planning
  impact              TEXT,                       -- 1-enterprise/2-site/3-department/4-user（3-Low等）
  urgency             TEXT,                       -- 1-critical/2-high/3-medium/4-low（2-Medium等）
  state               TEXT DEFAULT 'new',         -- new/assigned/in_progress/on_hold/resolved/closed
  caller_user_id      INTEGER REFERENCES user(user_id),               -- 報告者
  assigned_group_id   INTEGER REFERENCES assignment_group(group_id),  -- ★自動ルーティング先グループ
  assigned_user_id    INTEGER REFERENCES user(user_id),               -- ★グループ内の個人担当者
  department_id       INTEGER REFERENCES department(department_id),
  resolution_code     TEXT,
  resolution_notes    TEXT,
  opened_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
  resolved_at         DATETIME,
  closed_at           DATETIME,
  due_date            DATETIME
);

-- Priority自動計算ロジック（APIで実装）
-- Impact(1-4) × Urgency(1-4) のマトリクスでpriorityを決定
-- 例：Impact=1(enterprise) × Urgency=1(critical) → priority=1-critical
-- 例：Impact=3(department) × Urgency=2(high)     → priority=3-moderate

-- ワークノート（40件）
CREATE TABLE work_note (
  note_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_type     TEXT NOT NULL,    -- incident/problem/change
  ticket_id       TEXT NOT NULL,
  author_user_id  INTEGER REFERENCES user(user_id),
  note_type       TEXT DEFAULT 'work_note',  -- work_note / public_comment
  body            TEXT NOT NULL,
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### リレーションシップ

| From | To | カーディナリティ | 説明 |
|------|----|----------------|------|
| department | user | 1対多 | 所属部署 |
| department | incident | 1対多 | 発生元部署 |
| service_catalog | assignment_group | 1対1 | 窓口ごとに担当グループが1つ対応 |
| service_catalog | incident | 1対多 | どの窓口への問い合わせか |
| assignment_group | group_member | 1対多 | グループメンバー構成 |
| user | group_member | 1対多 | ユーザーが複数グループに所属可能 |
| assignment_group | incident | 1対多 | 自動ルーティング先グループ |
| user | incident | 1対多 | 報告者（caller_user_id） |
| user | incident | 1対多 | 個人担当者（assigned_user_id） |
| user | work_note | 1対多 | 投稿者 |
| incident | work_note | 1対多 | ticket_id（TEXT）で疎結合 ← フェーズ2で問題・変更にも流用 |

### サービスカタログ（窓口）サンプル 10件

ServiceNowのサービスポータルにおける「カタログカテゴリ」に相当。
利用者はポータルからカタログを選んでインシデントを起票する。
どのカタログから来たかによって `assigned_group_id` が自動セットされる。

| catalog_id | name | icon | 対応グループ |
|-----------|------|------|------------|
| 1 | 共通サービス・全般 | 🏢 | サービスデスク |
| 2 | コミュニケーション基盤 | 💬 | コミュニケーション基盤チーム |
| 3 | ネットワーク・インフラ | 🌐 | ITインフラチーム |
| 4 | 人事システム | 👥 | 人事システムチーム |
| 5 | 経理・財務システム | 💰 | 経理システムチーム |
| 6 | 情報セキュリティ | 🔐 | 情報セキュリティチーム |
| 7 | 営業支援システム | 📊 | 営業システムチーム |
| 8 | 調達・購買システム | 📦 | 調達システムチーム |
| 9 | PC・ハードウェア | 🖥️ | ハードウェアサポートチーム |
| 10 | アカウント・アクセス管理 | 🔑 | IT管理チーム |

### 自動ルーティング設計（重要）

ServiceNowのポータルと同じ流れを再現する：

```
【利用者側（ポータル）】
サービスポータルトップ（"どのようなご用件ですか？"）
    ↓ カタログ一覧から窓口を選ぶ（カードグリッド表示）
    ↓ 「インシデントを起票する」ボタンを押す
インシデント起票フォーム（シンプル：Urgency + 説明 のみ）
    ↓ Submit
マイリクエスト詳細（チケットID・ステータス + Activityコメント欄）

【自動処理】
service_catalog_id → assigned_group_id を自動セット
（カタログと担当グループは1対1対応）

【担当者側（管理画面）】
インシデント一覧（Number/Opened/Short description/Caller/Priority/State/Category/Assignment group/Assigned to）
    ↓ 個人担当者をグループ内からアサイン（assigned_user_id）
    ↓ Work Notesでコミュニケーション
    ↓ 解決・クローズ
```

### インシデントのcategoryカラム（ServiceNow標準に合わせる）

起票フォームではなく**管理者が分類するカラム**として保持する。
利用者の起票時は不要（Urgency＋説明のみ）。

```
category の値：
  inquiry   → Inquiry / Help（問い合わせ）
  software  → Software
  hardware  → Hardware
  network   → Network
  security  → Security
```

### サンプルデータ方針

- テーブル投入順序：department → service_catalog → assignment_group → user → group_member → incident → work_note
- インシデントはstate全種別・priority全種別・service_catalog全件が含まれるよう分散させる
- ワークノートは各インシデントに1〜3件紐付ける
- userは20件（admin1名・各グループにleader1名＋member1〜2名）

### ER図管理

ER図は `generate_erd.py` で自動生成し、`docs/erd.html` に出力する。
テーブル変更時は必ずこのスクリプトを更新・再実行してからコミットすること。

```bash
# ER図を再生成してコミット
python generate_erd.py
git add docs/erd.html && git commit -m "docs: ER図を更新" && git push
```

GitHub Pages（Settings → Pages → `docs/` フォルダ）を有効にすると以下のURLで常に最新ER図を確認できる：
`https://takamasasaito.github.io/itsm-portal/erd.html`

---

## UIデザイン方針

SPMポータルのデザインを**完全踏襲**する。

### 画面構成（2つのビュー）

このアプリは**利用者ビュー（ポータル）**と**管理者ビュー（管理画面）**の2面構成とする。
ヘッダーの「ポータル / 管理画面」トグルで切替える（JWT roleで制御）。

#### 利用者ビュー（ポータル側）

```
① サービスポータルトップ
   ─────────────────────────────────
   「どのようなご用件ですか？」（検索バー）
   [📋 リクエスト申請] [📚 ナレッジ] [🆘 ヘルプ]
   ─────────────────────────────────
   カタログ一覧（カードグリッド 3列）
     💬 コミュニケーション基盤
     🌐 ネットワーク・インフラ
     👥 人事システム  ...（10件）
   ─────────────────────────────────
   マイ オープンインシデント一覧（下部ウィジェット）

② カタログ選択後 → インシデント起票フォーム（シンプル）
   ─────────────────────────────────
   [Home > サービスカタログ > コミュニケーション基盤]
   タイトル：件名（自由入力）
   Urgency：1-High / 2-Medium / 3-Low
   説明：テキストエリア
   [下書き保存]  [送信]

③ マイリクエスト詳細
   ─────────────────────────────────
   INC0001001  [New バッジ]  作成日時
   Caller / Urgency
   ─────────────────────────────────
   [Activity タブ] [Attachments タブ]
   コメント入力欄 + [Post]
   コメント履歴（アバター・投稿者名・時刻）
```

#### 管理者ビュー（管理画面側）

```
サイドバー＋ヘッダーのレイアウト（SPMポータルと同じ）
```

### サイドバーメニュー構成（管理者ビュー）

```
📊 ITSMダッシュボード     ← 最上位・単独

--- インシデント管理 ---
  🚨 インシデント一覧
  ➕ 新規インシデント

--- 問題管理 ---（フェーズ2・表示だけしてグレーアウト可）
  🔍 問題一覧
  ➕ 新規問題登録

--- 変更管理 ---（同上）
  🔄 変更要求一覧
  ➕ 新規変更要求

--- サービス要求 ---（同上）
  📋 サービス要求一覧
  ➕ 新規サービス要求

--- 管理 ---
  ✅ 承認一覧（adminのみ表示）
```

### ステータスバッジ（SPMポータルのsbadgeスタイル流用）

```
new          → sbadge-draft（グレー）
assigned     → sbadge-submitted（青）
in_progress  → sbadge-submitted（青）
on_hold      → sbadge-project-pending（黄）
resolved     → sbadge-approved（緑）
closed       → sbadge-completed（緑）
cancelled    → sbadge-rejected（赤）
```

### ステージバー（シェブロン型・SPMポータルの`.stage-chevron-bar`流用）

```
New → Assigned → In Progress → Resolved → Closed
```

### インシデント詳細画面のフィールド構成（ServiceNow標準に準拠）

2カラムレイアウト（左：基本情報、右：ステータス・担当情報）

```
左カラム                         右カラム
─────────────────────────────────────────────────────
Number（読取専用）               Channel
Caller（報告者）★必須            State
Category                        Impact
Subcategory                     Urgency
Service                         Priority（Impact×Urgencyから自動計算・読取専用）
Service offering                Assignment group（グループ）
Configuration item              Assigned to（個人担当者）
Short description ★必須
Description（テキストエリア）
─────────────────────────────────────────────────────
```

### インシデント詳細の3タブ構成（ServiceNow標準に準拠）

```
[Notes] [Related Records] [Resolution Information]
```

#### Notesタブの構成（重要）

```
Watch list          |  Work notes list
────────────────────────────────────────────
Work notes テキストエリア（内部メモ）
                      □ Comments (Customer visible)  [Post]
────────────────────────────────────────────
Activities（履歴一覧）
  ・System Administrator  Work notes • 2018-12-12
    Changed the priority of the Incident
  ・System Administrator  Field changes • 2018-08-30
    Impact: 3 - Low  ...
```

**Work notesの2種類（デモの核心機能）：**

| 種別 | 表示先 | 用途 |
|------|--------|------|
| Work notes（チェックなし） | 担当者側のみ（内部メモ） | 対応メモ・引継ぎ |
| Comments（Customer visible チェックあり） | 申請者にも見える | 進捗連絡・回答 |

→ `work_note` テーブルの `note_type` カラムで管理：
  - `work_note`：内部メモ
  - `public_comment`：顧客可視コメント

---

## 認証設計

SPMポータルの`auth.py`をそのままコピーして流用する。

| アカウント | パスワード | 役割 |
|-----------|-----------|------|
| admin | admin | 事務局（全機能アクセス可） |
| user | user | 一般ユーザー |

---

## コーディング規約（iOS Safari対応必須）

以下は**絶対に使用禁止**：

- テンプレートリテラル（バッククォート）→ 文字列結合（`+`）で代替
- `...` スプレッド構文（`Math.max(...arr)` 等）→ `apply(null, arr)` で代替
- 8桁16進数カラーコード（`#RRGGBBAA`）→ `rgba()` で代替
- `confirm()` / `alert()` → カスタムモーダルで代替

---

## ファイル構成

```
itsm-portal/
├── main.py                  ← FastAPIエントリーポイント
├── auth.py                  ← JWT認証（apm-portalからコピー）
├── database.py              ← SQLite接続・初期化
├── models.py                ← Pydanticモデル
├── routers/
│   ├── incidents.py         ← インシデントCRUD API
│   ├── portal.py            ← 利用者ポータルAPI（カタログ一覧・起票・マイリクエスト）
│   └── dashboard.py         ← ダッシュボードAPI
├── static/
│   └── index.html           ← フロントエンド（単一ファイル）
├── requirements.txt
├── Procfile                 ← Railway用（web: uvicorn main:app ...）
├── generate_erd.py          ← ER図HTML生成スクリプト
├── docs/
│   └── erd.html             ← 自動生成ER図（GitHub Pages公開）
└── AGENTS.md                ← この指示書
```

---

## Codexへの指示のコツ（重要）

1. **1タスク1セッション**：新規チャットで1つの機能に絞って指示する
2. **関数名・行番号を明示**：「〇〇関数を修正して」ではなく具体的に
3. **ページネーションは最初から実装**：後から追加すると漏れが出やすい（10件/ページ固定）
4. **「変更しないこと」を明記**：既存機能を壊さないよう明示する
5. **セッション上限に注意**：長時間作業でエラーが出たら新規チャットで再開

---

## 開発ステップ（推奨順序）

### Step 1：プロジェクトセットアップ
```bash
cd ~
git clone https://github.com/TakamasaSaito/itsm-portal.git
cd itsm-portal
# apm-portalからauth.py・requirements.txt・Procfileをコピー
```

### Step 2：DB・サンプルデータ作成
- `database.py` でテーブル作成
- サンプルデータ投入（department 10件・service_catalog 10件・assignment_group 10件・user 20件・group_member 約25件・incident 30件・work_note 40件）

### Step 3：バックエンドAPI
- `routers/incidents.py`：一覧・詳細・作成・更新API
- `routers/dashboard.py`：KPI・グラフデータAPI

### Step 4：フロントエンド
- `index.html`：サイドバー＋ヘッダーのベースレイアウト（SPMポータルから流用）
- 【管理者ビュー】ダッシュボード画面
- 【管理者ビュー】インシデント一覧（ページネーション込み・10件/ページ）
- 【管理者ビュー】インシデント詳細（3タブ：Notes / Related Records / Resolution Information）
- 【利用者ビュー】サービスポータルトップ（カタログカードグリッド）
- 【利用者ビュー】インシデント起票フォーム（Urgency＋説明のみ）
- 【利用者ビュー】マイリクエスト詳細（Activity・コメント）

### Step 5：Railway デプロイ
```bash
git add . && git commit -m "feat: phase1 initial" && git push
```

---

## 将来統合イメージ（参考）

```
共通ヘッダーに横断ナビ：[SPMポータル] [ITSMポータル]

連携フロー（CSDMベース）：
インシデント多発 → 問題登録 → 変更要求 → デマンド昇格（SPMポータル）
```

---

## 統合を見越した設計原則（重要）

統合方針はまだ未確定だが、**後からどちらの方向にも対応できる設計**にしておく。

| 原則 | 理由 |
|------|------|
| userテーブルのカラム構成をSPMポータルと同じにする | 統合時のマイグレーションを容易にする |
| JWT認証のsecretキーは環境変数（`SECRET_KEY`）で管理 | 将来の共通化・Railway環境変数で切替可能にする |
| APIのURLプレフィックスは `/api/itsm/` に統一 | 将来同一アプリに同居させてもパスが衝突しない |
| 共通ヘッダーのナビリンクを最初からHTMLに組み込む | リンク先はSPMポータルのURL（`https://web-production-d5d824.up.railway.app`） |
