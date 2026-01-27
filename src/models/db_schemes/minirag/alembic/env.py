from logging.config import fileConfig

from sqlalchemy import engine_from_config
from schemes import SQLAlchemyBase
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = SQLAlchemyBase.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def include_object(object, name, type_, reflected, compare_to):
    """
    Function to exclude dynamic vector database tables from Alembic migrations.
    
    This function tells Alembic to ignore tables that are created dynamically
    for vector storage collections. These tables follow the pattern:
    collection_{vector_size}_{project_id}
    
    Note: This only applies when using PGVector as the vector database.
    When using QDrant, no dynamic tables are created in PostgreSQL.
    
    Examples of excluded objects (PGVector only):
    - Tables: collection_1536_1, collection_384_5, collection_768_100
    - Indexes: collection_1536_1_vector_idx, collection_384_5_vector_idx
    
    Examples of included objects:
    - Tables: projects, assets, chunks, collection_invalid
    - Indexes: ix_asset_project_id, ix_chunk_asset_id
    
    Args:
        object: The schema object being considered
        name: Name of the object
        type_: Type of the object (table, index, etc.)
        reflected: Whether the object was reflected from database
        compare_to: The object being compared against
    
    Returns:
        True if object should be included in migrations, False otherwise
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if type_ == 'table':
        # Ignore dynamic vector collections tables (PGVector only)
        # Pattern: collection_{vector_size}_{project_id}
        if name.startswith('collection_') and '_' in name[11:]:
            # Check if it matches the pattern: collection_{digits}_{digits}
            parts = name.split('_')
            if len(parts) >= 3 and parts[0] == 'collection':
                try:
                    # Try to parse vector_size and project_id as integers
                    vector_size = int(parts[1])  # vector_size
                    project_id = int(parts[2])   # project_id
                    logger.debug(f"Excluding PGVector dynamic table: {name} (vector_size={vector_size}, project_id={project_id})")
                    return False  # Exclude from migrations
                except ValueError:
                    pass  # Not a vector collection table, include it
    
    elif type_ == 'index':
        # Ignore indexes on dynamic vector collections tables (PGVector only)
        # Pattern: collection_{digits}_{digits}_vector_idx
        if 'collection_' in name and '_vector_idx' in name:
            # Extract table name from index name
            table_name = name.replace('_vector_idx', '')
            if table_name.startswith('collection_'):
                parts = table_name.split('_')
                if len(parts) >= 3 and parts[0] == 'collection':
                    try:
                        vector_size = int(parts[1])  # vector_size
                        project_id = int(parts[2])   # project_id
                        logger.debug(f"Excluding PGVector dynamic index: {name} for table {table_name} (vector_size={vector_size}, project_id={project_id})")
                        return False  # Exclude from migrations
                    except ValueError:
                        pass
    
    return True  # Include all other objects


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            include_object=include_object
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
