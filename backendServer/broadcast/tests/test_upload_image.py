"""Coverage for POST /broadcast/upload-image (T7): happy path, tier gating,
and rejection cases. Uploads are re-encoded via Pillow rather than trusted
as received — see broadcast/views.upload_image.
"""

import io
import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings, tag
from PIL import Image
from rest_framework.test import APIClient

from broadcast.models import BroadcastAccess, BroadcastImage

_MEDIA_ROOT = tempfile.mkdtemp(prefix="broadcast-media-test-")


def _jpeg_upload(name="event.jpg", size=(200, 150), color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


def _png_upload_with_alpha(name="event.png", size=(120, 80)):
    buf = io.BytesIO()
    Image.new("RGBA", size, (10, 200, 10, 128)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def _patch_jwt(email):
    return mock.patch("broadcast.access.verify_better_auth_jwt", return_value={"email": email})


@override_settings(RATELIMIT_ENABLE=False, MEDIA_ROOT=_MEDIA_ROOT)
@tag("db")
class UploadImageTest(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        BroadcastAccess.objects.create(email="uploader@example.com", tier=1)

    def _post(self, upload, email="uploader@example.com"):
        with _patch_jwt(email):
            return self.client.post(
                "/broadcast/upload-image",
                {"image": upload},
                format="multipart",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )

    def test_uploads_and_returns_absolute_url(self):
        resp = self._post(_jpeg_upload())
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertIn("url", body)
        self.assertTrue(body["url"].startswith("http"))
        self.assertEqual(BroadcastImage.objects.count(), 1)
        record = BroadcastImage.objects.get()
        self.assertEqual(record.client_label, "uploader@example.com")
        self.assertIn(record.image.url, body["url"])

    def test_forwarded_https_header_yields_https_url(self):
        # Regression for T46.2: nginx terminates TLS and proxies to gunicorn over
        # a Unix socket, so without SECURE_PROXY_SSL_HEADER (set in prod.py only)
        # request.build_absolute_uri() would compute an http:// URL on an https://
        # site — mixed-content blocked by every destination calendar. Simulate
        # prod's trust of X-Forwarded-Proto here since the test suite runs under
        # dev-derived settings, not prod.py.
        with override_settings(SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https")):
            with _patch_jwt("uploader@example.com"):
                resp = self.client.post(
                    "/broadcast/upload-image",
                    {"image": _jpeg_upload()},
                    format="multipart",
                    HTTP_AUTHORIZATION="Bearer faketoken",
                    HTTP_X_FORWARDED_PROTO="https",
                )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(resp.json()["url"].startswith("https://"))

    def test_png_with_alpha_is_reencoded_and_kept_as_png(self):
        resp = self._post(_png_upload_with_alpha())
        self.assertEqual(resp.status_code, 201, resp.content)
        record = BroadcastImage.objects.get()
        self.assertTrue(record.image.name.endswith(".png"))

    def test_tier_0_caller_is_forbidden(self):
        BroadcastAccess.objects.filter(email="uploader@example.com").update(tier=0)
        resp = self._post(_jpeg_upload())
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(BroadcastImage.objects.count(), 0)

    def test_non_image_upload_is_rejected(self):
        garbage = SimpleUploadedFile(
            "notes.txt", b"not an image, just some bytes", content_type="text/plain"
        )
        resp = self._post(garbage)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.json())
        self.assertEqual(BroadcastImage.objects.count(), 0)

    def test_malformed_image_bytes_are_rejected(self):
        # Valid JPEG magic bytes / content_type but truncated, unparseable body.
        malformed = SimpleUploadedFile(
            "broken.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 20, content_type="image/jpeg"
        )
        resp = self._post(malformed)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.json())
        self.assertEqual(BroadcastImage.objects.count(), 0)

    def test_oversized_file_is_rejected(self):
        # Exercise the 10MB size cap by lowering it rather than allocating a
        # real 10MB+ fixture image.
        with (
            _patch_jwt("uploader@example.com"),
            mock.patch("broadcast.serializers.MAX_IMAGE_UPLOAD_BYTES", 10),
        ):
            resp = self.client.post(
                "/broadcast/upload-image",
                {"image": _jpeg_upload()},
                format="multipart",
                HTTP_AUTHORIZATION="Bearer faketoken",
            )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.json())
        self.assertEqual(BroadcastImage.objects.count(), 0)

    def test_oversized_dimensions_are_downscaled_not_rejected(self):
        # Over the stored-output ceiling but well under the input pixel cap:
        # accepted, resized to fit, aspect ratio preserved.
        # views imports the name directly, so patch it where it is used.
        with mock.patch("broadcast.views.MAX_IMAGE_EDGE_PX", 400):
            resp = self._post(_jpeg_upload(size=(1000, 500)))
        self.assertEqual(resp.status_code, 201, resp.content)
        record = BroadcastImage.objects.get()
        with Image.open(record.image.path) as stored:
            self.assertEqual(stored.size, (400, 200))

    def test_image_within_output_ceiling_keeps_its_resolution(self):
        resp = self._post(_jpeg_upload(size=(1000, 500)))
        self.assertEqual(resp.status_code, 201, resp.content)
        record = BroadcastImage.objects.get()
        with Image.open(record.image.path) as stored:
            self.assertEqual(stored.size, (1000, 500))

    def test_excessive_pixel_count_is_rejected(self):
        # Guard against decode-memory blowup. Lower the cap rather than
        # allocating a real 80 MP fixture.
        with mock.patch("broadcast.serializers.MAX_IMAGE_PIXELS_IN", 1000):
            resp = self._post(_jpeg_upload(size=(200, 150)))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("resize it down", resp.json()["detail"])
        self.assertEqual(BroadcastImage.objects.count(), 0)

    def test_no_credentials_rejected(self):
        resp = self.client.post(
            "/broadcast/upload-image",
            {"image": _jpeg_upload()},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 403)
