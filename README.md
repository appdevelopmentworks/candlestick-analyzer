# TA-Lib ローソク足アナライザー

ウォッチリスト CSV を読み込み、TA-Lib のローソク足パターン検出を行う PySide6 デスクトップアプリです。DuckDB での価格キャッシュやスコアリング、指数リストの取得、シグナル強度を 5 段階で可視化する UI を備えています。

## クイックスタート

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/app.py --csv samples/watchlist_with_header.csv
```

> **TA-Lib ネイティブライブラリ** を事前に導入してください（[パッケージング&依存ガイド](docs/packaging_guide.md#2-ta-lib-ネイティブライブラリ) 参照）。

## 主な機能

- **ウォッチリスト解析**: CSV/指数リストを読み込み、yfinance から最大 400 日分の日足を取得。DuckDB でキャッシュし再取得を最小化。
- **パターン検出**: TA-Lib の 61 種ロウソク足関数を最終バーに適用し、ヒットしたパターンとスコアを一覧・詳細表示。
- **スコアの5段階表示**: `Strong＋ / Mild＋ / Neutral / Mild− / Strong−` に分類し、テーブル行をカテゴリ別カラーでハイライト。
- **詳細チャート**: Matplotlib + mplfinance でローソク足を描画（価格:出来高=3:1）。タイトルは「コード 銘柄名」で表示。
- **ログ & 再実行**: 非同期解析中の進捗・エラーをステータスパネルに表示し、失敗銘柄だけの再解析が可能。
- **エクスポート**: 現在のフィルタ結果を CSV / Excel / JSON へ保存（上書き確認・失敗時ダイアログ付）。

## セットアップ

1. **TA-Lib ネイティブライブラリ** を OS ごとに導入（Windows は DLL、macOS/Linux はパッケージをインストール）。
2. 仮想環境を作成し依存をインストール。
3. 必要に応じて `config.yaml` を編集（タイムゾーン、ハイライト閾値、サポートリンクなど）。

> DuckDB キャッシュは `data/ohlcv.duckdb`。既存ファイルを共有する際は機密情報にご注意ください。

## `make` ターゲット

| ターゲット | 内容 |
|-----------|------|
| `make lint` | `python -m compileall src` で構文チェック |
| `make test` | `pytest` を実行（全テスト: 18 件） |
| `make run` | `python src/app.py --csv samples/watchlist_with_header.csv` |

## テスト

```bash
python -m pytest
```

- CSV ローダー、DuckDB リポジトリ、エクスポート処理、アナライザのサニタイズ処理など主要ロジックをカバー。
- `.pytest_cache/` やテスト生成物は `.gitignore` 済みです。

## パッケージング

配布方法や TA-Lib の導入手順は [docs/packaging_guide.md](docs/packaging_guide.md) にまとめています。Nuitka を利用した単一バイナリ化、PyInstaller での互換ビルド、DLL 配置の注意点などを参照してください。

## ディレクトリ構成（抜粋）

```
├── src/
│   ├── analysis/        # TA-Lib パターン検出・スコアリング
│   ├── data/            # DuckDB 永続化層
│   ├── services/        # 解析・メタデータ・設定
│   ├── ui/              # PySide6 UI コンポーネント
│   └── ...
├── resources/           # パターンバイアス定義 CSV
├── samples/             # ウォッチリスト例
├── docs/                # 要件定義・パッケージングガイド
└── tests/               # pytest テストスイート
```

## 設定メモ

- `config.yaml` の `support_links` / `app.error_support` でエラーコードごとのサポートURLを差し替え可能。
- `fetch.period_days` や `scoring.highlight_threshold_*` を調整することで、取得期間やスコア閾値を変更できます。
- yfinance から 0 が返る OHLC 値は自動補正していますが、異常値が継続する場合は再取得やデータクリーニングをご検討ください。

## ライセンス

このスターターキットは社内利用・学習用途を想定しています。必要に応じてライセンス文言を追加してください。
