from sqlalchemy import Column, Integer, String, Text, Boolean
from .base import Base


class CopilotSchemaWhitelist(Base):
    __tablename__ = "copilot_schema_whitelist"

    id = Column(Integer, primary_key=True, index=True)
    table_name = Column(String(100), nullable=False)
    column_name = Column(String(100), nullable=True)  # NULL = all columns in table
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        col = f".{self.column_name}" if self.column_name else ""
        return f"<CopilotSchemaWhitelist({self.table_name}{col})>"
