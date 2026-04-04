"""
Simulation Database Query Tools for the Report Agent.

Provides direct access to the simulation SQLite databases (Twitter/Reddit) so the
report agent can analyse actual agent behaviour, debates, themes, and trends —
not just the seed knowledge graph.

Tools:
1. simulation_posts — Query posts/comments with persona enrichment
2. simulation_debates — Find opposing viewpoints and debate clusters
3. simulation_content_analysis — Theme trends, engagement metrics, content ratios
4. simulation_timeline — Round-by-round activity, quote chains, position shifts
"""

import csv
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logger import get_logger

logger = get_logger('miroclaw.simulation_tools')

# English stop words for keyword extraction
def _truncate_to_sentence(text: str, max_chars: int = 500) -> str:
    """Truncate text to max_chars, breaking at the last sentence boundary."""
    if not text or len(text) <= max_chars:
        return text
    # Find the last sentence-ending punctuation within the limit
    truncated = text[:max_chars]
    for sep in ['. ', '.\n', '! ', '? ', '!\n', '?\n']:
        last = truncated.rfind(sep)
        if last > max_chars * 0.3:  # Don't break too early
            return truncated[:last + 1].strip()
    # No good sentence boundary — just break at last space
    last_space = truncated.rfind(' ')
    if last_space > max_chars * 0.3:
        return truncated[:last_space].strip()
    return truncated.strip()


STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'shall', 'can', 'it', 'its', 'this',
    'that', 'these', 'those', 'i', 'you', 'he', 'she', 'we', 'they', 'me',
    'him', 'her', 'us', 'them', 'my', 'your', 'his', 'our', 'their', 'what',
    'which', 'who', 'whom', 'how', 'when', 'where', 'why', 'not', 'no', 'all',
    'if', 'than', 'then', 'so', 'as', 'very', 'just', 'about', 'also', 'some',
    'more', 'most', 'other', 'into', 'up', 'out', 'over', 'only', 'own',
    'same', 'such', 'each', 'every', 'both', 'few', 'many', 'much', 'any',
    'there', 'here', 'now', 'still', 'even', 'back', 'down', 'well',
    'through', 'during', 'before', 'after', 'above', 'below', 'between',
    'under', 'again', 'further', 'once', 'while', 'since', 'until',
    'because', 'although', 'though', 'whether', 'however', 'therefore',
    'thus', 'hence', 'yet', 'already', 'never', 'always', 'often',
    'say', 'said', 'like', 'know', 'think', 'see', 'make', 'go',
    'get', 'come', 'take', 'give', 'use', 'find', 'tell',
    'ask', 'work', 'call', 'try', 'need', 'become', 'keep',
    'let', 'begin', 'show', 'hear', 'play', 'run', 'move', 'live',
}


# ── Result Dataclasses ──


class SimulationPostsResult:
    """Result from simulation_posts tool."""

    def __init__(self, query: str, posts: List[Dict], total_posts: int,
                 platform: str, round_range: str, agent_type_filter: Optional[str] = None):
        self.query = query
        self.posts = posts
        self.total_posts = total_posts
        self.platform = platform
        self.round_range = round_range
        self.agent_type_filter = agent_type_filter

    def to_text(self) -> str:
        lines = [
            f"## Simulation Posts Query: \"{self.query}\"",
            f"Platform: {self.platform} | Round range: {self.round_range}"
        ]
        if self.agent_type_filter:
            lines.append(f"Agent type filter: {self.agent_type_filter}")
        lines.append(f"Found {len(self.posts)} matching posts (out of {self.total_posts} total)")
        lines.append("")

        for i, post in enumerate(self.posts, 1):
            content_preview = _truncate_to_sentence(post.get('content') or '', 500)
            round_info = f"Round {post.get('round', '?')}"
            likes = post.get('num_likes', 0)
            shares = post.get('num_shares', 0)
            is_original = "Original" if post.get('is_original') else "Quote/Repost"
            lines.append(f"**Post #{i}** by {post.get('author_name', 'Unknown')} "
                         f"({post.get('entity_type', '?')}, {post.get('profession', '')}) | "
                         f"{round_info} | Likes: {likes} | Shares: {shares} | {is_original}")
            if post.get('quote_content'):
                quote_preview = _truncate_to_sentence(post['quote_content'], 300)
                lines.append(f"  Quoting: \"{quote_preview}\"")
            lines.append(f'> "{content_preview}"')
            lines.append("")

        return "\n".join(lines)


