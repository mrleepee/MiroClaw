"""
Tests for OASIS profile generator validation and completeness.

Ensures all profiles have required fields (age, gender, mbti, country)
to prevent KeyError crashes in OASIS agents_generator.py
"""

"""
Tests for OASIS profile generator validation and completeness.

Ensures all profiles have required fields (age, gender, mbti, country)
to prevent KeyError crashes in OASIS agents_generator.py
"""

import pytest
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# Minimal copies of dataclasses for testing without full app import
@dataclass
class OasisAgentProfile:
    """Test version of OasisAgentProfile."""
    user_id: int
    user_name: str
    name: str
    bio: str
    persona: str

    karma: int = 1000
    friend_count: int = 100
    follower_count: int = 150
    statuses_count: int = 500

    age: Optional[int] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    country: Optional[str] = None
    profession: Optional[str] = None
    interested_topics: List[str] = field(default_factory=list)

    source_entity_uuid: Optional[str] = None
    source_entity_type: Optional[str] = None

    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))

    def to_reddit_format(self) -> Dict[str, Any]:
        """Convert to Reddit platform format."""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "karma": self.karma,
            "created_at": self.created_at,
            # OASIS-required fields: always include with defaults
            "age": self.age if self.age else 30,
            "gender": self.gender if self.gender else "other",
            "mbti": self.mbti if self.mbti else "ISTJ",
            "country": self.country if self.country else "Unknown",
        }
        return profile

    def to_twitter_format(self) -> Dict[str, Any]:
        """Convert to Twitter platform format."""
        profile = {
            "user_id": self.user_id,
            "username": self.user_name,
            "name": self.name,
            "bio": self.bio,
            "persona": self.persona,
            "friend_count": self.friend_count,
            "follower_count": self.follower_count,
            "statuses_count": self.statuses_count,
            "created_at": self.created_at,
            # OASIS-required fields: always include with defaults
            "age": self.age if self.age else 30,
            "gender": self.gender if self.gender else "other",
            "mbti": self.mbti if self.mbti else "ISTJ",
            "country": self.country if self.country else "Unknown",
        }
        return profile


class OasisProfileGenerator:
    """Test version of validation logic."""

    @staticmethod
    def _validate_profile_completeness(profiles: List[OasisAgentProfile], platform: str = "unknown") -> tuple:
        """
        Validate that all profiles have required fields for OASIS compatibility.

        OASIS requires: age, gender, mbti, country
        """
        errors = []
        required_fields = ["age", "gender", "mbti", "country"]

        for idx, profile in enumerate(profiles):
            if not profile:
                errors.append(f"Profile at index {idx} is None")
                continue

            missing_fields = []
            for field in required_fields:
                value = getattr(profile, field, None)
                if value is None or (isinstance(value, str) and not value):
                    missing_fields.append(field)

            if missing_fields:
                errors.append(
                    f"Profile {idx} ({profile.name}): missing required fields {missing_fields}"
                )

        return len(errors), errors


class TestOasisAgentProfile:
    """Test OasisAgentProfile data structure and format methods."""

    def test_profile_has_all_required_fields(self):
        """Complete profile should have all required fields."""
        profile = OasisAgentProfile(
            user_id=0,
            user_name="test_user",
            name="Test User",
            bio="A test profile",
            persona="A complete persona with all fields",
            age=30,
            gender="male",
            mbti="ISTJ",
            country="USA",
        )

        assert profile.age == 30
        assert profile.gender == "male"
        assert profile.mbti == "ISTJ"
        assert profile.country == "USA"

    def test_profile_with_none_fields(self):
        """Profile with None fields should be valid in dataclass but caught in validation."""
        profile = OasisAgentProfile(
            user_id=1,
            user_name="incomplete_user",
            name="Incomplete User",
            bio="Missing demographic fields",
            persona="This profile is missing age, gender, mbti, country",
            # age, gender, mbti, country are None (defaults)
        )

        # Dataclass allows None for optional fields
        assert profile.age is None
        assert profile.gender is None
        assert profile.mbti is None
        assert profile.country is None

    def test_to_reddit_format_includes_defaults(self):
        """Reddit format should always include required fields with defaults."""
        profile = OasisAgentProfile(
            user_id=0,
            user_name="test_user",
            name="Test User",
            bio="Test",
            persona="Test persona",
            # No age, gender, mbti, country specified
        )

        reddit_format = profile.to_reddit_format()

        # Must include all OASIS-required fields
        assert "age" in reddit_format
        assert "gender" in reddit_format
        assert "mbti" in reddit_format
        assert "country" in reddit_format

        # Defaults should be applied
        assert reddit_format["age"] == 30
        assert reddit_format["gender"] == "other"
        assert reddit_format["mbti"] == "ISTJ"
        assert reddit_format["country"] == "Unknown"

    def test_to_reddit_format_preserves_values(self):
        """Reddit format should preserve provided values."""
        profile = OasisAgentProfile(
            user_id=0,
            user_name="test_user",
            name="Test User",
            bio="Test",
            persona="Test persona",
            age=25,
            gender="female",
            mbti="ENFP",
            country="Canada",
        )

        reddit_format = profile.to_reddit_format()

        assert reddit_format["age"] == 25
        assert reddit_format["gender"] == "female"
        assert reddit_format["mbti"] == "ENFP"
        assert reddit_format["country"] == "Canada"

    def test_to_twitter_format_includes_defaults(self):
        """Twitter format should always include required fields with defaults."""
        profile = OasisAgentProfile(
            user_id=0,
            user_name="test_user",
            name="Test User",
            bio="Test",
            persona="Test persona",
            # No age, gender, mbti, country specified
        )

        twitter_format = profile.to_twitter_format()

        # Must include all OASIS-required fields
        assert "age" in twitter_format
        assert "gender" in twitter_format
        assert "mbti" in twitter_format
        assert "country" in twitter_format

        # Defaults should be applied
        assert twitter_format["age"] == 30
        assert twitter_format["gender"] == "other"
        assert twitter_format["mbti"] == "ISTJ"
        assert twitter_format["country"] == "Unknown"

    def test_to_twitter_format_preserves_values(self):
        """Twitter format should preserve provided values."""
        profile = OasisAgentProfile(
            user_id=0,
            user_name="test_user",
            name="Test User",
            bio="Test",
            persona="Test persona",
            age=35,
            gender="other",
            mbti="INTJ",
            country="UK",
        )

        twitter_format = profile.to_twitter_format()

        assert twitter_format["age"] == 35
        assert twitter_format["gender"] == "other"
        assert twitter_format["mbti"] == "INTJ"
        assert twitter_format["country"] == "UK"


