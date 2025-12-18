from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime, timedelta
from datetime import datetime, timedelta
import os
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
# 세션 보안을 위한 시크릿 키 설정 (실제 운영 시에는 안전한 난수로 변경 필요)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key_here')
CORS(app)

# --- Authentication Setup ---
# 관리자 비밀번호 설정 (환경 변수에서 로드하거나 기본값 사용)
# 실제로는 .env 파일에 ADMIN_PASSWORD=my_secure_password 형태로 설정하는 것이 좋습니다.
# 여기서는 편의상 해시된 비밀번호를 하드코딩하지 않고, 환경변수 비교 시 해시를 생성하여 비교하거나 단순 비교할 수 있습니다.
# 보안을 위해 환경변수의 평문 비밀번호와 입력받은 비밀번호를 비교합니다.
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '0000')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id == 'admin':
        return User('admin')
    return None

# --- Database Setup ---
# PostgreSQL 연결 설정
# 사용자: stweb, 데이터베이스: stweb_data
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://stweb:c1stweb@localhost:5432/stweb_data'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

SUBJECTS = ["원가", "세법", "재정", "행정", "세회", "재무", "독서"]

# --- Database Model ---
class StudySession(db.Model):
    __tablename__ = 'study_sessions'
    id = db.Column(db.Integer, primary_key=True)
    Date = db.Column(db.String, nullable=False)
    Subject = db.Column(db.String, nullable=False)
    StartTime = db.Column(db.String, nullable=False)
    EndTime = db.Column(db.String, nullable=False)
    Duration = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f'<StudySession {self.Subject} on {self.Date}>'

from zoneinfo import ZoneInfo

# --- Helper Functions ---
def get_custom_date():
    """5AM 기준으로 날짜를 계산합니다."""
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    if now.hour < 5:
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    return now.strftime('%Y-%m-%d')

def get_yesterday_date():
    """어제 날짜를 계산합니다 (5AM 기준)."""
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    if now.hour < 5:
        return (now - timedelta(days=2)).strftime('%Y-%m-%d')
    return (now - timedelta(days=1)).strftime('%Y-%m-%d')

def get_motivation_message(today_hours, yesterday_hours):
    """동기부여 메시지를 생성합니다."""
    if yesterday_hours == 0:
        return "새로운 시작이네요! 오늘도 화이팅! 🌟" if today_hours > 0 else "오늘부터 시작해보세요! 💪"
    
    if today_hours > yesterday_hours:
        improvement = today_hours - yesterday_hours
        return f"어제의 나를 넘어서고 있습니다! (+{improvement:.1f}시간) 🎉"
    elif today_hours < yesterday_hours:
        gap = yesterday_hours - today_hours
        return f"이길 수 있어요 힘내요! (어제보다 -{gap:.1f}시간) 💪"
    return None

# --- App Initialization ---

# --- Routes ---
@app.route('/')
@login_required
def index():
    """메인 페이지를 렌더링합니다."""
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            user = User('admin')
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            return render_template('login.html', error='비밀번호가 올바르지 않습니다.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/stopwatches')
@login_required
def multi_stopwatch_page():
    """멀티 스톱워치 페이지를 렌더링합니다."""
    return render_template('multi.html')

@app.route('/api/subjects')
@login_required
def get_subjects():
    """과목 목록을 반환합니다."""
    return jsonify(SUBJECTS)

