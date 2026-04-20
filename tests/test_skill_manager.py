import unittest

from app.core.skill_manager import SkillManager


class SkillManagerTest(unittest.TestCase):
    def setUp(self):
        self.manager = SkillManager()

    def test_extract_download_url_from_anchor_text(self):
        html = """
        <html>
          <body>
            <a href="/files/demo.zip" class="button">
              <span>Download zip</span>
            </a>
          </body>
        </html>
        """

        result = self.manager._extract_download_url(html)

        self.assertEqual(result, "https://clawhub.ai/files/demo.zip")

    def test_extract_download_url_from_convex_fallback(self):
        html = """
        <html>
          <body>
            <script>
              window.__data = {"archive":"https://skill-resources.convex.site/demo.zip"};
            </script>
          </body>
        </html>
        """

        result = self.manager._extract_download_url(html)

        self.assertEqual(result, "https://skill-resources.convex.site/demo.zip")


if __name__ == "__main__":
    unittest.main()
