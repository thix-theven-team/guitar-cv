from guitarcv_restapi.database.connection import Database


CREATE_CONVERSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS conversions (
    conversion_id TEXT PRIMARY KEY NOT NULL,

    status TEXT NOT NULL CHECK (
        status IN ('processing', 'ready', 'failed')
    ),

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    input_path TEXT,
    result_path TEXT,
    model_metadata_path TEXT,

    error_code TEXT,
    error_message TEXT,

    started_at TEXT,
    finished_at TEXT,

    input_expires_at TEXT,
    result_expires_at TEXT,
    model_metadata_expires_at TEXT,

    expires_at TEXT
);
"""


CREATE_INDEXES = (
    """
    CREATE INDEX IF NOT EXISTS idx_conversions_status
    ON conversions(status);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_conversions_finished_at
    ON conversions(finished_at);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_conversions_expires_at
    ON conversions(expires_at);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_conversions_input_expires_at
    ON conversions(input_expires_at);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_conversions_result_expires_at
    ON conversions(result_expires_at);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_conversions_metadata_expires_at
    ON conversions(model_metadata_expires_at);
    """,
)


def initialize_database(database: Database) -> None:
    with database.connection() as connection:
        connection.execute(CREATE_CONVERSIONS_TABLE)

        for query in CREATE_INDEXES:
            connection.execute(query)
