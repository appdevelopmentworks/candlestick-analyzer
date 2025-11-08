# TODO一覧

## 実装済み
- ウォッチリスト読込とメタデータ補完：`src/io_utils/csv_loader.py` がヘッダー自動判定・ティッカー正規化・市場推定を行い、`src/services/metadata.py` が DuckDB へ銘柄情報をキャッシュします。
- 価格キャッシュと再利用：`src/services/analyzer.py` が yfinance から取得した日足を `src/data/store.py` にアップサートし、再取得制御や鮮度判定を実装済みです。
- TA-Lib パターン検出とスコアリング：`src/analysis/patterns.py` と `src/analysis/scoring.py` が CDL 61種の検出、バイアスCSVからの補足情報付与、スコアの±5クリップまで完了しています。
- デスクトップUIの骨格：`src/ui/main.py` と `DetailPanel` / `StatusPanel` / 設定ダイアログがウォッチリスト読み込み、フィルタ、非同期解析、失敗銘柄再実行、ヒストリー表示をカバー済みです。
- 指数リスト連携：`src/services/index_service.py` と `src/io_utils/index_scraper.py` が S&P500 / 日経225 / 日経500 / JPX400 の構成銘柄取得とキャッシュ更新を実装済みです。
- ユーザー設定永続化：`src/services/user_settings.py` が UI 設定（自動解析、ハイライト閾値、パターン選択など）をホームディレクトリ配下に保存・復元します。
- エクスポート導線：ツールバー／メニューから表示中テーブルを CSV / Excel / JSON へ保存し、パス検証・上書き確認・失敗時ダイアログを実装済みです。
- ロギング初期化：`services.logging_setup.configure_logging` で `config.yaml` に基づくファイル出力、日次ローテーション、UI ログビュー連携を実現しています。
- 設定値の一元化：`AnalyzerService` が `config.yaml` の `fetch`／`analysis`／`app` セクションを読み込み、期間・並列数・リトライ・履歴・自動解析のデフォルトを同期します。
- エラーコード共通化：`domain/errors.py` に AppError を定義し、CSV読込・指数取得・解析処理でコード付き例外とガイダンス文・サポートリンク（`config.yaml` から動的参照）を UI/ログへ伝播するよう統一しました。
- テスト整備：CSVローダー／エクスポート機能／DuckDB入出力のユニットテストを `tests/` 配下に追加し、基本的な回帰をカバーしています。

## 未着手・優先候補
- パターン別リターン検証：vectorbt や backtesting.py を用いた翌日/5日/20日リターン統計の算出・レポート化。
- ルール合成と重みづけ学習：ADX/RSI/ボリンジャー等の補助指標を組み合わせたスコア最適化ロジック。
- 週足・分足対応と外部通知：時間足切替、メール/Slack通知、PDFレポート出力、Windows以外向けビルド。
- メタデータ取得方式の確定：yfinance の name/sector フィールド変動リスクに備えた代替ソース調査と切替機構。
- 指数スクレイピングの正式ソースと許諾整理：対象URLの安定性、利用規約確認、フェイルオーバー策定。
- ヘッダーレスCSVの扱い方針：自動推定ルールの明文化、ユーザーガイド更新、設定での挙動切替。
- UIテーマ/フォント指針：ライト/ダークテーマと日本語フォントの最終選定、設定メニュー反映。
