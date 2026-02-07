import hashlib
import json
from sqlalchemy import func, text
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, delete
from models.db_schemes.minirag.schemes.celery_task_execution import CeleryTaskExecution

class IdempotencyManager:

    def __init__(self, db_client, db_engine):
        self.db_client = db_client
        self.db_engine = db_engine

    def create_args_hash(self, task_name: str, task_args: dict):
        combined_data = {
            **task_args,
            "task_name": task_name
        }
        json_string = json.dumps(combined_data, sort_keys=True, default=str)
        return hashlib.sha256(json_string.encode()).hexdigest()
    
    async def create_task_record(self, task_name: str, task_args: dict, celery_task_id: str = None) -> CeleryTaskExecution:
        """Create new task execution record."""
        args_hash = self.create_args_hash(task_name, task_args)
        
        task_record = CeleryTaskExecution(
            task_name=task_name,
            task_args_hash=args_hash,
            task_args=task_args,
            celery_task_id=celery_task_id,
            status='PENDING',
            started_at=datetime.now(timezone.utc)
        )
        
        session = self.db_client()
        try:
            session.add(task_record)
            await session.commit()
            await session.refresh(task_record)
            return task_record
        except IntegrityError:
            await session.rollback()
            # Task was already created by another worker
            existing_record = await self.get_existing_task(
                            task_name=task_name, 
                            task_args=task_args
                        )
            if existing_record:
                return existing_record
            else:
                raise Exception("Race condition occurred but record not found!")
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def update_task_status(self, execution_id: int, status: str, result: dict = None):
        """Update task status and result."""
        session = self.db_client()
        try:
            task_record = await session.get(CeleryTaskExecution, execution_id)
            if task_record:
                task_record.status = status
                if result:
                    task_record.result = result
                    
                if status == 'STARTED':
                    task_record.started_at = datetime.now(timezone.utc)
                if status in ['SUCCESS', 'FAILURE']:
                    task_record.completed_at = datetime.now(timezone.utc)
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def get_existing_task(self, task_name: str, 
                                task_args: dict) -> CeleryTaskExecution:
        """Check if task with same name and args already exists."""
        args_hash = self.create_args_hash(task_name, task_args)
        
        session = self.db_client()
        try:
            stmt = select(CeleryTaskExecution).where(
                CeleryTaskExecution.task_name == task_name,
                CeleryTaskExecution.task_args_hash == args_hash
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        finally:
            await session.close()

    async def should_execute_task(self, task_name: str, task_args: dict,
                                  task_time_limit: int = 600) -> tuple[bool, CeleryTaskExecution]:
        """
        Check if task should be executed or return existing result.
        Args:
            task_time_limit: Time limit in seconds after which a stuck task can be re-executed
        Returns (should_execute, existing_task_or_none)
        """
        existing_task = await self.get_existing_task(task_name, task_args)
        
        if not existing_task:
            return True, None
            
        # Don't execute if task is already completed successfully
        if existing_task.status == 'SUCCESS':
            return False, existing_task
            
        # Check if task is stuck (running longer than time limit + 60 seconds)
        if existing_task.status in ['PENDING', 'STARTED', 'RETRY']:
            if existing_task.started_at:
                time_elapsed = (datetime.now(timezone.utc) - existing_task.started_at).total_seconds()
                time_gap = 60  # 60 seconds grace period
                if time_elapsed > (task_time_limit + time_gap):
                    return True, existing_task  # Task is stuck, allow re-execution
            return False, existing_task  # Task is still running within time limit
            
        # Re-execute if previous task failed
        return True, existing_task
    
    async def cleanup_old_tasks(self, time_retention: int = 86400) -> int:
        
        session = self.db_client()
        try:
            stmt = delete(CeleryTaskExecution).where(
                CeleryTaskExecution.created_at < func.now() - text(f"INTERVAL '{time_retention} seconds'"),
                CeleryTaskExecution.status.in_(['SUCCESS', 'FAILURE'])
            )
            
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()