# RSS Feed Configuration Guide

## ファイル構造
```
data/feeds/
├── rss_sources.csv  # RSSフィード設定ファイル
└── README.md        # このファイル
```

## CSV設定項目

| 項目 | 説明 | 例 |
|------|------|-----|
| 種別 | サイトの分類 | 公式, 専門メディア, 国内専門メディア |
| サイト名 | 識別しやすいサイト名 | Google Search Central Blog |
| URL | RSSフィードのURL | https://developers.google.com/search/blog |
| 取得方式 | 取得方法（現在はRSSのみ） | RSS |
| 説明 | サイトの特徴・内容説明 | Google検索に関する公式アップデート情報 |
| 制約 | 利用規約・制限事項 | Creative Commons Attribution 4.0 License |
| 優先度 | 1=最高, 2=高, 3=中 | 1 |
| カテゴリ | official/media/expert/tool_vendor | official |
| 言語 | ja/en | en |

## 優先度別取得制限

- **優先度1（公式）**: 最大5フィード
- **優先度2（専門メディア）**: 最大10フィード  
- **優先度3（ツールベンダー）**: 最大5フィード

## 新しいフィード追加方法

1. `rss_sources.csv`を開く
2. 新しい行を追加し、上記項目を埋める
3. システム再起動で自動反映

## カテゴリ別重み設定

- **official**: 1.0（最高重み）
- **expert**: 0.9
- **media**: 0.8
- **tool_vendor**: 0.7

システムが自動的に優先度とカテゴリに基づいて情報を取得・評価します。