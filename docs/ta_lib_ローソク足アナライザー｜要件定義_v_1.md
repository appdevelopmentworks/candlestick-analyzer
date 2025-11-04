# TA‑Lib ローソク足アナライザー｜要件定義 v1

最終更新: 2025-11-03 (Asia/Tokyo)
作成者: ChatGPT（GPT‑5 Thinking）

---

## 0. 目的とゴール
- **目的**: CSVで指定された銘柄群について日足データを取得し、**直近（最終バー）でヒットしたTA‑Libのローソク足パターン**を検出・可視化・エクスポートできるデスクトップアプリを提供する。
- **成功基準**:
  - CSVを読み込み、銘柄ごとの最終バーにおけるパターン検出結果（ヒット有無・方向・強度）と**総合スコア（−5〜+5）**を一覧化。
  - 任意銘柄の**チャート（ローソク・出来高・MA: 5/20/60）**で直近のヒット内容を説明付きで表示。
  - 取得と解析が**〜1,000銘柄**でも実用的な速度で完了（キャッシュ・並列化で最適化）。

---

## 1. スコープ
- **含む**: CSV読込 / yfinanceでの日足取得 / DuckDBキャッシュ / TA‑Lib全CDL（61種）検出 / スコアリング / 一覧・詳細UI / フィルタ＆ソート / エクスポート（CSV/Excel/JSON） / ログ / 主要指数リストのスクレイピング取得（S&P500, 日経225, 日経500）
- **含まない（v1では非対応）**: 通知（メール/Slack/LINE）、週足・分足、バックテスト、PDFレポート、自動売買連携

---

## 2. 入力仕様（CSV）
- **想定列**:
  - `ticker`（必須: 1列目。Yahoo表記: 例 米株`AAPL`、日株`7203.T`）
  - `name`（任意: 銘柄名。欠損時はyfinanceから取得）
  - `sector`（任意: セクター。欠損時はyfinanceから取得）
- 区切り: `,`（カンマ）/ 文字コード: UTF-8（BOM許容）
- ヘッダー行: ありを推奨。**なしの場合は自動推定**し、先頭行のカラム数・値パターンから `ticker` のみ行/ヘッダー有無を判定（先頭セルが英数字・記号のみで区切りが1列→ヘッダーなしと判断）。
- **欠損処理**: 2列目以降が欠損の場合、yfinanceの`info`/`fast_info`から補完（取得不可は空欄）

---

## 3. 対象市場とティッカー表記
- **対象市場**: 当面 **米株 + 日株**（欧州は次フェーズ）。
- **表記**: **Yahoo Finance準拠**（日株は `.T` サフィックスなど）。
- **市場推定ロジック**:
  - 末尾が`.T` → JP（Tokyo）
  - それ以外 → US（NYSE/Nasdaq 等）
  - 例外・将来拡張: 設定画面で市場マッピングを上書き可能

---

## 4. データ取得
- **データ源**: `yfinance`（無料 / 手軽）
- **期間**: 過去 **400 本**（営業日ベース、約1.5年）
- **足種**: **日足**（将来: 週足・分足オプション）
- **タイムゾーン**: 内部UTC、UI表示は **Asia/Tokyo**
- **更新**: 起動時に差分更新 + 「再取得」ボタン
- **並列化**: 同時 **5〜10**（設定可能）
- **リトライ/タイムアウト**: 失敗時指数バックオフで最大2回再試行

---

## 5. キャッシュ設計（DuckDB）
- **目的**: API負荷と待ち時間を削減し、再解析を高速化
- **ファイル**: `data/ohlcv.duckdb`
- **スキーマ（案）**:
  - `prices(symbol TEXT, date DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE, timezone TEXT, PRIMARY KEY(symbol, date))`
  - `metadata(symbol TEXT PRIMARY KEY, name TEXT, sector TEXT, market TEXT, last_updated TIMESTAMP)`
- **更新方針**: 不在データのみ取得、最終日比較で差分アップサート

---

## 6. パターン検出（TA‑Lib CDL 61種）
- **判定**: 各CDL関数は最終バーで **0/±100/±200** 等を返却。0は「不一致」。
- **強度**: `|値|/100` を強度倍率（1 or 2）として扱い、説明表示に反映。
- **対象**: v1は**全61種**（UIでON/OFF切替）。
- **方向衝突**: 同日で強弱が混在した場合は**合算で相殺**し、詳細内訳を併記。

