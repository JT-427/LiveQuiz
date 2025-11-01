# 即時問答系統

一個簡單的即時問答應用程式，支援多人同時參與的問答活動。

## 功能特色

### 管理頁面 (`/admin`)

- ✅ 新增/刪除題目（簡答題、選擇題、多選題）
- ✅ 設定題目回答時間限制
- ✅ 建立和管理活動
- ✅ 控制搶答開始/結束
- ✅ 查看回答紀錄

### 投影畫面 (`/display`)

- ✅ 顯示活動 QR Code
- ✅ 顯示活動統計數據（參與人數、回答數量）
- ✅ 顯示當前題目和倒數計時器

### 使用者畫面 (`/`)

- ✅ 輸入名字和小組加入活動
- ✅ 等待畫面
- ✅ 自動跳轉到回答頁面
- ✅ 倒數計時顯示
- ✅ 提交答案

## 系統需求

- Python 3.8+
- PostgreSQL 10+

## 安裝步驟

1. **安裝依賴套件**

```bash
pip install -r requirements.txt
```

2. **設定環境變數**

```bash
# 複製範例檔案
cp .env.example .env

# 編輯 .env 檔案，設定資料庫連線
DATABASE_URL=postgresql://username:password@localhost:5432/qna_db
SECRET_KEY=your-secret-key-here
```

3. **啟動應用程式**

> **注意**: 系統會自動建立資料庫和資料表，如果資料庫不存在會自動建立。如果自動建立失敗，請手動建立資料庫。

```bash
python app.py
```

5. **開啟瀏覽器**

- 管理介面: http://localhost:5000/admin
- 投影畫面: http://localhost:5000/display
- 使用者畫面: http://localhost:5000/

## 使用流程

1. **管理員操作**

   - 進入管理頁面 (`/admin`)
   - 在「題目管理」分頁新增題目
   - 在「活動管理」分頁建立新活動
   - 選擇活動進行管理，設定要使用的題目

2. **投影畫面設定**

   - 進入投影畫面 (`/display`)
   - 選擇活動
   - 選擇顯示模式（QR Code、統計、題目）

3. **使用者參與**
   - 掃描 QR Code 或輸入活動 ID
   - 輸入名字和小組名稱
   - 等待主持人開始搶答
   - 當搶答開始時自動跳轉到回答頁面
   - 在時間內提交答案

## 技術架構

- **後端**: Flask + Flask-SocketIO
- **資料庫**: PostgreSQL
- **前端**: HTML + CSS + JavaScript + Socket.IO
- **即時通訊**: WebSocket

## 資料庫結構

- `questions`: 題目表
- `activities`: 活動表
- `users`: 使用者表
- `answers`: 回答表

## 注意事項

- 請確保 PostgreSQL 服務正在運行
- **系統會自動建立資料庫**（如果不存在）
- 首次執行會自動建立資料表
- 如果自動建立資料庫失敗，請確保：
  - PostgreSQL 服務正在運行
  - DATABASE_URL 中的使用者有建立資料庫的權限
  - 或手動執行 `createdb <資料庫名稱>` 建立資料庫
- 建議在生產環境中使用更安全的 SECRET_KEY
- 如需部署，建議使用 Gunicorn 和 Nginx
