"""
Alat kalibrasi HSV interaktif. Jalankan di Jetson dengan monitor:
  python3 tools/hslider.py  (atau file ini)

Geser trackbar sampai mask menutupi sign dengan rapi, lalu salin
nilai lo/hi ke HSV_RANGES di config.py.
"""
import cv2

def nothing(_):
    pass

def main():
    cv2.namedWindow("track")
    ranges = {
        "H_low": (0, 179), "H_high": (0, 179),
        "S_low": (0, 255), "S_high": (0, 255),
        "V_low": (0, 255), "V_high": (0, 255),
    }
    for name, (_, mx) in ranges.items():
        cv2.createTrackbar(name, "track", 0, mx, nothing)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Kamera tidak ditemukan.")
        return
    print("Tekan ESC untuk keluar. Salin hasil ke config.py → HSV_RANGES.")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        vals = [cv2.getTrackbarPos(n, "track") for n in ranges]
        hl, hh, sl, sh, vl, vh = vals
        mask = cv2.inRange(hsv, (hl, sl, vl), (hh, sh, vh))
        cv2.imshow("frame", frame)
        cv2.imshow("mask", mask)
        print(f"\rHSV lo=({hl},{sl},{vl}) hi=({hh},{sh},{vh})", end="")
        if cv2.waitKey(1) & 0xFF == 27:
            break
    cap.release()
    cv2.destroyAllWindows()
    print()

if __name__ == "__main__":
    main()
