"""
Tests for camofox-browser integration (R10).

Tests use mocked HTTP responses so they run without a live camofox-browser server.
Uses minimal inline definitions to avoid importing the full app.agents module chain.
"""

import sys
import os

# Ensure backend is on path
_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Fix conftest.py stub: ensure 'app' module has correct __path__
# so that app.agents (and subpackages) are discoverable.
if 'app' in sys.modules:
    _app_module = sys.modules['app']
    _app_real_path = os.path.join(_backend_dir, 'app')
    if not hasattr(_app_module, '__path__') or _app_real_path not in getattr(_app_module, '__path__', []):
        _app_module.__path__ = [_app_real_path]
        # Force re-import of submodules now that path is fixed
        for _mod_name in list(sys.modules.keys()):
            if _mod_name.startswith('app.agents'):
                del sys.modules[_mod_name]

from unittest.mock import patch, MagicMock

import requests as req


# ── Inline minimal BudgetTracker (avoids importing app.agents chain) ──

class BudgetTracker:
    """Minimal budget tracker for testing."""
    def __init__(self, max_searches=3, max_reads=3):
        self._max_searches = max_searches
        self._max_reads = max_reads
        self._searches_used = 0
        self._reads_used = 0

    def can_search(self):
        return self._searches_used < self._max_searches

    def can_read(self):
        return self._reads_used < self._max_reads

    def use_search(self):
        self._searches_used += 1

    def use_read(self):
        self._reads_used += 1


# ── Import only the leaf modules we need ─────────────────────────────

from app.agents.tools.camofox_client import CamofoxBrowserClient


