"""
Configuration Management
Loads configuration from .env file in project root directory
"""

import os
from dotenv import load_dotenv

# Load .env file from project root directory
# Path: MiroClaw/.env (relative to backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # If no .env in root, try loading from environment variables (for production)
    load_dotenv(override=True)


class Config:
    """Flask configuration class"""

    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY', 'miroclaw-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'

    # JSON settings - disable ASCII escaping for non-ASCII characters
    JSON_AS_ASCII = False

    # LLM configuration (OpenAI-compatible format)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')

    # Neo4j configuration
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'miroclaw_password')

    # Embedding model configuration
    EMBEDDING_MODEL_NAME = os.environ.get('EMBEDDING_MODEL_NAME', 'Qwen/Qwen3-Embedding-4B')

    # File upload settings
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    # Text processing settings
    DEFAULT_CHUNK_SIZE = 500  # Default chunk size
    DEFAULT_CHUNK_OVERLAP = 50  # Default overlap size

    # OASIS simulation settings
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')

    # Stage 4 Optimization: Simulation tuning
    SIMULATION_BATCH_SIZE = int(os.environ.get('SIMULATION_BATCH_SIZE', '119'))
    SIMULATION_AGENT_ACTIVITY_RATE = float(os.environ.get('SIMULATION_AGENT_ACTIVITY_RATE', '0.3'))
    SIMULATION_ROUNDS_MAX = int(os.environ.get('SIMULATION_ROUNDS_MAX', '50'))
    SIMULATION_PARALLEL_PLATFORMS = os.environ.get('SIMULATION_PARALLEL_PLATFORMS', 'true').lower() == 'true'

    # OASIS platform available actions
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]

    # Report Agent settings
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    # MiroClaw Oracle settings
    ORACLE_MODEL_URL = os.environ.get('ORACLE_MODEL_URL', 'http://localhost:8080/v1')
    ORACLE_MODEL_NAME = os.environ.get('ORACLE_MODEL_NAME', 'openforecaster-8b')
    ORACLE_MODEL_API_KEY = os.environ.get('ORACLE_MODEL_API_KEY', 'sk-placeholder')
    ORACLE_FORECAST_INTERVAL = int(os.environ.get('ORACLE_FORECAST_INTERVAL', '5'))

    # Camofox browser integration (R10)
    CAMOFOX_URL = os.environ.get('CAMOFOX_URL', 'http://localhost:9377')
    CAMOFOX_ENABLED = os.environ.get('CAMOFOX_ENABLED', 'true').lower() == 'true'
    CAMOFOX_REQUEST_TIMEOUT = int(os.environ.get('CAMOFOX_REQUEST_TIMEOUT', '30'))
    CAMOFOX_SEARCH_ENGINE = os.environ.get('CAMOFOX_SEARCH_ENGINE', 'wikipedia')

    # MiroClaw research budget settings
    MIROCLAW_MAX_SEARCHES = int(os.environ.get('MIROCLAW_MAX_SEARCHES', '3'))
    MIROCLAW_MAX_READS = int(os.environ.get('MIROCLAW_MAX_READS', '3'))
    MIROCLAW_MAX_GRAPH_ADDITIONS = int(os.environ.get('MIROCLAW_MAX_GRAPH_ADDITIONS', '1'))
    MIROCLAW_MAX_ORACLE_CONSULTATIONS = int(os.environ.get('MIROCLAW_MAX_ORACLE_CONSULTATIONS', '1'))

    # MiroClaw curator settings
    MIROCLAW_GRAPH_SIZE_CEILING = int(os.environ.get('MIROCLAW_GRAPH_SIZE_CEILING', '5000'))
    MIROCLAW_CONTESTED_UPVOTE_THRESHOLD = int(os.environ.get('MIROCLAW_CONTESTED_UPVOTE_THRESHOLD', '3'))
    MIROCLAW_CONTESTED_DOWNVOTE_THRESHOLD = int(os.environ.get('MIROCLAW_CONTESTED_DOWNVOTE_THRESHOLD', '3'))

    # MiroClaw cross-session evolution
    MIROCLAW_MEMORY_DIR = os.environ.get(
        'MIROCLAW_MEMORY_DIR',
        os.path.join(os.path.dirname(__file__), '../uploads/miroclaw_memory')
    )

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY is not configured")
        if not cls.NEO4J_PASSWORD:
            errors.append("NEO4J_PASSWORD is not configured")
        return errors
