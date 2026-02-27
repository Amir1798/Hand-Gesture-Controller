import cv2
import mediapipe as mp
import numpy as np
import math

# ===== PYCAW =====
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

# ===== Initialiser volume =====
devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(
    IAudioEndpointVolume._iid_,
    CLSCTX_ALL,
    None
)
volume = cast(interface, POINTER(IAudioEndpointVolume))
volMin, volMax = volume.GetVolumeRange()[:2]

# ===== Mediapipe =====
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1)
mp_draw = mp.solutions.drawing_utils

# ===== Camera =====
cap = cv2.VideoCapture(0)

while True:
    success, img = cap.read()
    if not success:
        break

    imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(imgRGB)

    if results.multi_hand_landmarks:
        for handLms in results.multi_hand_landmarks:
            lmList = []

            h, w, _ = img.shape
            for id, lm in enumerate(handLms.landmark):
                cx, cy = int(lm.x * w), int(lm.y * h)
                lmList.append((id, cx, cy))

            # ===== Pouce (4) et Index (8) =====
            x1, y1 = lmList[4][1], lmList[4][2]
            x2, y2 = lmList[8][1], lmList[8][2]

            # Dessin
            cv2.circle(img, (x1, y1), 10, (255, 0, 255), -1)
            cv2.circle(img, (x2, y2), 10, (255, 0, 255), -1)
            cv2.line(img, (x1, y1), (x2, y2), (255, 0, 255), 3)

            # ===== Distance =====
            length = math.hypot(x2 - x1, y2 - y1)

            # ===== Mapping volume =====
            vol = np.interp(length, [30, 200], [volMin, volMax])
            volume.SetMasterVolumeLevel(vol, None)

            mp_draw.draw_landmarks(img, handLms, mp_hands.HAND_CONNECTIONS)

    cv2.imshow("Volume Control", img)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()
