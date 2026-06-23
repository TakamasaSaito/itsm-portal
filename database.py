import aiosqlite
import os
from passlib.context import CryptContext

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "itsm.db")
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


def calc_priority(impact: str, urgency: str) -> str:
    matrix = {
        ("1-enterprise", "1-critical"): "1-critical",
        ("1-enterprise", "2-high"):     "1-critical",
        ("1-enterprise", "3-medium"):   "2-high",
        ("1-enterprise", "4-low"):      "2-high",
        ("2-site",       "1-critical"): "1-critical",
        ("2-site",       "2-high"):     "2-high",
        ("2-site",       "3-medium"):   "3-moderate",
        ("2-site",       "4-low"):      "3-moderate",
        ("3-department", "1-critical"): "2-high",
        ("3-department", "2-high"):     "3-moderate",
        ("3-department", "3-medium"):   "3-moderate",
        ("3-department", "4-low"):      "4-low",
        ("4-user",       "1-critical"): "3-moderate",
        ("4-user",       "2-high"):     "3-moderate",
        ("4-user",       "3-medium"):   "4-low",
        ("4-user",       "4-low"):      "5-planning",
    }
    return matrix.get((impact, urgency), "3-moderate")


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS department (
    department_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    code            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS service_catalog (
    catalog_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT,
    icon            TEXT,
    is_active       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS assignment_group (
    group_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    catalog_id      INTEGER REFERENCES service_catalog(catalog_id),
    description     TEXT
);

CREATE TABLE IF NOT EXISTS user (
    user_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    email           TEXT,
    role            TEXT DEFAULT 'user',
    department_id   INTEGER REFERENCES department(department_id)
);

CREATE TABLE IF NOT EXISTS group_member (
    group_id        INTEGER REFERENCES assignment_group(group_id),
    user_id         INTEGER REFERENCES user(user_id),
    role            TEXT DEFAULT 'member',
    PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS incident (
    incident_id         TEXT PRIMARY KEY,
    short_description   TEXT NOT NULL,
    description         TEXT,
    service_catalog_id  INTEGER REFERENCES service_catalog(catalog_id),
    category            TEXT,
    subcategory         TEXT,
    channel             TEXT DEFAULT 'portal',
    priority            TEXT,
    impact              TEXT,
    urgency             TEXT,
    state               TEXT DEFAULT 'new',
    caller_user_id      INTEGER REFERENCES user(user_id),
    assigned_group_id   INTEGER REFERENCES assignment_group(group_id),
    assigned_user_id    INTEGER REFERENCES user(user_id),
    department_id       INTEGER REFERENCES department(department_id),
    resolution_code     TEXT,
    resolution_notes    TEXT,
    opened_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at         DATETIME,
    closed_at           DATETIME,
    due_date            DATETIME
);

CREATE TABLE IF NOT EXISTS work_note (
    note_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_type     TEXT NOT NULL,
    ticket_id       TEXT NOT NULL,
    author_user_id  INTEGER REFERENCES user(user_id),
    note_type       TEXT DEFAULT 'work_note',
    body            TEXT NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
        """)
        await db.commit()
        await _seed_data(db)


async def _seed_data(db):
    async with db.execute("SELECT COUNT(*) FROM department") as cur:
        if (await cur.fetchone())[0] > 0:
            return

    # ── department (10件) ────────────────────────────────────
    await db.executemany(
        "INSERT INTO department (name, code) VALUES (?, ?)",
        [
            ("IT部門",        "DEPT-IT"),
            ("営業部",        "DEPT-SALES"),
            ("人事部",        "DEPT-HR"),
            ("経理部",        "DEPT-FIN"),
            ("総務部",        "DEPT-GA"),
            ("調達部",        "DEPT-PROC"),
            ("マーケティング部", "DEPT-MKT"),
            ("物流部",        "DEPT-LOG"),
            ("法務部",        "DEPT-LEGAL"),
            ("経営企画部",    "DEPT-CORP"),
        ],
    )

    # ── service_catalog (10件) ───────────────────────────────
    await db.executemany(
        "INSERT INTO service_catalog (name, description, icon) VALUES (?, ?, ?)",
        [
            ("共通サービス・全般",     "PCやシステム全般に関するお問い合わせ",               "🏢"),
            ("コミュニケーション基盤", "メール・Teams・チャットツールに関するお問い合わせ",   "💬"),
            ("ネットワーク・インフラ", "ネットワーク接続・インフラ障害に関するお問い合わせ", "🌐"),
            ("人事システム",           "勤怠・給与・人事評価システムに関するお問い合わせ",   "👥"),
            ("経理・財務システム",     "会計・経費精算・財務システムに関するお問い合わせ",   "💰"),
            ("情報セキュリティ",       "セキュリティインシデント・情報漏洩に関するお問い合わせ", "🔐"),
            ("営業支援システム",       "CRM・SFAシステムに関するお問い合わせ",               "📊"),
            ("調達・購買システム",     "発注・購買システムに関するお問い合わせ",               "📦"),
            ("PC・ハードウェア",       "PC・プリンター・周辺機器に関するお問い合わせ",       "🖥️"),
            ("アカウント・アクセス管理", "IDアカウント・パスワードリセットに関するお問い合わせ", "🔑"),
        ],
    )

    # ── assignment_group (10件) ──────────────────────────────
    # catalog_id 1-10 に対し 1:1 で対応
    await db.executemany(
        "INSERT INTO assignment_group (name, catalog_id, description) VALUES (?, ?, ?)",
        [
            ("サービスデスク",             1, "共通お問い合わせ窓口・一次対応"),
            ("コミュニケーション基盤チーム", 2, "メール・ビデオ会議・チャット基盤の管理"),
            ("ITインフラチーム",            3, "ネットワーク・サーバー・クラウドインフラの管理"),
            ("人事システムチーム",          4, "人事・勤怠・給与システムの管理"),
            ("経理システムチーム",          5, "会計・経費精算システムの管理"),
            ("情報セキュリティチーム",      6, "セキュリティインシデント対応・ポリシー管理"),
            ("営業システムチーム",          7, "CRM・SFAシステムの管理"),
            ("調達システムチーム",          8, "購買・調達システムの管理"),
            ("ハードウェアサポートチーム",  9, "PC・プリンター・周辺機器のサポート"),
            ("IT管理チーム",               10, "アカウント・権限管理"),
        ],
    )

    # ── user (20件) ─────────────────────────────────────────
    # 挿入順に user_id が 1-20 になる
    # user_id=1: admin, user_id=2: user, user_id=3-12: グループリーダー, user_id=13-20: メンバー
    raw_users = [
        ("admin",              "admin",   "管理者 太郎",   "admin@example.com",      "admin", 1),
        ("user",               "user",    "一般 次郎",     "user@example.com",        "user",  2),
        ("yamada.kenji",       "pass123", "山田 健二",     "yamada.k@example.com",    "user",  1),
        ("tanaka.yuki",        "pass123", "田中 雪",       "tanaka.y@example.com",    "user",  1),
        ("suzuki.hiroshi",     "pass123", "鈴木 浩",       "suzuki.h@example.com",    "user",  1),
        ("sato.emi",           "pass123", "佐藤 恵美",     "sato.e@example.com",      "user",  1),
        ("ito.masato",         "pass123", "伊藤 雅人",     "ito.m@example.com",       "user",  1),
        ("watanabe.jun",       "pass123", "渡辺 純",       "watanabe.j@example.com",  "user",  1),
        ("nakamura.ryota",     "pass123", "中村 亮太",     "nakamura.r@example.com",  "user",  1),
        ("kobayashi.ai",       "pass123", "小林 愛",       "kobayashi.a@example.com", "user",  1),
        ("kato.shinji",        "pass123", "加藤 信二",     "kato.s@example.com",      "user",  1),
        ("yoshida.mika",       "pass123", "吉田 美香",     "yoshida.m@example.com",   "user",  1),
        ("ogawa.daisuke",      "pass123", "小川 大輔",     "ogawa.d@example.com",     "user",  1),
        ("hayashi.noriko",     "pass123", "林 典子",       "hayashi.n@example.com",   "user",  1),
        ("shimizu.takashi",    "pass123", "清水 隆",       "shimizu.t@example.com",   "user",  1),
        ("inoue.yoko",         "pass123", "井上 洋子",     "inoue.y@example.com",     "user",  1),
        ("matsumoto.ken",      "pass123", "松本 健",       "matsumoto.k@example.com", "user",  1),
        ("kimura.sachiko",     "pass123", "木村 幸子",     "kimura.s@example.com",    "user",  1),
        ("nakano.takeshi",     "pass123", "中野 武",       "nakano.t@example.com",    "user",  3),
        ("fujita.misaki",      "pass123", "藤田 美咲",     "fujita.m@example.com",    "user",  4),
    ]
    users_to_insert = [
        (u, _pwd.hash(p), fn, em, r, d) for u, p, fn, em, r, d in raw_users
    ]
    await db.executemany(
        "INSERT INTO user (username, password_hash, full_name, email, role, department_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        users_to_insert,
    )

    # ── group_member (25件) ──────────────────────────────────
    # user_id対応: 3=yamada(G1L), 4=tanaka(G2L), 5=suzuki(G3L), 6=sato(G4L), 7=ito(G5L)
    #              8=watanabe(G6L), 9=nakamura(G7L), 10=kobayashi(G8L), 11=kato(G9L), 12=yoshida(G10L)
    #              13=ogawa, 14=hayashi, 15=shimizu, 16=inoue, 17=matsumoto, 18=kimura
    await db.executemany(
        "INSERT INTO group_member (group_id, user_id, role) VALUES (?, ?, ?)",
        [
            (1, 3,  "leader"), (1, 13, "member"), (1, 14, "member"),   # サービスデスク
            (2, 4,  "leader"), (2, 15, "member"), (2, 18, "member"),   # コミュニケーション基盤
            (3, 5,  "leader"), (3, 16, "member"), (3, 17, "member"),   # ITインフラ
            (4, 6,  "leader"), (4, 13, "member"), (4, 15, "member"),   # 人事システム
            (5, 7,  "leader"), (5, 14, "member"),                       # 経理システム
            (6, 8,  "leader"), (6, 15, "member"), (6, 17, "member"),   # 情報セキュリティ
            (7, 9,  "leader"), (7, 16, "member"),                       # 営業システム
            (8, 10, "leader"), (8, 17, "member"),                       # 調達システム
            (9, 11, "leader"), (9, 18, "member"),                       # ハードウェアサポート
            (10, 12, "leader"), (10, 13, "member"),                     # IT管理
        ],
    )

    # ── incident (30件) ──────────────────────────────────────
    # フィールド順: incident_id, short_description, description,
    #   catalog_id, category, subcategory, channel,
    #   impact, urgency, state,
    #   caller_user_id, group_id, assigned_user_id, dept_id,
    #   resolution_code, resolution_notes,
    #   opened_at, resolved_at, closed_at, due_date
    inc_rows = [
        # ── catalog=1 共通サービス・全般 (group=1 サービスデスク) ──────────
        ("INC0001001", "社内ポータルへのアクセスが遅い",
         "社内ポータルサイトへのアクセスが非常に遅く、ページ読み込みに10秒以上かかっています。業務に支障が出ています。",
         1, "inquiry", "performance", "portal",
         "3-department", "2-high", "new",
         2, 1, None, 2, None, None,
         "2026-06-20 09:00:00", None, None, "2026-06-23 09:00:00"),

        ("INC0001002", "共有フォルダにアクセスできない",
         "部門共有フォルダ（\\\\fileserver\\sales）へのアクセスが全社員できない状態です。至急対応をお願いします。",
         1, "inquiry", "file_access", "email",
         "2-site", "1-critical", "assigned",
         2, 1, 3, 2, None, None,
         "2026-06-15 10:30:00", None, None, "2026-06-15 14:30:00"),

        ("INC0001003", "プリンターから印刷できない",
         "3Fの複合機（MFP-301）から印刷ジョブが送れない状態が昨日から続いています。",
         1, "inquiry", "printer", "portal",
         "3-department", "3-medium", "in_progress",
         19, 1, 13, 3, None, None,
         "2026-06-10 14:00:00", None, None, "2026-06-13 14:00:00"),

        # ── catalog=2 コミュニケーション基盤 (group=2) ──────────────────
        ("INC0001004", "Teamsの通話品質が悪い",
         "Teams会議中に音声が途切れることが多く、リモート会議に支障が出ています。",
         2, "software", "teams", "portal",
         "4-user", "3-medium", "new",
         2, 2, None, 2, None, None,
         "2026-06-21 11:00:00", None, None, "2026-06-24 11:00:00"),

        ("INC0001005", "メールサーバー全社停止",
         "全社員のメール送受信が停止しています。Exchange Onlineへの接続ができない状態です。緊急対応を依頼します。",
         2, "software", "email", "phone",
         "1-enterprise", "1-critical", "assigned",
         2, 2, 4, 2, None, None,
         "2026-06-18 08:00:00", None, None, "2026-06-18 10:00:00"),

        ("INC0001006", "Teams認証エラーが発生している",
         "一部部門でTeamsへのサインインができないエラーが発生しています。エラーコード：AADSTS70011",
         2, "software", "teams", "portal",
         "3-department", "2-high", "in_progress",
         20, 2, 15, 4, None, None,
         "2026-06-12 13:00:00", None, None, "2026-06-15 13:00:00"),

        # ── catalog=3 ネットワーク・インフラ (group=3) ──────────────────
        ("INC0001007", "全社VPN接続が不安定",
         "在宅勤務者全員からVPN接続が頻繁に切断されるとの報告があります。接続成功率が30%以下になっています。",
         3, "network", "vpn", "portal",
         "1-enterprise", "3-medium", "new",
         2, 3, None, 2, None, None,
         "2026-06-22 09:30:00", None, None, "2026-06-25 09:30:00"),

        ("INC0001008", "本社ビルのネットワーク速度が低下",
         "本社2Fおよび3Fのネットワーク速度が通常の10%以下に低下しています。スイッチのポートエラーが疑われます。",
         3, "network", "lan", "walk-in",
         "2-site", "2-high", "assigned",
         19, 3, 5, 3, None, None,
         "2026-06-17 15:00:00", None, None, "2026-06-18 15:00:00"),

        ("INC0001009", "特定PCがWi-Fiに接続できない",
         "経理部のPC（PC-FIN-042）がWi-Fiネットワークに接続できません。他の端末は正常に接続できています。",
         3, "network", "wifi", "portal",
         "3-department", "4-low", "in_progress",
         20, 3, 16, 4, None, None,
         "2026-06-05 16:00:00", None, None, "2026-06-12 16:00:00"),

        # ── catalog=4 人事システム (group=4) ────────────────────────────
        ("INC0001010", "勤怠入力フォームのUIが崩れている",
         "勤怠管理システムのUI表示がChromeで崩れています。Edgeでは正常表示です。",
         4, "software", "ui", "portal",
         "4-user", "4-low", "new",
         19, 4, None, 3, None, None,
         "2026-06-23 10:00:00", None, None, "2026-06-30 10:00:00"),

        ("INC0001011", "人事評価システムで評価が保存されない",
         "人事評価画面で「保存」ボタンを押しても保存されず、再度開くと入力内容が消えています。",
         4, "software", "hr_eval", "portal",
         "3-department", "3-medium", "assigned",
         19, 4, 6, 3, None, None,
         "2026-06-19 11:00:00", None, None, "2026-06-22 11:00:00"),

        ("INC0001012", "給与明細PDFがダウンロードできない",
         "給与明細画面でPDFダウンロードボタンを押すとエラーが発生します。エラー：500 Internal Server Error",
         4, "software", "payroll", "portal",
         "2-site", "3-medium", "in_progress",
         2, 4, 13, 2, None, None,
         "2026-06-08 09:00:00", None, None, "2026-06-11 09:00:00"),

        # ── catalog=5 経理・財務システム (group=5) ──────────────────────
        ("INC0001013", "会計システムへのログインができない",
         "経理システム（SAP）へのSSO認証が失敗し、全経理部員がログインできない状態です。月次締め作業に影響しています。",
         5, "software", "sap", "phone",
         "1-enterprise", "3-medium", "new",
         20, 5, None, 4, None, None,
         "2026-06-22 08:30:00", None, None, "2026-06-25 08:30:00"),

        ("INC0001014", "経費精算の承認フローが止まっている",
         "経費精算システムで承認者へ通知メールが送信されず、承認フローが止まっています。",
         5, "software", "expense", "portal",
         "3-department", "2-high", "assigned",
         20, 5, 7, 4, None, None,
         "2026-06-16 14:00:00", None, None, "2026-06-19 14:00:00"),

        ("INC0001015", "月次財務レポートのデータが不正",
         "今月の月次レポートで売上合計が前月比-80%と表示されています。データ集計ロジックに問題がある可能性があります。",
         5, "software", "report", "email",
         "2-site", "2-high", "in_progress",
         2, 5, 14, 2, None, None,
         "2026-06-11 10:00:00", None, None, "2026-06-14 10:00:00"),

        # ── catalog=6 情報セキュリティ (group=6) ────────────────────────
        ("INC0001016", "マルウェア感染の疑い",
         "ウイルス対策ソフトがマルウェアを検知しましたが、除去に失敗しています。該当PC（PC-SALES-015）を隔離中です。外部機関への報告を検討中。",
         6, "security", "malware", "phone",
         "1-enterprise", "1-critical", "on_hold",
         2, 6, 8, 2, None, None,
         "2026-06-01 09:00:00", None, None, "2026-06-01 13:00:00"),

        ("INC0001017", "フィッシングメールによるアカウント侵害",
         "フィッシングメールのリンクをクリックしてしまい、Microsoftアカウントのパスワードを入力してしまいました。",
         6, "security", "phishing", "portal",
         "2-site", "1-critical", "resolved",
         19, 6, 15, 3, "solved",
         "フィッシングメールを検出し、対象ユーザーのMicrosoftアカウントのパスワードをリセットしました。MFAを有効化し、不審なサインインログを調査した結果、被害は確認されませんでした。",
         "2026-06-10 09:00:00", "2026-06-20 15:00:00", None, "2026-06-10 13:00:00"),

        ("INC0001018", "不審なUSBデバイス接続",
         "退職者のPC（PC-HR-008）に不審なUSBデバイスが接続された形跡があります。データ持ち出しの調査を依頼します。",
         6, "security", "usb", "walk-in",
         "3-department", "1-critical", "closed",
         20, 6, 17, 4, "solved",
         "PC-HR-008のUSBログを確認した結果、接続されたデバイスは会社支給の暗号化USBであることが確認できました。データ持ち出しの証跡はありませんでした。",
         "2026-04-25 14:00:00", "2026-05-10 16:00:00", "2026-05-12 10:00:00", "2026-04-25 18:00:00"),

        # ── catalog=7 営業支援システム (group=7) ────────────────────────
        ("INC0001019", "CRMの顧客データが同期されない",
         "SalesforceとSAPのデータ同期が停止しており、CRMの顧客情報が2日前のデータのままです。ベンダーへの確認待ちでホールド中。",
         7, "software", "crm_sync", "portal",
         "4-user", "2-high", "on_hold",
         2, 7, 9, 2, None, None,
         "2026-05-15 10:00:00", None, None, "2026-05-18 10:00:00"),

        ("INC0001020", "SFAの商談ステージが更新されない",
         "SFAシステムで商談ステージを「提案中」から「交渉中」に変更しても、保存後に元に戻ってしまいます。",
         7, "software", "sfa", "portal",
         "3-department", "3-medium", "resolved",
         2, 7, 16, 2, "workaround",
         "SFAシステムのセッションタイムアウト設定を延長し、商談ステータス更新APIのバグを特定しました。暫定対処としてキャッシュクリアの手順をご案内します。恒久対応はベンダーと調整中です。",
         "2026-06-05 11:00:00", "2026-06-15 17:00:00", None, "2026-06-08 11:00:00"),

        ("INC0001021", "営業レポートのグラフが表示されない",
         "営業ダッシュボードの月次グラフが空白になっています。データは存在しているようです。",
         7, "software", "report", "portal",
         "4-user", "4-low", "closed",
         19, 7, 9, 3, "no_resolution_required",
         "レポートシステムのJavaScriptライブラリのバージョン差異によるものでした。ブラウザのキャッシュクリアで解消しています。根本対応はシステムアップデート時に対応予定です。",
         "2026-04-10 13:00:00", "2026-04-25 15:00:00", "2026-04-27 10:00:00", "2026-04-17 13:00:00"),

        # ── catalog=8 調達・購買システム (group=8) ──────────────────────
        ("INC0001022", "発注システムの承認フローが機能しない",
         "発注申請後、承認者に通知が届かず、承認フローが進みません。月末の支払い処理に影響が出る可能性があります。ワークフロー設定を見直し中。",
         8, "software", "approval", "portal",
         "2-site", "3-medium", "on_hold",
         20, 8, 10, 4, None, None,
         "2026-06-03 09:00:00", None, None, "2026-06-06 09:00:00"),

        ("INC0001023", "EDI受注データの取り込みエラー",
         "取引先からのEDI受注データが購買システムに取り込めないエラーが発生しています。エラーコード：EDI-4022",
         8, "software", "edi", "email",
         "3-department", "2-high", "resolved",
         2, 8, 17, 2, "solved",
         "EDIフォーマットバージョンの不一致が原因でした。変換設定を更新し、正常にデータ取り込みができることを確認しました。",
         "2026-06-08 15:00:00", "2026-06-18 11:00:00", None, "2026-06-11 15:00:00"),

        ("INC0001024", "在庫管理画面の数量表示がおかしい",
         "在庫管理システムで在庫数量が実際と異なる数字（マイナス値）が表示されています。",
         8, "software", "inventory", "portal",
         "4-user", "3-medium", "closed",
         19, 8, 10, 3, "solved",
         "ブラウザのキャッシュが古いデータを表示していました。キャッシュクリアで正常な数値が表示されることを確認しました。",
         "2026-03-05 11:00:00", "2026-03-20 14:00:00", "2026-03-22 10:00:00", "2026-03-12 11:00:00"),

        # ── catalog=9 PC・ハードウェア (group=9) ────────────────────────
        ("INC0001025", "複数台のプリンターが印刷不能",
         "4Fの複合機3台（MFP-401, MFP-402, MFP-403）がすべて印刷できない状態です。ファームウェアアップデート待ちでホールド中。",
         9, "hardware", "printer", "walk-in",
         "2-site", "2-high", "on_hold",
         2, 9, 11, 2, None, None,
         "2026-05-20 10:00:00", None, None, "2026-05-22 10:00:00"),

        ("INC0001026", "PCの動作が極端に遅い",
         "経理部のPC（PC-FIN-018）が起動後も非常に動作が遅く、業務に支障が出ています。使用年数は5年です。",
         9, "hardware", "performance", "portal",
         "3-department", "3-medium", "resolved",
         20, 9, 18, 4, "solved",
         "メモリを4GBから16GBに増設しました。また、HDDからSSDへの換装も実施し、起動時間が10秒以下になったことを確認しました。",
         "2026-05-28 14:00:00", "2026-06-10 16:00:00", None, "2026-06-04 14:00:00"),

        ("INC0001027", "キーボードの一部キーが反応しない",
         "人事部のPC（PC-HR-022）のキーボードで「A」「S」キーが全く反応しません。",
         9, "hardware", "keyboard", "portal",
         "4-user", "3-medium", "closed",
         19, 9, 11, 3, "workaround",
         "キーボードドライバーを最新版に更新し、物理的なキークリーニングを実施しました。現在は正常に動作しています。",
         "2026-02-10 09:00:00", "2026-02-28 15:00:00", "2026-03-02 10:00:00", "2026-02-17 09:00:00"),

        # ── catalog=10 アカウント・アクセス管理 (group=10) ─────────────
        ("INC0001028", "新システムへのアクセス権限が必要",
         "来月稼働予定の調達システム（新バージョン）のアクセス権限付与を依頼します。上長承認待ちでホールド中。",
         10, "security", "access_request", "portal",
         "2-site", "2-high", "on_hold",
         2, 10, 12, 2, None, None,
         "2026-06-02 10:00:00", None, None, "2026-06-05 10:00:00"),

        ("INC0001029", "パスワードを忘れてログインできない",
         "社内システムのパスワードを忘れてしまい、ログインができません。パスワードリセットをお願いします。",
         10, "inquiry", "password_reset", "portal",
         "3-department", "4-low", "resolved",
         19, 10, 13, 3, "solved",
         "本人確認を実施した後、パスワードリセットを行いました。初回ログイン時に新しいパスワードを設定していただくよう案内しました。",
         "2026-06-14 15:00:00", "2026-06-22 10:00:00", None, "2026-06-21 15:00:00"),

        ("INC0001030", "新入社員のIDアカウント作成依頼",
         "7月1日入社予定の新入社員5名分のIDアカウント作成を依頼します。詳細は添付の申請書を参照ください。",
         10, "inquiry", "account_create", "email",
         "2-site", "3-medium", "closed",
         20, 10, 12, 4, "solved",
         "5名分のIDアカウントを作成し、初回ログイン手順書をメールにて送付しました。入社日当日にサポートデスクに来ていただくよう案内しました。",
         "2026-05-01 10:00:00", "2026-05-15 14:00:00", "2026-05-17 10:00:00", "2026-06-25 10:00:00"),
    ]

    for row in inc_rows:
        (inc_id, short_desc, desc, cat_id, cat, subcat, channel,
         impact, urgency, state,
         caller_id, group_id, assigned_user_id, dept_id,
         res_code, res_notes,
         opened_at, resolved_at, closed_at, due_date) = row

        priority = calc_priority(impact, urgency)

        await db.execute(
            """INSERT INTO incident (
                incident_id, short_description, description,
                service_catalog_id, category, subcategory, channel,
                priority, impact, urgency, state,
                caller_user_id, assigned_group_id, assigned_user_id, department_id,
                resolution_code, resolution_notes,
                opened_at, resolved_at, closed_at, due_date
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (inc_id, short_desc, desc, cat_id, cat, subcat, channel,
             priority, impact, urgency, state,
             caller_id, group_id, assigned_user_id, dept_id,
             res_code, res_notes,
             opened_at, resolved_at, closed_at, due_date),
        )

    # ── work_note (40件) ──────────────────────────────────────
    # (ticket_type, ticket_id, author_user_id, note_type, body, created_at)
    work_notes = [
        # INC0001001 (new) 1件
        ("incident", "INC0001001", 3,  "work_note",
         "インシデントを受領しました。パフォーマンス低下の原因を確認します。サーバー側のログを確認中です。",
         "2026-06-20 09:30:00"),

        # INC0001002 (assigned) 1件
        ("incident", "INC0001002", 3,  "work_note",
         "担当を引き受けました。ファイルサーバーの接続状況を確認中です。ネットワーク経路の調査も並行して進めます。",
         "2026-06-15 11:00:00"),

        # INC0001003 (in_progress) 2件
        ("incident", "INC0001003", 13, "work_note",
         "MFP-301のスプーラーを確認したところ、ジョブがキューに溜まっている状態でした。ドライバーを再インストール中です。",
         "2026-06-10 15:00:00"),
        ("incident", "INC0001003", 13, "public_comment",
         "現在プリンタードライバーの再インストールを実施しています。本日中に復旧見込みです。",
         "2026-06-10 16:30:00"),

        # INC0001004 (new) 1件
        ("incident", "INC0001004", 4,  "work_note",
         "Teams通話品質の問題を受領しました。ネットワーク帯域の確認とTeams診断ツールでの調査を開始します。",
         "2026-06-21 11:30:00"),

        # INC0001005 (assigned) 1件
        ("incident", "INC0001005", 4,  "work_note",
         "Exchange Online管理センターでサービス正常性を確認しました。Microsoft側でインシデントが発生中（EX789456）。Microsoftの対応完了を待ちながら回避策を検討します。",
         "2026-06-18 08:30:00"),

        # INC0001006 (in_progress) 2件
        ("incident", "INC0001006", 15, "work_note",
         "Azure ADの条件付きアクセスポリシーが原因でTeams認証が失敗していることを確認しました。ポリシー設定を調整中です。",
         "2026-06-12 14:00:00"),
        ("incident", "INC0001006", 15, "public_comment",
         "Teams認証の問題の原因を特定しました。設定変更作業中です。本日17時までに復旧予定です。",
         "2026-06-12 15:30:00"),

        # INC0001007 (new) 1件
        ("incident", "INC0001007", 5,  "work_note",
         "VPN集約装置のログを確認中です。セッション数が上限に達している可能性があります。接続セッション数を調査します。",
         "2026-06-22 10:00:00"),

        # INC0001008 (assigned) 1件
        ("incident", "INC0001008", 5,  "work_note",
         "2Fと3Fに接続するL2スイッチ（SW-B2F-01）のポートエラーカウンターが増加していることを確認。スイッチの交換を手配中です。",
         "2026-06-17 15:30:00"),

        # INC0001009 (in_progress) 2件
        ("incident", "INC0001009", 16, "work_note",
         "PC-FIN-042のWi-Fiドライバーを確認しました。ドライバーのバージョンが古く、最新版への更新作業を実施中です。",
         "2026-06-05 16:30:00"),
        ("incident", "INC0001009", 16, "public_comment",
         "Wi-Fiドライバーを更新中です。作業完了後にご確認をお願いします。",
         "2026-06-05 17:00:00"),

        # INC0001010 (new) 1件
        ("incident", "INC0001010", 6,  "work_note",
         "勤怠システムのUIバグを確認しました。Chromeのバージョン差異による表示崩れの可能性があります。ベンダーに問い合わせ中です。",
         "2026-06-23 10:30:00"),

        # INC0001011 (assigned) 1件
        ("incident", "INC0001011", 6,  "work_note",
         "人事評価システムの保存機能のバグを確認しました。セッションタイムアウト設定が短すぎることが原因の可能性があります。ベンダーに修正を依頼しました。",
         "2026-06-19 11:30:00"),

        # INC0001012 (in_progress) 2件
        ("incident", "INC0001012", 13, "work_note",
         "PDF生成サービスのログを確認したところ、メモリ不足エラーが発生していることが判明しました。サービスの再起動で一時的に改善しました。",
         "2026-06-08 10:00:00"),
        ("incident", "INC0001012", 13, "public_comment",
         "給与明細PDFの問題を確認しました。一時的な対処として担当者が手動でPDFを送付します。恒久対応は今週中に完了予定です。",
         "2026-06-08 11:00:00"),

        # INC0001013 (new) 1件
        ("incident", "INC0001013", 7,  "work_note",
         "SAPへのSSOが失敗していることを確認。Active DirectoryとSAPのSSO設定を確認中です。月次締め作業への影響を最小化するため、緊急対応中です。",
         "2026-06-22 09:00:00"),

        # INC0001014 (assigned) 1件
        ("incident", "INC0001014", 7,  "work_note",
         "経費精算システムのメール送信ログを確認したところ、SMTPサーバーへの接続タイムアウトが発生していました。メール設定を見直し中です。",
         "2026-06-16 14:30:00"),

        # INC0001015 (in_progress) 2件
        ("incident", "INC0001015", 14, "work_note",
         "月次レポートの集計SQLを確認したところ、結合条件に誤りがあることを発見しました。修正版のSQLをテスト環境で検証中です。",
         "2026-06-11 11:00:00"),
        ("incident", "INC0001015", 14, "public_comment",
         "財務レポートのデータ不整合の原因を特定しました。本日18時までに修正版を本番環境に適用予定です。",
         "2026-06-11 14:00:00"),

        # INC0001016 (on_hold) 2件
        ("incident", "INC0001016", 8,  "work_note",
         "PC-SALES-015を物理的に社内ネットワークから隔離しました。マルウェアの種類を特定するためJPCERT/CCに相談中です。ウイルス対策ベンダーとも連携しています。",
         "2026-06-01 09:30:00"),
        ("incident", "INC0001016", 8,  "public_comment",
         "セキュリティインシデントとして対応中です。詳細な調査のため時間を要しています。代替PCの手配をご検討ください。",
         "2026-06-01 13:00:00"),

        # INC0001017 (resolved) 1件
        ("incident", "INC0001017", 15, "public_comment",
         "フィッシングメールへの対応が完了しました。アカウントは保護されており、不正アクセスの痕跡はありませんでした。今後のフィッシング対策として、セキュリティ研修の受講をお勧めします。",
         "2026-06-20 15:30:00"),

        # INC0001018 (closed) 1件
        ("incident", "INC0001018", 17, "public_comment",
         "USB接続の調査が完了しました。会社支給の暗号化USBの正規使用であることが確認され、情報漏洩の事実はありませんでした。クローズします。",
         "2026-05-10 17:00:00"),

        # INC0001019 (on_hold) 2件
        ("incident", "INC0001019", 9,  "work_note",
         "SalesforceとSAPの連携APIを調査したところ、Salesforce側のAPIバージョンが変更されたことによる互換性問題が原因と判明しました。ベンダーに修正を依頼中です。",
         "2026-05-15 11:00:00"),
        ("incident", "INC0001019", 9,  "public_comment",
         "データ同期の問題はベンダー側のAPIバージョン変更が原因です。修正リリースの準備ができるまでホールドとなります。進捗があり次第ご連絡します。",
         "2026-05-15 14:00:00"),

        # INC0001020 (resolved) 1件
        ("incident", "INC0001020", 16, "public_comment",
         "SFAの商談ステータス更新の問題を修正しました。暫定対処としてブラウザのローカルストレージをクリアしてからご利用ください。恒久対応はベンダーと次回リリースで対応予定です。",
         "2026-06-15 17:30:00"),

        # INC0001021 (closed) 1件
        ("incident", "INC0001021", 9,  "public_comment",
         "営業レポートのグラフ表示問題はブラウザのキャッシュが原因でした。Ctrl+Shift+Delでキャッシュをクリアし正常表示されることを確認しました。クローズします。",
         "2026-04-25 15:30:00"),

        # INC0001022 (on_hold) 2件
        ("incident", "INC0001022", 10, "work_note",
         "発注承認フローのワークフローエンジンのログを確認中です。通知メール送信キューでエラーが発生していることを特定しました。メール設定を修正中ですが、上位承認者との調整が必要なためホールドします。",
         "2026-06-03 10:00:00"),
        ("incident", "INC0001022", 10, "public_comment",
         "承認フローの問題を調査中です。暫定対処として承認依頼はメールで直接承認者に送付してください。今週中に恒久対応予定です。",
         "2026-06-03 14:00:00"),

        # INC0001023 (resolved) 1件
        ("incident", "INC0001023", 17, "public_comment",
         "EDI連携エラーの修正が完了しました。取引先のEDIフォーマットが最新版（Ver.3.1）に変更されていたため、変換設定を更新しました。正常に受注データが取り込めることを確認しました。",
         "2026-06-18 11:30:00"),

        # INC0001024 (closed) 1件
        ("incident", "INC0001024", 10, "public_comment",
         "在庫数量の表示問題はブラウザキャッシュが原因でした。キャッシュクリア後に正常な数値が表示されることを確認しました。クローズします。",
         "2026-03-20 14:30:00"),

        # INC0001025 (on_hold) 2件
        ("incident", "INC0001025", 11, "work_note",
         "メーカーに問い合わせたところ、ファームウェアの不具合が確認されており、修正版ファームウェアのリリースを待っている状況です。修正版リリース予定日は来週です。",
         "2026-05-20 11:00:00"),
        ("incident", "INC0001025", 11, "public_comment",
         "プリンターファームウェアの不具合が原因でした。修正版のリリースを待っています。来週中には復旧予定です。ご不便をおかけして申し訳ありません。",
         "2026-05-20 14:00:00"),

        # INC0001026 (resolved) 1件
        ("incident", "INC0001026", 18, "public_comment",
         "PC-FIN-018のメモリを4GBから16GBに増設し、HDDからSSDへの換装も実施しました。起動時間が2分から10秒以下に短縮され、業務アプリの動作も大幅に改善しました。",
         "2026-06-10 17:00:00"),

        # INC0001027 (closed) 1件
        ("incident", "INC0001027", 11, "public_comment",
         "キーボードドライバーを最新版に更新し、キーボード内部のクリーニングを実施しました。全キーが正常に動作することを確認しました。クローズします。",
         "2026-02-28 16:00:00"),

        # INC0001028 (on_hold) 2件
        ("incident", "INC0001028", 12, "work_note",
         "アクセス権限付与の申請を受け付けました。規定に従い上長承認が必要です。承認フローを起動しました。承認完了次第、権限を付与します。",
         "2026-06-02 10:30:00"),
        ("incident", "INC0001028", 12, "public_comment",
         "アクセス権限の付与申請を受け付けました。上長の承認待ちとなっております。承認が完了次第、速やかに権限を付与いたします。",
         "2026-06-02 11:00:00"),

        # INC0001029 (resolved) 1件
        ("incident", "INC0001029", 13, "public_comment",
         "本人確認（社員証+秘密の質問）を実施した後、パスワードリセットを行いました。新しい仮パスワードを設定しましたので、初回ログイン後に変更してください。",
         "2026-06-22 10:30:00"),

        # INC0001030 (closed) 1件
        ("incident", "INC0001030", 12, "public_comment",
         "7月1日入社予定の5名分のIDアカウントを作成しました。各人に初回ログイン手順書をメールにて送付しました。入社日当日はサービスデスク（内線1234）にお問い合わせください。",
         "2026-05-15 14:30:00"),
    ]

    await db.executemany(
        "INSERT INTO work_note (ticket_type, ticket_id, author_user_id, note_type, body, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        work_notes,
    )

    await db.commit()
