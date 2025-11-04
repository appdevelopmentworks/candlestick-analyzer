CREATE TABLE IF NOT EXISTS prices (symbol TEXT, date DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE, timezone TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS metadata (symbol TEXT PRIMARY KEY, name TEXT, sector TEXT, market TEXT, last_updated TIMESTAMP);
