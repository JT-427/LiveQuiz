from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
from dotenv import load_dotenv
import qrcode
import io
import base64
import json
from datetime import datetime
from urllib.parse import urlparse

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
socketio = SocketIO(app, cors_allowed_origins="*")

# 建立資料庫（如果不存在）
def create_database_if_not_exists():
    database_url = os.getenv('DATABASE_URL', 'postgresql://localhost/qna_db')
    parsed = urlparse(database_url)
    
    # 解析資料庫名稱
    db_name = parsed.path[1:] if parsed.path and len(parsed.path) > 1 else 'qna_db'  # 移除開頭的 /
    
    try:
        # 嘗試連接到目標資料庫
        conn = psycopg2.connect(database_url)
        conn.close()
        print(f"✓ 資料庫 '{db_name}' 已存在")
        return
    except psycopg2.OperationalError as e:
        error_msg = str(e).lower()
        # 檢查是否是資料庫不存在的錯誤
        if 'does not exist' in error_msg or 'database' in error_msg:
            # 資料庫不存在，需要建立
            print(f"資料庫 '{db_name}' 不存在，正在建立...")
            try:
                # 建立連接到預設資料庫（postgres）的 URL，保留使用者名稱、密碼、主機、端口
                if parsed.path:
                    # 替換路徑部分的資料庫名稱
                    default_db_url = database_url.rsplit('/', 1)[0] + '/postgres'
                else:
                    default_db_url = database_url + '/postgres'
                
                # 連接到預設資料庫來建立新資料庫
                conn = psycopg2.connect(default_db_url)
                conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
                cur = conn.cursor()
                
                # 檢查資料庫是否真的不存在（避免權限錯誤被誤判）
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
                exists = cur.fetchone()
                
                if not exists:
                    cur.execute(f'CREATE DATABASE "{db_name}"')
                    print(f"✓ 資料庫 '{db_name}' 建立成功")
                else:
                    print(f"✓ 資料庫 '{db_name}' 已存在")
                
                cur.close()
                conn.close()
            except Exception as create_error:
                print(f"✗ 無法自動建立資料庫: {create_error}")
                print("提示：請確保 PostgreSQL 服務正在運行，並且有足夠的權限建立資料庫")
                print("或者您可以手動執行：createdb " + db_name)
                # 不拋出異常，讓使用者可以選擇手動建立資料庫
                return
        else:
            # 其他連線錯誤（如主機不可達、認證失敗等）
            print(f"✗ 無法連接到資料庫: {e}")
            print("請檢查 DATABASE_URL 設定和 PostgreSQL 服務狀態")
            raise

# 資料庫連線
def get_db_connection():
    database_url = os.getenv('DATABASE_URL', 'postgresql://localhost/qna_db')
    conn = psycopg2.connect(database_url)
    return conn