### 6.1 スコアリング仕様（−5〜+5）
1. **ベーススコア**: 各パターンの経験則バイアス（−5〜+5）を事前表（同梱CSV）で定義。
2. **強度補正**: `strength = abs(cdl_value)/100` を乗算（例: 200なら×2）。
3. **総合スコア**: 当日ヒットした全パターンの `ベース × 強度` を**合算**し、**−5〜+5にクリップ**。
4. **表示**: 「総合スコア: +3（内訳: Engulfing+3, Inverted Hammer+2, ShootingStar−2）」のように併記。
5. **閾値例**: 強気注目: `≥ +4`、弱気注目: `≤ −4`（UIでしきい値可変）
6. **ハイライト**: 一覧テーブルで総合スコアが `≥ +4` または `≤ −4` の行を色分け（例: +系=淡緑, −系=淡赤）。詳細パネルでも該当スコアを強調表示。

> 備考: ベーススコアは当社作成の**簡易バイアス表**（経験則）に基づく。実運用ではバックテストで再学習（将来フェーズ）。

---

## 7. UI/UX（PySide6 / Qt）

### 7.1 主要画面
- **A) 銘柄一覧**
  - 列: `Symbol / Name / Market / Sector / Close / 最終日ヒット数 / 総合スコア / 最終更新日`
  - 検索/フィルタ: 市場（US/JP）、スコア範囲、強気/弱気、出来高急増、GAP有無、ヒット種類数、セクター
  - ソート: スコア降順、出来高、終値、ヒット数
- **B) 詳細パネル**
  - チャート: **ローソク + 出来高 + MA(5/20/60)**、当日ヒット箇所にアイコン/マーカー
  - パターン内訳: ヒット関数名、強弱、`cdl値`、**説明テキスト（次にどう動きやすいか）**
  - 直近N日（例: 20日）のパターン履歴タイムライン
- **C) ログ/エラー**
  - API取得失敗、CSV不整合、パースエラーを一覧表示

### 7.2 操作系
- メニュー: 「CSVを開く」「指数リストから選ぶ（S&P500/日経225/日経500）」「再取得」「エクスポート（CSV/Excel/JSON）」
- ステータスバー: 取得進捗（並列数、残り件数、失敗件数）
- 設定ダイアログ: 並列数、データ期間、対象パターンON/OFF、スコア閾値

### 7.3 テーマとフォント
- **テーマ**: **ライト**固定（v1）。
- **フォント**: 読みやすさ優先（Windows例: "Yu Gothic UI", "Meiryo", "Segoe UI"）。日本語表示のにじみを抑えるサイズ・ウェイトをプリセット。

## 8. 主要指数リストの取得（オプションボタン)
 主要指数リストの取得（オプションボタン)
- **対象**: S&P500 / 日経225 / 日経500
- **取得元**:
  - **S&P500**: Wikipedia（従来通り、ティッカーはYahoo表記へ正規化）
  - **日経500**: Nikkei公式ページ https://www.nikkei.com/markets/kabu/nidxprice/?StockIndex=N500
  - **日経225**: Nikkei公式ページ https://www.nikkei.com/markets/kabu/nidxprice/
- **方法（v1）**: 上記ページを**スクレイピング**し、ティッカー列へ正規化（Yahoo表記）。
- **更新**: 手動「再取得」ボタン。キャッシュ: `data/indexlists.duckdb`
- **注意**: ページ構造変化に備え、柔軟な列マッピング・フォールバック実装（例: テーブル検出のCSS/見出しパターン複数対応）。

---

## 9. エクスポート
- **対応形式**: CSV / Excel（.xlsx） / JSON
- **内容**: 一覧テーブルの現在フィルタ状態をそのまま出力。詳細パネルのスクリーンショットは将来対応。

---

## 10. ログ・監査
- **ログレベル**: INFO/DEBUG（UI切替）
- **出力**: `logs/app.log`、ローテーション**7世代**
- **内容**: 取得URL・所要時間・失敗理由・再試行回数・キャッシュ命中率

---

## 11. エラー処理
- CSV不正: 行単位でスキップし、理由をログとUIトーストで通知
- ティッカー無効/データ欠損: 可能な最終営業日を採用。UIに**「最終日」明記**
- TA‑Lib未初期化/共有ライブラリ欠落: 初回起動時に自己診断ダイアログを表示

