"""
Capture kamera CSI Jetson (imx219 / Raspberry Pi Camera) via GStreamer.

OpenCV yang terinstall dari apt Jetson sering dibuild TANPA GStreamer,
sehingga cv2.VideoCapture() pada kamera CSI menghasilkan frame hijau
(format Bayer/CSI mentah tidak dikonversi). Modul ini memakai
nvarguscamerasrc + appsink (PyGObject) lalu mengubah frame menjadi
array BGR numpy yang siap dipakai OpenCV.

API dibuat mirip cv2.VideoCapture: isOpened(), read(), release().
"""

import numpy as np

try:
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    _HAS_GST = True
except Exception:
    _HAS_GST = False


def apply_flip(frame):
    """Terapkan orientasi kamera sesuai config.CAMERA_FLIP."""
    if frame is None:
        return frame
    try:
        from config import CAMERA_FLIP
    except Exception:
        return frame
    import cv2
    if CAMERA_FLIP == "horizontal":
        return cv2.flip(frame, 1)
    if CAMERA_FLIP == "vertical":
        return cv2.flip(frame, 0)
    if CAMERA_FLIP in ("rotate180", "both"):
        return cv2.flip(frame, -1)
    return frame


class V4L2Capture:
    """Adapter cv2.VideoCapture agar menerapkan flip yang sama."""

    def __init__(self, cap):
        self.cap = cap

    def isOpened(self):
        return self.cap.isOpened()

    def set(self, *args, **kwargs):
        return self.cap.set(*args, **kwargs)

    def read(self):
        ok, frame = self.cap.read()
        if not ok:
            return ok, frame
        return ok, apply_flip(frame)

    def release(self):
        self.cap.release()


class GSTCamera:
    """Kamera CSI Jetson via nvarguscamerasrc → appsink → numpy BGR."""

    def __init__(self, sensor_id=0, width=640, height=480, fps=30):
        if not _HAS_GST:
            raise RuntimeError("PyGObject GStreamer tidak tersedia")
        Gst.init(None)
        self.width = width
        self.height = height
        self._opened = False

        pipeline_str = (
            f"nvarguscamerasrc sensor-id={sensor_id} ! "
            f"video/x-raw(memory:NVMM),width={width},height={height},"
            f"framerate={fps}/1,format=NV12 ! "
            f"nvvidconv ! video/x-raw,format=BGRx ! "
            f"videoconvert ! video/x-raw,format=BGR ! "
            f"appsink name=sink max-buffers=1 drop=true sync=false"
        )
        self.pipeline = Gst.parse_launch(pipeline_str)
        self.sink = self.pipeline.get_by_name("sink")
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self.pipeline.set_state(Gst.State.NULL)
            raise RuntimeError("Gagal memulai pipeline GStreamer (nvarguscamerasrc)")
        self._opened = True

    def isOpened(self):
        return self._opened

    def read(self):
        """Kembalikan (True, frame BGR numpy) atau (False, None)."""
        if not self._opened:
            return False, None
        sample = self.sink.emit("pull-sample")
        if sample is None:
            return False, None
        buf = sample.get_buffer()
        caps = sample.get_caps()
        structure = caps.get_structure(0)
        w = structure.get_value("width")
        h = structure.get_value("height")
        ok, map_info = buf.map(Gst.MapFlags.READ)
        if not ok:
            return False, None
        try:
            frame = np.ndarray(
                (h, w, 3), buffer=map_info.data, dtype=np.uint8
            ).copy()
        finally:
            buf.unmap(map_info)
        return True, apply_flip(frame)

    def release(self):
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
        self._opened = False


def gstreamer_available():
    return _HAS_GST
