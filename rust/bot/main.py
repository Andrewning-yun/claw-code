"""Claude Bot - Main entry point.

A Discord/Telegram bot that integrates with Claude API for AI conversations
and includes scheduled task functionality.
"""

import asyncio
import logging
import signal
import sys
from typing import Optional

from config import Config, load_env_file, get_config_path
from scheduler import TaskScheduler
from claude_client import ClaudeClient
from handlers import ClaudeHandler, SchedulerHandler


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Bot:
    """Main bot class that coordinates all components."""
    
    def __init__(self, config: Config):
        """Initialize the bot with configuration.
        
        Args:
            config: Bot configuration.
        """
        self.config = config
        self.scheduler: Optional[TaskScheduler] = None
        self.claude_client: Optional[ClaudeClient] = None
        self.claude_handler: Optional[ClaudeHandler] = None
        self.scheduler_handler: Optional[SchedulerHandler] = None
        self._running = False
        
    async def initialize(self) -> None:
        """Initialize all bot components."""
        logger.info("Initializing bot...")
        
        # Initialize scheduler
        if self.config.scheduler_enabled:
            self.scheduler = TaskScheduler(
                check_interval=self.config.scheduler_check_interval
            )
            self.scheduler_handler = SchedulerHandler(self.scheduler)
            logger.info("Scheduler initialized")
        
        # Initialize Claude client
        self.claude_client = ClaudeClient(self.config)
        logger.info("Claude client initialized")
        
        # Initialize handlers
        self.claude_handler = ClaudeHandler(
            client=self.claude_client,
            scheduler=self.scheduler
        )
        logger.info("Handlers initialized")
        
    async def start(self) -> None:
        """Start the bot and all its components."""
        if self._running:
            return
            
        self._running = True
        logger.info("Starting bot...")
        
        # Start scheduler if enabled
        if self.scheduler:
            asyncio.create_task(self.scheduler.start())
            
        logger.info("Bot started successfully!")
        
    async def stop(self) -> None:
        """Stop the bot and cleanup resources."""
        logger.info("Stopping bot...")
        self._running = False
        
        # Stop scheduler
        if self.scheduler:
            await self.scheduler.stop()
            
        # Close Claude client
        if self.claude_client:
            await self.claude_client.close()
            
        logger.info("Bot stopped")
        
    async def handle_command(self, command: str, args: str) -> str:
        """Handle a bot command.
        
        Args:
            command: The command name (e.g., /claude, /scheduler).
            args: Command arguments.
            
        Returns:
            Command response.
        """
        if command == "/claude":
            if not self.claude_handler:
                return "Claude handler not initialized"
            # Forward to Claude handler
            return "Claude chat mode - send your message"
            
        elif command in ("/scheduler", "/cron", "/task"):
            if not self.scheduler_handler:
                return "Scheduler not enabled"
            return self.scheduler_handler.handle_command(args)
            
        elif command == "/status":
            lines = ["Bot Status:", f"  Running: {self._running}"]
            
            if self.scheduler:
                status = self.scheduler.get_status()
                lines.append(f"  Scheduler: {status['running']}")
                lines.append(f"  Tasks: {status['task_count']}")
                
            return "\n".join(lines)
            
        elif command == "/help":
            return self._get_help_text()
            
        return f"Unknown command: {command}"
    
    def _get_help_text(self) -> str:
        """Get help text for available commands."""
        return """Claude Bot Commands:
  /claude <message>  - Chat with Claude
  /scheduler <args>  - Manage scheduled tasks
  /cron <args>       - Cron expression help
  /task <args>       - Alias for /scheduler
  /status            - Show bot status
  /help              - Show this help"""


async def main():
    """Main entry point."""
    # Load environment variables from .env file
    load_env_file()
    
    # Load configuration
    try:
        config = Config.load_from_env()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.info(f"Please configure your settings in {get_config_path()}")
        sys.exit(1)
    
    # Validate configuration
    issues = config.validate()
    if issues:
        logger.warning("Configuration issues:")
        for issue in issues:
            logger.warning(f"  - {issue}")
    
    # Create and initialize bot
    bot = Bot(config)
    
    # Setup signal handlers
    loop = asyncio.get_event_loop()
    
    def signal_handler(sig):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(bot.stop())
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    # Initialize and start
    await bot.initialize()
    await bot.start()
    
    # Keep running
    try:
        while bot._running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await bot.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        sys.exit(1)