# Repository Guidelines

## Project Structure & Module Organization
- アプリ本体は `src/` 以下にあり、UI (`src/ui`)、データ層 (`src/data`)、入出力 (`src/io_utils`)、解析 (`src/analysis`)、エクスポート (`src/export`) に分割されています。
- `resources/` にスコアリング用バイアスCSV、`samples/` にウォッチリスト例、`config.yaml` と `schema.sql` に設定とスキーマを定義しています。
- テストは `tests/` 配下に置き、対象モジュールのパスに合わせて `src` をインポートできる構成を維持してください。

## Build, Test, and Development Commands
- `make lint` : `python -m compileall src` で構文チェックを実行します。
- `make test` : `pytest` を起動し、`tests/` のユニットテストを走らせます。
- `make run` : `python src/app.py --csv samples/watchlist_with_header.csv` を実行してUIを起動します（`CSV=path.csv` で差し替え可）。

## Coding Style & Naming Conventions
- Python 3.11+ を対象に4スペースインデントで記述し、PEP 8 を基準に読みやすさを優先してください。
- モジュール・パッケージはスネークケース（例: `price_fetcher.py`）、クラスはパスカルケース、定数は大文字スネークを推奨します。
- 可能な範囲で型ヒントを付与し、外部APIやデータフレーム操作には簡潔なコメントで意図を補足します。

## Testing Guidelines
- テストフレームワークは `pytest` を使用します。ファイル名は `test_*.py`、関数は `test_*` で命名してください。
- テストは必ずローカルで `make test` を実行し、失敗したケースを解消してからコミットします。
- データ依存のテストはサンプルCSVやモック化したDataFrameで完結させ、外部APIには依存しないようにしてください。

## Commit & Pull Request Guidelines
- コミットメッセージは動詞始まりで要約を1行目に書き、必要なら箇条書きで詳細を追記します。
- Pull Request には変更概要、テスト結果（例: `make test` の実行可否）、関連Issueやスクリーンショット（UI変更時）を記載してください。
- 影響範囲が広い変更はリリースノート向けに「前後比較」や「リスク／ロールバック手順」をまとめ、レビュアーが判断しやすい情報を添えます。

## Security & Configuration Tips
- 認証情報やAPIキーは `config.yaml` や環境変数に委ね、リポジトリへ直書きしないでください。
- DuckDBファイル（デフォルト: `data/ohlcv.duckdb`）は開発用のキャッシュです。共有が必要な場合は明示的にエクスポートし、機密データを含めないよう注意してください。
