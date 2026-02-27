import cv2
import time
import threading
import tkinter as tk
from tkinter import ttk
import numpy as np
import mediapipe as mp
import pyautogui
import screen_brightness_control as sbc
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

# ================= GLOBAL STATE =================
running = False
cap = None
start_time = None
gesture_count = 0
positions = []
smoothening_value = 5
selected_mode = "Mouse"
calibrated = False

left_clicked = False
right_clicked = False
CLICK_DIST = 35

# NEW: scroll smoothing
last_scroll_time = 0
SCROLL_DELAY = 0.05  # plus petit = scroll plus fluide

pyautogui.FAILSAFE = False  # important pour scroll global

# ================= MEDIAPIPE =================
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=2)
mp_draw = mp.solutions.drawing_utils

# ================= AUDIO =================
try:
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume_control = cast(interface, POINTER(IAudioEndpointVolume))
    vol_range = volume_control.GetVolumeRange()
    min_vol, max_vol = vol_range[0], vol_range[1]
except Exception as e:
    print("Volume control not available:", e)
    volume_control = None

def set_volume(level):
    if volume_control:
        try:
            vol = min_vol + (level / 100) * (max_vol - min_vol)
            volume_control.SetMasterVolumeLevel(vol, None)
        except Exception as e:
            print("Failed to set volume:", e)

def set_brightness(level):
    try:
        sbc.set_brightness(int(level))
    except Exception as e:
        print("Failed to set brightness:", e)

# ================= FINGERS =================
def fingers_up(hand_landmarks):
    tips = [8, 12, 16, 20]
    fingers = []

    if hand_landmarks.landmark[4].x < hand_landmarks.landmark[3].x:
        fingers.append(1)
    else:
        fingers.append(0)

    for tip in tips:
        if hand_landmarks.landmark[tip].y < hand_landmarks.landmark[tip - 2].y:
            fingers.append(1)
        else:
            fingers.append(0)

    return fingers

# ================= HEATMAP =================
def show_heatmap():
    if len(positions) < 10:
        return
    heatmap = np.zeros((480, 640), dtype=np.float32)
    for (x, y) in positions:
        if 0 <= x < 640 and 0 <= y < 480:
            heatmap[int(y), int(x)] += 1
    heatmap = cv2.GaussianBlur(heatmap, (51, 51), 0)
    heatmap = cv2.normalize(heatmap, None, 0, 255, cv2.NORM_MINMAX)
    heatmap = heatmap.astype(np.uint8)
    heatmap_color = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
    cv2.imshow("Heatmap", heatmap_color)

