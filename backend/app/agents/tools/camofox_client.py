"""
Camofox Browser Client — REST client for camofox-browser API

Wraps camofox-browser's REST API (https://github.com/jo-inc/camofox-browser)
to provide web search and page extraction for MiroClaw agents during the
Research phase.

Satisfies: R10 (Browser integration)
"""

import re
from typing import Any, Dict, List, Optional

import requests

from ...utils.logger import get_logger

logger = get_logger('miroclaw.camofox')

# Search macro mapping — config name to camofox macro
SEARCH_MACROS = {
    'wikipedia': '@wikipedia_search',
    'google': '@google_search',
    'reddit': '@reddit_search',
    'youtube': '@youtube_search',
}


class CamofoxBrowserClient:
    """REST client for camofox-browser server.

    Provides per-agent browser session isolation via userId/sessionKey.
    Each MiroClaw agent gets its own browser session so cookies, storage,
    and history never leak between agents.
    """

    def __init__(
        self,
        base_url: str = 'http://localhost:9377',
        request_timeout: int = 30,
        search_engine: str = 'wikipedia',
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = request_timeout
        self.search_engine = search_engine

        # Per-agent session tracking: {agent_id: (tab_id, session_key)}
        self._sessions: Dict[str, tuple] = {}
        self._session_counter = 0

    # ── Health ──────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Check if camofox-browser server is reachable."""
        try:
            resp = requests.get(
                f'{self.base_url}/health',
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get('ok', False) and data.get('browserConnected', False)
            return False
        except (requests.ConnectionError, requests.Timeout, Exception) as e:
            logger.warning(f'Camofox health check failed: {e}')
            return False

    # ── Search ──────────────────────────────────────────────────────

    def search(self, agent_id: str, query: str) -> Dict[str, Any]:
        """Perform a web search via camofox-browser.

        Creates a browser tab for the agent (reuses if one exists),
        navigates using the configured search macro, and returns
        parsed search results.
        """
        try:
            tab_id, session_key = self._get_or_create_session(agent_id)
            macro = SEARCH_MACROS.get(self.search_engine, '@wikipedia_search')

            # Navigate to search results
            nav_resp = requests.post(
                f'{self.base_url}/tabs/{tab_id}/navigate',
                json={
                    'userId': f'miroclaw_{agent_id}',
                    'macro': macro,
                    'query': query,
                },
                timeout=self.timeout,
            )
            nav_resp.raise_for_status()
            nav_data = nav_resp.json()

            if not nav_data.get('ok'):
                return {
                    'success': False,
                    'error': f"Navigation failed: {nav_data.get('error', 'unknown')}",
                    'results': [],
                }

            # Get accessibility snapshot of search results
            snapshot = self._get_snapshot(tab_id, agent_id)
            if not snapshot:
                return {
                    'success': False,
                    'error': 'Failed to get page snapshot',
                    'results': [],
                }

            # Parse results from snapshot
            results = self._parse_search_results(snapshot, nav_data.get('url', ''))
            return {
                'success': True,
                'query': query,
                'results': results,
            }

        except requests.ConnectionError:
            logger.warning(f'Camofox server unreachable for agent {agent_id}')
            return {
                'success': False,
                'error': 'Browser server unreachable',
                'results': [],
            }
        except requests.Timeout:
            logger.warning(f'Camofox request timeout for agent {agent_id}')
            return {
                'success': False,
                'error': 'Browser request timed out',
                'results': [],
            }
        except Exception as e:
            logger.error(f'Search failed for agent {agent_id}: {e}')
            return {
                'success': False,
                'error': str(e),
                'results': [],
            }

    # ── Extract ─────────────────────────────────────────────────────

    def extract(self, agent_id: str, url: str) -> Dict[str, Any]:
        """Extract text content from a URL via camofox-browser.

        Creates a new tab (or navigates existing), waits for load,
        and returns the accessibility tree as text.
        """
        try:
            tab_id, session_key = self._get_or_create_session(agent_id)

            # Navigate to URL
            nav_resp = requests.post(
                f'{self.base_url}/tabs/{tab_id}/navigate',
                json={
                    'userId': f'miroclaw_{agent_id}',
                    'url': url,
                },
                timeout=self.timeout,
            )
            nav_resp.raise_for_status()

            # Get snapshot
            snapshot = self._get_snapshot(tab_id, agent_id)
            if not snapshot:
                return {
                    'success': False,
                    'error': 'Failed to get page snapshot',
                    'content': '',
                }

            # Extract text from accessibility tree
            content = self._extract_text_from_snapshot(snapshot)

            return {
                'success': True,
                'url': url,
                'content': content,
            }

        except requests.ConnectionError:
            logger.warning(f'Camofox server unreachable for agent {agent_id}')
            return {
                'success': False,
                'error': 'Browser server unreachable',
                'content': '',
            }
        except requests.Timeout:
            logger.warning(f'Camofox request timeout for agent {agent_id}')
            return {
                'success': False,
                'error': 'Browser request timed out',
                'content': '',
            }
        except Exception as e:
            logger.error(f'Extract failed for agent {agent_id}: {e}')
            return {
                'success': False,
                'error': str(e),
                'content': '',
            }

    # ── Cleanup ─────────────────────────────────────────────────────

    def close_session(self, agent_id: str) -> None:
        """Close browser session for an agent."""
        if agent_id not in self._sessions:
            return
        tab_id, _ = self._sessions.pop(agent_id)
        try:
            requests.delete(
                f'{self.base_url}/tabs/{tab_id}',
                params={'userId': f'miroclaw_{agent_id}'},
                timeout=5,
            )
        except Exception:
            pass  # Best-effort cleanup

    def close_all_sessions(self) -> None:
        """Close all browser sessions."""
        for agent_id in list(self._sessions.keys()):
            self.close_session(agent_id)

    # ── Internal ────────────────────────────────────────────────────

    def _get_or_create_session(self, agent_id: str) -> tuple:
        """Get or create a browser tab session for an agent.

        Returns (tab_id, session_key).
        """
        if agent_id in self._sessions:
            return self._sessions[agent_id]

        self._session_counter += 1
        session_key = f'miroclaw_sim_{self._session_counter}'

        resp = requests.post(
            f'{self.base_url}/tabs',
            json={
                'userId': f'miroclaw_{agent_id}',
                'sessionKey': session_key,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        tab_id = data['tabId']

        self._sessions[agent_id] = (tab_id, session_key)
        logger.info(f'Created browser session for agent {agent_id}: tab={tab_id}')
        return (tab_id, session_key)

    def _get_snapshot(self, tab_id: str, agent_id: str) -> Optional[str]:
        """Get accessibility snapshot from a tab."""
        try:
            resp = requests.get(
                f'{self.base_url}/tabs/{tab_id}/snapshot',
                params={'userId': f'miroclaw_{agent_id}'},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get('snapshot', '')
        except Exception as e:
            logger.error(f'Snapshot failed: {e}')
            return None

    def _parse_search_results(self, snapshot: str, url: str) -> List[Dict[str, str]]:
        """Parse search results from accessibility tree snapshot.

        Extracts link text and URLs from the snapshot. Works with
        Wikipedia search results (primary engine) and falls back to
        generic link extraction for other engines.
        """
        results = []
        seen_urls = set()

        # Parse links from accessibility tree: link "text" [eN]: /url: href
        # Pattern: link "Title Text" [eN]:
        #   - /url: https://...
        link_pattern = re.finditer(
            r'link\s+"([^"]+)"\s+\[e\d+\]:\s*\n\s+-\s+/url:\s+"?([^"\n]+)"?',
            snapshot,
        )

        for match in link_pattern:
            title = match.group(1).strip()
            link_url = match.group(2).strip()

            # Skip navigation links, internal links
            if not link_url.startswith('http'):
                continue
            if any(skip in title.lower() for skip in [
                'main page', 'log in', 'create account', 'donate',
                'talk', 'edit', 'history', 'tools', 'search',
                'contents', 'about', 'help', 'jump to',
            ]):
                continue
            if link_url in seen_urls:
                continue

            seen_urls.add(link_url)
            results.append({
                'title': title,
                'url': link_url,
                'snippet': '',  # Snippets not available in accessibility tree
            })

            if len(results) >= 10:
                break

        return results

    def _extract_text_from_snapshot(self, snapshot: str) -> str:
        """Extract readable text content from accessibility tree.

        Strips element refs, navigation chrome, and structural markers
        to produce clean text suitable for agent consumption.
        """
        lines = []
        for line in snapshot.split('\n'):
            # Strip element ref markers like [e123]
            cleaned = re.sub(r'\s*\[e\d+\]', '', line)
            # Strip indentation markers
            cleaned = cleaned.strip('- ').strip()
            if not cleaned:
                continue

            # Extract text from "text: content" lines
            text_match = re.match(r'^text:\s*(.+)$', cleaned)
            if text_match:
                content = text_match.group(1).strip()
                if len(content) > 10:  # Skip very short text fragments
                    lines.append(content)
                continue

            # Extract link text (titles of linked resources)
            link_match = re.match(r'^link\s+"([^"]+)"', cleaned)
            if link_match:
                link_text = link_match.group(1).strip()
                if len(link_text) > 5:
                    lines.append(f'[{link_text}]')
                continue

            # Extract heading text
            heading_match = re.match(r'^heading\s+"([^"]+)"', cleaned)
            if heading_match:
                lines.append(f'\n## {heading_match.group(1).strip()}\n')
                continue

        content = '\n'.join(lines)
        # Cap at ~10K chars to prevent token overflow
        if len(content) > 10000:
            content = content[:10000] + '\n\n[... content truncated at 10000 chars ...]'

        return content


def create_browser_client_from_config() -> Optional['CamofoxBrowserClient']:
    """Create a CamofoxBrowserClient from application config.

    Returns None if camofox is disabled or server is unreachable.
    Called once during simulation setup, shared across all agents.
    """
    from ...config import Config

    if not Config.CAMOFOX_ENABLED:
        logger.info('Camofox browser disabled (CAMOFOX_ENABLED=false)')
        return None

    client = CamofoxBrowserClient(
        base_url=Config.CAMOFOX_URL,
        request_timeout=Config.CAMOFOX_REQUEST_TIMEOUT,
        search_engine=Config.CAMOFOX_SEARCH_ENGINE,
    )

    if not client.health_check():
        logger.warning(
            f'Camofox browser not reachable at {Config.CAMOFOX_URL}. '
            'Research tools will return empty results.'
        )
        return None

    logger.info(f'Camofox browser connected at {Config.CAMOFOX_URL}')
    return client
