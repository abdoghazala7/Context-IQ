from .BaseDataModel import BaseDataModel
from .db_schemes import User
from sqlalchemy.future import select
import logging

logger = logging.getLogger('uvicorn.error')


class UserModel(BaseDataModel):

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client)
        return instance

    async def get_user_by_api_key(self, api_key: str):
        """Look up an active user by their unique API key."""
        async with self.db_client() as session:
            async with session.begin():
                query = select(User).where(
                    User.user_api_key == api_key,
                    User.is_active == True
                )
                result = await session.execute(query)
                user = result.scalar_one_or_none()
                return user

    async def create_user(self, user_name: str = None):
        """Register a new user and generate a unique API key for them."""
        async with self.db_client() as session:
            async with session.begin():
                user = User(user_name=user_name)
                session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def get_user_by_id(self, user_id: int):
        """Get a user by their integer ID."""
        async with self.db_client() as session:
            async with session.begin():
                query = select(User).where(User.user_id == user_id)
                result = await session.execute(query)
                user = result.scalar_one_or_none()
                return user
