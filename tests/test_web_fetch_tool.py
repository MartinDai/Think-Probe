import os
import unittest

from app.tools.search import web_fetch


@unittest.skipUnless(os.getenv("TAVILY_API_KEY"), "TAVILY_API_KEY 未配置，跳过 Tavily 集成测试")
class WebFetchToolIntegrationTest(unittest.TestCase):
    def test_web_fetch_calls_tavily_http_and_returns_page_content(self):
        url = "https://fastapi.tiangolo.com/"
        result = web_fetch.invoke({
            "url": url,
            "extract_depth": "basic",
            "max_content_chars": 1500,
        })

        self.assertNotIn("Error:", result)
        self.assertIn("Fetched pages: 1", result)
        self.assertIn(f"URL: {url}", result)
        self.assertIn("Content:", result)


if __name__ == "__main__":
    unittest.main()
