from threading import Lock
from PIL import Image, ImageOps
from mss import mss


class ScreenCapture:
    def __init__(self, region: dict):
        self._region = region
        self._lock = Lock()

    @property
    def region(self) -> dict:
        return self._region

    @region.setter
    def region(self, value: dict):
        with self._lock:
            self._region = value

    def capture(self) -> Image.Image:
        with self._lock:
            with mss() as sct:
                screenshot = sct.grab(self._region)
                return Image.frombytes("RGB", screenshot.size, screenshot.rgb)

    @staticmethod
    def preprocess(img: Image.Image, invert_dark: bool = True) -> Image.Image:
        img = img.convert("L")
        if invert_dark:
            extrema = img.getextrema()
            if extrema[1] < 128:
                img = ImageOps.invert(img)
        img = img.point(lambda x: 0 if x < 140 else 255)
        return img
