import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..Crud.async_base import CRUDBase
from unittest.mock import AsyncMock

@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)

@pytest.fixture
def crud_async_base(mock_model):
    return CRUDBase(model=mock_model)

@pytest.mark.asyncio
async def test_resolve_reference_success(mock_db, crud_async_base, mock_model):
    mock_db.query.return_value.filter.return_value.first.return_value = mock_model
    reference = {"id": 1}
    result = await crud_async_base.resolve_reference(mock_db, reference)
    assert result == mock_model

@pytest.mark.asyncio
async def test_resolve_reference_not_found(mock_db, crud_async_base):
    mock_db.query.return_value.filter.return_value.first.return_value = None
    reference = {"id": 999}
    with pytest.raises(HTTPException) as exc:
        await crud_async_base.resolve_reference(mock_db, reference)
    assert exc.value.status_code == 404
