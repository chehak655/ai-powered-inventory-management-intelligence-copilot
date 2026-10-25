import os
import uuid
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, status
from app.core.config import settings


class StorageService:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or settings.STORAGE_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_company_dir(self, company_id: str, subfolder: str = "datasets") -> Path:
        """Get and ensure company-specific subfolder."""
        # Sanitize company_id to prevent any path tricks
        safe_cid = "".join(c for c in company_id if c.isalnum() or c in "-_")
        safe_sub = "".join(c for c in subfolder if c.isalnum() or c in "-_")
        target_dir = self.base_dir / "companies" / safe_cid / safe_sub
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def save_file(
        self,
        company_id: str,
        content: bytes,
        extension: str,
        subfolder: str = "datasets",
    ) -> str:
        """
        Save file content under server-controlled UUID name within company directory.
        Returns the relative storage identifier (e.g., 'companies/{company_id}/datasets/{uuid}.csv').
        """
        clean_ext = extension.lower().strip()
        if not clean_ext.startswith("."):
            clean_ext = f".{clean_ext}"

        file_uuid = str(uuid.uuid4())
        filename = f"{file_uuid}{clean_ext}"
        company_dir = self._get_company_dir(company_id, subfolder)
        file_path = company_dir / filename

        temp_path = file_path.with_suffix(f"{clean_ext}.tmp")
        try:
            with open(temp_path, "wb") as f:
                f.write(content)
            temp_path.replace(file_path)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to persist uploaded file securely: {str(e)}",
            )

        # Storage identifier is relative to base storage dir
        storage_identifier = str(file_path.relative_to(self.base_dir)).replace("\\", "/")
        return storage_identifier

    def get_file_path(self, company_id: str, storage_identifier: str) -> Path:
        """
        Safely resolve storage path and verify it belongs to the specified company.
        Raises 403 / 404 on invalid paths or traversal attempts.
        """
        # Clean path separator
        clean_id = storage_identifier.replace("\\", "/").strip("/")
        
        # Guard against traversal
        if ".." in clean_id or clean_id.startswith("/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid storage identifier: path traversal detected.",
            )

        resolved_path = (self.base_dir / clean_id).resolve()

        # Company directory must be a prefix
        safe_cid = "".join(c for c in company_id if c.isalnum() or c in "-_")
        expected_company_root = (self.base_dir / "companies" / safe_cid).resolve()

        try:
            resolved_path.relative_to(expected_company_root)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: File does not belong to your company workspace.",
            )

        if not resolved_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The requested file was not found in storage.",
            )

        return resolved_path

    def read_file(self, company_id: str, storage_identifier: str) -> bytes:
        """Read content of stored file securely."""
        path = self.get_file_path(company_id, storage_identifier)
        return path.read_bytes()

    def load_file(self, company_id: str, storage_identifier: str) -> bytes:
        """Alias for read_file."""
        return self.read_file(company_id, storage_identifier)

    def delete_file(self, company_id: str, storage_identifier: str) -> bool:
        """Delete stored file safely."""
        try:
            path = self.get_file_path(company_id, storage_identifier)
            if path.exists():
                path.unlink()
            return True
        except HTTPException:
            return False


storage_service = StorageService()
