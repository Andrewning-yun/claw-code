"""Configuration module for the bot.

Loads and validates configuration from environment variables.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """Bot configuration loaded from environment variables."""
    
    # Claude API settings
    anthropic_api_key: str
    anthropic_base_url: str
    anthropic_model: str
    anthropic_max_tokens: int
    anthropic_temperature: float
    
    # Scheduler settings
    scheduler_enabled: bool
    scheduler_check_interval: int  # seconds
    
    @classmethod
    def load_from_env(cls) -> "Config":
        """Load configuration from environment variables.
        
        Returns:
            Config instance with settings from environment.
            
        Raises:
            ValueError: If required configuration is missing or invalid.
        """
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        
        max_tokens_str = os.getenv("ANTHROPIC_MAX_TOKENS", "4096")
        try:
            max_tokens = int(max_tokens_str)
        except ValueError:
            max_tokens = 4096
            
        temp_str = os.getenv("ANTHROPIC_TEMPERATURE", "1.0")
        try:
            temperature = float(temp_str)
        except ValueError:
            temperature = 1.0
        
        # Scheduler settings
        scheduler_enabled = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
        check_interval_str = os.getenv("SCHEDULER_CHECK_INTERVAL", "60")
        try:
            check_interval = int(check_interval_str)
        except ValueError:
            check_interval = 60
        
        return cls(
            anthropic_api_key=api_key,
            anthropic_base_url=base_url,
            anthropic_model=model,
            anthropic_max_tokens=max_tokens,
            anthropic_temperature=temperature,
            scheduler_enabled=scheduler_enabled,
            scheduler_check_interval=check_interval,
        )
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of issues.
        
        Returns:
            List of validation error messages (empty if valid).
        """
        issues = []
        
        if not self.anthropic_api_key or self.anthropic_api_key == "your-api-key-here":
            issues.append("ANTHROPIC_API_KEY is not set or is placeholder")
        
        if not self.anthropic_base_url.startswith("http"):
            issues.append("ANTHROPIC_BASE_URL must be a valid URL")
        
        if self.anthropic_max_tokens <= 0:
            issues.append("ANTHROPIC_MAX_TOKENS must be positive")
        
        if not 0 <= self.anthropic_temperature <= 2:
            issues.append("ANTHROPIC_TEMPERATURE must be between 0 and 2")
        
        if self.scheduler_check_interval <= 0:
            issues.append("SCHEDULER_CHECK_INTERVAL must be positive")
        
        return issues


def get_config_path() -> Path:
    """Get the path to the .env file.
    
    Returns:
        Path to the .env file in the bot directory.
    """
    return Path(__file__).parent / ".env"


def load_env_file(path: Optional[Path] = None) -> None:
    """Load environment variables from .env file.
    
    Args:
        path: Path to .env file. Defaults to bot/.env
    """
    if path is None:
        path = get_config_path()
    
    if not path.exists():
        return
    
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                os.environ.setdefault(key, value)