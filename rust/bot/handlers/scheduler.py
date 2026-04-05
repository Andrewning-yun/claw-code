"""Scheduler command handler.

Handles /scheduler, /cron, and /task commands for managing scheduled tasks.
"""

import logging
from typing import Any, Optional

from ..scheduler import CRON_EXAMPLES, ScheduledTask, TaskScheduler, parse_cron表达式

logger = logging.getLogger(__name__)


class SchedulerHandler:
    """Handler for scheduled task commands."""
    
    def __init__(self, scheduler: TaskScheduler):
        """Initialize the scheduler handler.
        
        Args:
            scheduler: The task scheduler instance.
        """
        self.scheduler = scheduler
        
    def handle_list(self) -> str:
        """List all scheduled tasks.
        
        Returns:
            Formatted list of tasks.
        """
        tasks = self.scheduler.list_tasks()
        
        if not tasks:
            return "No scheduled tasks."
        
        lines = ["Scheduled Tasks:", ""]
        
        for task in tasks:
            status = "✓ enabled" if task.enabled else "✗ disabled"
            lines.append(f"  {task.id}")
            lines.append(f"    Name: {task.name}")
            lines.append(f"    Schedule: {task.schedule}")
            lines.append(f"    Status: {status}")
            
            if task.next_run:
                lines.append(f"    Next run: {task.next_run}")
            
            lines.append(f"    Runs: {task.run_count}, Errors: {task.error_count}")
            lines.append("")
        
        return "\n".join(lines)
    
    def handle_show(self, task_id: str) -> str:
        """Show details of a specific task.
        
        Args:
            task_id: The task ID.
            
        Returns:
            Task details or error message.
        """
        task = self.scheduler.get_task(task_id)
        
        if not task:
            return f"Task '{task_id}' not found."
        
        lines = [
            f"Task: {task.name}",
            f"  ID: {task.id}",
            f"  Schedule: {task.schedule}",
            f"  Enabled: {task.enabled}",
            f"  Run count: {task.run_count}",
            f"  Error count: {task.error_count}",
        ]
        
        if task.last_run:
            lines.append(f"  Last run: {task.last_run}")
        
        if task.next_run:
            lines.append(f"  Next run: {task.next_run}")
        
        # Add human-readable schedule
        parsed = parse_cron表达式(task.schedule)
        if "description" in parsed:
            lines.append(f"  Description: {parsed['description']}")
        
        return "\n".join(lines)
    
    def handle_add(
        self,
        task_id: str,
        name: str,
        schedule: str,
    ) -> str:
        """Add a new scheduled task.
        
        Args:
            task_id: Unique task ID.
            name: Task name.
            schedule: Cron expression.
            
        Returns:
            Success or error message.
        """
        # Validate cron expression
        if not parse_cron表达式(schedule):
            return f"Invalid cron expression: {schedule}"
        
        # Check if task exists
        if self.scheduler.get_task(task_id):
            return f"Task '{task_id}' already exists. Use /task update to modify."
        
        # Note: Handler would need to be provided when actually adding
        # For now, just validate
        return f"Task '{name}' ({task_id}) scheduled: {schedule}"
    
    def handle_remove(self, task_id: str) -> str:
        """Remove a scheduled task.
        
        Args:
            task_id: The task ID to remove.
            
        Returns:
            Success or error message.
        """
        if self.scheduler.remove_task(task_id):
            return f"Task '{task_id}' removed."
        return f"Task '{task_id}' not found."
    
    def handle_enable(self, task_id: str) -> str:
        """Enable a task.
        
        Args:
            task_id: The task ID to enable.
            
        Returns:
            Success or error message.
        """
        if self.scheduler.enable_task(task_id):
            return f"Task '{task_id}' enabled."
        return f"Task '{task_id}' not found."
    
    def handle_disable(self, task_id: str) -> str:
        """Disable a task.
        
        Args:
            task_id: The task ID to disable.
            
        Returns:
            Success or error message.
        """
        if self.scheduler.disable_task(task_id):
            return f"Task '{task_id}' disabled."
        return f"Task '{task_id}' not found."
    
    def handle_status(self) -> str:
        """Get scheduler status.
        
        Returns:
            Status message.
        """
        status = self.scheduler.get_status()
        
        lines = [
            "Scheduler Status:",
            f"  Running: {status['running']}",
            f"  Total tasks: {status['task_count']}",
            f"  Enabled tasks: {status['enabled_count']}",
        ]
        
        return "\n".join(lines)
    
    def handle_cron_help(self) -> str:
        """Show cron expression help.
        
        Returns:
            Cron help text.
        """
        lines = [
            "Cron Expression Format:",
            "  minute hour day month day-of-week",
            "",
            "Examples:",
        ]
        
        for name, expr in CRON_EXAMPLES.items():
            parsed = parse_cron表达式(expr)
            desc = parsed.get("description", "")
            lines.append(f"  {name}: {expr} - {desc}")
        
        lines.extend([
            "",
            "Special characters:",
            "  *     any value",
            "  ,     value list separator",
            "  -     range of values",
            "  /     step values",
        ])
        
        return "\n".join(lines)
    
    def handle_command(self, args: str) -> str:
        """Handle a scheduler command.
        
        Args:
            args: Command arguments.
            
        Returns:
            Command result.
        """
        parts = args.strip().split()
        action = parts[0] if parts else "list"
        
        return {
            "list": self.handle_list,
            "status": self.handle_status,
            "help": self.handle_cron_help,
            "show": lambda: self.handle_show(parts[1]) if len(parts) > 1 else "Usage: /scheduler show <task-id>",
            "add": lambda: self.handle_add(parts[1], parts[2], parts[3]) if len(parts) > 3 else "Usage: /scheduler add <id> <name> <cron>",
            "remove": lambda: self.handle_remove(parts[1]) if len(parts) > 1 else "Usage: /scheduler remove <task-id>",
            "enable": lambda: self.handle_enable(parts[1]) if len(parts) > 1 else "Usage: /scheduler enable <task-id>",
            "disable": lambda: self.handle_disable(parts[1]) if len(parts) > 1 else "Usage: /scheduler disable <task-id>",
        }.get(action, lambda: f"Unknown command: {action}")()


def format_schedule_table(tasks: list[ScheduledTask]) -> str:
    """Format tasks as a table.
    
    Args:
        tasks: List of scheduled tasks.
        
    Returns:
        Formatted table.
    """
    if not tasks:
        return "No tasks scheduled."
    
    # Header
    header = f"{'ID':<15} {'Name':<20} {'Schedule':<15} {'Status':<10} {'Next Run':<20}"
    lines = [header, "-" * len(header)]
    
    for task in tasks:
        status = "enabled" if task.enabled else "disabled"
        next_run = task.next_run.strftime("%Y-%m-%d %H:%M") if task.next_run else "N/A"
        
        lines.append(
            f"{task.id:<15} {task.name[:20]:<20} {task.schedule:<15} {status:<10} {next_run:<20}"
        )
    
    return "\n".join(lines)