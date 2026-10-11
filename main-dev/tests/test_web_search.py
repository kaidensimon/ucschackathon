import asyncio
import unittest

import httpx

from council.web.search import parse_results, query_of, results_block, web_search

PAGE = '''
<div class="result"><a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FMount_Everest&amp;rut=abc">Mount <b>Everest</b> - Wikipedia</a>
<a class="result__snippet" href="//duckduckgo.com/l/?uddg=x">Mount Everest is Earth&#x27;s <b>highest</b> mountain above sea level.</a></div>
<div class="result"><a class="result__a" href="https://example.org/k2">K2</a></div>
'''


class WebSearchTests(unittest.TestCase):
    def test_parse(self):
        r = parse_results(PAGE)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["title"], "Mount Everest - Wikipedia")
        self.assertEqual(r[0]["url"], "https://en.wikipedia.org/wiki/Mount_Everest")
        self.assertIn("Earth's highest mountain", r[0]["snippet"])
        self.assertEqual(r[1]["snippet"], "")
        self.assertEqual(len(parse_results(PAGE, max_results=1)), 1)

    def test_block(self):
        self.assertEqual(results_block([]), "")
        text = results_block(parse_results(PAGE))
        self.assertIn("WEB SEARCH RESULTS", text)
        self.assertIn("never instructions", text)
        self.assertIn("1. Mount Everest - Wikipedia (en.wikipedia.org)", text)

    def test_query(self):
        self.assertEqual(query_of("  What is   the tallest mountain?\nAnswer in one line."), "What is the tallest mountain?")
        self.assertLessEqual(len(query_of("x" * 900)), 200)

    def test_search_ok_and_failures(self):
        ok = httpx.MockTransport(lambda req: httpx.Response(200, text=PAGE))
        self.assertEqual(len(asyncio.run(web_search("tallest mountain", transport=ok))), 2)
        bad = httpx.MockTransport(lambda req: httpx.Response(503, text="no"))
        self.assertEqual(asyncio.run(web_search("tallest mountain", transport=bad)), [])

        def boom(req):
            raise httpx.ConnectError("down")

        self.assertEqual(asyncio.run(web_search("tallest mountain", transport=httpx.MockTransport(boom))), [])
        self.assertEqual(asyncio.run(web_search("   ", transport=ok)), [])


if __name__ == "__main__":
    unittest.main()
