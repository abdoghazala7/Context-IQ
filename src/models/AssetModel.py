from .BaseDataModel import BaseDataModel
from .db_schemes import Asset
from sqlalchemy.future import select
from sqlalchemy import func  
from models.enums.AssetTypeEnum import AssetTypeEnum  

class AssetModel(BaseDataModel):

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: object):
        instance = cls(db_client)
        return instance

    async def create_asset(self, asset: Asset):

        async with self.db_client() as session:
            async with session.begin():
                session.add(asset)
            await session.commit()
            await session.refresh(asset)
        return asset

    async def get_all_project_assets(self, asset_project_id: str, asset_type: str):

        async with self.db_client() as session:
            stmt = select(Asset).where(
                Asset.asset_project_id == asset_project_id,
                Asset.asset_type == asset_type
            )
            result = await session.execute(stmt)
            records = result.scalars().all()
        return records

    async def get_asset_record(self, asset_project_id: str, asset_name: str):

        async with self.db_client() as session:
            stmt = select(Asset).where(
                Asset.asset_project_id == asset_project_id,
                Asset.asset_name == asset_name
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
        return record
    
    # For Idempotency checks
    async def get_project_files_count(self, project_id: int) -> int:
        """
        Get the total count of assets of type 'FILE' in a specific project.
        Used for generating state version for idempotency checks.
        """
        async with self.db_client() as session:
            stmt = select(func.count()).select_from(Asset).where(
                Asset.asset_project_id == project_id,
                Asset.asset_type == AssetTypeEnum.FILE.value
            )
            
            result = await session.execute(stmt)
            
            count = result.scalar()
            return count if count is not None else 0
