"""
OASIS Platform Plugin

Retains OASIS Twitter/Reddit databases and feed algorithms as an
interaction surface for MiroClaw agents, not the simulation backbone.

The create_post tool writes to OASIS's SQLite databases so posts appear
in other agents' feeds via OASIS's feed algorithm. The simulation loop
itself is CAMEL-native (Workforce), not OASIS's round_robin().

Satisfies: R04 (OASIS platform plugin)
"""

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from ...utils.logger import get_logger

logger = get_logger('miroclaw.oasis_platform')


class OasisPlatformPlugin:
    """Plugin that wraps OASIS social platform databases.

    Provides create_post functionality that writes to OASIS's SQLite
    databases, maintaining compatibility with the existing OASIS
    feed algorithms and database schemas.
    """

    def __init__(
        self,
        twitter_db_path: Optional[str] = None,
        reddit_db_path: Optional[str] = None,
    ):
        self.twitter_db_path = twitter_db_path
        self.reddit_db_path = reddit_db_path

    def create_post(
        self,
        agent_id: int,
        content: str,
        platform: str = "twitter",
    ) -> Dict[str, Any]:
        """Create a post on the OASIS social platform.

        Args:
            agent_id: The OASIS user_id for the posting agent.
            content: Post content text.
            platform: "twitter" or "reddit".

        Returns:
            Dict with success status and post_id.
        """
        if platform == "twitter" and self.twitter_db_path:
            return self._create_twitter_post(agent_id, content)
        elif platform == "reddit" and self.reddit_db_path:
            return self._create_reddit_post(agent_id, content)
        else:
            # Fallback: log the post without database write
            logger.info(
                f"[{platform}] Post from agent {agent_id}: {content[:100]}..."
            )
            return {
                "success": True,
                "post_id": None,
                "platform": platform,
                "note": "Post logged (no database available)",
            }

    def _create_twitter_post(
        self,
        agent_id: int,
        content: str,
    ) -> Dict[str, Any]:
        """Write a post to the OASIS Twitter SQLite database."""
        if not self.twitter_db_path:
            return {"success": False, "error": "Twitter database not configured"}

        try:
            conn = sqlite3.connect(self.twitter_db_path)
            cursor = conn.cursor()

            # Get the internal user_id from the user table
            cursor.execute(
                "SELECT user_id FROM user WHERE agent_id = ?",
                (agent_id,),
            )
            row = cursor.fetchone()
            if not row:
                conn.close()
                return {"success": False, "error": f"Agent {agent_id} not found in user table"}

            internal_user_id = row[0]

            # Insert post
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO post (user_id, content, created_at) VALUES (?, ?, ?)",
                (internal_user_id, content, created_at),
            )
            post_id = cursor.lastrowid

            # Log action in trace table
            info = json.dumps({"content": content})
            cursor.execute(
                "INSERT INTO trace (user_id, action, info, created_at) VALUES (?, ?, ?, ?)",
                (internal_user_id, "create_post", info, created_at),
            )

            conn.commit()
            conn.close()

            logger.info(f"[Twitter] Post created: agent_id={agent_id}, post_id={post_id}")
            return {
                "success": True,
                "post_id": post_id,
                "platform": "twitter",
            }

        except Exception as e:
            logger.error(f"Failed to create Twitter post: {e}")
            return {"success": False, "error": str(e)}

    def _create_reddit_post(
        self,
        agent_id: int,
        content: str,
    ) -> Dict[str, Any]:
        """Write a post to the OASIS Reddit SQLite database."""
        if not self.reddit_db_path:
            return {"success": False, "error": "Reddit database not configured"}

        try:
            conn = sqlite3.connect(self.reddit_db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT user_id FROM user WHERE agent_id = ?",
                (agent_id,),
            )
            row = cursor.fetchone()
            if not row:
                conn.close()
                return {"success": False, "error": f"Agent {agent_id} not found in user table"}

            internal_user_id = row[0]

            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S+00:00")
            cursor.execute(
                "INSERT INTO post (user_id, content, created_at) VALUES (?, ?, ?)",
                (internal_user_id, content, created_at),
            )
            post_id = cursor.lastrowid

            info = json.dumps({"content": content})
            cursor.execute(
                "INSERT INTO trace (user_id, action, info, created_at) VALUES (?, ?, ?, ?)",
                (internal_user_id, "create_post", info, created_at),
            )

            conn.commit()
            conn.close()

            logger.info(f"[Reddit] Post created: agent_id={agent_id}, post_id={post_id}")
            return {
                "success": True,
                "post_id": post_id,
                "platform": "reddit",
            }

        except Exception as e:
            logger.error(f"Failed to create Reddit post: {e}")
            return {"success": False, "error": str(e)}

    def get_feed(
        self,
        agent_id: int,
        platform: str = "twitter",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get posts from other agents for a given agent's feed.

        Uses OASIS's existing database schema to retrieve recent posts.
        """
        db_path = self.twitter_db_path if platform == "twitter" else self.reddit_db_path
        if not db_path:
            return []

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT p.post_id, p.content, p.created_at, u.agent_id, u.name
                FROM post p
                JOIN user u ON p.user_id = u.user_id
                WHERE u.agent_id != ?
                ORDER BY p.created_at DESC
                LIMIT ?
                """,
                (agent_id, limit),
            )
            posts = []
            for post_id, content, created_at, author_id, author_name in cursor.fetchall():
                posts.append({
                    "post_id": post_id,
                    "content": content,
                    "created_at": created_at,
                    "author_id": author_id,
                    "author_name": author_name,
                })
            conn.close()
            return posts
        except Exception as e:
            logger.error(f"Failed to get feed: {e}")
            return []