---

## 12. アーキテクチャ
- **言語/環境**: Python **3.11**（TA‑Lib互換のため）、Windows 10/11
- **主要ライブラリ**: pandas / numpy / yfinance / TA‑Lib / DuckDB / PySide6 / (matplotlib + mplfinance)
- **構成**:
  - `io/` CSV & 指数スクレイパ
  - `data/` DuckDB層（価格・メタデータ）
  - `analysis/` TA‑Libパターン検出・スコアリング
  - `ui/` PySide6ビュー・ViewModel（MVVM）
  - `export/` エクスポート機能
  - `resources/` ベーススコア表（−5〜+5）CSV

### 12.1 疑似コード（最終日判定）
```pseudo
for symbol in symbols:
  df = load_prices_from_cache_or_yf(symbol, period=400d)
  last = df.iloc[-1]
  hits = []
  for cdl_fn in CDL_FUNCTIONS:
    v = cdl_fn(df.open, df.high, df.low, df.close).iloc[-1]  # 0/±100/±200
    if v != 0:
      base = SCORE_TABLE[cdl_fn]            # −5〜+5
      strength = abs(v) / 100               # 1 or 2
      signed = (1 if v>0 else -1) * abs(base)
      hits.append({fn: cdl_fn, value: v, base: base, score: signed * strength})
  total = clip(sum(h.score for h in hits), -5, +5)
  save_result(symbol, total, hits, last_date)
```

---

## 13. 配布
- **パッケージング**: 推奨 **Nuitka**（パフォーマンス・配布サイズ）。互換優先時はPyInstaller。
- **TA‑Lib同梱**: Windows向けにバンドル（`ta_lib` DLL/静的ライブラリ）。初回起動時に自己診断。

---

## 14. 受け入れ基準（Acceptance Criteria）
1. CSVを選択して読み込むと、**1,000銘柄**まで一覧が生成される。
2. 各行で**最終日ヒット数**と**総合スコア（−5〜+5）**が表示され、ソート可能。
3. 任意銘柄を選ぶと、**ローソク + 出来高 + MA(5/20/60)** のチャートと、ヒット内訳・説明文が表示される。
4. エクスポート（CSV/Excel/JSON）が現在のフィルタ状態で出力される。
5. 再取得ボタン実行で差分更新され、ログに結果が記録される。
6. S&P500/日経225/日経500 ボタンからリストを読み込み、同等の分析が実行できる。

---

## 15. テスト観点
- **ユニット**: CSVパーサ、シンボル正規化、CDLごとの最終値計算、スコア合算・クリップ
- **結合**: キャッシュ→解析→UI反映のエンドツーエンド
- **回帰**: 主要指数リストスクレイピングのスキーマ変化耐性
- **パフォーマンス**: 1,000銘柄での処理時間・並列設定の効果
- **異常系**: 欠損・無効ティッカー・ネットワーク障害・市場休日

---

## 16. セキュリティ & ライセンス
- yfinance/Wikipediaの利用規約遵守、過剰なスクレイピング回避（レート制御）
- ログにAPIキー等の秘匿情報は記録しない（本v1では未使用）

---

## 17. 今後の拡張
- バックテスト（vectorbt/backtesting.py）でパターン別の翌日/5日/20日リターン統計
- ルール合成（ADX/RSI/ボリンジャー等）と重み学習
- 週足・分足対応、通知連携、PDFレポート、マルチOS対応

---

## 18. 未決定・要確認事項
- セクター・銘柄名の取得における**yfinanceのフィールド確定**（`info`は予告なく変化の可能性）。代替: 有料APIや別ソース検討
- スクレイピングの**正式取得元URL**と許諾範囲
- CSVにヘッダーがないケースの扱い（自動推定 or 事前フォーマット固定）
- UIテーマ（ライト/ダーク）とフォント（日本語表示品質）

---

### 付録A: ベーススコア表（−5〜+5）
- 同梱CSV: `resources/cdl_bias_ja.csv`（前回ご提供の「簡易バイアス＆数値化表」をそのまま採用）
  - 例: `CDLENGULFING(bull)=+3, bear=−3` / `CDLKICKINGBYLENGTH(bull)=+5, bear=−5` など