class SimulationDebatesResult:
    """Result from simulation_debates tool."""

    def __init__(self, query: str, clusters: List[Dict], platform: str):
        self.query = query
        self.clusters = clusters
        self.platform = platform

    def to_text(self) -> str:
        lines = [
            f"## Debate Analysis: \"{self.query}\"",
            f"Platform: {self.platform} | Found {len(self.clusters)} debate clusters",
            ""
        ]

        for i, cluster in enumerate(self.clusters, 1):
            lines.append(f"### Debate Cluster {i}: \"{cluster.get('topic', 'Unknown')}\"")
            lines.append("")

            supporting = cluster.get('supporting', [])
            opposing = cluster.get('opposing', [])

            if supporting:
                lines.append(f"**Supporting/Defending ({len(supporting)} posts):**")
                for post in supporting[:3]:
                    content = _truncate_to_sentence(post.get('content') or '', 500)
                    lines.append(f"- {post.get('author_name', '?')} ({post.get('entity_type', '?')}): \"{content}\"")
                lines.append("")

            if opposing:
                lines.append(f"**Questioning/Opposing ({len(opposing)} posts):**")
                for post in opposing[:3]:
                    content = _truncate_to_sentence(post.get('content') or '', 500)
                    lines.append(f"- {post.get('author_name', '?')} ({post.get('entity_type', '?')}): \"{content}\"")
                lines.append("")

            breakdown = cluster.get('agent_type_breakdown', {})
            if breakdown:
                lines.append("**Agent type breakdown:**")
                for atype, positions in breakdown.items():
                    lines.append(f"- {atype}: {positions}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)


class SimulationContentResult:
    """Result from simulation_content_analysis tool."""

    def __init__(self, analysis_type: str, platform: str, data: Dict[str, Any]):
        self.analysis_type = analysis_type
        self.platform = platform
        self.data = data

    def to_text(self) -> str:
        lines = [f"## Content Analysis: {self.analysis_type} ({self.platform})"]

        if self.analysis_type == "overview":
            lines.append("")
            for k, v in self.data.items():
                lines.append(f"**{k}:** {v}")
            return "\n".join(lines)

        if self.analysis_type == "themes":
            themes_by_band = self.data.get('themes_by_band', {})
            for band_label, themes in themes_by_band.items():
                lines.append(f"\n**{band_label}:**")
                for theme in themes[:6]:
                    lines.append(f"- \"{theme['keyword']}\" ({theme['count']} mentions) — "
                                  f"Sample: \"{theme['sample']}\"")
                lines.append("")

            evolution = self.data.get('theme_evolution', [])
            if evolution:
                lines.append("**Theme Evolution:**")
                for e in evolution:
                    lines.append(f"- {e}")
            return "\n".join(lines)

        if self.analysis_type == "engagement":
            top_posts = self.data.get('top_posts', [])
            lines.append(f"\n### Top Posts by Engagement:")
            for i, post in enumerate(top_posts[:10], 1):
                content = _truncate_to_sentence(post.get('content') or '', 500)
                lines.append(f"{i}. **{post.get('author_name', '?')}** "
                             f"({post.get('entity_type', '?')}) | "
                             f"Likes: {post.get('num_likes', 0)} | Shares: {post.get('num_shares', 0)}")
                lines.append(f'> "{content}"')
                lines.append("")

            by_type = self.data.get('engagement_by_type', {})
            if by_type:
                lines.append("### Engagement by Agent Type:")
                for atype, stats in by_type.items():
                    lines.append(f"- **{atype}**: avg {stats.get('avg_likes', 0):.1f} likes/post, "
                                  f"{stats.get('total_posts', 0)} total posts")
            return "\n".join(lines)

        if self.analysis_type == "content_ratio":
            bands = self.data.get('bands', [])
            for band in bands:
                lines.append(f"\n**{band['label']}:**")
                lines.append(f"  Original: {band['originals']}, Quotes: {band['quotes']}, "
                              f"Reposts: {band['reposts']}, Do-nothing: {band['do_nothing']}")
                lines.append(f"  Total posts: {band['total']}, Active%: {band['active_pct']:.0f}%")
            overall = self.data.get('overall', '')
            if overall:
                lines.append(f"\n**Overall:** {overall}")
            return "\n".join(lines)

        return "\n".join(lines)


class SimulationTimelineResult:
    """Result from simulation_timeline tool."""

    def __init__(self, view_type: str, platform: str, data: Dict[str, Any]):
        self.view_type = view_type
        self.platform = platform
        self.data = data

    def to_text(self) -> str:
        lines = [f"## Timeline Analysis: {self.view_type} ({self.platform})"]

        if self.view_type == "timeline":
            rounds = self.data.get('rounds', [])
            for rd in rounds[:25]:
                lines.append(f"\n**Round {rd['round']}** ({rd['total_actions']} actions, {rd['active_agents']} active agents)")
                for action, count in rd.get('action_counts', {}).most_common(4):
                    lines.append(f"  {action}: {count}")
                samples = rd.get('sample_posts', [])
                for s in samples[:2]:
                    lines.append(f"  > {_truncate_to_sentence(s, 300)}")
            total_rounds = self.data.get('total_rounds', '?')
            lines.append(f"\nTotal rounds: {total_rounds}")
            return "\n".join(lines)

        if self.view_type == "quote_chains":
            chains = self.data.get('chains', [])
            if not chains:
                lines.append("\nNo quote chains found in this simulation.")
            for i, chain in enumerate(chains[:10], 1):
                lines.append(f"\n### Chain {i}: Original by {chain['original_author']}")
                content = _truncate_to_sentence(chain['original_content'] or '', 500)
                lines.append(f'> "{content}"')
                lines.append(f"  Reposted/quoted {chain['response_count']} times:")
                for resp in chain.get('responses', [])[:5]:
                    lines.append(f"  - {resp.get('author_name', '?')} ({resp.get('entity_type', '?')}): "
                                  f"\"{_truncate_to_sentence(resp.get('content') or '', 300)}\"")
            return "\n".join(lines)

        if self.view_type == "position_shifts":
            shifts = self.data.get('shifts', [])
            if not shifts:
                lines.append("\nNo clear position shifts detected in this simulation.")
            for i, shift in enumerate(shifts[:10], 1):
                lines.append(f"\n### Shift {i}: {shift['agent_name']} ({shift['entity_type']})")
                lines.append(f"  Early stance (R{shift.get('early_band', '?')}): {shift.get('early_stance', 'Unknown')}")
                lines.append(f"  Later stance (R{shift.get('late_band', '?')}): {shift.get('late_stance', 'Unknown')}")
                lines.append(f"  Evidence: {_truncate_to_sentence(shift.get('evidence') or '', 500)}")
            return "\n".join(lines)

        return "\n".join(lines)


# ── Main Service Class ──


class SimulationDBTools:
    """
    Simulation database query tools for the Report Agent.

    Reads directly from simulation SQLite databases and profile files.
    Provides the report agent with access to what agents actually said and did.
    """

    def __init__(self, simulation_id: str):
        self.simulation_id = simulation_id
        self.sim_dir = os.path.join(
            os.path.dirname(__file__),
            f'../../uploads/simulations/{simulation_id}'
        )
        self._profile_cache = None
        self._config_cache = None

    # ── Data Loading Helpers ──

    def _get_db_connection(self, platform: str) -> Optional[sqlite3.Connection]:
        db_path = os.path.join(self.sim_dir, f"{platform}_simulation.db")
        if not os.path.exists(db_path):
            return None
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _load_agent_profiles(self) -> Dict[int, Dict]:
        if self._profile_cache is not None:
            return self._profile_cache

        profiles = {}

        # Reddit profiles have richer data (profession, interested_topics, persona)
        reddit_path = os.path.join(self.sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_path):
            with open(reddit_path, 'r', encoding='utf-8') as f:
                for p in json.load(f):
                    profiles[p['user_id']] = {
                        'name': p.get('name', ''),
                        'username': p.get('username', ''),
                        'bio': p.get('bio', ''),
                        'persona': p.get('persona', ''),
                        'profession': p.get('profession', ''),
                        'interested_topics': p.get('interested_topics', []),
                    }

        # Twitter profiles as fallback
        twitter_path = os.path.join(self.sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_path) and not profiles:
            with open(twitter_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    uid = int(row.get('user_id', 0))
                    profiles[uid] = {
                        'name': row.get('name', ''),
                        'username': row.get('username', ''),
                        'bio': row.get('description', ''),
                        'persona': row.get('user_char', ''),
                        'profession': '',
                        'interested_topics': [],
                    }

        self._profile_cache = profiles
        return profiles

    def _load_simulation_config(self) -> Dict:
        if self._config_cache is not None:
            return self._config_cache

        config_path = os.path.join(self.sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            self._config_cache = {}
            return self._config_cache

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self._config_cache = config
        return config

    def _get_agent_info(self, agent_id: int) -> Dict:
        profiles = self._load_agent_profiles()
        config = self._load_simulation_config()

        profile = profiles.get(agent_id, {})

        # Find matching agent config by agent_id
        agent_config = {}
        for ac in config.get('agent_configs', []):
            if ac.get('agent_id') == agent_id:
                agent_config = ac
                break

        return {
            'name': profile.get('name') or agent_config.get('entity_name', f'Agent_{agent_id}'),
            'username': profile.get('username', ''),
            'bio': profile.get('bio', ''),
            'profession': profile.get('profession', ''),
            'entity_type': agent_config.get('entity_type', 'Unknown'),
            'entity_name': agent_config.get('entity_name', ''),
            'stance': agent_config.get('stance', 'unknown'),
            'influence_weight': agent_config.get('influence_weight', 1.0),
            'interested_topics': profile.get('interested_topics', []),
        }

    def _enrich_posts(self, raw_posts: List[Dict], platform: str) -> List[Dict]:
        enriched = []
        for post in raw_posts:
            agent_id = post.get('agent_id', post.get('user_id'))
            info = self._get_agent_info(agent_id)
            is_original = not post.get('original_post_id') or post.get('original_post_id') == 0
            round_num = self._get_round_for_post(post, platform)
            enriched.append({
                **post,
                'author_name': info['name'],
                'entity_type': info['entity_type'],
                'profession': info['profession'],
                'stance': info['stance'],
                'is_original': is_original,
                'round': round_num,
            })
        return enriched

    def _get_round_for_post(self, post: Dict, platform: str) -> int:
        created_at = post.get('created_at', 0)
        if platform == 'twitter':
            try:
                return int(created_at)
            except (ValueError, TypeError):
                return 0
        else:
            # Reddit uses timestamps — map to round via trace table
            return 0  # fallback

    def _get_rounds_for_platform(self, platform: str) -> List[int]:
        conn = self._get_db_connection(platform)
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            if platform == 'twitter':
                cursor.execute("SELECT DISTINCT CAST(created_at AS INTEGER) as r FROM post ORDER BY r")
            else:
                cursor.execute("SELECT 0")  # Reddit rounds are timestamp-based
            rounds = [row[0] for row in cursor.fetchall()]
            conn.close()
            return rounds
        except Exception:
            conn.close()
            return []

    def _keyword_search(self, posts: List[Dict], query: str) -> List[Dict]:
        terms = [t.lower() for t in query.split() if len(t) > 2]
        if not terms:
            return posts

        scored = []
        for post in posts:
            content = (post.get('content') or '').lower()
            quote = (post.get('quote_content') or '').lower()
            text = content + ' ' + quote
            score = sum(1 for t in terms if t in text)
            if score > 0:
                scored.append((score, post))

        scored.sort(key=lambda x: -x[0])
        return [post for _, post in scored]

    def _extract_keywords(self, texts: List[str], top_n: int = 15) -> List[Tuple[str, int]]:
        word_counts = Counter()
        for text in texts:
            words = re.findall(r'\b[a-z]{4,}\b', text.lower())
            words = [w for w in words if w not in STOP_WORDS]
            word_counts.update(words)
        return word_counts.most_common(top_n)

    def _get_all_posts(self, platform: str, limit: int = 500) -> List[Dict]:
        conn = self._get_db_connection(platform)
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.post_id, p.user_id, p.original_post_id, p.content, p.quote_content,
                       p.created_at, p.num_likes, p.num_dislikes, p.num_shares, p.num_reports,
                       u.agent_id, u.name as author_name, u.user_name, u.bio
                FROM post p
                JOIN user u ON p.user_id = u.user_id
                ORDER BY p.created_at ASC
                LIMIT ?
            """, (limit,))
            posts = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return posts
        except Exception as e:
            logger.error(f"Error querying {platform} posts: {e}")
            conn.close()
            return []

    def _get_all_comments(self, platform: str, limit: int = 500) -> List[Dict]:
        conn = self._get_db_connection(platform)
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.comment_id, c.post_id, c.user_id, c.content, c.created_at,
                       c.num_likes, c.num_dislikes,
                       u.agent_id, u.name as author_name, u.user_name, u.bio
                FROM comment c
                JOIN user u ON c.user_id = u.user_id
                ORDER BY c.num_likes DESC
                LIMIT ?
            """, (limit,))
            comments = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return comments
        except Exception as e:
            logger.error(f"Error querying {platform} comments: {e}")
            conn.close()
            return []

    def _get_trace_data(self, platform: str) -> List[Dict]:
        conn = self._get_db_connection(platform)
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, created_at, action, info
                FROM trace
                ORDER BY created_at
            """)
            traces = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return traces
        except Exception as e:
            logger.error(f"Error querying {platform} traces: {e}")
            conn.close()
            return []

    def _resolve_platform(self, platform: Optional[str]) -> List[str]:
        if platform in ('twitter', 'reddit'):
            return [platform]
        return ['twitter', 'reddit']

    # ── Tool 1: simulation_posts ──

    def get_posts(self, query: str, platform: Optional[str] = None,
                 agent_type: Optional[str] = None,
                 round_start: Optional[int] = None, round_end: Optional[int] = None,
                 sort_by: str = "engagement", limit: int = 20) -> str:
        """Query agent posts with persona enrichment."""
        platforms = self._resolve_platform(platform)
        all_enriched = []

        for plat in platforms:
            raw = self._get_all_posts(plat)
            enriched = self._enrich_posts(raw, plat)
            # Also get comments for reddit
            if plat == 'reddit':
                raw_comments = self._get_all_comments(plat)
                enriched_comments = self._enrich_posts(raw_comments, plat)
                enriched.extend(enriched_comments)
            all_enriched.extend(enriched)

        # Filter by keyword
        if query:
            all_enriched = self._keyword_search(all_enriched, query)

        # Filter by agent_type
        if agent_type:
            all_enriched = [p for p in all_enriched if p.get('entity_type', '').lower() == agent_type.lower()]

        # Filter by round range
        if round_start is not None:
            all_enriched = [p for p in all_enriched if p.get('round', 0) >= round_start]
        if round_end is not None:
            all_enriched = [p for p in all_enriched if p.get('round', 0) <= round_end]

        # Sort
        if sort_by == "engagement":
            all_enriched.sort(key=lambda p: (p.get('num_likes', 0) + p.get('num_shares', 0)), reverse=True)
        else:
            all_enriched.sort(key=lambda p: p.get('round', 0))

        total = len(all_enriched)
        limited = all_enriched[:limit]

        round_min = min((p.get('round', 0) for p in limited), default=0)
        round_max = max((p.get('round', 0) for p in limited), default=0)
        round_range = f"{round_min}-{round_max}" if limited else "N/A"

        result = SimulationPostsResult(
            query=query or "all",
            posts=limited,
            total_posts=total,
            platform=", ".join(platforms),
            round_range=round_range,
            agent_type_filter=agent_type,
        )
        return result.to_text()

    # ── Tool 2: simulation_debates ──

    def get_debates(self, query: str, platform: Optional[str] = None,
                    agent_type: Optional[str] = None, limit: int = 10) -> str:
        """Find opposing viewpoints and debate clusters."""
        platforms = self._resolve_platform(platform)
        all_enriched = []

        for plat in platforms:
            raw = self._get_all_posts(plat)
            enriched = self._enrich_posts(raw, plat)
            all_enriched.extend(enriched)

        if not all_enriched:
            return f"No posts found for debate analysis."

        # Filter by keyword
        if query:
            all_enriched = self._keyword_search(all_enriched, query)

        if agent_type:
            all_enriched = [p for p in all_enriched if p.get('entity_type', '').lower() == agent_type.lower()]

        # Split into stance groups based on configured stance
        stance_groups = defaultdict(list)
        for post in all_enriched:
            stance = post.get('stance', 'unknown')
            stance_groups[stance].append(post)

        # Build debate clusters by grouping contrasting stances
        SUPPORT_STANCES = {'supportive', 'strongly_supportive', 'advocate'}
        OPPOSE_STANCES = {'opposing', 'strongly_opposing', 'critical', 'skeptical'}

        clusters = []

        # Cluster 1: framework supporters vs framework skeptics
        supporting = [p for p in all_enriched if p.get('stance') in SUPPORT_STANCES]
        opposing = [p for p in all_enriched if p.get('stance') in OPPOSE_STANCES]
        neutral = [p for p in all_enriched if p.get('stance') in ('neutral', 'unknown')]

        if supporting or opposing:
            # Type breakdown
            type_breakdown = defaultdict(lambda: defaultdict(int))
            for p in supporting:
                type_breakdown[p.get('entity_type', 'Unknown')]['supporting'] += 1
            for p in opposing:
                type_breakdown[p.get('entity_type', 'Unknown')]['opposing'] += 1
            for p in neutral:
                type_breakdown[p.get('entity_type', 'Unknown')]['neutral'] += 1

            breakdown_text = {}
            for etype, counts in type_breakdown.items():
                parts = [f"{k}: {v}" for k, v in counts.items()]
                breakdown_text[etype] = ", ".join(parts)

            clusters.append({
                'topic': query or "framework debate",
                'supporting': supporting[:5],
                'opposing': opposing[:5],
                'agent_type_breakdown': breakdown_text,
            })

        # Cluster by entity type contrasts
        type_groups = defaultdict(list)
        for post in all_enriched:
            type_groups[post.get('entity_type', 'Unknown')].append(post)

        for etype, posts in type_groups.items():
            if len(posts) >= 2:
                clusters.append({
                    'topic': f"{etype} perspective on {query or 'main topic'}",
                    'supporting': posts[:3],
                    'opposing': [],
                    'agent_type_breakdown': {etype: f"{len(posts)} posts"},
                })

        result = SimulationDebatesResult(
            query=query,
            clusters=clusters[:limit],
            platform=", ".join(platforms),
        )
        return result.to_text()

    # ── Tool 3: simulation_content_analysis ──

    def get_content_analysis(self, analysis_type: str = "themes",
                             platform: Optional[str] = None,
                             round_start: Optional[int] = None,
                             round_end: Optional[int] = None,
                             agent_type: Optional[str] = None,
                             limit: int = 15) -> str:
        """Analyze themes, engagement, content ratios, or overview."""
        platforms = self._resolve_platform(platform)

        if analysis_type == "overview":
            return self._analysis_overview(platforms)
        elif analysis_type == "themes":
            return self._analysis_themes(platforms, round_start, round_end, agent_type, limit)
        elif analysis_type == "engagement":
            return self._analysis_engagement(platforms, agent_type, limit)
        elif analysis_type == "content_ratio":
            return self._analysis_content_ratio(platforms)
        else:
            return f"Unknown analysis type: {analysis_type}. Use: themes, engagement, content_ratio, overview"

    def _analysis_overview(self, platforms: List[str]) -> str:
        data = {}
        for plat in platforms:
            conn = self._get_db_connection(plat)
            if not conn:
                continue
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM post")
                posts = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM user")
                users = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM trace")
                traces = cursor.fetchone()[0]
                try:
                    cursor.execute("SELECT COUNT(*) FROM comment")
                    comments = cursor.fetchone()[0]
                except Exception:
                    comments = 0
                data[f"{plat.title()} posts"] = posts
                data[f"{plat.title()} comments"] = comments
                data[f"{plat.title()} traces"] = traces
                data[f"{plat.title()} agents"] = users
                conn.close()
            except Exception:
                conn.close()

        # Agent type distribution
        config = self._load_simulation_config()
        agent_configs = config.get('agent_configs', [])
        type_counts = Counter(ac.get('entity_type', 'Unknown') for ac in agent_configs)
        data["Agent type distribution"] = ", ".join(f"{t}: {c}" for t, c in type_counts.most_common())

        # Stance distribution
        stance_counts = Counter(ac.get('stance', 'unknown') for ac in agent_configs)
        data["Stance distribution"] = ", ".join(f"{s}: {c}" for s, c in stance_counts.most_common())

        # Agent roster grouped by entity type — provides key agents overview
        profiles = self._load_agent_profiles()
        by_type = defaultdict(list)
        for ac in agent_configs:
            aid = ac.get('agent_id', 0)
            profile = profiles.get(aid, {})
            by_type[ac.get('entity_type', 'Unknown')].append({
                'name': ac.get('entity_name') or profile.get('name', f'Agent_{aid}'),
                'stance': ac.get('stance', 'unknown'),
                'profession': profile.get('profession', ''),
                'influence_weight': ac.get('influence_weight', 1.0),
            })

        roster_lines = []
        for etype in sorted(by_type.keys()):
            agents = by_type[etype]
            # Sort by influence weight descending
            agents.sort(key=lambda a: -a.get('influence_weight', 1.0))
            roster_lines.append(f"**{etype}** ({len(agents)} agents):")
            for a in agents[:8]:  # Show top 8 per type
                parts = [a['name']]
                if a['profession']:
                    parts.append(a['profession'])
                parts.append(f"stance: {a['stance']}")
                if a['influence_weight'] > 1.0:
                    parts.append(f"influence: {a['influence_weight']}")
                roster_lines.append(f"  - {', '.join(parts)}")
            if len(agents) > 8:
                roster_lines.append(f"  - ... and {len(agents) - 8} more")
            roster_lines.append("")

        data["Agent roster"] = "\n".join(roster_lines)

        result = SimulationContentResult("overview", ", ".join(platforms), data)
        return result.to_text()

    def _analysis_themes(self, platforms: List[str],
                         round_start: Optional[int], round_end: Optional[int],
                         agent_type: Optional[str], limit: int) -> str:
        all_posts = []
        for plat in platforms:
            raw = self._get_all_posts(plat)
            enriched = self._enrich_posts(raw, plat)
            all_posts.extend(enriched)

        if agent_type:
            all_posts = [p for p in all_posts if p.get('entity_type', '').lower() == agent_type.lower()]

        # Group posts into bands of 10 rounds (for twitter)
        bands = defaultdict(list)
        for p in all_posts:
            r = p.get('round', 0)
            band = (r // 10) * 10
            bands[band].append(p)

        themes_by_band = {}
        for band_start in sorted(bands.keys()):
            if round_start is not None and band_start < round_start:
                continue
            if round_end is not None and band_start > round_end:
                continue

            band_posts = bands[band_start]
            texts = [p.get('content', '') for p in band_posts if p.get('content')]
            keywords = self._extract_keywords(texts, limit)

            band_label = f"Rounds {band_start}-{band_start + 9} ({len(band_posts)} posts)"
            themes_by_band[band_label] = [
                {
                    'keyword': kw,
                    'count': count,
                    'sample': _truncate_to_sentence(
                        next((p.get('content', '') for p in band_posts
                              if kw in (p.get('content') or '').lower()), ''), 300),
                }
                for kw, count in keywords
            ]

        # Theme evolution narrative
        evolution = []
        all_keywords_by_band = {}
        for band_label, themes in themes_by_band.items():
            all_keywords_by_band[band_label] = {t['keyword'] for t in themes}

        band_labels = list(all_keywords_by_band.keys())
        for i in range(1, len(band_labels)):
            prev = all_keywords_by_band[band_labels[i - 1]]
            curr = all_keywords_by_band[band_labels[i]]
            emerging = curr - prev
            declining = prev - curr
            if emerging:
                evolution.append(f"Emerging in {band_labels[i]}: {', '.join(list(emerging)[:5])}")
            if declining:
                evolution.append(f"Declining after {band_labels[i - 1]}: {', '.join(list(declining)[:5])}")

        result = SimulationContentResult("themes", ", ".join(platforms), {
            'themes_by_band': themes_by_band,
            'theme_evolution': evolution,
        })
        return result.to_text()

    def _analysis_engagement(self, platforms: List[str],
                             agent_type: Optional[str], limit: int) -> str:
        all_posts = []
        for plat in platforms:
            raw = self._get_all_posts(plat)
            enriched = self._enrich_posts(raw, plat)
            all_posts.extend(enriched)

        if agent_type:
            all_posts = [p for p in all_posts if p.get('entity_type', '').lower() == agent_type.lower()]

        # Top posts by engagement
        sorted_posts = sorted(all_posts,
                              key=lambda p: (p.get('num_likes', 0) + p.get('num_shares', 0)),
                              reverse=True)

        # Engagement by agent type
        type_stats = defaultdict(lambda: {'total_likes': 0, 'total_shares': 0, 'total_posts': 0})
        for p in all_posts:
            etype = p.get('entity_type', 'Unknown')
            type_stats[etype]['total_likes'] += p.get('num_likes', 0)
            type_stats[etype]['total_shares'] += p.get('num_shares', 0)
            type_stats[etype]['total_posts'] += 1

        engagement_by_type = {}
        for etype, stats in type_stats.items():
            avg_likes = stats['total_likes'] / max(stats['total_posts'], 1)
            engagement_by_type[etype] = {
                'avg_likes': round(avg_likes, 1),
                'total_posts': stats['total_posts'],
            }

        result = SimulationContentResult("engagement", ", ".join(platforms), {
            'top_posts': sorted_posts[:limit],
            'engagement_by_type': engagement_by_type,
        })
        return result.to_text()

    def _analysis_content_ratio(self, platforms: List[str]) -> str:
        bands_data = []

        for plat in platforms:
            all_posts = self._get_all_posts(plat)
            enriched = self._enrich_posts(all_posts, plat)
            traces = self._get_trace_data(plat)

            # Group by round band
            round_posts = defaultdict(list)
            for p in enriched:
                r = p.get('round', 0)
                band = (r // 10) * 10
                round_posts[band].append(p)

            round_do_nothing = defaultdict(int)
            for t in traces:
                if t.get('action') == 'do_nothing':
                    created = t.get('created_at', 0)
                    try:
                        r = int(created)
                    except (ValueError, TypeError):
                        r = 0
                    band = (r // 10) * 10
                    round_do_nothing[band] += 1

            for band_start in sorted(round_posts.keys()):
                posts = round_posts[band_start]
                originals = sum(1 for p in posts if p.get('is_original'))
                quotes = sum(1 for p in posts if not p.get('is_original'))
                reposts = sum(1 for p in posts if p.get('original_post_id') and not p.get('quote_content'))
                do_nothing = round_do_nothing.get(band_start, 0)
                total = len(posts)

                active_pct = (total / max(total + do_nothing, 1)) * 100
                bands_data.append({
                    'label': f"{plat.title()} Rounds {band_start}-{band_start + 9}",
                    'originals': originals,
                    'quotes': quotes,
                    'reposts': reposts,
                    'do_nothing': do_nothing,
                    'total': total,
                    'active_pct': active_pct,
                })

        overall_originals = sum(b['originals'] for b in bands_data)
        overall_total = sum(b['total'] for b in bands_data)
        overall_pct = (overall_originals / max(overall_total, 1)) * 100
        overall = f"{overall_originals} originals out of {overall_total} posts ({overall_pct:.0f}%)"

        result = SimulationContentResult("content_ratio", ", ".join(platforms), {
            'bands': bands_data,
            'overall': overall,
        })
        return result.to_text()

    # ── Tool 4: simulation_timeline ──

    def get_timeline(self, view_type: str = "timeline",
                     platform: Optional[str] = None,
                     round_start: Optional[int] = None,
                     round_end: Optional[int] = None,
                     agent_type: Optional[str] = None,
                     limit: int = 20) -> str:
        """Round-by-round activity, quote chains, or position shifts."""
        platforms = self._resolve_platform(platform)

        if view_type == "timeline":
            return self._timeline_rounds(platforms, round_start, round_end, limit)
        elif view_type == "quote_chains":
            return self._timeline_quote_chains(platforms, limit)
        elif view_type == "position_shifts":
            return self._timeline_position_shifts(platforms, round_start, round_end, limit)
        else:
            return f"Unknown view type: {view_type}. Use: timeline, quote_chains, position_shifts"

    def _timeline_rounds(self, platforms: List[str],
                         round_start: Optional[int], round_end: Optional[int],
                         limit: int) -> str:
        rounds_data = []

        for plat in platforms:
            traces = self._get_trace_data(plat)
            posts = self._get_all_posts(plat)
            enriched = self._enrich_posts(posts, plat)

            # Group by round
            round_traces = defaultdict(Counter)
            round_posts = defaultdict(list)
            round_agents = defaultdict(set)

            for t in traces:
                created = t.get('created_at', 0)
                try:
                    r = int(created)
                except (ValueError, TypeError):
                    r = 0
                action = t.get('action', 'unknown')
                uid = t.get('user_id')
                if action not in ('sign_up',):
                    round_traces[r][action] += 1
                    if uid is not None:
                        round_agents[r].add(uid)

            for p in enriched:
                r = p.get('round', 0)
                round_posts[r].append(p)

            for r in sorted(round_traces.keys()):
                if round_start is not None and r < round_start:
                    continue
                if round_end is not None and r > round_end:
                    continue

                action_counts = round_traces[r]
                sample_posts = [_truncate_to_sentence(p.get('content', ''), 300)
                                for p in round_posts.get(r, [])[:2]]

                rounds_data.append({
                    'round': r,
                    'total_actions': sum(action_counts.values()),
                    'active_agents': len(round_agents[r]),
                    'action_counts': action_counts,
                    'sample_posts': sample_posts,
                })

        rounds_data.sort(key=lambda x: x['round'])
        total_rounds = len(rounds_data)

        result = SimulationTimelineResult("timeline", ", ".join(platforms), {
            'rounds': rounds_data[:limit],
            'total_rounds': total_rounds,
        })
        return result.to_text()

    def _timeline_quote_chains(self, platforms: List[str], limit: int) -> str:
        chains = []

        for plat in platforms:
            posts = self._get_all_posts(plat)
            enriched = self._enrich_posts(posts, plat)

            # Group by original_post_id
            originals = {p['post_id']: p for p in enriched if p.get('is_original')}
            responses = defaultdict(list)
            for p in enriched:
                oid = p.get('original_post_id')
                if oid and oid != 0:
                    responses[oid].append(p)

            for orig_id, resps in sorted(responses.items(), key=lambda x: -len(x[1])):
                orig = originals.get(orig_id)
                if not orig:
                    continue
                chains.append({
                    'original_author': orig.get('author_name', 'Unknown'),
                    'original_content': orig.get('content', ''),
                    'response_count': len(resps),
                    'responses': [
                        {
                            'author_name': r.get('author_name', 'Unknown'),
                            'entity_type': r.get('entity_type', '?'),
                            'content': r.get('content', ''),
                        }
                        for r in resps[:5]
                    ],
                })

        chains.sort(key=lambda x: -x['response_count'])

        result = SimulationTimelineResult("quote_chains", ", ".join(platforms), {
            'chains': chains[:limit],
        })
        return result.to_text()

    def _timeline_position_shifts(self, platforms: List[str],
                                   round_start: Optional[int],
                                   round_end: Optional[int],
                                   limit: int) -> str:
        shifts = []

        for plat in platforms:
            posts = self._get_all_posts(plat)
            enriched = self._enrich_posts(posts, plat)

            # Group posts by agent
            agent_posts = defaultdict(list)
            for p in enriched:
                uid = p.get('user_id')
                if uid is not None:
                    agent_posts[uid].append(p)

            config = self._load_simulation_config()
            stance_map = {ac['agent_id']: ac.get('stance', 'unknown')
                         for ac in config.get('agent_configs', [])}

            for uid, posts in agent_posts.items():
                if len(posts) < 3:
                    continue

                posts_sorted = sorted(posts, key=lambda p: p.get('round', 0))

                # Split into early and late
                mid = len(posts_sorted) // 2
                early = posts_sorted[:mid]
                late = posts_sorted[mid:]

                if not early or not late:
                    continue

                # Simple stance detection: look for stance-revealing keywords
                early_keywords = self._extract_keywords(
                    [p.get('content', '') for p in early], 5)
                late_keywords = self._extract_keywords(
                    [p.get('content', '') for p in late], 5)

                early_top = set(kw for kw, _ in early_keywords)
                late_top = set(kw for kw, _ in late_keywords)

                # Only report if keyword overlap is low (meaning the agent shifted topics/stance)
                overlap = early_top & late_top
                if len(overlap) < 2 and early_top and late_top:
                    info = self._get_agent_info(uid)
                    early_stance = ", ".join(f"{kw} ({ct})" for kw, ct in early_keywords[:3])
                    late_stance = ", ".join(f"{kw} ({ct})" for kw, ct in late_keywords[:3])

                    early_round = early[0].get('round', 0)
                    late_round = late[-1].get('round', 0)

                    shifts.append({
                        'agent_name': info['name'],
                        'entity_type': info['entity_type'],
                        'early_band': f"R{early_round}",
                        'late_band': f"R{late_round}",
                        'early_stance': early_stance,
                        'late_stance': late_stance,
                        'evidence': _truncate_to_sentence(late[-1].get('content') or '', 500),
                    })

        result = SimulationTimelineResult("position_shifts", ", ".join(platforms), {
            'shifts': shifts[:limit],
        })
        return result.to_text()

    # ── Tool 5: simulation_position_drift ──

    def _load_position_drift(self) -> List[Dict[str, Any]]:
        """Load position_drift.json from the simulation directory."""
        drift_path = os.path.join(self.sim_dir, 'position_drift.json')
        if not os.path.exists(drift_path):
            return []
        try:
            with open(drift_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load position_drift.json: {e}")
            return []

    def get_position_drift(
        self,
        analysis_type: str = "overview",
        agent_type: Optional[str] = None,
        limit: int = 15,
    ) -> str:
        """Analyse persisted stance drift data from position_drift.json.

        Provides authoritative stance-shift analysis (not heuristic post-derived drift).

        Args:
            analysis_type: One of: overview, agent_breakdown, round_summary, transition_patterns
            agent_type: Optional entity type filter (e.g. "NationalTeam")
            limit: Max items to return for some views
        """
        drift_data = self._load_position_drift()
        if not drift_data:
            return "No position drift data found for this simulation."

        # Apply optional filter
        if agent_type:
            drift_data = [
                a for a in drift_data
                if a.get('entity_type', '').lower() == agent_type.lower()
            ]

        total_agents = len(drift_data)
        agents_with_shifts = [a for a in drift_data if a.get('changelog')]
        total_shift_events = sum(len(a.get('changelog', [])) for a in drift_data)

        if total_shift_events == 0:
            return (f"No recorded stance shifts found for this simulation. "
                    f"({total_agents} agents, all remained at their initial stance.)")

        if analysis_type == "overview":
            return self._drift_overview(drift_data, agents_with_shifts, total_shift_events)
        elif analysis_type == "agent_breakdown":
            return self._drift_agent_breakdown(drift_data, agents_with_shifts, limit)
        elif analysis_type == "round_summary":
            return self._drift_round_summary(drift_data, limit)
        elif analysis_type == "transition_patterns":
            return self._drift_transition_patterns(drift_data)
        else:
            return f"Unknown analysis_type: {analysis_type}. Use: overview, agent_breakdown, round_summary, transition_patterns"

    def _drift_overview(self, drift_data, agents_with_shifts, total_shift_events):
        lines = ["## Stance Drift Overview"]
        total_agents = len(drift_data)

        # Final stance distribution
        stance_counts = Counter(a.get('stance', 'unknown') for a in drift_data)
        lines.append(f"\n**Agents:** {total_agents} total, {len(agents_with_shifts)} with shifts, "
                     f"{total_agents - len(agents_with_shifts)} stable")
        lines.append(f"**Total shift events:** {total_shift_events}")
        lines.append(f"**Final stance distribution:** "
                     + ", ".join(f"{stance}: {count}" for stance, count in stance_counts.most_common()))

        # Flexibility stats
        flex_values = [a.get('epistemic_flexibility', 0) for a in drift_data]
        avg_flex = sum(flex_values) / max(len(flex_values), 1)
        lines.append(f"**Avg epistemic flexibility:** {avg_flex:.3f}")

        # Top volatile agents
        sorted_by_shifts = sorted(drift_data, key=lambda a: len(a.get('changelog', [])), reverse=True)
        lines.append("\n**Most volatile agents:**")
        for a in sorted_by_shifts[:5]:
            shifts = len(a.get('changelog', []))
            if shifts > 0:
                lines.append(f"  - {a.get('entity_name', a.get('agent_id'))} "
                            f"({a.get('entity_type', '')}, flex={a.get('epistemic_flexibility', 0):.3f}): "
                            f"{shifts} shifts, final stance: {a.get('stance', 'unknown')}")

        # Most stable agents
        stable = [a for a in drift_data if not a.get('changelog')]
        if stable:
            lines.append("\n**Stable agents (no shifts):**")
            for a in stable[:3]:
                lines.append(f"  - {a.get('entity_name', a.get('agent_id'))} "
                            f"({a.get('entity_type', '')}, flex={a.get('epistemic_flexibility', 0):.3f}): "
                            f"stance remained {a.get('stance', 'unknown')}")

        return "\n".join(lines)

    def _drift_agent_breakdown(self, drift_data, agents_with_shifts, limit):
        lines = ["## Agent Stance Drift Breakdown"]
        sorted_agents = sorted(drift_data, key=lambda a: len(a.get('changelog', [])), reverse=True)

        for a in sorted_agents[:limit]:
            name = a.get('entity_name', a.get('agent_id'))
            changelog = a.get('changelog', [])
            flex = a.get('epistemic_flexibility', 0)
            final_stance = a.get('stance', 'unknown')

            lines.append(f"\n### {name} ({a.get('entity_type', '')})")
            lines.append(f"  Flexibility: {flex:.3f} | Shifts: {len(changelog)} | Final stance: {final_stance}")

            if changelog:
                # Infer starting stance
                first_shift = changelog[0].get('shift', '')
                start_stance = first_shift.split(' -> ')[0] if ' -> ' in first_shift else 'unknown'
                lines.append(f"  Start stance: {start_stance}")

                # First and last shift
                first = changelog[0]
                last = changelog[-1]
                lines.append(f"  First shift (R{first.get('round', '?')}): {first.get('shift', '?')}")
                lines.append(f"  Last shift (R{last.get('round', '?')}): {last.get('shift', '?')}")

                # Sample evidence
                for entry in changelog[:3]:
                    evidence = _truncate_to_sentence(entry.get('evidence', ''), 120)
                    lines.append(f"  - R{entry.get('round', '?')}: {entry.get('shift', '?')} — {evidence}")

        return "\n".join(lines)

    def _drift_round_summary(self, drift_data, limit):
        lines = ["## Stance Drift by Round"]

        # Aggregate shifts per round
        round_shifts = defaultdict(list)
        for a in drift_data:
            for entry in a.get('changelog', []):
                rnd = entry.get('round', 0)
                round_shifts[rnd].append({
                    'agent': a.get('entity_name', a.get('agent_id')),
                    'shift': entry.get('shift', ''),
                    'evidence': entry.get('evidence', ''),
                })

        for rnd in sorted(round_shifts.keys())[:limit]:
            shifts = round_shifts[rnd]
            upvote_count = sum(1 for s in shifts if 'Upvoted' in s.get('evidence', ''))
            downvote_count = sum(1 for s in shifts if 'Downvoted' in s.get('evidence', ''))
            agents = Counter(s['agent'] for s in shifts)

            lines.append(f"\n**Round {rnd}:** {len(shifts)} shift(s)")
            lines.append(f"  Triggers: {upvote_count} upvotes, {downvote_count} downvotes")
            if agents:
                top_agents = ", ".join(f"{name} ({ct})" for name, ct in agents.most_common(3))
                lines.append(f"  Top shifting agents: {top_agents}")

        return "\n".join(lines)

    def _drift_transition_patterns(self, drift_data):
        lines = ["## Stance Transition Patterns"]

        transition_counts = Counter()
        trigger_counts = Counter()

        for a in drift_data:
            for entry in a.get('changelog', []):
                shift = entry.get('shift', '')
                if shift:
                    transition_counts[shift] += 1

                evidence = entry.get('evidence', '')
                if 'Upvoted' in evidence:
                    trigger_counts['Upvoted triple'] += 1
                elif 'Downvoted' in evidence:
                    trigger_counts['Downvoted triple'] += 1

        lines.append("\n**Transition frequency:**")
        for transition, count in transition_counts.most_common():
            lines.append(f"  {transition}: {count}")

        lines.append("\n**Evidence triggers:**")
        for trigger, count in trigger_counts.most_common():
            lines.append(f"  {trigger}: {count}")

        return "\n".join(lines)