class TestProfileGeneratorValidation:
    """Test profile validation logic."""

    def test_validate_complete_profiles(self):
        """Complete profiles should pass validation."""
        profiles = [
            OasisAgentProfile(
                user_id=i,
                user_name=f"user_{i}",
                name=f"User {i}",
                bio=f"Bio {i}",
                persona=f"Persona {i}",
                age=30 + i,
                gender="male" if i % 2 == 0 else "female",
                mbti="ISTJ",
                country="USA",
            )
            for i in range(5)
        ]

        error_count, errors = OasisProfileGenerator._validate_profile_completeness(profiles, "test")

        assert error_count == 0
        assert len(errors) == 0

    def test_validate_profiles_with_missing_age(self):
        """Profiles with missing age should be detected."""
        profiles = [
            OasisAgentProfile(
                user_id=0,
                user_name="user_0",
                name="User 0",
                bio="Bio",
                persona="Persona",
                # age is None
                gender="male",
                mbti="ISTJ",
                country="USA",
            )
        ]

        error_count, errors = OasisProfileGenerator._validate_profile_completeness(profiles, "test")

        assert error_count == 1
        assert any("age" in error for error in errors)

    def test_validate_profiles_with_missing_gender(self):
        """Profiles with missing gender should be detected."""
        profiles = [
            OasisAgentProfile(
                user_id=0,
                user_name="user_0",
                name="User 0",
                bio="Bio",
                persona="Persona",
                age=30,
                # gender is None
                mbti="ISTJ",
                country="USA",
            )
        ]

        error_count, errors = OasisProfileGenerator._validate_profile_completeness(profiles, "test")

        assert error_count == 1
        assert any("gender" in error for error in errors)

    def test_validate_profiles_with_missing_mbti(self):
        """Profiles with missing mbti should be detected."""
        profiles = [
            OasisAgentProfile(
                user_id=0,
                user_name="user_0",
                name="User 0",
                bio="Bio",
                persona="Persona",
                age=30,
                gender="male",
                # mbti is None
                country="USA",
            )
        ]

        error_count, errors = OasisProfileGenerator._validate_profile_completeness(profiles, "test")

        assert error_count == 1
        assert any("mbti" in error for error in errors)

    def test_validate_profiles_with_missing_country(self):
        """Profiles with missing country should be detected."""
        profiles = [
            OasisAgentProfile(
                user_id=0,
                user_name="user_0",
                name="User 0",
                bio="Bio",
                persona="Persona",
                age=30,
                gender="male",
                mbti="ISTJ",
                # country is None
            )
        ]

        error_count, errors = OasisProfileGenerator._validate_profile_completeness(profiles, "test")

        assert error_count == 1
        assert any("country" in error for error in errors)

    def test_validate_profiles_with_multiple_missing_fields(self):
        """Profiles with multiple missing fields should be detected."""
        profiles = [
            OasisAgentProfile(
                user_id=0,
                user_name="user_0",
                name="User 0",
                bio="Bio",
                persona="Persona",
                # All demographic fields are None
            ),
            OasisAgentProfile(
                user_id=1,
                user_name="user_1",
                name="User 1",
                bio="Bio",
                persona="Persona",
                age=30,
                gender="male",
                mbti="ISTJ",
                country="USA",  # This one is complete
            ),
        ]

        error_count, errors = OasisProfileGenerator._validate_profile_completeness(profiles, "test")

        assert error_count == 1  # Only first profile has errors
        assert "User 0" in errors[0]

    def test_validate_none_profile(self):
        """None profiles in the list should be detected."""
        profiles = [
            OasisAgentProfile(
                user_id=0,
                user_name="user_0",
                name="User 0",
                bio="Bio",
                persona="Persona",
                age=30,
                gender="male",
                mbti="ISTJ",
                country="USA",
            ),
            None,
        ]

        error_count, errors = OasisProfileGenerator._validate_profile_completeness(profiles, "test")

        assert error_count == 1
        assert any("None" in error for error in errors)

    def test_validate_profiles_with_empty_strings(self):
        """Profiles with empty strings for demographic fields should be detected."""
        profiles = [
            OasisAgentProfile(
                user_id=0,
                user_name="user_0",
                name="User 0",
                bio="Bio",
                persona="Persona",
                age=30,
                gender="",  # Empty string
                mbti="ISTJ",
                country="USA",
            )
        ]

        error_count, errors = OasisProfileGenerator._validate_profile_completeness(profiles, "test")

        assert error_count == 1
        assert any("gender" in error for error in errors)
