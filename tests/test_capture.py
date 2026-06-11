from src.capture.screen_capture import ScreenCapture


class TestScreenCapture:
    def test_preprocess_grayscale(self):
        from PIL import Image, ImageChops

        img = Image.new("RGB", (100, 30), color="white")
        processed = ScreenCapture.preprocess(img)
        assert processed.mode == "L"
        assert processed.size == (100, 30)

    def test_preprocess_binarization(self):
        from PIL import Image

        img = Image.new("RGB", (100, 30), color="black")
        processed = ScreenCapture.preprocess(img)
        extrema = processed.getextrema()
        assert extrema[0] == 255

    def test_region_property(self):
        region = {"top": 0, "left": 50, "width": 100, "height": 80}
        sc = ScreenCapture(region)
        assert sc.region == region

    def test_region_setter(self):
        sc = ScreenCapture({"top": 0, "left": 0, "width": 10, "height": 10})
        new_region = {"top": 10, "left": 20, "width": 200, "height": 50}
        sc.region = new_region
        assert sc.region == new_region
