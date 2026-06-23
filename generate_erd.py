#!/usr/bin/env python3
"""
ER図生成スクリプト
使い方: python generate_erd.py
出力:  docs/erd.html（GitHub Pages で閲覧可能）
"""

HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ITSMポータル ER図</title>
<style>
  body { margin: 0; padding: 24px; font-family: sans-serif; background: #f5f6fa; }
  h1 { font-size: 18px; color: #1a2340; margin-bottom: 4px; }
  p  { font-size: 13px; color: #8892a4; margin: 0 0 24px; }
  #erd { background: #fff; border-radius: 12px; padding: 24px; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
</style>
</head>
<body>
<h1>ITSMポータル — ER図（フェーズ1）</h1>
<p>department / user / incident / work_note の4テーブル構成</p>
<div id="erd"></div>
<script type="module">
import mermaid from 'https://esm.sh/mermaid@11/dist/mermaid.esm.min.mjs';
await document.fonts.ready;
mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  fontFamily: 'sans-serif',
  themeVariables: {
    fontSize: '13px',
    lineColor: '#73726c',
    textColor: '#3d3d3a',
  },
});
const { svg } = await mermaid.render('erd-svg', `erDiagram
  department {
    int department_id PK
    string name
    string code
  }
  service_catalog {
    int catalog_id PK
    string name
    string description
    string icon
    int is_active
  }
  assignment_group {
    int group_id PK
    string name
    int catalog_id FK
    string description
  }
  group_member {
    int group_id FK
    int user_id FK
    string role
  }
  user {
    int user_id PK
    string username
    string password_hash
    string full_name
    string email
    string role
    int department_id FK
  }
  incident {
    string incident_id PK
    string title
    string description
    string category
    string priority
    string impact
    string urgency
    string state
    int service_catalog_id FK
    int assigned_group_id FK
    int caller_user_id FK
    int assigned_user_id FK
    int department_id FK
    string resolution_code
    string resolution_notes
    datetime opened_at
    datetime resolved_at
    datetime closed_at
    datetime due_date
  }
  work_note {
    int note_id PK
    string ticket_type
    string ticket_id
    int author_user_id FK
    string note_type
    string body
    datetime created_at
  }
  department ||--o{ user : "所属"
  department ||--o{ incident : "発生元"
  service_catalog ||--|| assignment_group : "窓口→グループ"
  service_catalog ||--o{ incident : "問い合わせ先"
  assignment_group ||--o{ group_member : "メンバー構成"
  user ||--o{ group_member : "グループ所属"
  assignment_group ||--o{ incident : "自動ルーティング先"
  user ||--o{ incident : "報告者(caller)"
  user ||--o{ incident : "個人担当者(assigned)"
  user ||--o{ work_note : "投稿者"
  incident ||--o{ work_note : "紐付き"
`);
document.getElementById('erd').innerHTML = svg;
</script>
</body>
</html>
"""

import os

os.makedirs("docs", exist_ok=True)
with open("docs/erd.html", "w", encoding="utf-8") as f:
    f.write(HTML)

print("生成完了: docs/erd.html")