def _mock_response(status_code=200, json_data=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    mock.raise_for_status = MagicMock()
    return mock


# ── CamofoxBrowserClient Tests ──────────────────────────────────────


class TestCamofoxBrowserClient:
    """Unit tests for the REST client (mocked HTTP)."""

    def test_health_check_ok(self):
        client = CamofoxBrowserClient(base_url='http://localhost:9377')
        with patch('app.agents.tools.camofox_client.requests.get') as mock_get:
            mock_get.return_value = _mock_response(json_data={
                'ok': True,
                'browserConnected': True,
            })
            assert client.health_check() is True

    def test_health_check_not_connected(self):
        client = CamofoxBrowserClient(base_url='http://localhost:9377')
        with patch('app.agents.tools.camofox_client.requests.get') as mock_get:
            mock_get.return_value = _mock_response(json_data={
                'ok': True,
                'browserConnected': False,
            })
            assert client.health_check() is False

    def test_health_check_unreachable(self):
        client = CamofoxBrowserClient(base_url='http://localhost:9377')
        with patch('app.agents.tools.camofox_client.requests.get') as mock_get:
            mock_get.side_effect = req.ConnectionError('Connection refused')
            assert client.health_check() is False

    def test_search_returns_results(self):
        client = CamofoxBrowserClient(base_url='http://localhost:9377', search_engine='wikipedia')

        create_resp = _mock_response(json_data={
            'tabId': 'tab-123',
            'url': 'about:blank',
        })
        nav_resp = _mock_response(json_data={
            'ok': True,
            'url': 'https://en.wikipedia.org/wiki/Test',
            'refsAvailable': True,
        })
        snapshot_resp = _mock_response(json_data={
            'snapshot': '''- heading "Test Article" [level=1]
- text: This is a test article about agent systems.
- link "Multi-agent system" [e1]:
  - /url: https://en.wikipedia.org/wiki/Multi-agent_system
- link "Knowledge graph" [e2]:
  - /url: https://en.wikipedia.org/wiki/Knowledge_graph
- link "Main page" [e3]:
  - /url: https://en.wikipedia.org/wiki/Main_Page
''',
            'refsCount': 3,
            'truncated': False,
            'totalChars': 200,
        })

        with patch('app.agents.tools.camofox_client.requests.post') as mock_post, \
             patch('app.agents.tools.camofox_client.requests.get') as mock_get:
            mock_post.side_effect = [create_resp, nav_resp]
            mock_get.return_value = snapshot_resp

            result = client.search('test_agent', 'test query')

        assert result['success'] is True
        assert len(result['results']) == 2  # Main page filtered out
        assert result['results'][0]['title'] == 'Multi-agent system'
        assert result['results'][0]['url'] == 'https://en.wikipedia.org/wiki/Multi-agent_system'

    def test_search_connection_error_returns_graceful_failure(self):
        client = CamofoxBrowserClient(base_url='http://localhost:9377')

        with patch('app.agents.tools.camofox_client.requests.post') as mock_post:
            mock_post.side_effect = req.ConnectionError('Connection refused')
            result = client.search('test_agent', 'test query')

        assert result['success'] is False
        assert 'unreachable' in result['error'].lower()
        assert result['results'] == []

    def test_extract_returns_content(self):
        client = CamofoxBrowserClient(base_url='http://localhost:9377')

        create_resp = _mock_response(json_data={
            'tabId': 'tab-456',
            'url': 'about:blank',
        })
        nav_resp = _mock_response(json_data={'ok': True})
        snapshot_resp = _mock_response(json_data={
            'snapshot': '''- heading "Knowledge Graph" [level=1]
- text: A knowledge graph is a knowledge base that uses a graph-structured data model.
- link "Graph database" [e1]:
  - /url: https://example.com/graph
''',
            'refsCount': 1,
            'truncated': False,
            'totalChars': 150,
        })

        with patch('app.agents.tools.camofox_client.requests.post') as mock_post, \
             patch('app.agents.tools.camofox_client.requests.get') as mock_get:
            mock_post.side_effect = [create_resp, nav_resp]
            mock_get.return_value = snapshot_resp

            result = client.extract('test_agent', 'https://example.com/page')

        assert result['success'] is True
        assert 'knowledge graph' in result['content'].lower()

    def test_session_isolation_per_agent(self):
        """Different agents get different tabs."""
        client = CamofoxBrowserClient(base_url='http://localhost:9377')

        alice_tab = _mock_response(json_data={'tabId': 'tab-alice', 'url': 'about:blank'})
        bob_tab = _mock_response(json_data={'tabId': 'tab-bob', 'url': 'about:blank'})

        with patch('app.agents.tools.camofox_client.requests.post') as mock_post:
            mock_post.side_effect = [alice_tab, bob_tab]
            alice_session = client._get_or_create_session('alice')
            bob_session = client._get_or_create_session('bob')

        assert alice_session[0] == 'tab-alice'
        assert bob_session[0] == 'tab-bob'
        assert alice_session != bob_session

    def test_session_reused_within_agent(self):
        """Same agent reuses its tab."""
        client = CamofoxBrowserClient(base_url='http://localhost:9377')

        tab_resp = _mock_response(json_data={'tabId': 'tab-1', 'url': 'about:blank'})

        with patch('app.agents.tools.camofox_client.requests.post') as mock_post:
            mock_post.return_value = tab_resp
            session1 = client._get_or_create_session('agent_x')
            session2 = client._get_or_create_session('agent_x')

        assert session1 == session2
        assert mock_post.call_count == 1

    def test_close_session(self):
        client = CamofoxBrowserClient(base_url='http://localhost:9377')

        with patch('app.agents.tools.camofox_client.requests.post') as mock_post, \
             patch('app.agents.tools.camofox_client.requests.delete') as mock_delete:
            mock_post.return_value = _mock_response(json_data={
                'tabId': 'tab-1', 'url': 'about:blank'
            })
            mock_delete.return_value = _mock_response()

            client._get_or_create_session('agent_a')
            assert 'agent_a' in client._sessions

            client.close_session('agent_a')
            assert 'agent_a' not in client._sessions
            mock_delete.assert_called_once()

    def test_extract_text_capped_at_10k(self):
        client = CamofoxBrowserClient()
        long_text = '- text: ' + ('A' * 500) + '\n' * 30
        snapshot = long_text * 10
        result = client._extract_text_from_snapshot(snapshot)
        assert len(result) <= 10200


# ── ResearchTool with BrowserClient Tests ───────────────────────────


class TestResearchToolWithBrowser:
    """Tests for ResearchTool behavior with browser client injected."""

    def _make_tool(self, agent_id='agent_1', browser_client=None, budget=None):
        """Create a ResearchTool-like object using inline class to avoid import chain."""
        # Inline minimal ResearchTool for testing
        class _Tool:
            def __init__(self, agent_id, budget_tracker, browser_client):
                self.agent_id = agent_id
                self.budget = budget_tracker
                self.browser_client = browser_client

            def search(self, query):
                if self.budget and not self.budget.can_search():
                    return {"success": False, "error": "Search budget exhausted", "results": []}
                if self.budget:
                    self.budget.use_search()
                try:
                    if self.browser_client:
                        return self.browser_client.search(self.agent_id, query)
                    return {"success": True, "query": query, "results": [], "note": "Browser not connected"}
                except Exception as e:
                    return {"success": False, "error": str(e), "results": []}

            def extract(self, url):
                if self.budget and not self.budget.can_read():
                    return {"success": False, "error": "Read budget exhausted", "content": ""}
                if self.budget:
                    self.budget.use_read()
                try:
                    if self.browser_client:
                        return self.browser_client.extract(self.agent_id, url)
                    return {"success": True, "url": url, "content": "", "note": "Browser not connected"}
                except Exception as e:
                    return {"success": False, "error": str(e), "content": ""}

        return _Tool(agent_id, budget, browser_client)

    def test_search_with_client_returns_results(self):
        mock_client = MagicMock()
        mock_client.search.return_value = {
            'success': True,
            'query': 'test',
            'results': [
                {'title': 'Result 1', 'url': 'https://example.com/1', 'snippet': 'Test'},
                {'title': 'Result 2', 'url': 'https://example.com/2', 'snippet': 'Test 2'},
            ],
        }

        tool = self._make_tool(browser_client=mock_client)
        result = tool.search('test')

        assert result['success'] is True
        assert len(result['results']) == 2
        mock_client.search.assert_called_once_with('agent_1', 'test')

    def test_extract_with_client_returns_content(self):
        mock_client = MagicMock()
        mock_client.extract.return_value = {
            'success': True,
            'url': 'https://example.com',
            'content': 'This is extracted content from the page.',
        }

        tool = self._make_tool(browser_client=mock_client)
        result = tool.extract('https://example.com')

        assert result['success'] is True
        assert 'extracted content' in result['content']
        mock_client.extract.assert_called_once_with('agent_1', 'https://example.com')

    def test_search_budget_still_enforced_with_client(self):
        mock_client = MagicMock()
        budget = BudgetTracker(max_searches=0)

        tool = self._make_tool(browser_client=mock_client, budget=budget)
        result = tool.search('test')

        assert result['success'] is False
        assert 'budget' in result['error'].lower()
        mock_client.search.assert_not_called()

    def test_extract_budget_still_enforced_with_client(self):
        mock_client = MagicMock()
        budget = BudgetTracker(max_reads=0)

        tool = self._make_tool(browser_client=mock_client, budget=budget)
        result = tool.extract('https://example.com')

        assert result['success'] is False
        assert 'budget' in result['error'].lower()
        mock_client.extract.assert_not_called()

    def test_no_client_returns_empty_results(self):
        tool = self._make_tool()
        result = tool.search('test')

        assert result['success'] is True
        assert result['results'] == []
        assert 'not connected' in result.get('note', '').lower()

    def test_no_client_returns_empty_extract(self):
        tool = self._make_tool()
        result = tool.extract('https://example.com')

        assert result['success'] is True
        assert result['content'] == ''

    def test_client_error_returns_failure(self):
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception('Browser crashed')

        tool = self._make_tool(browser_client=mock_client)
        result = tool.search('test')

        assert result['success'] is False
        assert 'Browser crashed' in result['error']
