# パッケージング & 依存関係ガイド

本書は TA-Lib ローソク足アナライザーを配布する際のビルド手順と、依存ライブラリの整備手順をまとめたものです。

## 1. 共通準備

1. リポジトリのルートで仮想環境を作成し、有効化します。
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

2. 依存パッケージをインストールします。
   ```bash
   pip install -r requirements.txt
   ```

3. TA-Lib ネイティブライブラリをインストールします（次節参照）。

4. `python -m pytest` でユニットテストを実行し、すべて成功することを確認します。

## 2. TA-Lib ネイティブライブラリ

TA-Lib は Python パッケージだけではなく、プラットフォームごとのネイティブライブラリが必要です。環境ごとの代表的な導入手順は以下の通りです。

### Windows
- [TA-Lib ダウンロードページ](https://ta-lib.org/hdr_dw.html) から Windows 用バイナリ（例: `ta-lib-0.4.0-msvc.zip`）を取得し解凍します。
- `ta-lib` フォルダーを `C:\ta-lib` に配置し、以下の環境変数を設定します。
  ```text
  set TA_LIBRARY_PATH=C:\ta-lib\lib
  set TA_INCLUDE_PATH=C:\ta-lib\include
  ```
- 既に PowerShell や Git Bash を使用している場合は、`[Environment]::SetEnvironmentVariable` で永続化します。
- `pip install ta-lib` を再実行し、ネイティブバインディングが正しくリンクされることを確認します。

### macOS (Homebrew)
```bash
brew install ta-lib
export TA_LIBRARY_PATH="/opt/homebrew/opt/ta-lib/lib"
export TA_INCLUDE_PATH="/opt/homebrew/opt/ta-lib/include"
pip install ta-lib
```

### Ubuntu / Debian
```bash
sudo apt update
sudo apt install -y ta-lib
export TA_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu"
export TA_INCLUDE_PATH="/usr/include"
pip install ta-lib
```

### 動作確認
```bash
python - <<'PY'
import talib
print("TA-Lib version:", talib.__ta_version__)
PY
```

## 3. Nuitka によるビルド

パフォーマンスと単一ファイル配布を両立させるには Nuitka を推奨します。

### 3.1 追加依存のインストール
```bash
pip install nuitka ordered-set zstandard
```

### 3.2 ビルドコマンド例（Windows）
```bash
python -m nuitka \
  --onefile \
  --enable-plugin=pyside6 \
  --follow-imports \
  --include-data-dir=resources=resources \
  --include-data-dir=samples=samples \
  --include-data-file=config.yaml=config.yaml \
  --include-data-file=schema.sql=schema.sql \
  --windows-company-name="YourCompany" \
  --windows-product-name="Candlestick Analyzer" \
  --windows-file-version=1.0.0 \
  --output-dir=build \
  src/app.py
```

生成物は `build/app.exe`（またはプラットフォームに応じたバイナリ）として出力されます。パッケージング後、次の項目を確認してください。

- `resources/`・`samples/`・`config.yaml` などのデータファイルが同梱されているか。
- TA-Lib DLL が解決されるか（Windows の場合は `DLLs` フォルダに配置するか PATH を設定）。
- 依存 DLL について `Dependency Walker` 等で欠落がないか。

### 3.3 macOS / Linux
基本的なオプションは同じですが、アイコン設定や署名が異なります。例：
```bash
python -m nuitka \
  --onefile \
  --enable-plugin=pyside6 \
  --follow-imports \
  --include-data-dir=resources=resources \
  --output-dir=build \
  src/app.py
```

実行ファイルを生成した後、`chmod +x build/app.bin` で実行権限を付与します。

## 4. PyInstaller を使う場合

互換性重視で PyInstaller を利用する場合の簡易手順です。

```bash
pip install pyinstaller
pyinstaller \
  --onefile \
  --name candlestick-analyzer \
  --add-data "resources;resources" \
  --add-data "samples;samples" \
  --add-data "config.yaml;." \
  --add-data "schema.sql;." \
  src/app.py
```

TA-Lib の DLL を実行ファイルと同じフォルダに置くか、`--paths` で DLL の場所を指定します。

## 5. 起動確認 & 自動テスト

1. `build/`（または `dist/`）に生成された実行ファイルで `--csv samples/watchlist_with_header.csv` を渡して起動確認。
2. アプリ内で指数リストや CSV ロード、解析、エクスポートが行えることを確認。
3. ユーザー環境に配布する前に、`python -m pytest` を再実行してユニットテストが全て成功していることを保証します。

## 6. 依存バージョンの管理

- `requirements.txt` を配布パッケージに同梱し、ローカル利用者が仮想環境内で同じ依存を再現できるようにします。
- CI/CD を導入する場合は、`pip-tools` や `poetry` で lock ファイルを生成することを検討してください。

## 7. トラブルシューティング

- **TA-Lib が見つからない**: `TA_LIBRARY_PATH` / `TA_INCLUDE_PATH` が正しく設定されているかを確認し、`talib.__ta_version__` が取得できることを事前にチェックします。
- **PySide6 の DLL が不足**: Nuitka の場合は `--enable-plugin=pyside6`、PyInstaller の場合は `--hidden-import` を追加し、`PySide6.QtGui`・`PySide6.QtWidgets` などのモジュールが同梱されているか確認します。
- **DuckDB ファイル**: 既存の `data/ohlcv.duckdb` を同梱する場合は、機密情報が含まれていないか再確認し、必要に応じて初期化スクリプトを用意します。

以上でパッケージングと依存関係の整備手順は完了です。環境や配布先に応じて適宜カスタマイズしてください。
