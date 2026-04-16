import os
import unittest

from app.tools.search import web_search


@unittest.skipUnless(os.getenv("TAVILY_API_KEY"), "TAVILY_API_KEY 未配置，跳过 Tavily 集成测试")
class WebSearchToolIntegrationTest(unittest.TestCase):
    def test_web_search_calls_tavily_http_and_returns_results(self):
        result = web_search.invoke({
            "query": "FastAPI documentation",
            "max_results": 2,
            "fetch_content": True,
            "domains": ["fastapi.tiangolo.com"],
            "search_depth": "basic",
            "max_content_chars": 1200,
        })

        self.assertNotIn("Error:", result)
        self.assertIn("Web search provider: tavily", result)
        self.assertIn("Query: FastAPI documentation", result)
        self.assertIn("URL: https://fastapi.tiangolo.com/", result)
        self.assertIn("Content:", result)


if __name__ == "__main__":
    unittest.main()
