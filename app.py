from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import sqlite3

app = Flask(__name__)
CORS(app)

# --- Database Setup ---
# Render의 영구 디스크 경로를 확인하고, 그렇지 않으면 로컬 파일을 사용합니다.
if os.environ.get('RENDER'):
    # Render 환경에서는 지정된 마운트 경로를 사용합니다.
    db_dir = '/var/data'
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    DATABASE_PATH = os.path.join(db_dir, 'database.db')
else:
    # 로컬 환경에서는 프로젝트 루트에 데이터베이스 파일을 생성합니다.
    DATABASE_PATH = 'database.db'

SUBJECTS = ["원가", "세법", "재정", "행정", "세회", "재무", "독서", "craft"]

def get_db_connection():
    """데이터베이스 연결을 생성하고 반환합니다."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # 결과를 딕셔너리처럼 사용할 수 있게 합니다.
    return conn

def init_db():
    """데이터베이스 테이블을 초기화합니다."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS study_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Date TEXT NOT NULL,
                Subject TEXT NOT NULL,
                StartTime TEXT NOT NULL,
                EndTime TEXT NOT NULL,
                Duration INTEGER NOT NULL
            )
        ''')
        conn.commit()

# --- Helper Functions ---
def get_custom_date():
    """3AM 기준으로 날짜를 계산합니다."""
    now = datetime.now()
    if now.hour < 3:
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    return now.strftime('%Y-%m-%d')

def get_yesterday_date():
    """어제 날짜를 계산합니다 (3AM 기준)."""
    now = datetime.now()
    if now.hour < 3:
        return (now - timedelta(days=2)).strftime('%Y-%m-%d')
    return (now - timedelta(days=1)).strftime('%Y-%m-%d')

def get_motivation_message(today_hours, yesterday_hours):
    """동기부여 메시지를 생성합니다."""
    if yesterday_hours == 0:
        return "새로운 시작이네요! 오늘도 화이팅! 🌟" if today_hours > 0 else "오늘부터 시작해보세요! 💪"
    
    if today_hours > yesterday_hours:
        improvement = today_hours - yesterday_hours
        return f"어제의 나를 넘어서고 있습니��! (+{improvement:.1f}시간) 🎉"
    elif today_hours < yesterday_hours:
        gap = yesterday_hours - today_hours
        return f"이길 수 있어요 힘내요! (어제보다 -{gap:.1f}시간) 💪"
    return None

# --- App Initialization ---
init_db()

# --- Routes ---
@app.route('/')
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')

@app.route('/stopwatches')
def multi_stopwatch_page():
    """멀티 스톱워치 페이지를 렌더링합니다."""
    return render_template('multi.html')

@app.route('/api/subjects')
def get_subjects():
    """과목 목록을 반환합니다."""
    return jsonify(SUBJECTS)

@app.route('/api/record-session', methods=['POST'])
def record_session():
    """공부 세션을 데이터베이스에 기록합니다."""
    data = request.json
    duration = data.get('duration', 0)

    if duration < 60:
        return jsonify({'message': 'Session too short, not recorded'}), 400

    custom_date = get_custom_date()
    start_str = datetime.fromtimestamp(data['start_time']).strftime('%Y-%m-%d %H:%M:%S')
    end_str = datetime.fromtimestamp(data['end_time']).strftime('%Y-%m-%d %H:%M:%S')

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO study_sessions (Date, Subject, StartTime, EndTime, Duration) VALUES (?, ?, ?, ?, ?)",
                (custom_date, data['subject'], start_str, end_str, int(duration))
            )
            conn.commit()
        return jsonify({
            'message': 'Session recorded successfully',
            'duration_minutes': round(duration / 60, 2)
        })
    except sqlite3.Error as e:
        return jsonify({'error': 'Database record failed', 'details': str(e)}), 500

@app.route('/api/today-stats')
def get_today_stats():
    """오늘의 공부 통계를 반환합니다."""
    try:
        today_date = get_custom_date()
        yesterday_date = get_yesterday_date()
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 오늘의 총 공부 시간
            cursor.execute("SELECT SUM(Duration) FROM study_sessions WHERE Date = ?", (today_date,))
            today_total_seconds = cursor.fetchone()[0] or 0

            # 어제의 총 공부 시간
            cursor.execute("SELECT SUM(Duration) FROM study_sessions WHERE Date = ?", (yesterday_date,))
            yesterday_total_seconds = cursor.fetchone()[0] or 0

            # 오늘의 과목별 공부 시간
            cursor.execute("SELECT Subject, SUM(Duration) FROM study_sessions WHERE Date = ? GROUP BY Subject", (today_date,))
            subject_rows = cursor.fetchall()

        today_total_hours = today_total_seconds / 3600
        yesterday_total_hours = yesterday_total_seconds / 3600
        
        subject_times = {
            row['Subject']: {
                'minutes': row['SUM(Duration)'] / 60,
                'hours': row['SUM(Duration)'] / 3600
            } for row in subject_rows
        }

        motivation_message = get_motivation_message(today_total_hours, yesterday_total_hours)
        
        response_data = {
            'date': today_date,
            'total_hours': round(today_total_hours, 2),
            'subject_times': subject_times,
            'current_time': datetime.now().strftime('%H:%M:%S')
        }
        if motivation_message:
            response_data['motivation_message'] = motivation_message

        return jsonify(response_data)
    except sqlite3.Error as e:
        return jsonify({'error': 'Failed to retrieve today stats', 'details': str(e)}), 500

@app.route('/api/statistics/<int:days>')
def get_statistics(days):
    """지정된 기간 동안의 통계를 반환합니다."""
    try:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 총 공부 시간
            cursor.execute("SELECT SUM(Duration) FROM study_sessions WHERE Date >= ?", (cutoff_date,))
            total_time = cursor.fetchone()[0] or 0

            # 과목별 공부 시간
            cursor.execute("SELECT Subject, SUM(Duration) FROM study_sessions WHERE Date >= ? GROUP BY Subject", (cutoff_date,))
            subject_rows = cursor.fetchall()
            
            # 일별 공부 시간
            cursor.execute("SELECT Date, SUM(Duration) FROM study_sessions WHERE Date >= ? GROUP BY Date", (cutoff_date,))
            daily_rows = cursor.fetchall()

        subject_times = {
            row['Subject']: {
                'minutes': round(row['SUM(Duration)'] / 60, 2),
                'hours': round(row['SUM(Duration)'] / 3600, 2)
            } for row in subject_rows
        }
        
        daily_stats = {
            row['Date']: round(row['SUM(Duration)'] / 3600, 2) for row in daily_rows
        }
        
        return jsonify({
            'days': days,
            'total_minutes': round(total_time / 60, 2),
            'total_hours': round(total_time / 3600, 2),
            'average_hours_per_day': round(total_time / 3600 / days, 2) if days > 0 else 0,
            'subject_times': subject_times,
            'daily_stats': daily_stats
        })
    except sqlite3.Error as e:
        return jsonify({'error': 'Failed to retrieve statistics', 'details': str(e)}), 500

@app.route('/api/subject-comparison')
def get_subject_comparison():
    """기간별 과목 통계를 비교하여 반환합니다."""
    try:
        periods = [3, 7, 14, 30]
        comparison_data = {}
        
        with get_db_connection() as conn:
            for days in periods:
                cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT Subject, SUM(Duration) as TotalDuration FROM study_sessions WHERE Date >= ? GROUP BY Subject",
                    (cutoff_date,)
                )
                rows = cursor.fetchall()
                
                period_stats = {subject: {'minutes': 0, 'hours': 0, 'seconds': 0} for subject in SUBJECTS}
                total_time = 0
                
                for row in rows:
                    subject = row['Subject']
                    duration = row['TotalDuration']
                    if subject in period_stats:
                        period_stats[subject] = {
                            'minutes': round(duration / 60, 2),
                            'hours': round(duration / 3600, 2),
                            'seconds': duration
                        }
                    total_time += duration
                
                comparison_data[f'{days}days'] = {
                    'total_hours': round(total_time / 3600, 2),
                    'average_per_day': round(total_time / 3600 / days, 2) if days > 0 else 0,
                    'subjects': period_stats
                }
        
        return jsonify(comparison_data)
    except sqlite3.Error as e:
        return jsonify({'error': 'Failed to retrieve subject comparison', 'details': str(e)}), 500

@app.route('/api/health')
def health_check():
    """서버 상태를 확인합니다."""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# if __name__ == '__main__':
#     app.run(debug=True, host='0.0.0.0', port=5001)
