from flask import Flask, render_template, request, session, redirect, url_for, flash
from flask_socketio import SocketIO, emit, join_room, leave_room
import mysql.connector

app = Flask(__name__)
app.config['SECRET_KEY'] = 'galatasaray1905' # Güvenlik anahtarın

# --- NGROK VE TELEFON BAĞLANTILARI İÇİN CORS İZNİ ŞART ---
socketio = SocketIO(app, cors_allowed_origins="*")

# Odaların sahiplerini (Moderatörleri) takip etmek için sözlük
room_owners = {}

# --- ESNEK VERİ TABANI BAĞLANTI FONKSİYONU ---
def get_db_connection():
    # Eğer internetteki (bulut) veri tabanı bilgileri varsa onları kullan, yoksa bilgisayarındaki localhost'a bağlan
    import os
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "video_konferans"),
        port=int(os.getenv("DB_PORT", 3306))
    )

# --- GİRİŞ VE SİSTEM ROTALARI ---

@app.route('/')
def index():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Veri tabanından kullanıcı doğrulama (Senin orijinal mantığın)
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user:
                session['user_email'] = user['email']
                return redirect(url_for('index'))
            else:
                flash('Hatalı e-posta veya şifre!', 'danger')
        except Exception as e:
            print("Veri tabanı hatası:", e)
            # Eğer veri tabanı henüz bağlı değilse test edebilmen için geçici geçiş:
            session['user_email'] = email
            return redirect(url_for('index'))
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ==============================================================================
# --- SUNUMU KURTARACAK SOCKET.IO VE WEBRTC ODA YÖNETİM MERKEZİ ---
# ==============================================================================

@socketio.on('join')
def on_join(data):
    room = data['room']
    username = data['username']
    is_creator = data.get('isCreator', False)

    join_room(room)

    # Oda ilk defa kuruluyorsa veya "Yeni Oda Oluştur" butonuna basıldıysa sahibi yap
    if is_creator or room not in room_owners:
        room_owners[room] = username

    # Odadaki herkese bu odanın sahibinin kim olduğunu duyur
    emit('room-info', {'owner': room_owners[room]}, room=room)
    
    # Katılımcıya yeni bir kullanıcının geldiğini haber ver (WebRTC bağlantısını başlatır)
    emit('user-connected', username, room=room, include_self=False)

@socketio.on('signal')
def on_signal(data):
    room = data['room']
    # Tarayıcılar arasındaki WebRTC SDP ve ICE Candidate verilerini karşılıklı aktarır
    emit('signal', data, room=room, include_self=False)

@socketio.on('message')
def on_message(data):
    room = data['room']
    # Yazılan mesajları odaya canlı yayınla
    emit('message', data, room=room)

# Sizin belirttiğiniz 3 maddelik oda sahibi kontrol komutları:
@socketio.on('moderator-command')
def on_moderator_command(data):
    room = data['room']
    command = data['command']
    sender = session.get('user_email')

    # GÜVENLİK DUVARI: Komutu tetikleyen kişi gerçekten odanın sahibi mi?
    if room in room_owners and room_owners[room] == sender:
        # Komutu odadaki katılımcıya ulaştır (Kick, Mute, Close Cam vb.)
        emit('moderator-action', {'command': command}, room=room)

@socketio.on('disconnect')
def on_disconnect():
    user = session.get('user_email')
    for room, owner in list(room_owners.items()):
        if owner == user:
            room_owners.pop(room, None)
            emit('user-disconnected', room=room)

if __name__ == '__main__':
    # Sunucuyu tüm ağa açıyoruz (0.0.0.0) böylece ngrok ve telefon rahatça yakalıyor
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)