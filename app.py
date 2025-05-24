from flask import Flask, render_template, Response, send_file, jsonify, make_response, flash, request, redirect, url_for
import cv2
import datetime
import os
import threading
import json
import requests

app = Flask(__name__)
app.secret_key = 'a_super_secret_key_123'  # Replace with a secure value

camera = cv2.VideoCapture(0)
print(f"Frame default resolution: ({camera.get(cv2.CAP_PROP_FRAME_WIDTH)}; {camera.get(cv2.CAP_PROP_FRAME_HEIGHT)})")

motion_detected = False
motion_timer = 0
no_motion_limit = 10
frame_width = int(camera.get(3))
frame_height = int(camera.get(4))
out = None
fourcc = cv2.VideoWriter_fourcc(*'V','P','8','0')  # For WebM (VP8)
fgbg = cv2.createBackgroundSubtractorMOG2(history=100, varThreshold=40)

latest_frame = None  # Used for video streaming

SETTINGS_FILE = "settings.json"
settings_lock = threading.Lock()

def load_settings():
    try:
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {
            "recordings_folder": "recordings",
            "motion_threshold": 30
        }

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

def send_ha_notification(title, message):
    token = "enter ha token"
    ha_url = "http://YOURIP:8123/api/services/notify/mobile_app_gov_public"

    headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    }

    payload = {
        "message": message,
        "title": title
    }

    response = requests.post(ha_url, headers=headers, json=payload)

    if response.status_code == 200:
        print("Notification sent!")
    else:
        print(f"Failed to send notification: {response.text}")        

# Load initial settings
settings = load_settings()
os.makedirs(settings["recordings_folder"], exist_ok=True)

def motion_detection_loop():
    global motion_detected, motion_timer, out, latest_frame

    while True:
        success, frame = camera.read()
        if not success:
            continue

        latest_frame = frame.copy()

        fgmask = fgbg.apply(frame)
        contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        with settings_lock:
            threshold = settings.get("motion_threshold", 30)
            save_path = settings.get("recordings_folder", "recordings")
        
        motion = any(cv2.contourArea(c) > threshold for c in contours)

        if motion:
            if not motion_detected:
                print("🔴 Motion detected", flush=True)
                send_ha_notification("📼 Motion Alert", "New recording started on the Raspberry Pi")
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                os.makedirs(save_path, exist_ok=True)
                filename = f"{save_path}/motion_{timestamp}.webm"
                out = cv2.VideoWriter(filename, fourcc, 20.0, (frame_width, frame_height))
            motion_detected = True
            motion_timer = 0
        else:
            if motion_detected:
                motion_timer += 1
                if motion_timer > no_motion_limit:
                    print("🟢 Motion ended, saving file", flush=True)
                    motion_detected = False
                    motion_timer = 0
                    if out:
                        out.release()
                        out = None

        if motion_detected and out:
            out.write(frame)

def generate_frames():
    global latest_frame
    while True:
        if latest_frame is None:
            continue

        ret, buffer = cv2.imencode('.jpg', latest_frame)
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route("/delete", methods=["POST"])
def delete_recording():
    filename = request.form.get("filename")
    if filename:
        path = os.path.join(settings['recordings_folder'], filename)
        if os.path.exists(path):
            os.remove(path)
            flash(f"{filename} deleted.")
    return redirect(url_for("list_recordings"))

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video')
def video():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/recordings')
def list_recordings():
    with settings_lock:
        save_path = settings.get("recordings_folder", "recordings")
    files = [f for f in sorted(os.listdir(save_path), reverse=True) if f != '.DS_Store']
    return render_template('recordings.html', files=files)


@app.route('/recordings/<path:filename>')
def serve_recording(filename):
    with settings_lock:
        save_path = settings.get("recordings_folder", "recordings")
    file_path = os.path.join(save_path, filename)
    response = make_response(send_file(file_path, mimetype='video/webm'))
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@app.route('/motion-status')
def motion_status():
    return jsonify({'motion': motion_detected})


@app.route('/settings', methods=['GET', 'POST'])
def settings_page():
    global settings

    if request.method == 'POST':
        with settings_lock:
            settings["recordings_folder"] = request.form.get('recordings_folder')
            settings["motion_threshold"] = int(request.form.get('motion_threshold'))
            save_settings(settings)
        flash('Settings updated!')
        return redirect(url_for('settings_page'))

    with settings_lock:
        current_settings = settings.copy()
    return render_template('settings.html', settings=current_settings)


if __name__ == "__main__":
    # Start background thread for motion detection
    motion_thread = threading.Thread(target=motion_detection_loop, daemon=True)
    motion_thread.start()

    app.run(host="0.0.0.0", port=5050, debug=False)