@app.route('/api/record-session', methods=['POST'])
@login_required
def record_session():
    """공부 세션을 데이터베이스에 기록합니다."""
    data = request.json
    duration = data.get('duration', 0)

    if duration < 60:
        return jsonify({'message': 'Session too short, not recorded'}), 400

    new_session = StudySession(
        Date=get_custom_date(),
        Subject=data['subject'],
        StartTime=datetime.fromtimestamp(data['start_time']).strftime('%Y-%m-%d %H:%M:%S'),
        EndTime=datetime.fromtimestamp(data['end_time']).strftime('%Y-%m-%d %H:%M:%S'),
        Duration=int(duration)
    )
    
    try:
        db.session.add(new_session)
        db.session.commit()
        return jsonify({
            'message': 'Session recorded successfully',
            'duration_minutes': round(duration / 60, 2)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Database record failed', 'details': str(e)}), 500

@app.route('/api/today-stats')
@login_required
def get_today_stats():
    """오늘의 공부 통계를 반환합니다."""
    try:
        today_date = get_custom_date()
        yesterday_date = get_yesterday_date()
        
        # 오늘의 총 공부 시간
        today_total_seconds = db.session.query(func.sum(StudySession.Duration)).filter_by(Date=today_date).scalar() or 0
        
        # 어제의 총 공부 시간
        yesterday_total_seconds = db.session.query(func.sum(StudySession.Duration)).filter_by(Date=yesterday_date).scalar() or 0

        # 오늘의 과목별 공부 시간
        subject_rows = db.session.query(
            StudySession.Subject, func.sum(StudySession.Duration)
        ).filter_by(Date=today_date).group_by(StudySession.Subject).all()

        today_total_hours = today_total_seconds / 3600
        yesterday_total_hours = yesterday_total_seconds / 3600
        
        subject_times = {
            subject: {
                'minutes': duration / 60,
                'hours': duration / 3600
            } for subject, duration in subject_rows
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
    except Exception as e:
        return jsonify({'error': 'Failed to retrieve today stats', 'details': str(e)}), 500

@app.route('/api/statistics/<int:days>')
@login_required
def get_statistics(days):
    """지정된 기간 동안의 통계를 반환합니다."""
    try:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # 총 공부 시간
        total_time = db.session.query(func.sum(StudySession.Duration)).filter(StudySession.Date >= cutoff_date).scalar() or 0

        # 과목별 공부 시간
        subject_rows = db.session.query(
            StudySession.Subject, func.sum(StudySession.Duration)
        ).filter(StudySession.Date >= cutoff_date).group_by(StudySession.Subject).all()
        
        # 일별 공부 시간
        daily_rows = db.session.query(
            StudySession.Date, func.sum(StudySession.Duration)
        ).filter(StudySession.Date >= cutoff_date).group_by(StudySession.Date).all()

        subject_times = {
            subject: {
                'minutes': round(duration / 60, 2),
                'hours': round(duration / 3600, 2)
            } for subject, duration in subject_rows
        }
        
        daily_stats = {
            date: round(duration / 3600, 2) for date, duration in daily_rows
        }
        
        return jsonify({
            'days': days,
            'total_minutes': round(total_time / 60, 2),
            'total_hours': round(total_time / 3600, 2),
            'average_hours_per_day': round(total_time / 3600 / days, 2) if days > 0 else 0,
            'subject_times': subject_times,
            'daily_stats': daily_stats
        })
    except Exception as e:
        return jsonify({'error': 'Failed to retrieve statistics', 'details': str(e)}), 500

@app.route('/api/subject-comparison')
@login_required
def get_subject_comparison():
    """기간별 과목 통계를 비교하여 반환합니다."""
    try:
        periods = [3, 7, 14, 30, 180]
        comparison_data = {}
        
        for days in periods:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            
            rows = db.session.query(
                StudySession.Subject, func.sum(StudySession.Duration).label('TotalDuration')
            ).filter(StudySession.Date >= cutoff_date).group_by(StudySession.Subject).all()
            
            period_stats = {subject: {'minutes': 0, 'hours': 0, 'seconds': 0} for subject in SUBJECTS}
            total_time = 0
            
            for row in rows:
                subject = row.Subject
                duration = row.TotalDuration
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
    except Exception as e:
        return jsonify({'error': 'Failed to retrieve subject comparison', 'details': str(e)}), 500

@app.route('/history')
@login_required
def history_page():
    """학습 기록 상세 페이지를 렌더링합니다."""
    return render_template('history.html')

@app.route('/api/streak-info')
@login_required
def get_streak_info():
    """연속 학습일, 빠진 날, 응원 메시지를 반환합니다."""
    try:
        # 1. DB에서 모든 학습 날짜를 중복 없이 가져오기
        all_study_dates_query = db.session.query(StudySession.Date).distinct().all()
        all_study_dates = {row[0] for row in all_study_dates_query}

        if not all_study_dates:
            return jsonify({
                'streak_days': 0,
                'missed_days': [],
                'message': '첫 공부를 시작해보세요!'
            })

        # 2. 연속 학습일 계산
        streak_days = 0
        current_date_str = get_custom_date()
        current_date = datetime.strptime(current_date_str, '%Y-%m-%d').date()
        
        if current_date_str in all_study_dates:
            streak_days = 1
            check_date = current_date - timedelta(days=1)
            while (check_date.strftime('%Y-%m-%d') in all_study_dates):
                streak_days += 1
                check_date -= timedelta(days=1)
        
        # 3. 빠진 날 계산
        first_day_str = min(all_study_dates)
        first_day = datetime.strptime(first_day_str, '%Y-%m-%d').date()
        
        missed_days = []
        # 첫 공부날부터 오늘까지 모든 날짜를 확인
        for i in range((current_date - first_day).days + 1):
            check_date = first_day + timedelta(days=i)
            check_date_str = check_date.strftime('%Y-%m-%d')
            if check_date_str not in all_study_dates:
                missed_days.append(check_date_str)
        
        # 4. 응원 메시지 생성
        message = ""
        if streak_days > 0:
            message = f"연속 {streak_days}일째 공부 중입니다! 대단해요! 🔥"
        else:
            last_study_day_str = max(all_study_dates) if all_study_dates else None
            if last_study_day_str:
                last_study_day = datetime.strptime(last_study_day_str, '%Y-%m-%d').date()
                days_since_last_study = (current_date - last_study_day).days
                
                if days_since_last_study == 1:
                     message = "오늘의 공부를 시작해볼까요? 꾸준함이 중요해요! 🚀"
                elif days_since_last_study > 1:
                     message = f"{days_since_last_study}일 동안 쉬셨네요. 다시 함께 달려봐요! 🚀"
            else:
                 message = "오늘부터 새로운 시작! 화이팅! 🌟"


        return jsonify({
            'streak_days': streak_days,
            'missed_days': sorted(missed_days, reverse=True),
            'message': message
        })

    except Exception as e:
        return jsonify({'error': 'Failed to retrieve streak info', 'details': str(e)}), 500

@app.route('/api/health')
def health_check():
    """서버 상태를 확인합니다."""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# --- CLI Commands ---
@app.cli.command("init-db")
def init_db_command():
    """Initializes the database."""
    with app.app_context():
        db.create_all()
    print("Database initialized.")

if __name__ == '__main__':
    # 로컬 테스트용: python app.py 실행 시
    app.run(debug=True, host='0.0.0.0', port=5001)