# 初始化資料庫
def init_db():
    # 先嘗試建立資料庫（如果不存在）
    create_database_if_not_exists()
    
    # 建立資料表
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 題目表
    cur.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            type VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            options JSONB,
            time_limit INTEGER,
            answer_limit INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 添加新欄位（如果不存在）- 用於資料庫遷移
    try:
        cur.execute('ALTER TABLE questions ADD COLUMN IF NOT EXISTS answer_limit INTEGER')
    except:
        pass
    
    # 活動表
    cur.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            status VARCHAR(20) DEFAULT 'preparing',
            current_question_id INTEGER,
            groups_count INTEGER,
            groups JSONB,
            display_mode VARCHAR(20) DEFAULT 'none',
            started_at TIMESTAMP,
            ended_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 添加新欄位（如果不存在）- 用於資料庫遷移
    try:
        cur.execute('ALTER TABLE activities ADD COLUMN IF NOT EXISTS groups_count INTEGER')
        cur.execute('ALTER TABLE activities ADD COLUMN IF NOT EXISTS groups JSONB')
        cur.execute('ALTER TABLE activities ADD COLUMN IF NOT EXISTS display_mode VARCHAR(20) DEFAULT \'none\'')
    except:
        pass
    
    # 使用者表
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            activity_id INTEGER REFERENCES activities(id),
            name VARCHAR(100) NOT NULL,
            group_name VARCHAR(100),
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 回答表
    cur.execute('''
        CREATE TABLE IF NOT EXISTS answers (
            id SERIAL PRIMARY KEY,
            activity_id INTEGER REFERENCES activities(id),
            question_id INTEGER REFERENCES questions(id),
            user_id INTEGER REFERENCES users(id),
            answer_text TEXT,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    cur.close()
    conn.close()

@app.route('/')
def index():
    return render_template('user.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/admin/activity/<int:activity_id>')
def admin_activity(activity_id):
    return render_template('admin_activity.html', activity_id=activity_id)

@app.route('/display')
def display():
    return render_template('display.html')

# API: 取得所有題目
@app.route('/api/questions', methods=['GET'])
def get_questions():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM questions ORDER BY created_at DESC')
    questions = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(q) for q in questions])

# API: 取得使用者的回答（用於檢查回答次數）
@app.route('/api/answers', methods=['GET'])
def get_answers():
    question_id = request.args.get('question_id', type=int)
    user_id = request.args.get('user_id', type=int)
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if question_id and user_id:
        cur.execute('''
            SELECT * FROM answers 
            WHERE question_id = %s AND user_id = %s
            ORDER BY submitted_at DESC
        ''', (question_id, user_id))
    else:
        cur.execute('SELECT * FROM answers ORDER BY submitted_at DESC LIMIT 100')
    
    answers = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(a) for a in answers])

# API: 新增題目
@app.route('/api/questions', methods=['POST'])
def create_question():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    answer_limit = data.get('answer_limit')
    if answer_limit:
        answer_limit = int(answer_limit)
    else:
        answer_limit = None
    cur.execute('''
        INSERT INTO questions (type, content, options, time_limit, answer_limit)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    ''', (data['type'], data['content'], 
          json.dumps(data.get('options', [])), 
          data.get('time_limit'),
          answer_limit))
    question_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    socketio.emit('question_created', {'id': question_id})
    return jsonify({'id': question_id}), 201

# API: 更新題目
@app.route('/api/questions/<int:question_id>', methods=['PUT'])
def update_question(question_id):
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    
    answer_limit = data.get('answer_limit')
    if answer_limit:
        answer_limit = int(answer_limit)
    else:
        answer_limit = None
    
    cur.execute('''
        UPDATE questions 
        SET type = %s, content = %s, options = %s, time_limit = %s, answer_limit = %s
        WHERE id = %s
    ''', (data['type'], data['content'], 
          json.dumps(data.get('options', [])), 
          data.get('time_limit'),
          answer_limit,
          question_id))
    conn.commit()
    cur.close()
    conn.close()
    socketio.emit('question_updated', {'id': question_id})
    return jsonify({'success': True})

# API: 刪除題目
@app.route('/api/questions/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM questions WHERE id = %s', (question_id,))
    conn.commit()
    cur.close()
    conn.close()
    socketio.emit('question_deleted', {'id': question_id})
    return jsonify({'success': True})

# API: 取得所有活動
@app.route('/api/activities', methods=['GET'])
def get_activities():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM activities ORDER BY created_at DESC')
    activities = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(a) for a in activities])

# API: 建立活動
@app.route('/api/activities', methods=['POST'])
def create_activity():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    groups_count = data.get('groups_count')
    groups = data.get('groups', [])
    
    if groups_count:
        groups_count = int(groups_count)
    
    # 如果提供了小組名稱陣列，使用它；否則根據數量生成
    if groups and isinstance(groups, list):
        groups_json = json.dumps(groups)
        if not groups_count:
            groups_count = len(groups)
    else:
        groups_json = None
    
    cur.execute('''
        INSERT INTO activities (name, status, groups_count, groups)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    ''', (data['name'], 'preparing', groups_count, groups_json))
    activity_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    socketio.emit('activity_created', {'id': activity_id})
    return jsonify({'id': activity_id}), 201

# API: 取得活動詳情
@app.route('/api/activities/<int:activity_id>', methods=['GET'])
def get_activity(activity_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # 取得活動資訊
    cur.execute('SELECT * FROM activities WHERE id = %s', (activity_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return jsonify({'error': 'Activity not found'}), 404
    activity = dict(row)
    
    # 取得使用者
    cur.execute('SELECT * FROM users WHERE activity_id = %s', (activity_id,))
    activity['users'] = [dict(u) for u in cur.fetchall()]
    
    # 取得所有回答（所有題目）
    cur.execute('''
        SELECT a.*, u.name as user_name, u.group_name
        FROM answers a
        JOIN users u ON a.user_id = u.id
        WHERE a.activity_id = %s
        ORDER BY a.question_id, a.submitted_at DESC
    ''', (activity_id,))
    activity['answers'] = [dict(a) for a in cur.fetchall()]
    
    cur.close()
    conn.close()
    return jsonify(activity)

# API: 更新活動狀態
@app.route('/api/activities/<int:activity_id>', methods=['PUT'])
def update_activity(activity_id):
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    
    updates = []
    values = []
    
    if 'status' in data:
        updates.append('status = %s')
        values.append(data['status'])
        if data['status'] == 'active':
            updates.append('started_at = CURRENT_TIMESTAMP')
    
    if 'current_question_id' in data:
        updates.append('current_question_id = %s')
        values.append(data['current_question_id'])
    
    if 'groups_count' in data:
        updates.append('groups_count = %s')
        values.append(data['groups_count'] if data['groups_count'] else None)
    
    if 'groups' in data:
        updates.append('groups = %s')
        if data['groups']:
            groups_json = json.dumps(data['groups']) if isinstance(data['groups'], list) else data['groups']
            values.append(groups_json)
            # 同時更新 groups_count
            if 'groups_count' not in data:
                updates.append('groups_count = %s')
                values.append(len(data['groups']) if isinstance(data['groups'], list) else None)
        else:
            values.append(None)
    
    if 'display_mode' in data:
        updates.append('display_mode = %s')
        values.append(data['display_mode'])
    
    # projected_answer 不需要存儲到數據庫，只通過 WebSocket 發送
    
    if updates:
        values.append(activity_id)
        cur.execute(f'UPDATE activities SET {", ".join(updates)} WHERE id = %s', values)
        conn.commit()
    
    cur.close()
    conn.close()
    
    # 廣播狀態更新
    socketio.emit('activity_updated', {'activity_id': activity_id, 'updates': data})
    
    # 如果是顯示模式更新，也要廣播給投影畫面
    if 'display_mode' in data:
        display_data = {
            'activity_id': activity_id,
            'display_mode': data['display_mode']
        }
        # 如果有回答數據，一併發送
        if 'projected_answer' in data:
            display_data['answer'] = data['projected_answer']
        # 如果有統計數據限制筆數，一併發送
        if 'stats_limit' in data:
            display_data['stats_limit'] = data['stats_limit']
        socketio.emit('display_update', display_data)
    # 如果狀態變為 active 且設置了題目，也要發送 display_update
    elif 'status' in data and data['status'] == 'active' and 'current_question_id' in data:
        # 檢查活動當前的 display_mode
        cur.execute('SELECT display_mode FROM activities WHERE id = %s', (activity_id,))
        row = cur.fetchone()
        if row:
            display_mode = dict(row).get('display_mode') or 'question'
            socketio.emit('display_update', {
                'activity_id': activity_id,
                'display_mode': display_mode
            })
    
    return jsonify({'success': True})

# API: 使用者加入活動
@app.route('/api/users', methods=['POST'])
def join_activity():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (activity_id, name, group_name)
        VALUES (%s, %s, %s)
        RETURNING id
    ''', (data['activity_id'], data['name'], data.get('group_name')))
    user_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    
    socketio.emit('user_joined', {'activity_id': data['activity_id'], 'user_id': user_id})
    return jsonify({'id': user_id}), 201

