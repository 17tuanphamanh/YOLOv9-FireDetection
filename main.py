import cv2
import requests
import time
import os
import threading
import numpy as np
from ultralytics import YOLO
from datetime import datetime
import config 
import logging
import tkinter as tk
from tkinter import Label, Button, Canvas
from PIL import Image, ImageTk
import subprocess

# Logging
logging.basicConfig(filename="server.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load YOLOv8
model = YOLO(os.path.join(os.path.dirname(__file__), "best.pt"))

# save status
status = "An toàn"
last_status = "An toàn"
fire_count = 0
smoke_count = 0
system_active = True
frame_lock = threading.Lock()
latest_frame = None
fire_area = 0
smoke_area = 0

# create fille
ALERTS_DIR = "alerts"
os.makedirs(ALERTS_DIR, exist_ok=True)

last_alert_time = 0
ALERT_INTERVAL = 20 

def play_alert_sound():
    subprocess.run(["afplay", "/System/Library/Sounds/Ping.aiff"])  # sound for system

# connect camera
cap = cv2.VideoCapture(config.CAMERA_URL)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
cap.set(cv2.CAP_PROP_FPS, 60)

def send_telegram_alert(image_path):
    global last_alert_time
    if time.time() - last_alert_time < ALERT_INTERVAL:
        return
    try:
        alert_text = f"🚨 CẢNH BÁO!\n🔥 LỬA: {fire_count} (Diện tích: {fire_area}) | 💨 KHÓI: {smoke_count} (Diện tích: {smoke_area})\n🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendPhoto"
        with open(image_path, "rb") as img:
            response = requests.post(url, data={"chat_id": config.CHAT_ID, "caption": alert_text}, files={"photo": img})
        if response.status_code == 200:
            last_alert_time = time.time()
    except Exception as e:
        logging.error(f"❌ Lỗi khi gửi cảnh báo: {str(e)}")

# Tkinter
root = tk.Tk()
root.title("Hệ thống phát hiện cháy")
root.attributes('-fullscreen', True)

video_label = Label(root)
video_label.pack(fill=tk.BOTH, expand=True)  # Phóng to video

status_label = Label(root, text="Trạng thái: An toàn", font=("Arial", 24, "bold"), fg="green")
status_label.pack()

fire_smoke_label = Label(root, text="🔥 0 | 💨 0", font=("Arial", 20))
fire_smoke_label.pack()

canvas = Canvas(root, width=300, height=300, bg="white")
canvas.pack()

def toggle_system():
    global system_active
    system_active = not system_active
    btn_text.set("Bật hệ thống" if not system_active else "Tắt hệ thống")

btn_text = tk.StringVar(value="Tắt hệ thống")
toggle_button = Button(root, textvariable=btn_text, command=toggle_system, font=("Arial", 18), bg="gray", fg="white")
toggle_button.pack()

def update_ui():
    if latest_frame is not None:
        img = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(latest_frame, cv2.COLOR_BGR2RGB)))
        video_label.config(image=img)
        video_label.img_tk = img
    status_label.config(text=f"Trạng thái: {status}", fg="red" if status == "Nguy hiểm" else "green")
    fire_smoke_label.config(text=f"🔥 {fire_count} (Diện tích: {fire_area}) | 💨 {smoke_count} (Diện tích: {smoke_area})")
    root.configure(bg="red" if status == "Nguy hiểm" else "white")
    canvas.delete("all")
    if fire_count > 0:
        canvas.create_oval(50, 50, 50 + fire_area / 100, 50 + fire_area / 100, outline="red", width=3)
    if smoke_count > 0:
        canvas.create_oval(150, 150, 150 + smoke_area / 100, 150 + smoke_area / 100, outline="blue", width=3)
    root.after(30, update_ui)  # Cập nhật nhanh hơn
update_ui()

def detect_fire():
    global status, last_status, fire_count, smoke_count, latest_frame, fire_area, smoke_area
    while True:
        if not system_active or cap is None or not cap.isOpened():
            time.sleep(1)
            continue
        success, frame = cap.read()
        if not success:
            time.sleep(0.3)
            continue
        frame = cv2.resize(frame, (1280, 720))  # Tăng kích thước hiển thị video
        results = model(frame, conf=0.7, iou=0.5)
        fire_count = 0
        smoke_count = 0
        fire_area = 0
        smoke_area = 0
        for r in results:
            for box in r.boxes:
                cls = int(box.cls[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                area = (x2 - x1) * (y2 - y1)
                if cls == 0:
                    fire_count += 1
                    fire_area += area
                elif cls == 1:
                    smoke_count += 1
                    smoke_area += area
        
        status = "Nguy hiểm" if fire_count or smoke_count else "An toàn"
        if status == "Nguy hiểm" and last_status == "An toàn":
            play_alert_sound()
            img_path = os.path.join(ALERTS_DIR, f"alert_{int(time.time())}.jpg")
            cv2.imwrite(img_path, frame)
            send_telegram_alert(img_path)
        last_status = status
        with frame_lock:
            latest_frame = frame.copy()
        time.sleep(0.03)

threading.Thread(target=detect_fire, daemon=True).start()
root.mainloop()