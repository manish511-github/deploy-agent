import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, List
import uuid

import psycopg2
import psycopg2.extras
from src.core.config import get_settings
from src.core.exceptions import DatabaseError

@dataclass
class AgentTask:
    task_id: str
    device_id: str
    task_type: str
    payload: Dict[str, Any]
    status: str

class AgentService:
    """Service for handling agent communication and task queue logic."""

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url or get_settings().database_url

    def _connect(self) -> psycopg2.extensions.connection:
        try:
            return psycopg2.connect(self._database_url)
        except psycopg2.OperationalError as exc:
            raise DatabaseError(f"Database connection failed: {exc}") from exc

    def create_task(self, device_id: str, task_type: str, payload: Dict[str, Any], created_by: str = 'system') -> AgentTask:
        """Queue a new task for an agent."""
        sql = """
            INSERT INTO task_queue (device_id, task_type, payload, created_by)
            VALUES (%s, %s, %s, %s)
            RETURNING task_id, device_id, task_type, payload, status
        """
        try:
            conn = self._connect()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, (device_id, task_type, json.dumps(payload), created_by))
            row = cur.fetchone()
            conn.commit()
            cur.close()
            conn.close()
            return AgentTask(**row) if row else None
        except psycopg2.Error as exc:
            raise DatabaseError(f"Failed to create task: {exc}") from exc

    def get_next_pending_task(self, device_id: str) -> Optional[AgentTask]:
        """Fetch the oldest pending task for a specific device."""
        sql = """
            SELECT task_id, device_id, task_type, payload, status
            FROM task_queue
            WHERE device_id = %s AND status = 'pending'
            ORDER BY created_at ASC
            LIMIT 1
        """
        try:
            conn = self._connect()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, (device_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            return AgentTask(**row) if row else None
        except psycopg2.Error as exc:
            raise DatabaseError(f"Failed to fetch next task: {exc}") from exc

    def mark_task_sent(self, task_id: str) -> None:
        """Mark a task as sent to the agent."""
        sql = """
            UPDATE task_queue 
            SET status = 'sent', sent_at = NOW() 
            WHERE task_id = %s
        """
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(sql, (task_id,))
            conn.commit()
            cur.close()
            conn.close()
        except psycopg2.Error as exc:
            raise DatabaseError(f"Failed to mark task sent: {exc}") from exc

    def complete_task(self, task_id: str, status: str, result: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> None:
        """Mark a task as completed (success or failed) and move it to history."""
        update_queue_sql = """
            UPDATE task_queue 
            SET status = %s, result = %s, error = %s, completed_at = NOW() 
            WHERE task_id = %s
            RETURNING task_id, device_id, task_type, status, result, error, created_at, completed_at
        """
        insert_history_sql = """
            INSERT INTO task_history (task_id, device_id, task_type, status, result, error, created_at, completed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        delete_queue_sql = """
            DELETE FROM task_queue WHERE task_id = %s
        """
        try:
            conn = self._connect()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            # Update the queue record to get the full data
            cur.execute(update_queue_sql, (status, json.dumps(result) if result else None, error, task_id))
            row = cur.fetchone()
            
            if row:
                # Insert into history
                cur.execute(insert_history_sql, (
                    row['task_id'], row['device_id'], row['task_type'], 
                    row['status'], psycopg2.extras.Json(row['result']) if row['result'] is not None else None, row['error'], 
                    row['created_at'], row['completed_at']
                ))
                # Delete from queue
                cur.execute(delete_queue_sql, (task_id,))
                
            conn.commit()
            cur.close()
            conn.close()
        except psycopg2.Error as exc:
            raise DatabaseError(f"Failed to complete task: {exc}") from exc

    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Fetch the result of a completed task from task_history."""
        sql = """
            SELECT status, result, error 
            FROM task_history 
            WHERE task_id = %s
        """
        try:
            conn = self._connect()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, (task_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            
            if not row:
                return None
                
            return {
                "status": row['status'],
                "result": row['result'],
                "error": row['error']
            }
        except psycopg2.Error as exc:
            raise DatabaseError(f"Failed to get task result: {exc}") from exc
