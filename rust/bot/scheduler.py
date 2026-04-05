"""Task scheduler for the bot.

Provides cron-like scheduling for periodic tasks.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from croniter import croniter

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    """Represents a scheduled task."""
    id: str
    name: str
    schedule: str  # cron expression
    handler: Callable[..., Any]
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    error_count: int = 0
    kwargs: dict = field(default_factory=dict)
    
    def get_next_run_time(self, base_time: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate the next run time based on cron expression.
        
        Args:
            base_time: Base time for calculation. Defaults to now.
            
        Returns:
            Next scheduled run time or None if invalid.
        """
        if base_time is None:
            base_time = datetime.now()
            
        try:
            cron = croniter(self.schedule, base_time)
            return cron.get_next(datetime)
        except (KeyError, ValueError) as e:
            logger.error(f"Invalid cron expression '{self.schedule}': {e}")
            return None


class TaskScheduler:
    """Manages scheduled tasks with cron-like expressions."""
    
    def __init__(self, check_interval: int = 60):
        """Initialize the scheduler.
        
        Args:
            check_interval: How often to check for tasks (seconds).
        """
        self.check_interval = check_interval
        self.tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._task_lock = asyncio.Lock()
        
    def add_task(
        self,
        task_id: str,
        name: str,
        schedule: str,
        handler: Callable[..., Any],
        **kwargs: Any,
    ) -> ScheduledTask:
        """Add a new scheduled task.
        
        Args:
            task_id: Unique identifier for the task.
            name: Human-readable name.
            schedule: Cron expression (e.g., "0 * * * *" for hourly).
            handler: Async function to call.
            **kwargs: Additional arguments passed to handler.
            
        Returns:
            The created ScheduledTask.
        """
        task = ScheduledTask(
            id=task_id,
            name=name,
            schedule=schedule,
            handler=handler,
            kwargs=kwargs,
        )
        
        # Validate cron expression
        if not croniter.is_valid(schedule):
            raise ValueError(f"Invalid cron expression: {schedule}")
            
        task.next_run = task.get_next_run_time()
        self.tasks[task_id] = task
        
        logger.info(f"Added task '{name}' (ID: {task_id}) with schedule: {schedule}")
        if task.next_run:
            logger.info(f"  Next run: {task.next_run}")
            
        return task
    
    def remove_task(self, task_id: str) -> bool:
        """Remove a scheduled task.
        
        Args:
            task_id: ID of task to remove.
            
        Returns:
            True if task was removed, False if not found.
        """
        if task_id in self.tasks:
            task = self.tasks.pop(task_id)
            logger.info(f"Removed task '{task.name}' (ID: {task_id})")
            return True
        return False
    
    def enable_task(self, task_id: str) -> bool:
        """Enable a task.
        
        Args:
            task_id: ID of task to enable.
            
        Returns:
            True if enabled, False if not found.
        """
        if task_id in self.tasks:
            self.tasks[task_id].enabled = True
            self.tasks[task_id].next_run = self.tasks[task_id].get_next_run_time()
            return True
        return False
    
    def disable_task(self, task_id: str) -> bool:
        """Disable a task.
        
        Args:
            task_id: ID of task to disable.
            
        Returns:
            True if disabled, False if not found.
        """
        if task_id in self.tasks:
            self.tasks[task_id].enabled = False
            self.tasks[task_id].next_run = None
            return True
        return False
    
    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a task by ID.
        
        Args:
            task_id: ID of task to retrieve.
            
        Returns:
            ScheduledTask or None if not found.
        """
        return self.tasks.get(task_id)
    
    def list_tasks(self) -> list[ScheduledTask]:
        """Get list of all tasks.
        
        Returns:
            List of all scheduled tasks.
        """
        return list(self.tasks.values())
    
    def get_status(self) -> dict[str, Any]:
        """Get scheduler status.
        
        Returns:
            Dictionary with scheduler status.
        """
        return {
            "running": self._running,
            "task_count": len(self.tasks),
            "enabled_count": sum(1 for t in self.tasks.values() if t.enabled),
            "tasks": [
                {
                    "id": t.id,
                    "name": t.name,
                    "schedule": t.schedule,
                    "enabled": t.enabled,
                    "last_run": t.last_run.isoformat() if t.last_run else None,
                    "next_run": t.next_run.isoformat() if t.next_run else None,
                    "run_count": t.run_count,
                    "error_count": t.error_count,
                }
                for t in self.tasks.values()
            ],
        }
    
    async def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return
            
        self._running = True
        logger.info("Task scheduler started")
        
        while self._running:
            await self._check_and_run_tasks()
            await asyncio.sleep(self.check_interval)
    
    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        logger.info("Task scheduler stopped")
    
    async def _check_and_run_tasks(self) -> None:
        """Check for tasks that need to run and execute them."""
        now = datetime.now()
        
        async with self._task_lock:
            for task in self.tasks.values():
                if not task.enabled:
                    continue
                    
                if task.next_run and now >= task.next_run:
                    await self._run_task(task)
    
    async def _run_task(self, task: ScheduledTask) -> None:
        """Run a single task.
        
        Args:
            task: The task to run.
        """
        logger.info(f"Running task '{task.name}' (ID: {task.id})")
        
        try:
            result = task.handler(**task.kwargs)
            
            # Handle both sync and async handlers
            if asyncio.iscoroutine(result):
                await result
                
            task.last_run = datetime.now()
            task.run_count += 1
            task.next_run = task.get_next_run_time(task.last_run)
            
            logger.info(f"Task '{task.name}' completed. Next run: {task.next_run}")
            
        except Exception as e:
            task.error_count += 1
            logger.error(f"Task '{task.name}' failed: {e}")


def parse_cron表达式(expression: str) -> dict[str, Any]:
    """Parse a cron expression into human-readable format.
    
    Args:
        expression: Cron expression (e.g., "0 * * * *")
        
    Returns:
        Dictionary with parsed components.
    """
    parts = expression.split()
    
    if len(parts) != 5:
        return {"error": "Invalid cron expression (need 5 parts)"}
    
    minute, hour, day, month, dow = parts
    
    # Simple interpretations
    descriptions = []
    
    if minute == "0" and hour == "*":
        descriptions.append("every hour")
    elif minute == "*" and hour == "*":
        descriptions.append("every minute")
    elif minute.startswith("*/"):
        interval = minute[2:]
        descriptions.append(f"every {interval} minutes")
    elif hour.startswith("*/"):
        interval = hour[2:]
        descriptions.append(f"every {interval} hours")
    elif day == "*" and month == "*" and dow == "*":
        descriptions.append(f"daily at {hour.zfill(2)}:{minute.zfill(2)}")
    
    return {
        "expression": expression,
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "dow": dow,
        "description": " ".join(descriptions) if descriptions else expression,
    }


# Common cron expressions
CRON_EXAMPLES = {
    "every_minute": "* * * * *",
    "every_hour": "0 * * * *",
    "every_day_midnight": "0 0 * * *",
    "every_day_noon": "0 12 * * *",
    "every_week_monday": "0 0 * * 1",
    "every_month_first": "0 0 1 * *",
}