# API: 提交回答
@app.route('/api/answers', methods=['POST'])
def submit_answer():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # 檢查題目的回答次數限制
    cur.execute('SELECT answer_limit FROM questions WHERE id = %s', (data['question_id'],))
    question = cur.fetchone()
    
    if question and question.get('answer_limit'):
        answer_limit = question['answer_limit']
        # 檢查該用戶已經回答了幾次
        cur.execute('''
            SELECT COUNT(*) as count 
            FROM answers 
            WHERE question_id = %s AND user_id = %s
        ''', (data['question_id'], data['user_id']))
        answer_count = cur.fetchone()['count']
        
        if answer_count >= answer_limit:
            cur.close()
            conn.close()
            return jsonify({
                'error': f'您已達到此題的回答次數限制（{answer_limit}次）',
                'error_code': 'ANSWER_LIMIT_EXCEEDED'
            }), 400
    
    # 插入新的回答
    cur.execute('''
        INSERT INTO answers (activity_id, question_id, user_id, answer_text)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    ''', (data['activity_id'], data['question_id'], 
          data['user_id'], data['answer_text']))
    answer_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()
    
    socketio.emit('answer_submitted', {
        'activity_id': data['activity_id'],
        'question_id': data['question_id']
    })
    return jsonify({'id': answer_id}), 201

