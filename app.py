from flask import Flask, render_template, Response, send_file, jsonify, make_response
import cv2
import datetime
import os
import threading

app = Flask(__name__)
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

RECORDINGS_FOLDER = "recordings"
os.makedirs(RECORDINGS_FOLDER, exist_ok=True)

latest_frame = None  # Used for video streaming

def motion_detection_loop():
    global motion_detected, motion_timer, out, latest_frame

    while True:
        success, frame = camera.read()
        if not success:
            continue

        latest_frame = frame.copy()  # Save for stream

        fgmask = fgbg.apply(frame)
        contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        motion = any(cv2.contourArea(c) > 1500 for c in contours)

        if motion:
            if not motion_detected:
                print("🔴 Motion detected", flush=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{RECORDINGS_FOLDER}/motion_{timestamp}.webm"
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


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/video')
def video():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/recordings')
def list_recordings():
    files = [f for f in sorted(os.listdir(RECORDINGS_FOLDER), reverse=True) if f != '.DS_Store']
    return render_template('recordings.html', files=files)


@app.route('/recordings/<path:filename>')
def serve_recording(filename):
    file_path = os.path.join(RECORDINGS_FOLDER, filename)
    response = make_response(send_file(file_path, mimetype='video/webm'))
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@app.route('/motion-status')
def motion_status():
    return jsonify({'motion': motion_detected})


if __name__ == "__main__":
    # Start background thread for motion detection
    motion_thread = threading.Thread(target=motion_detection_loop, daemon=True)
    motion_thread.start()

    app.run(host="0.0.0.0", port=5050, debug=False)
