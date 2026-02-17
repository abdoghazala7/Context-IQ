from .BaseDataModel import BaseDataModel
from .db_schemes import Project
from .enums.DataBaseEnum import DataBaseEnum
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
import logging

logger = logging.getLogger('uvicorn.error')


class ProjectModel(BaseDataModel):

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client)
        return instance

    async def create_project(self, project: Project):
        async with self.db_client() as session:
            async with session.begin():
                session.add(project)
            await session.commit()
            await session.refresh(project)

        return project

    async def get_project_or_create_one(self, project_id: int, user_id: int):
        """Get a project by project_id for a specific user, or create one if it doesn't exist."""
        async with self.db_client() as session:
            async with session.begin():
                query = select(Project).where(
                    Project.project_id == project_id,
                    Project.user_id == user_id
                )
                result = await session.execute(query)
                project = result.scalar_one_or_none()
                if project is not None:
                    return project

        # Project not found for this user — create one.
        # The (project_id, user_id) unique constraint allows different users
        # to have the same project_id.
        project_rec = Project(
            project_id=project_id,
            user_id=user_id
        )
        try:
            return await self.create_project(project=project_rec)
        except IntegrityError:
            # Race condition: another concurrent request created it first
            logger.info(f"Project {project_id} for user {user_id} was created concurrently, fetching it.")
            async with self.db_client() as session:
                async with session.begin():
                    query = select(Project).where(
                        Project.project_id == project_id,
                        Project.user_id == user_id
                    )
                    result = await session.execute(query)
                    return result.scalar_one()

    async def get_user_project(self, project_id: int, user_id: int):
        """Get a project only if it belongs to the given user. Returns None if not found."""
        async with self.db_client() as session:
            async with session.begin():
                query = select(Project).where(
                    Project.project_id == project_id,
                    Project.user_id == user_id
                )
                result = await session.execute(query)
                project = result.scalar_one_or_none()
                return project

    async def get_all_projects(self, user_id: int, page: int = 1, page_size: int = 10):
        """Get all projects belonging to a specific user with pagination."""
        async with self.db_client() as session:
            async with session.begin():

                total_documents = await session.execute(select(
                    func.count(Project.id)
                ).where(Project.user_id == user_id))

                total_documents = total_documents.scalar_one()

                total_pages = total_documents // page_size
                if total_documents % page_size > 0:
                    total_pages += 1

                query = select(Project).where(
                    Project.user_id == user_id
                ).offset((page - 1) * page_size).limit(page_size)
                result = await session.execute(query)
                projects = result.scalars().all()

                return projects, total_pages

    async def get_project_by_id(self, project_id: int):
        """
        Get a project by its internal ID (surrogate key).
        Used internally by background tasks where authentication 
        was already performed at the API layer.
        """
        async with self.db_client() as session:
            async with session.begin():
                query = select(Project).where(Project.id == project_id)
                result = await session.execute(query)
                project = result.scalar_one_or_none()
                return project