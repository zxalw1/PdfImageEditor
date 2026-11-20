# -*- coding: utf-8 -*-
import os

import pytest
from PIL import Image

from app.core import image_ops as io_
from app.core.image_ops import TransformOptions as T
from app.core.utils import HEIF, SAVE_FORMATS


def test_transform_rotate_flip():
    im = Image.new("RGB", (40, 20))
    assert io_.transform_image(im, T(rotate=1)).size == (20, 40)
    assert io_.transform_image(im, T(rotate=2)).size == (20, 40)
    assert io_.transform_image(im, T(rotate=3)).size == (40, 20)
    im.putpixel((0, 0), (255, 0, 0))
    assert io_.transform_image(im, T(flip_x=True)).getpixel((39, 0)) == (255, 0, 0)
    assert io_.transform_image(im, T(flip_y=True)).getpixel((0, 19)) == (255, 0, 0)


def test_transform_resize():
    im = Image.new("RGB", (400, 200))
    assert io_.transform_image(im, T(resize_mode=io_.RESIZE_PCT, pct=50)).size == (200, 100)
    assert io_.transform_image(im, T(resize_mode=io_.RESIZE_WIDTH, width=100)).size == (100, 50)
    assert io_.transform_image(im, T(resize_mode=io_.RESIZE_HEIGHT, height=50)).size == (100, 50)
    assert io_.transform_image(im, T(resize_mode=io_.RESIZE_BOX, width=100, height=100)).size == (100, 50)
    assert io_.transform_image(im, T(resize_mode=io_.RESIZE_BOX, width=100, height=100,
                                     keep_ratio=False)).size == (100, 100)
    # 확대 금지
    assert io_.transform_image(im, T(resize_mode=io_.RESIZE_WIDTH, width=800)).size == (400, 200)
    assert io_.transform_image(im, T(resize_mode=io_.RESIZE_WIDTH, width=800,
                                     no_upscale=False)).size == (800, 400)


@pytest.mark.parametrize("fmt", list(SAVE_FORMATS))
def test_save_all_formats(fmt, sample_png, tmp_path):
    im = io_.open_image(sample_png)
    dst = tmp_path / f"o.{fmt.lower()}"
    n = io_.save_image(im, str(dst), fmt, 85)
    assert n == os.path.getsize(dst) > 0
    Image.open(dst).verify()


def test_flatten_white(sample_png):
    im = io_.flatten_white(Image.open(sample_png))
    assert im.mode == "RGB"
    r, g, b = im.getpixel((0, 0))
    assert r == 255 and g > 100  # 반투명 빨강 + 흰 배경


@pytest.mark.parametrize("fmt", ["JPG", "WEBP", "PNG"])
def test_target_size(fmt, sample_jpg, tmp_path):
    im = io_.open_image(sample_jpg)
    dst = tmp_path / f"t.{fmt.lower()}"
    n = io_.save_image(im, str(dst), fmt, 90, target_kb=100)
    assert n <= 100 * 1024


def test_exif_orientation(tmp_path):
    im = Image.new("RGB", (40, 20))
    ex = Image.Exif()
    ex[0x0112] = 6  # 90° 회전 필요
    p = tmp_path / "rot.jpg"
    im.save(p, "JPEG", exif=ex.tobytes())
    assert io_.open_image(str(p)).size == (20, 40)


@pytest.mark.skipif(not HEIF, reason="pillow-heif 없음")
def test_heic(tmp_path):
    p = tmp_path / "a.heic"
    Image.new("RGB", (64, 48), (0, 128, 255)).save(p, "HEIF")
    im = io_.open_image(str(p))
    assert im.size == (64, 48)
    dst = tmp_path / "a.jpg"
    io_.save_image(im, str(dst), "JPG")
    assert Image.open(dst).format == "JPEG"


def test_batch_convert(sample_jpg, sample_png, tmp_path):
    out = tmp_path / "out"
    seen = []

    class Rec:
        def report(self, v, label=None):
            seen.append((v, label))

        def cancelled(self):
            return False
    res = io_.batch_convert([sample_jpg, sample_png, str(tmp_path / "none.jpg")], "원본 유지", 85, 0, "_x",
                            str(out), T(resize_mode=io_.RESIZE_PCT, pct=50), Rec())
    assert res.ok == 2 and len(res.errors) == 1
    assert sorted(os.listdir(out)) == ["alpha_x.png", "photo_x.jpg"]
    assert Image.open(out / "photo_x.jpg").size == (800, 600)
    assert seen[-1] == (3, None)


def test_batch_default_dir(sample_jpg, tmp_path):
    res = io_.batch_convert([sample_jpg], "PNG", 85, 0, "", "", T())
    assert res.last_dir == os.path.join(str(tmp_path), "변환")
    assert os.path.exists(os.path.join(res.last_dir, "photo.png"))
