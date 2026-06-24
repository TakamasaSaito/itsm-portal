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
        ("yamada.kenji",       "pass123", "山田 健二",     "yamada.k@example.com",    "group_leader", 1),
        ("tanaka.yuki",        "pass123", "田中 雪",       "tanaka.y@example.com",    "group_leader", 1),
        ("suzuki.hiroshi",     "pass123", "鈴木 浩",       "suzuki.h@example.com",    "group_leader", 1),
        ("sato.emi",           "pass123", "佐藤 恵美",     "sato.e@example.com",      "group_leader", 1),
        ("ito.masato",         "pass123", "伊藤 雅人",     "ito.m@example.com",       "group_leader", 1),
        ("watanabe.jun",       "pass123", "渡辺 純",       "watanabe.j@example.com",  "group_leader", 1),
        ("nakamura.ryota",     "pass123", "中村 亮太",     "nakamura.r@example.com",  "group_leader", 1),
        ("kobayashi.ai",       "pass123", "小林 愛",       "kobayashi.a@example.com", "group_leader", 1),
        ("kato.shinji",        "pass123", "加藤 信二",     "kato.s@example.com",      "group_leader", 1),
        ("yoshida.mika",       "pass123", "吉田 美香",     "yoshida.m@example.com",   "group_leader", 1),
        ("ogawa.daisuke",      "pass123", "小川 大輔",     "ogawa.d@example.com",     "member", 1),
        ("hayashi.noriko",     "pass123", "林 典子",       "hayashi.n@example.com",   "member", 1),
        ("shimizu.takashi",    "pass123", "清水 隆",       "shimizu.t@example.com",   "member", 1),
        ("inoue.yoko",         "pass123", "井上 洋子",     "inoue.y@example.com",     "member", 1),
        ("matsumoto.ken",      "pass123", "松本 健",       "matsumoto.k@example.com", "member", 1),
        ("kimura.sachiko",     "pass123", "木村 幸子",     "kimura.s@example.com",    "member", 1),
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
    # catalog: 1=2件 2=6件 3=5件 4=1件 5=2件 6=4件 7=3件 8=1件 9=4件 10=2件
    # priority: 1-critical=3 2-high=7 3-moderate=12 4-low=6 5-planning=2
    # state: new=8 assigned=5 in_progress=7 on_hold=3 resolved=5 closed=2
    # 週次trend(今日2026-06-24): 6日前=1 5日前=2 4日前=1 3日前=4 2日前=3 1日前=6 本日=2
    inc_rows = [
        # ── cat2 コミュニケーション基盤 6件 ─────────────────────────────
        # INC01 cat2 new 6日前(06-18) 4-user 3-medium → 4-low
        ("INC0001001", "Teamsの通話音声が断続的に途切れる",
         "Teamsビデオ会議中に音声が1〜2秒おきに途切れる現象が発生しています。複数の会議参加者から同様の報告があります。",
         2, "software", "teams", "portal",
         "4-user", "3-medium", "new",
         2, 2, None, 2, None, None,
         "2026-06-18 09:15:00", None, None, "2026-06-21 09:15:00"),

        # INC02 cat2 new 5日前(06-19) 3-dept 3-medium → 3-moderate
        ("INC0001002", "メールへの添付ファイルが送れない",
         "Outlookから5MB以上の添付ファイルを送信しようとするとエラーになります。受信は正常です。",
         2, "software", "email", "portal",
         "3-department", "3-medium", "new",
         20, 2, None, 4, None, None,
         "2026-06-19 10:00:00", None, None, "2026-06-22 10:00:00"),

        # INC03 cat2 assigned 5日前(06-19) 4-user 2-high → 3-moderate
        ("INC0001003", "Teams会議室の予約が重複してしまう",
         "Teams会議室カレンダーで同一時間帯に複数の予約が入ってしまう問題が発生しています。会議室の二重ブッキングが続いています。",
         2, "software", "teams", "portal",
         "4-user", "2-high", "assigned",
         19, 2, 15, 3, None, None,
         "2026-06-19 13:30:00", None, None, "2026-06-22 13:30:00"),

        # INC04 cat2 in_progress 4日前(06-20) 1-enterprise 1-critical → 1-critical
        ("INC0001004", "全社メールサーバーが完全停止",
         "Exchange Onlineへの接続が全社でできない状態です。送受信ともに停止しています。月末の重要業務に影響が出ています。緊急対応が必要です。",
         2, "software", "email", "phone",
         "1-enterprise", "1-critical", "in_progress",
         2, 2, 4, 2, None, None,
         "2026-06-20 08:05:00", None, None, "2026-06-20 10:00:00"),

        # INC05 cat2 new 3日前(06-21) 3-dept 4-low → 4-low
        ("INC0001005", "TeamsのプレゼンスがオフラインのままになるBug",
         "Teamsを起動しているのにステータスが「オフライン」と表示されたままになっています。チャットの着信も届きません。",
         2, "software", "teams", "portal",
         "3-department", "4-low", "new",
         19, 2, None, 3, None, None,
         "2026-06-21 09:30:00", None, None, "2026-06-28 09:30:00"),

        # INC06 cat2 in_progress 3日前(06-21) 2-site 2-high → 2-high
        ("INC0001006", "SharePointの外部共有リンクがアクセス拒否になる",
         "SharePointで発行した共有リンクを外部ユーザーがクリックするとアクセス拒否になります。同一テナント内では正常です。",
         2, "software", "sharepoint", "portal",
         "2-site", "2-high", "in_progress",
         2, 2, 15, 2, None, None,
         "2026-06-21 14:00:00", None, None, "2026-06-24 14:00:00"),

        # ── cat3 ネットワーク・インフラ 5件 ─────────────────────────────
        # INC07 cat3 assigned 3日前(06-21) 2-site 2-high → 2-high
        ("INC0001007", "本社2Fネットワーク速度が大幅低下",
         "本社2Fの有線LANが通常比10%以下の速度になっています。L2スイッチのポートエラーが疑われます。",
         3, "network", "lan", "walk-in",
         "2-site", "2-high", "assigned",
         19, 3, 5, 1, None, None,
         "2026-06-21 11:00:00", None, None, "2026-06-22 11:00:00"),

        # INC08 cat3 in_progress 3日前(06-21) 1-enterprise 3-medium → 2-high
        ("INC0001008", "在宅勤務者のVPN接続が全員切断される",
         "在宅勤務者全員からVPNが繰り返し切断されるとの報告が続いています。接続成功率が20%以下です。セッション上限超過が疑われます。",
         3, "network", "vpn", "portal",
         "1-enterprise", "3-medium", "in_progress",
         20, 3, 16, 4, None, None,
         "2026-06-21 09:00:00", None, None, "2026-06-24 09:00:00"),

        # INC09 cat3 new 2日前(06-22) 4-user 3-medium → 4-low
        ("INC0001009", "特定PCのWi-Fi接続が断続的に切れる",
         "営業部のPC（PC-SALES-031）がWi-Fiに断続的にしか接続できません。他の端末は正常に接続できています。",
         3, "network", "wifi", "portal",
         "4-user", "3-medium", "new",
         2, 3, None, 2, None, None,
         "2026-06-22 10:30:00", None, None, "2026-06-29 10:30:00"),

        # INC10 cat3 assigned 2日前(06-22) 3-dept 2-high → 3-moderate
        ("INC0001010", "ファイアウォールに大量のドロップログが記録される",
         "ファイアウォール管理画面で大量のドロップログが記録されています。外部からのポートスキャン攻撃の可能性があります。",
         3, "network", "firewall", "email",
         "3-department", "2-high", "assigned",
         2, 3, 5, 1, None, None,
         "2026-06-22 14:00:00", None, None, "2026-06-23 14:00:00"),

        # INC11 cat3 in_progress 2日前(06-22) 2-site 1-critical → 1-critical
        ("INC0001011", "データセンターコアスイッチ障害",
         "データセンターのコアスイッチが障害を起こし、複数のサーバーへの到達不能が発生しています。STPループが疑われます。緊急対応中。",
         3, "network", "infrastructure", "phone",
         "2-site", "1-critical", "in_progress",
         2, 3, 16, 1, None, None,
         "2026-06-22 17:00:00", None, None, "2026-06-22 19:00:00"),

        # ── cat6 情報セキュリティ 4件 ────────────────────────────────────
        # INC12 cat6 new 1日前(06-23) 1-enterprise 2-high → 1-critical
        ("INC0001012", "大規模フィッシングメールが全社着信",
         "全社員に対してMicrosoftを騙るフィッシングメールが大量送信されています。クリックした社員がいる可能性があり緊急対応が必要です。",
         6, "security", "phishing", "email",
         "1-enterprise", "2-high", "new",
         2, 6, None, 2, None, None,
         "2026-06-23 08:00:00", None, None, "2026-06-23 12:00:00"),

        # INC13 cat6 in_progress 1日前(06-23) 3-dept 1-critical → 2-high
        ("INC0001013", "PC端末へのランサムウェア感染疑い",
         "ウイルス対策ソフトがランサムウェアの亜種を検知し除去に失敗しています。対象PC（PC-MKT-007）を隔離中。外部機関への報告を検討中。",
         6, "security", "malware", "phone",
         "3-department", "1-critical", "in_progress",
         2, 6, 8, 7, None, None,
         "2026-06-23 09:30:00", None, None, "2026-06-23 13:00:00"),

        # INC14 cat6 new 1日前(06-23) 2-site 3-medium → 3-moderate
        ("INC0001014", "深夜の管理者アカウントへの不審ログイン試行",
         "SIEMツールが深夜2時台に管理者アカウントへの連続ログイン失敗を検知しました。ブルートフォース攻撃の可能性があります。",
         6, "security", "unauthorized_access", "portal",
         "2-site", "3-medium", "new",
         2, 6, None, 1, None, None,
         "2026-06-23 06:00:00", None, None, "2026-06-24 06:00:00"),

        # INC15 cat6 on_hold 1日前(06-23) 2-site 2-high → 2-high
        ("INC0001015", "営業資料の社外流出疑惑",
         "競合他社が自社未公開の営業資料を所持しているとの情報があり、内部からの流出を調査中。DLP調査が完了するまでホールド。",
         6, "security", "data_leak", "walk-in",
         "2-site", "2-high", "on_hold",
         2, 6, 15, 2, None, None,
         "2026-06-23 10:00:00", None, None, "2026-06-26 10:00:00"),

        # ── cat9 PC・ハードウェア 4件 ────────────────────────────────────
        # INC16 cat9 assigned 1日前(06-23) 3-dept 3-medium → 3-moderate
        ("INC0001016", "PC起動後に黒画面で止まる",
         "法務部のPC（PC-LEGAL-004）が電源ボタンを押しても黒画面のままで起動しません。昨日まで正常に動作していました。",
         9, "hardware", "pc_boot", "walk-in",
         "3-department", "3-medium", "assigned",
         2, 9, 11, 9, None, None,
         "2026-06-23 09:00:00", None, None, "2026-06-24 09:00:00"),

        # INC17 cat9 resolved 1日前(06-23) 4-user 4-low → 5-planning
        ("INC0001017", "キーボードの複数キーが反応しない",
         "経営企画部のPC（PC-CORP-012）のキーボードで「E」「R」「T」キーが反応しません。コーヒーをこぼした可能性があります。",
         9, "hardware", "keyboard", "portal",
         "4-user", "4-low", "resolved",
         2, 9, 18, 10, "workaround",
         "代替キーボードを貸し出しました。水没したキーボードはメーカー修理に送ります。",
         "2026-06-23 11:00:00", "2026-06-23 15:00:00", None, "2026-06-30 11:00:00"),

        # INC18 cat9 new 本日(06-24) 3-dept 3-medium → 3-moderate
        ("INC0001018", "3Fフロアの複合機から印刷できない",
         "3F設置の複合機（MFP-301）からどのPCも印刷できません。印刷ジョブはスプールされていますが処理されない状態です。",
         9, "hardware", "printer", "walk-in",
         "3-department", "3-medium", "new",
         19, 9, None, 3, None, None,
         "2026-06-24 08:30:00", None, None, "2026-06-25 08:30:00"),

        # INC19 cat9 resolved 本日(06-24) 4-user 3-medium → 4-low
        ("INC0001019", "外付けHDDがPCで認識されない",
         "経理部で使用している外付けHDD（Buffalo 2TB）がPCに接続しても認識されません。デバイスマネージャーでエラーが表示されます。",
         9, "hardware", "storage", "portal",
         "4-user", "3-medium", "resolved",
         20, 9, 11, 4, "solved",
         "デバイスドライバーを最新版に更新し、正常に認識されることを確認しました。",
         "2026-06-24 10:00:00", "2026-06-24 12:00:00", None, "2026-07-01 10:00:00"),

        # ── cat7 営業支援システム 3件 ────────────────────────────────────
        # INC20 cat7 in_progress 旧(06-10) 3-dept 2-high → 3-moderate
        ("INC0001020", "SalesforceとSAPのデータ同期が停止",
         "SalesforceとSAP間のデータ連携バッチが停止しており、CRMの顧客情報が2日前のデータになっています。ベンダーに調査依頼中。",
         7, "software", "crm_sync", "portal",
         "3-department", "2-high", "in_progress",
         2, 7, 9, 2, None, None,
         "2026-06-10 10:00:00", None, None, "2026-06-13 10:00:00"),

        # INC21 cat7 on_hold 旧(06-05) 2-site 4-low → 3-moderate
        ("INC0001021", "SFAへの新メンバーのアクセス権限エラー",
         "営業部の新メンバー3名がSFAシステムにアクセスできません。権限設定の見直し中で部門長確認待ちのためホールド。",
         7, "software", "access", "portal",
         "2-site", "4-low", "on_hold",
         2, 7, 9, 2, None, None,
         "2026-06-05 11:00:00", None, None, "2026-06-12 11:00:00"),

        # INC22 cat7 resolved 旧(05-20) 4-user 4-low → 5-planning
        ("INC0001022", "営業ダッシュボードのグラフが空白表示",
         "営業ダッシュボードの月次グラフが空白表示になっています。データは存在しているはずです。",
         7, "software", "report", "portal",
         "4-user", "4-low", "resolved",
         19, 7, 16, 3, "workaround",
         "ブラウザキャッシュのクリアで解消することを確認しました。根本対応は次回アップデートで対応予定です。",
         "2026-05-20 13:00:00", "2026-05-25 16:00:00", None, "2026-05-27 13:00:00"),

        # ── cat1 共通サービス・全般 2件 ──────────────────────────────────
        # INC23 cat1 new 旧(06-15) 3-dept 4-low → 4-low
        ("INC0001023", "社内ポータルへのアクセスが極端に遅い",
         "社内ポータルサイトの読み込みが非常に遅く、ページ表示に20秒以上かかることがあります。午前中に集中している模様です。",
         1, "inquiry", "performance", "portal",
         "3-department", "4-low", "new",
         2, 1, None, 2, None, None,
         "2026-06-15 09:00:00", None, None, "2026-06-22 09:00:00"),

        # INC24 cat1 closed 旧(06-01) 3-dept 3-medium → 3-moderate
        ("INC0001024", "部門共有フォルダへのアクセス権限付与",
         "総務部の新担当者に部門共有フォルダへのアクセス権限を付与してほしい。業務引き継ぎのために至急対応をお願いします。",
         1, "inquiry", "access", "email",
         "3-department", "3-medium", "closed",
         19, 1, 3, 5, "solved",
         "Active Directoryのグループに追加し、アクセス可能なことを申請者に確認していただきました。",
         "2026-06-01 10:00:00", "2026-06-02 11:00:00", "2026-06-03 10:00:00", "2026-06-08 10:00:00"),

        # ── cat5 経理・財務システム 2件 ──────────────────────────────────
        # INC25 cat5 assigned 旧(06-12) 1-enterprise 3-medium → 2-high
        ("INC0001025", "会計システム（SAP）へのSSO認証が全社で失敗",
         "全経理部員がSAPへのSSOログインに失敗しています。月次締め処理に影響が出ており、ADFSの証明書期限切れが疑われます。",
         5, "software", "sso", "phone",
         "1-enterprise", "3-medium", "assigned",
         20, 5, 7, 4, None, None,
         "2026-06-12 08:30:00", None, None, "2026-06-12 12:00:00"),

        # INC26 cat5 resolved 旧(06-08) 3-dept 2-high → 3-moderate
        ("INC0001026", "経費精算の承認メール通知が届かない",
         "経費精算システムで申請を出しても承認者に通知メールが届かないため、承認フローが止まっています。月末精算に影響が出ています。",
         5, "software", "expense", "portal",
         "3-department", "2-high", "resolved",
         20, 5, 7, 4, "solved",
         "SMTPサーバーの認証設定を修正しました。承認通知メールが正常に送信されることを確認しました。",
         "2026-06-08 14:00:00", "2026-06-15 17:00:00", None, "2026-06-11 14:00:00"),

        # ── cat10 アカウント・アクセス管理 2件 ──────────────────────────
        # INC27 cat10 in_progress 旧(06-14) 4-user 3-medium → 4-low
        ("INC0001027", "パスワードリセット要求",
         "社内システムのパスワードを忘れてしまい、全社システムにログインができない状態です。本人確認書類を提出済みです。",
         10, "inquiry", "password_reset", "portal",
         "4-user", "3-medium", "in_progress",
         19, 10, 12, 3, None, None,
         "2026-06-14 15:00:00", None, None, "2026-06-21 15:00:00"),

        # INC28 cat10 on_hold 旧(06-03) 2-site 3-medium → 3-moderate
        ("INC0001028", "新購買システムへのアクセス権限付与依頼",
         "来月稼働する新購買システムのアクセス権限を事前に付与してほしい。部門長承認待ちのためホールド中。",
         10, "inquiry", "access_request", "email",
         "2-site", "3-medium", "on_hold",
         20, 10, 12, 4, None, None,
         "2026-06-03 10:00:00", None, None, "2026-06-10 10:00:00"),

        # ── cat4 人事システム 1件 ────────────────────────────────────────
        # INC29 cat4 resolved 旧(06-10) 3-dept 3-medium → 3-moderate
        ("INC0001029", "勤怠入力データが保存されない",
         "勤怠管理システムで月次の勤怠データを入力後に「保存」を押しても保存されず、再度開くと消えています。月末締めに影響が出ています。",
         4, "software", "hr_attendance", "portal",
         "3-department", "3-medium", "resolved",
         19, 4, 6, 3, "solved",
         "セッションタイムアウト設定を30分から120分に延長しました。保存が正常に行われることを確認しました。",
         "2026-06-10 11:00:00", "2026-06-16 14:00:00", None, "2026-06-13 11:00:00"),

        # ── cat8 調達・購買システム 1件 ──────────────────────────────────
        # INC30 cat8 closed 旧(05-15) 2-site 2-high → 2-high
        ("INC0001030", "EDI受注データの取り込みエラーが継続",
         "取引先からのEDI受注データが購買システムに取り込めないエラーが継続しています。エラーコード：EDI-4022。月末発注処理に影響が出ています。",
         8, "software", "edi", "email",
         "2-site", "2-high", "closed",
         2, 8, 10, 6, "solved",
         "EDIフォーマットのバージョン不一致が原因でした。変換設定を更新し、正常取り込みを確認しました。",
         "2026-05-15 15:00:00", "2026-05-28 11:00:00", "2026-05-30 10:00:00", "2026-05-18 15:00:00"),
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

    # ── work_note (80件) ──────────────────────────────────────
    # アクター: admin(1)=自動通知/指名, leader=指示・調査, member=調査メモ・利用者連絡
    # 比率: work_note=70% / public_comment=30%
    # (ticket_type, ticket_id, author_user_id, note_type, body, created_at)
    work_notes = [
        # INC0001001 cat2/コミュニケーション基盤 new (3件: 2wn+1pc)
        # group=2: leader=4(田中), member=15(清水),18(木村)
        ("incident", "INC0001001", 1, "work_note",
         "INC0001001 が作成されました。コミュニケーション基盤チームに自動アサインされました。",
         "2026-06-18 09:20:00"),
        ("incident", "INC0001001", 4, "work_note",
         "清水さん、対応をお願いします。Teamsの通話音声断続問題を調査し、状況を随時報告してください。",
         "2026-06-18 10:00:00"),
        ("incident", "INC0001001", 15, "public_comment",
         "現在調査中です。Teams診断ツールの結果を確認しています。進捗があり次第ご連絡します。",
         "2026-06-18 14:00:00"),
        # INC0001002 cat2 new (3件: 2wn+1pc)
        # group=2: leader=4(田中), member=15(清水),18(木村)
        ("incident", "INC0001002", 1, "work_note",
         "INC0001002 が作成されました。コミュニケーション基盤チームに自動アサインされました。",
         "2026-06-19 10:05:00"),
        ("incident", "INC0001002", 4, "work_note",
         "木村さん、Outlookの添付ファイル送信エラーを調査してください。Exchangeの制限とウイルスチェックの状況を確認の上、報告をお願いします。",
         "2026-06-19 10:30:00"),
        ("incident", "INC0001002", 18, "public_comment",
         "現在調査中です。進捗があり次第ご連絡します。",
         "2026-06-19 14:00:00"),
        # INC0001003 cat2 assigned=15(清水) (3件: 2wn+1pc)
        # group=2: leader=4(田中), member=15(清水),18(木村)
        ("incident", "INC0001003", 1, "work_note",
         "INC0001003 が作成されました。コミュニケーション基盤チームに自動アサインされました。",
         "2026-06-19 13:35:00"),
        ("incident", "INC0001003", 1, "work_note",
         "清水 隆さんにアサインします。Teams会議室の重複予約問題を優先対応してください。",
         "2026-06-19 13:40:00"),
        ("incident", "INC0001003", 15, "public_comment",
         "会議室の重複予約問題について調査中です。Exchange Onlineのリソースメールボックス設定を確認中です。本日中に原因特定と対処法をご連絡します。",
         "2026-06-19 15:30:00"),
        # INC0001004 cat2 in_progress critical assigned=4(田中) (4件: 3wn+1pc)
        # group=2: leader=4(田中), member=15(清水),18(木村)
        ("incident", "INC0001004", 1, "work_note",
         "INC0001004 が作成されました。コミュニケーション基盤チームに自動アサインされました。",
         "2026-06-20 08:10:00"),
        ("incident", "INC0001004", 1, "work_note",
         "Priority 1-Critical。田中 雪さんにアサインします。全社メール停止のため最優先での対応をお願いします。",
         "2026-06-20 08:12:00"),
        ("incident", "INC0001004", 4, "work_note",
         "Exchange Online管理センターを確認したところ、Microsoftのサービス障害（EX892134）が発生中。Microsoft Status Pageにて復旧作業が進行中と更新あり。推定復旧時刻は12:00予定。経過観察継続中。",
         "2026-06-20 08:20:00"),
        ("incident", "INC0001004", 15, "public_comment",
         "全社メール停止はMicrosoft側のサービス障害が原因です。緊急連絡はTeamsまたは電話をご使用ください。復旧次第ご連絡します。",
         "2026-06-20 08:45:00"),
        # INC0001005 cat2 new (3件: 2wn+1pc)
        # group=2: leader=4(田中), member=15(清水),18(木村)
        ("incident", "INC0001005", 1, "work_note",
         "INC0001005 が作成されました。コミュニケーション基盤チームに自動アサインされました。",
         "2026-06-21 09:35:00"),
        ("incident", "INC0001005", 4, "work_note",
         "清水さん、TeamsのプレゼンスがオフラインになるBugを調査してください。キャッシュクリアや再インストールを確認し、状況を報告してください。",
         "2026-06-21 10:00:00"),
        ("incident", "INC0001005", 15, "public_comment",
         "ベンダー対応待ちのため、解決まで少しお時間をいただいております。一時的な回避策として、Teamsアプリを完全終了後に再起動する方法をお試しください。",
         "2026-06-21 14:00:00"),
        # INC0001006 cat2 in_progress assigned=15(清水) (3件: 2wn+1pc)
        # group=2: leader=4(田中), member=15(清水),18(木村)
        ("incident", "INC0001006", 1, "work_note",
         "INC0001006 が作成されました。コミュニケーション基盤チームに自動アサインされました。",
         "2026-06-21 14:05:00"),
        ("incident", "INC0001006", 1, "work_note",
         "清水 隆さんにアサインします。SharePointの外部共有アクセス拒否問題を対応してください。",
         "2026-06-21 14:10:00"),
        ("incident", "INC0001006", 15, "public_comment",
         "外部共有リンクのアクセス問題を調査中です。Azure ADのゲストアクセスポリシーを確認しており、本日中に暫定対応方法をご案内します。",
         "2026-06-21 16:00:00"),
        # INC0001007 cat3/ITインフラ assigned=5(鈴木) (3件: 2wn+1pc)
        # group=3: leader=5(鈴木), member=16(井上),17(松本)
        ("incident", "INC0001007", 1, "work_note",
         "INC0001007 が作成されました。ITインフラチームに自動アサインされました。",
         "2026-06-21 11:05:00"),
        ("incident", "INC0001007", 1, "work_note",
         "鈴木 浩さんにアサインします。本社2Fのネットワーク速度低下を優先対応してください。",
         "2026-06-21 11:10:00"),
        ("incident", "INC0001007", 5, "public_comment",
         "原因を特定しました。L2スイッチのポート障害により交換部品を手配中です。それまでの間は別のスイッチポートを使用した迂回経路で対応します。復旧まで2〜3営業日お待ちください。",
         "2026-06-21 16:00:00"),
        # INC0001008 cat3 in_progress assigned=16(井上) (3件: 2wn+1pc)
        # group=3: leader=5(鈴木), member=16(井上),17(松本)
        ("incident", "INC0001008", 1, "work_note",
         "INC0001008 が作成されました。ITインフラチームに自動アサインされました。",
         "2026-06-21 09:05:00"),
        ("incident", "INC0001008", 5, "work_note",
         "井上さん、在宅勤務者全員のVPN接続問題を緊急対応してください。VPN集約装置のセッション数上限を確認し、状況を報告してください。",
         "2026-06-21 09:20:00"),
        ("incident", "INC0001008", 16, "public_comment",
         "VPN接続の問題を調査中です。接続が切れた場合は5分待ってから再接続をお試しください。引き続き原因の調査を続けます。",
         "2026-06-21 11:00:00"),
        # INC0001009 cat3 new (2件: 1wn+1pc)
        # group=3: leader=5(鈴木), member=16(井上),17(松本)
        ("incident", "INC0001009", 1, "work_note",
         "INC0001009 が作成されました。ITインフラチームに自動アサインされました。",
         "2026-06-22 10:35:00"),
        ("incident", "INC0001009", 5, "public_comment",
         "現在調査中です。リモートで設定確認を行いますので、PCの電源を入れたままにしておいてください。",
         "2026-06-22 13:00:00"),
        # INC0001010 cat3 assigned=5(鈴木) (3件: 2wn+1pc)
        # group=3: leader=5(鈴木), member=16(井上),17(松本)
        ("incident", "INC0001010", 1, "work_note",
         "INC0001010 が作成されました。ITインフラチームに自動アサインされました。",
         "2026-06-22 14:05:00"),
        ("incident", "INC0001010", 1, "work_note",
         "鈴木 浩さんにアサインします。ファイアウォールの大量ドロップログを優先調査してください。",
         "2026-06-22 14:10:00"),
        ("incident", "INC0001010", 5, "public_comment",
         "ファイアウォールの設定を更新し、不審な通信を遮断しました。外部からのポートスキャン攻撃への対策が完了しています。引き続き監視を継続します。",
         "2026-06-23 09:00:00"),
        # INC0001011 cat3 in_progress critical assigned=16(井上) (3件: 3wn+0pc)
        # group=3: leader=5(鈴木), member=16(井上),17(松本)
        ("incident", "INC0001011", 1, "work_note",
         "INC0001011 が作成されました。ITインフラチームに自動アサインされました。",
         "2026-06-22 17:05:00"),
        ("incident", "INC0001011", 5, "work_note",
         "Priority 1-Critical。井上さん、データセンターコアスイッチ障害を緊急対応してください。STPループの確認と収束を最優先でお願いします。",
         "2026-06-22 17:10:00"),
        ("incident", "INC0001011", 16, "work_note",
         "コアスイッチのSTPループを確認。特定ポートをシャットダウンしループを収束させました。サーバー到達性を確認中。10台中8台は復旧。残り2台（SRV-APP-003, SRV-DB-001）への接続が不安定。ベンダーのオンサイトサポートを要請。",
         "2026-06-22 17:20:00"),
        # INC0001012 cat6/情報セキュリティ new (3件: 2wn+1pc)
        # group=6: leader=8(渡辺), member=15(清水),17(松本)
        ("incident", "INC0001012", 1, "work_note",
         "INC0001012 が作成されました。情報セキュリティチームに自動アサインされました。",
         "2026-06-23 08:05:00"),
        ("incident", "INC0001012", 8, "work_note",
         "松本さん、全社フィッシングメールを緊急対応してください。ヘッダー解析とクリックした社員の特定を最優先でお願いします。インシデント対応手順書に従い証跡を保全してください。",
         "2026-06-23 08:15:00"),
        ("incident", "INC0001012", 17, "public_comment",
         "調査の結果、フィッシングメールへのリンクをクリックした可能性のある方には個別に連絡しております。不審なメールは開かずに情報セキュリティチームまでご報告ください。",
         "2026-06-23 12:00:00"),
        # INC0001013 cat6 in_progress assigned=8(渡辺) (4件: 3wn+1pc)
        # group=6: leader=8(渡辺), member=15(清水),17(松本)
        ("incident", "INC0001013", 1, "work_note",
         "INC0001013 が作成されました。情報セキュリティチームに自動アサインされました。",
         "2026-06-23 09:35:00"),
        ("incident", "INC0001013", 1, "work_note",
         "Priority 2-High。渡辺 純さんにアサインします。ランサムウェア感染疑いのため最優先での対応をお願いします。",
         "2026-06-23 09:38:00"),
        ("incident", "INC0001013", 8, "work_note",
         "PC-MKT-007をネットワークから物理隔離しました。フォレンジック調査の結果、感染経路は外部サイトからダウンロードされたマクロ付きExcelファイルと特定。ランサムウェアの暗号化の痕跡は確認されず、データ外部送信も検出されていない。JPCERT/CCへの報告を完了。",
         "2026-06-23 09:45:00"),
        ("incident", "INC0001013", 15, "public_comment",
         "セキュリティインシデントとして対応中です。代替PCを手配しますのでサービスデスクにお問い合わせください。",
         "2026-06-23 10:30:00"),
        # INC0001014 cat6 new (3件: 3wn+0pc)
        # group=6: leader=8(渡辺), member=15(清水),17(松本)
        ("incident", "INC0001014", 1, "work_note",
         "INC0001014 が作成されました。情報セキュリティチームに自動アサインされました。",
         "2026-06-23 06:05:00"),
        ("incident", "INC0001014", 8, "work_note",
         "松本さん、深夜の管理者アカウントへの不審ログイン試行を調査してください。SIEMのアラートを確認し、攻撃元のIPブロックと法務部への報告を進めてください。",
         "2026-06-23 07:00:00"),
        ("incident", "INC0001014", 17, "work_note",
         "SIEMのアラートを確認。管理者アカウントへの総当たり攻撃と判断。アカウントを一時ロックし送信元IPをブロックしました。試行回数は1時間で847回すべて失敗を確認。アカウントロックポリシーが適切に機能していました。法務部・コンプライアンス部に報告済み。",
         "2026-06-23 09:00:00"),
        # INC0001015 cat6 on_hold assigned=15(清水) (3件: 3wn+0pc)
        # group=6: leader=8(渡辺), member=15(清水),17(松本)
        ("incident", "INC0001015", 1, "work_note",
         "INC0001015 が作成されました。情報セキュリティチームに自動アサインされました。",
         "2026-06-23 10:05:00"),
        ("incident", "INC0001015", 1, "work_note",
         "清水 隆さんにアサインします。営業資料の社外流出疑惑を調査してください。法務部とも連携して対応をお願いします。",
         "2026-06-23 10:10:00"),
        ("incident", "INC0001015", 15, "work_note",
         "DLPツールでの調査を開始しました。過去30日間の機密ファイルへのアクセスログを解析中。外部へのデータ送信はDLPポリシーでブロックされていることを確認。機密ファイルへの最終アクセスは3週間前、社内IPからのみ。法務部と連携して調査継続中。",
         "2026-06-23 11:00:00"),
        # INC0001016 cat9/ハードウェアサポート assigned=11(加藤) (3件: 2wn+1pc)
        # group=9: leader=11(加藤), member=18(木村)
        ("incident", "INC0001016", 1, "work_note",
         "INC0001016 が作成されました。ハードウェアサポートチームに自動アサインされました。",
         "2026-06-23 09:05:00"),
        ("incident", "INC0001016", 11, "work_note",
         "PC-LEGAL-004を持ち込みで確認しました。診断ツールの結果、HDDの不良セクターが原因と特定。バックアップ後にHDDを交換する方向で調整中。PCの交換が必要と判断し資産管理システムに申請を行いました。",
         "2026-06-23 10:00:00"),
        ("incident", "INC0001016", 18, "public_comment",
         "PC内のデータをバックアップします。本日中に代替PCをご用意できる見込みです。大変ご不便をおかけして申し訳ありません。",
         "2026-06-23 15:00:00"),
        # INC0001017 cat9 resolved assigned=18(木村) (2件: 1wn+1pc)
        # group=9: leader=11(加藤), member=18(木村)
        ("incident", "INC0001017", 1, "work_note",
         "INC0001017 が作成されました。ハードウェアサポートチームに自動アサインされました。",
         "2026-06-23 11:05:00"),
        ("incident", "INC0001017", 18, "public_comment",
         "キーボードを代替品に交換し正常動作を確認しました。水没した元のキーボードはメーカー修理（東京サービスセンター）に送付手配しました。ご不便をおかけしました。",
         "2026-06-23 15:00:00"),
        # INC0001018 cat9 new (2件: 2wn+0pc)
        # group=9: leader=11(加藤), member=18(木村)
        ("incident", "INC0001018", 1, "work_note",
         "INC0001018 が作成されました。ハードウェアサポートチームに自動アサインされました。",
         "2026-06-24 08:35:00"),
        ("incident", "INC0001018", 11, "work_note",
         "MFP-301の印刷スプールを確認しました。プリントサーバーとMFP間の通信エラーが多発しています。ファームウェアのバージョンが最新版から3世代古いことを確認。ファームウェアのアップデートで解消する可能性があるためメーカーサポートに連絡中。",
         "2026-06-24 09:00:00"),
        # INC0001019 cat9 resolved assigned=11(加藤) (2件: 1wn+1pc)
        # group=9: leader=11(加藤), member=18(木村)
        ("incident", "INC0001019", 1, "work_note",
         "INC0001019 が作成されました。ハードウェアサポートチームに自動アサインされました。",
         "2026-06-24 10:05:00"),
        ("incident", "INC0001019", 11, "public_comment",
         "外付けHDDの認識問題を解決しました。デバイスドライバーを最新版（v4.2.1）に更新したことで正常認識されるようになりました。",
         "2026-06-24 12:00:00"),
        # INC0001020 cat7/営業システム in_progress assigned=9(中村) (3件: 3wn+0pc)
        # group=7: leader=9(中村), member=16(井上)
        ("incident", "INC0001020", 1, "work_note",
         "INC0001020 が作成されました。営業システムチームに自動アサインされました。",
         "2026-06-10 10:05:00"),
        ("incident", "INC0001020", 1, "work_note",
         "中村 亮太さんにアサインします。SalesforceとSAPのデータ同期停止を優先対応してください。",
         "2026-06-10 10:10:00"),
        ("incident", "INC0001020", 9, "work_note",
         "Salesforce-SAP連携APIのバージョン不整合を確認。Salesforceのスプリング24アップデートでAPIレスポンスのフィールド名が変更されたことが原因。SAPのマッピング設定を修正する必要あり。ベンダーのサポートポータルにチケットを起票し対応を依頼中。",
         "2026-06-10 11:00:00"),
        # INC0001021 cat7 on_hold assigned=9(中村) (2件: 1wn+1pc)
        # group=7: leader=9(中村), member=16(井上)
        ("incident", "INC0001021", 1, "work_note",
         "INC0001021 が作成されました。営業システムチームに自動アサインされました。",
         "2026-06-05 11:05:00"),
        ("incident", "INC0001021", 9, "public_comment",
         "SFAアクセス権限の申請を受け付けました。部門長の承認が必要です。承認フローを起動しました。承認完了後に権限を設定します。",
         "2026-06-05 11:30:00"),
        # INC0001022 cat7 resolved assigned=16(井上) (2件: 1wn+1pc)
        # group=7: leader=9(中村), member=16(井上)
        ("incident", "INC0001022", 1, "work_note",
         "INC0001022 が作成されました。営業システムチームに自動アサインされました。",
         "2026-05-20 13:05:00"),
        ("incident", "INC0001022", 16, "public_comment",
         "営業ダッシュボードのグラフ表示問題を解決しました。ブラウザのキャッシュが古いChartライブラリを読み込んでいたことが原因でした。Ctrl+Shift+Rで解消します。",
         "2026-05-25 16:30:00"),
        # INC0001023 cat1/サービスデスク new (2件: 2wn+0pc)
        # group=1: leader=3(山田), member=13(小川),14(林)
        ("incident", "INC0001023", 1, "work_note",
         "INC0001023 が作成されました。サービスデスクに自動アサインされました。",
         "2026-06-15 09:05:00"),
        ("incident", "INC0001023", 3, "work_note",
         "ポータルの応答速度低下を確認しました。Webサーバーの監視ツールを確認したところ、午前9時〜11時のCPU使用率が90%を超えており、データベース接続プールが枯渇していることを確認。サーバーの増強またはキャッシュ設定の見直しをインフラチームに相談する予定。",
         "2026-06-15 09:30:00"),
        # INC0001024 cat1 closed assigned=3(山田) (2件: 1wn+1pc)
        # group=1: leader=3(山田), member=13(小川),14(林)
        ("incident", "INC0001024", 1, "work_note",
         "INC0001024 が作成されました。サービスデスクに自動アサインされました。",
         "2026-06-01 10:05:00"),
        ("incident", "INC0001024", 3, "public_comment",
         "共有フォルダへのアクセス権限付与が完了しました。Active Directoryの「総務部-共有フォルダ-ReadWrite」グループに追加し、アクセス可能なことを確認しました。",
         "2026-06-02 11:30:00"),
        # INC0001025 cat5/経理システム assigned=7(伊藤) (3件: 2wn+1pc)
        # group=5: leader=7(伊藤), member=14(林)
        ("incident", "INC0001025", 1, "work_note",
         "INC0001025 が作成されました。経理システムチームに自動アサインされました。",
         "2026-06-12 08:35:00"),
        ("incident", "INC0001025", 7, "work_note",
         "ADFS管理コンソールでトークン署名証明書の有効期限を確認。有効期限が本日00:00に切れていることを確認。新しい証明書の発行手続きを開始。月次締め処理に影響が出る可能性があるため経理部長に状況を共有し上位者にエスカレーション中。",
         "2026-06-12 09:15:00"),
        ("incident", "INC0001025", 14, "public_comment",
         "SAPへのアクセス認証に問題が発生しており、現在修復作業を行っています。月次締め処理については、対応完了後の日程調整をご検討ください。",
         "2026-06-12 13:00:00"),
        # INC0001026 cat5 resolved assigned=7(伊藤) (2件: 1wn+1pc)
        # group=5: leader=7(伊藤), member=14(林)
        ("incident", "INC0001026", 1, "work_note",
         "INC0001026 が作成されました。経理システムチームに自動アサインされました。",
         "2026-06-08 14:05:00"),
        ("incident", "INC0001026", 7, "public_comment",
         "経費精算の承認メール通知を修正しました。SMTPサーバーの認証方式がOAuth2.0に変更されていたが経費精算システムの設定が旧方式のままだったことが原因でした。現在は正常に通知が送信されています。",
         "2026-06-15 17:30:00"),
        # INC0001027 cat10/IT管理 in_progress assigned=12(吉田) (3件: 2wn+1pc)
        # group=10: leader=12(吉田), member=13(小川)
        ("incident", "INC0001027", 1, "work_note",
         "INC0001027 が作成されました。IT管理チームに自動アサインされました。",
         "2026-06-14 15:05:00"),
        ("incident", "INC0001027", 12, "work_note",
         "社員証と従業員番号で本人確認が完了。全社システムのパスワードリセットを実施。初回ログイン時に強制パスワード変更が求められる設定にした。あわせてMFAのスマートフォン認証アプリの再登録も実施。",
         "2026-06-14 15:30:00"),
        ("incident", "INC0001027", 13, "public_comment",
         "パスワードのリセットが完了しました。仮パスワードを別途メールでお送りします。初回ログイン時にパスワードの変更をお願いします。",
         "2026-06-15 10:30:00"),
        # INC0001028 cat10 on_hold assigned=12(吉田) (2件: 1wn+1pc)
        # group=10: leader=12(吉田), member=13(小川)
        ("incident", "INC0001028", 1, "work_note",
         "INC0001028 が作成されました。IT管理チームに自動アサインされました。",
         "2026-06-03 10:05:00"),
        ("incident", "INC0001028", 12, "public_comment",
         "アクセス権限付与申請を受け付けました。部門長の承認待ちとなっています。承認完了後、速やかに権限を設定いたします。",
         "2026-06-03 10:30:00"),
        # INC0001029 cat4/人事システム resolved assigned=6(佐藤) (2件: 1wn+1pc)
        # group=4: leader=6(佐藤), member=13(小川),15(清水)
        ("incident", "INC0001029", 1, "work_note",
         "INC0001029 が作成されました。人事システムチームに自動アサインされました。",
         "2026-06-10 11:05:00"),
        ("incident", "INC0001029", 6, "public_comment",
         "勤怠データの保存問題を解決しました。セッションタイムアウトを30分から120分に延長し、正常に保存されることを確認しました。ご不便をおかけしました。",
         "2026-06-16 14:30:00"),
        # INC0001030 cat8/調達システム closed assigned=10(小林) (2件: 1wn+1pc)
        # group=8: leader=10(小林), member=17(松本)
        ("incident", "INC0001030", 1, "work_note",
         "INC0001030 が作成されました。調達システムチームに自動アサインされました。",
         "2026-05-15 15:05:00"),
        ("incident", "INC0001030", 10, "public_comment",
         "EDI連携エラーを解決しました。取引先のEDIフォーマットがVer.3.2に更新されていたため変換設定を修正しました。正常に受注データが取り込めることを確認しました。",
         "2026-05-28 11:30:00"),
    ]

    await db.executemany(
        "INSERT INTO work_note (ticket_type, ticket_id, author_user_id, note_type, body, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        work_notes,
    )

    await db.commit()