# API: 取得活動統計
@app.route('/api/activities/<int:activity_id>/stats', methods=['GET'])
def get_activity_stats(activity_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # 獲取當前題目ID（如果有）
    cur.execute('SELECT current_question_id FROM activities WHERE id = %s', (activity_id,))
    activity = cur.fetchone()
    current_question_id = activity['current_question_id'] if activity else None
    
    # 使用者數量
    cur.execute('SELECT COUNT(*) as count FROM users WHERE activity_id = %s', (activity_id,))
    user_count = cur.fetchone()['count']
    
    # 回答數量
    cur.execute('SELECT COUNT(*) as count FROM answers WHERE activity_id = %s', (activity_id,))
    answer_count = cur.fetchone()['count']
    
    # 橫式長條圖：以每位使用者為單位統計該題回答數量
    user_stats = []
    if current_question_id:
        cur.execute('''
            SELECT u.id, u.name, u.group_name, COUNT(a.id) as answer_count
            FROM users u
            LEFT JOIN answers a ON a.user_id = u.id AND a.question_id = %s AND a.activity_id = %s
            WHERE u.activity_id = %s
            GROUP BY u.id, u.name, u.group_name
            ORDER BY answer_count DESC, u.name
        ''', (current_question_id, activity_id, activity_id))
        user_stats = [dict(row) for row in cur.fetchall()]
    
    # 直式長條圖：以小組為單位統計各組回答總量除以各組人數的平均每人答題數
    group_stats = []
    if current_question_id:
        cur.execute('''
            SELECT 
                COALESCE(u.group_name, '未分組') as group_name,
                COUNT(DISTINCT u.id) as member_count,
                COUNT(a.id) as total_answers,
                CASE 
                    WHEN COUNT(DISTINCT u.id) > 0 
                    THEN ROUND(COUNT(a.id)::numeric / COUNT(DISTINCT u.id), 2)
                    ELSE 0
                END as avg_answers_per_person
            FROM users u
            LEFT JOIN answers a ON a.user_id = u.id AND a.question_id = %s AND a.activity_id = %s
            WHERE u.activity_id = %s
            GROUP BY COALESCE(u.group_name, '未分組')
            ORDER BY group_name
        ''', (current_question_id, activity_id, activity_id))
        group_stats = [dict(row) for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    return jsonify({
        'user_count': user_count,
        'answer_count': answer_count,
        'current_question_id': current_question_id,
        'user_stats': user_stats,  # 橫式長條圖數據
        'group_stats': group_stats  # 直式長條圖數據
    })

# API: 生成 QR Code
@app.route('/api/activities/<int:activity_id>/qrcode', methods=['GET'])
def get_qrcode(activity_id):
    url = request.host_url + f'?activity={activity_id}'
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    img_base64 = base64.b64encode(img_io.getvalue()).decode()
    return jsonify({'qrcode': f'data:image/png;base64,{img_base64}', 'url': url})

# API: 取得活動的可用小組列表
@app.route('/api/activities/<int:activity_id>/groups', methods=['GET'])
def get_activity_groups(activity_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT groups_count, groups FROM activities WHERE id = %s', (activity_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    
    if not row:
        return jsonify({'error': 'Activity not found'}), 404
    
    groups_count = row['groups_count']
    
    # 如果有自訂的小組名稱，使用它；否則根據數量生成
    if row.get('groups'):
        try:
            import json
            groups = json.loads(row['groups']) if isinstance(row['groups'], str) else row['groups']
        except:
            groups = None
    else:
        groups = None
    
    if groups and isinstance(groups, list):
        # 使用自訂小組名稱
        group_list = groups
    elif groups_count:
        # 根據數量生成預設名稱
        group_list = [f'第{i}組' for i in range(1, groups_count + 1)]
    else:
        group_list = []
    
    return jsonify({'groups': group_list, 'groups_count': groups_count})

# WebSocket: 連線
@socketio.on('connect')
def handle_connect():
    emit('connected', {'status': 'connected'})

@socketio.on('join_activity')
def handle_join_activity(data):
    emit('joined_activity', {'activity_id': data['activity_id']}, broadcast=True)

@socketio.on('join_display')
def handle_join_display():
    emit('display_joined', {'status': 'connected'})

@socketio.on('broadcast_timer')
def handle_broadcast_timer(data):
    # 廣播計時器時間到所有投影畫面
    emit('timer_update', {
        'activity_id': data.get('activity_id'),
        'time_remaining': data.get('time_remaining')
    }, broadcast=True, include_self=False)

@socketio.on('project_answer')
def handle_project_answer(data):
    # 廣播回答內容到所有投影畫面
    emit('answer_display', {
        'activity_id': data.get('activity_id'),
        'answer': data.get('answer')
    }, broadcast=True, include_self=False)

if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True, host='0.0.0.0', port=5001)