# ================= TRACKING LOOP =================
def tracking_loop():
    global running, cap, start_time, gesture_count, positions
    global left_clicked, right_clicked, last_scroll_time

    cap = cv2.VideoCapture(0)
    start_time = time.time()
    prev_x, prev_y = 0, 0

    screen_w, screen_h = pyautogui.size()

    while running:
        success, img = cap.read()
        if not success:
            break

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = hands.process(img_rgb)
        h, w, _ = img.shape

        if results.multi_hand_landmarks:
            gesture_count += len(results.multi_hand_landmarks)

            for handLms in results.multi_hand_landmarks:
                mp_draw.draw_landmarks(img, handLms, mp_hands.HAND_CONNECTIONS)

                x = int(handLms.landmark[8].x * w)
                y = int(handLms.landmark[8].y * h)

                curr_x = prev_x + (x - prev_x) / max(1, smoothening_value)
                curr_y = prev_y + (y - prev_y) / max(1, smoothening_value)

                # ================= MOUSE =================
                if selected_mode == "Mouse":
                    mouse_x = int(curr_x / w * screen_w)
                    mouse_y = int(curr_y / h * screen_h)
                    pyautogui.moveTo(mouse_x, mouse_y)

                    ix, iy = int(handLms.landmark[8].x * w), int(handLms.landmark[8].y * h)
                    tx, ty = int(handLms.landmark[4].x * w), int(handLms.landmark[4].y * h)
                    mx, my = int(handLms.landmark[12].x * w), int(handLms.landmark[12].y * h)

                    dist_thumb_index = np.hypot(ix - tx, iy - ty)
                    dist_index_middle = np.hypot(ix - mx, iy - my)

                    if dist_thumb_index < CLICK_DIST:
                        if not left_clicked:
                            pyautogui.click(button="left")
                            left_clicked = True
                    else:
                        left_clicked = False

                    if dist_index_middle < CLICK_DIST:
                        if not right_clicked:
                            pyautogui.click(button="right")
                            right_clicked = True
                    else:
                        right_clicked = False

                # ================= SCROLL GLOBAL =================
                elif selected_mode == "Scroll":
                    fingers = fingers_up(handLms)

                    # ✨ index + middle levés = scroll actif
                    if fingers[1] == 1 and fingers[2] == 1:
                        now = time.time()

                        if now - last_scroll_time > SCROLL_DELAY:
                            dy = curr_y - prev_y

                            # scroll proportionnel (PLUS FLUIDE)
                            scroll_amount = int(-dy * 3)

                            if abs(scroll_amount) > 1:
                                pyautogui.scroll(scroll_amount)
                                last_scroll_time = now

                    cv2.putText(img, "SCROLL MODE ACTIVE", (350, 80),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                # ================= VOLUME =================
                elif selected_mode == "Volume":
                    vol_level = int(100 - (curr_y / h) * 100)
                    vol_level = max(0, min(100, vol_level))
                    set_volume(vol_level)

                    bar_y = int((vol_level / 100) * 300)
                    cv2.rectangle(img, (50, 150), (85, 450), (0, 0, 0), 3)
                    cv2.rectangle(img, (50, 450 - bar_y), (85, 450), (0, 255, 0), cv2.FILLED)
                    cv2.putText(img, f"{vol_level}%", (40, 480),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                # ================= BRIGHTNESS =================
                elif selected_mode == "Brightness":
                    bright_level = int(100 - (curr_y / h) * 100)
                    bright_level = max(0, min(100, bright_level))
                    set_brightness(bright_level)

                    bar_y = int((bright_level / 100) * 300)
                    cv2.rectangle(img, (100, 150), (135, 450), (0, 0, 0), 3)
                    cv2.rectangle(img, (100, 450 - bar_y), (135, 450), (0, 255, 255), cv2.FILLED)
                    cv2.putText(img, f"{bright_level}%", (90, 480),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

                prev_x, prev_y = curr_x, curr_y
                positions.append((int(curr_x), int(curr_y)))
                cv2.circle(img, (int(curr_x), int(curr_y)), 10, (255, 0, 255), cv2.FILLED)

        cv2.putText(img, f"Mode: {selected_mode}", (10, 80),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)

        cv2.imshow("Hand Tracking", img)
        show_heatmap()

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()

# ================= GUI =================
def start_tracking():
    global running, selected_mode
    if running:
        return
    selected_mode = mode_var.get()
    running = True
    threading.Thread(target=tracking_loop, daemon=True).start()

def stop_tracking():
    global running
    running = False

def update_smooth(val):
    global smoothening_value
    smoothening_value = int(float(val))

root = tk.Tk()
root.title("Hand Tracking PRO Control Panel")
root.geometry("350x350")

title = ttk.Label(root, text="Hand Tracking PRO", font=("Arial", 14, "bold"))
title.pack(pady=10)

ttk.Label(root, text="Select Mode").pack()
mode_var = tk.StringVar(value="Mouse")
mode_combo = ttk.Combobox(
    root,
    textvariable=mode_var,
    values=["Mouse", "Volume", "Scroll", "Brightness"],
    state="readonly"
)
mode_combo.pack(pady=5)

ttk.Label(root, text="Smoothening").pack()
smooth_slider = ttk.Scale(root, from_=1, to=20, orient="horizontal", command=update_smooth)
smooth_slider.set(5)
smooth_slider.pack(pady=5)

start_btn = ttk.Button(root, text="▶ Start", command=start_tracking)
start_btn.pack(pady=10)

stop_btn = ttk.Button(root, text="⏹ Stop", command=stop_tracking)
stop_btn.pack(pady=5)

root.mainloop()