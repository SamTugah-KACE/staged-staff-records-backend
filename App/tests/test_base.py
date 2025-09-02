import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from ..Crud.base import CRUDBase
from unittest.mock import MagicMock

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)

@pytest.fixture
def crud_base(mock_model):
    return CRUDBase(model=mock_model)

def test_resolve_reference_success(mock_db, crud_base, mock_model):
    mock_db.query.return_value.filter.return_value.first.return_value = mock_model
    reference = {"id": 1}
    result = crud_base.resolve_reference(mock_db, reference)
    assert result == mock_model

def test_resolve_reference_not_found(mock_db, crud_base):
    mock_db.query.return_value.filter.return_value.first.return_value = None
    reference = {"id": 999}
    with pytest.raises(HTTPException) as exc:
        crud_base.resolve_reference(mock_db, reference)
    assert exc.value.status_code == 404