### 付録B: 画面モック（簡易）
- 一覧: DataTable + 条件フィルタ（左パネル）+ ステータスバー
- 詳細: 上部にチャート、下部に当日ヒット内訳と説明、右側に履歴タイムライン

---

## 19. Codex向け 開発ドキュメント・スターターキット（v0）
**目的**: 要件定義をもとに、Codexでの実装を円滑に進めるための雛形セット。

### 19.1 基本設計書（skeleton）
- **アーキテクチャ**: MVVM（ui/viewmodel/analysis/data/io）
- **主要モジュールとI/F**
  - `io.csv_loader.load_symbols(path) -> List[SymbolRecord]`
  - `io.index_scraper.fetch_sp500() -> pd.DataFrame`
  - `io.index_scraper.fetch_nikkei225() / fetch_nikkei500()`
  - `data.store.PricesRepo`（DuckDB: upsert/get_range/get_latest）
  - `analysis.patterns.detect_all(df_ohlc) -> List[Hit]`
  - `analysis.scoring.score(hits) -> int`（−5〜+5）
  - `ui.viewmodel.MainVM`（検索/フィルタ/並列取得の進捗）

### 19.2 データ定義書（DuckDB DDL）
```sql
CREATE TABLE IF NOT EXISTS prices (
  symbol TEXT,
  date   DATE,
  open   DOUBLE,
  high   DOUBLE,
  low    DOUBLE,
  close  DOUBLE,
  volume DOUBLE,
  timezone TEXT,
  PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS metadata (
  symbol TEXT PRIMARY KEY,
  name   TEXT,
  sector TEXT,
  market TEXT,
  last_updated TIMESTAMP
);
```

### 19.3 設定ファイル仕様（config.yaml）
```yaml
app:
  timezone: Asia/Tokyo
  theme: light
  fonts: ["Yu Gothic UI", "Meiryo", "Segoe UI"]
fetch:
  period_days: 400
  parallel_max: 8
  retry:
    max_attempts: 2
    backoff: 1.6
scoring:
  highlight_threshold_pos: 4
  highlight_threshold_neg: -4
  clip_min: -5
  clip_max: 5
cache:
  duckdb_path: data/ohlcv.duckdb
logging:
  level: INFO
  path: logs/app.log
  rotate_keep: 7
```

### 19.4 TA‑Lib マッピング仕様
- `resources/cdl_bias_ja.csv` を同梱（関数名/英名/日本語/ベーススコア/説明）
- 出力の`cdl値`は `strength = abs(val)/100` として倍率化

### 19.5 エラー設計（例）
| Code | 概要 | ユーザー表示 | 対応 |
|---|---|---|---|
| E-CSV-HEADER | ヘッダー推定失敗 | CSVの先頭行を確認してください | サンプルCSVへのリンク表示 |
| E-YF-404 | yfinance取得失敗 | データ取得に失敗しました | リトライとログ参照案内 |
| E-TA-LIB | TA‑Lib未初期化 | TA‑Libが使用できません | セットアップ手順表示 |

### 19.6 UI定義（主要テーブル列）
- 一覧: `Symbol, Name, Market, Sector, Close, Hits(#), Score, LastDate`
- 詳細: チャート(MA 5/20/60), 当日ヒット一覧（関数名/方向/値/説明）

### 19.7 テスト計画（要約）
- 単体: CSV推定・スクレイピング・スコア合算
- 結合: 取得→保存→検出→表示のE2E
- パフォーマンス: 1,000銘柄×400本での所要時間

### 19.8 Codexプロンプト雛形
**例: モジュール実装依頼**
```
あなたは熟練Pythonエンジニアです。次の仕様で関数を実装してください。
- 入力: ...（I/F定義に準拠）
- 例外: 上記エラー設計に従って例外型/メッセージを統一
- 型ヒント/Docstring/単体テスト（pytest）を同梱
- Black/Ruffに準拠
```
**例: 画面実装依頼**
```
PySide6でDataTableとチャートビューを作成。config.yamlの値に従いテーマ/フォント設定。表の行ハイライトはscore閾値を使用。
```

### 19.9 サンプルCSV/固定値
- `samples/watchlist.csv`（ヘッダー有/無の両方パターン）
- `samples/cdl_bias_ja.csv`（前出の表を同梱）

